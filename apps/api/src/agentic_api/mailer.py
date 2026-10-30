"""Emails notifications to the users they are for.

Every API instance runs a pass in the background every INTERVAL_SECONDS. A pass derives the
notifications of each user who has email notifications on, as the in-app list does
(agentic_api.notifications), and emails those of EMAILED_KINDS not emailed yet, in the user's
language (agentic_api.emails). A notification older than WINDOW, or older than the user's
``emails_since`` (when their settings row was written, or when they last switched emails back
on), is never emailed: nobody gets a flood of old ones when emails ship or come back on.

Several instances may pass at the same time. A send is claimed first, in one statement that
inserts its ``notification_emails`` row or takes over a row whose earlier attempt failed or
lapsed (INSERT ... ON CONFLICT DO UPDATE ... WHERE), so each email goes out once. A failed send
gives its claim back for a later pass, after a wait that doubles each time, and is tried
MAX_ATTEMPTS times at most. The claim of an instance that died lapses after CLAIM_LEASE; that
email may then go out twice.
"""

import asyncio
import logging
import smtplib
import ssl
import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from typing import Protocol
from urllib.parse import unquote, urlsplit

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.auth import CurrentUser
from agentic_api.emails import EMAILED_KINDS, Email, notification_email
from agentic_api.notifications import derive_notifications
from agentic_api.schemas import NotificationOut
from agentic_api.settings import Settings
from agentic_api.users import active_users
from agentic_db.models import NotificationEmail, StageRun, UserSettings

log = logging.getLogger(__name__)
INTERVAL_SECONDS = 60.0
WINDOW = timedelta(days=2)
BATCH = 100  # emails per pass at most
MAX_ATTEMPTS = 8
RETRY_DELAY = timedelta(minutes=1)  # the wait after a first failed attempt; then it doubles
SMTP_TIMEOUT_SECONDS = 30.0
CLAIM_LEASE = timedelta(minutes=5)  # far longer than a send may take
# Their notifications carry no stage; the email names the one the run stopped at.
_STOPPED_KINDS = frozenset({"run_failed", "run_paused"})


class MailSender(Protocol):
    async def send(self, message: EmailMessage) -> None:
        """Hand ``message`` to the mail server; raises when it is not accepted."""
        ...


@dataclass(frozen=True)
class SmtpSender:
    """Sends through SMTP_URL as the web's nodemailer transport does: smtps:// over TLS,
    smtp:// upgraded with STARTTLS when the server offers it, and a login with the URL's
    credentials."""

    host: str
    port: int
    secure: bool
    username: str | None = None
    password: str = field(default="", repr=False)

    @classmethod
    def from_url(cls, url: str) -> "SmtpSender":
        parts = urlsplit(url)
        if parts.scheme not in {"smtp", "smtps"} or not parts.hostname:
            raise ValueError("SMTP_URL must look like smtp://host:port or smtps://host:port")
        secure = parts.scheme == "smtps"
        return cls(
            host=parts.hostname,
            port=parts.port or (465 if secure else 587),  # nodemailer's defaults
            secure=secure,
            username=unquote(parts.username) if parts.username else None,
            password=unquote(parts.password or ""),
        )

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._send, message)

    def _send(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        if self.secure:
            smtp = smtplib.SMTP_SSL(
                self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS, context=context
            )
        else:
            smtp = smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS)
        with smtp:
            if not self.secure:
                smtp.ehlo()
                if smtp.has_extn("starttls"):
                    smtp.starttls(context=context)
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)


@dataclass(frozen=True)
class _Recipient:
    user: CurrentUser
    locale: str
    emails_since: datetime


async def email_notifications(
    sessions: async_sessionmaker[AsyncSession],
    sender: MailSender,
    settings: Settings,
    *,
    user_ids: Collection[str] | None = None,
) -> list[tuple[str, str]]:
    """One pass: email what is due; returns the (user id, notification key) of each email sent.
    ``user_ids`` limits the pass to those users.

    A failed send ends the pass: the mail server is down or refuses us, so the rest wait for
    the next pass instead of failing one by one.
    """
    now = datetime.now(UTC)
    origin = settings.public_origin.split(",")[0].strip().rstrip("/")  # links open the app here
    async with sessions() as session:
        recipients = await _recipients(session, user_ids)
    sent: list[tuple[str, str]] = []
    for recipient in recipients:
        user_id = recipient.user.id
        async with sessions() as session:
            for item, stage in await _due(session, recipient, now):
                if len(sent) >= BATCH:
                    return sent
                email = notification_email(
                    item,
                    locale=recipient.locale,
                    name=recipient.user.name,
                    stage=stage,
                    origin=origin,
                )
                attempt = await _claim(session, user_id, item)
                if attempt is None:
                    continue  # another pass holds it, or it went out meanwhile
                try:
                    await sender.send(_message(email, recipient.user.email, settings.mail_from))
                except Exception as exc:
                    await _give_back(session, user_id, item.key, attempt)
                    log.warning(
                        "could not email notification %s to user %s (attempt %d of %d): %s",
                        item.key,
                        user_id,
                        attempt,
                        MAX_ATTEMPTS,
                        _reason(exc),
                    )
                    return sent
                await _record_sent(session, user_id, item.key)
                log.info("emailed notification %s to user %s", item.key, user_id)
                sent.append((user_id, item.key))
    return sent


async def email_forever(
    sessions: async_sessionmaker[AsyncSession],
    sender: MailSender,
    settings: Settings,
    *,
    interval_seconds: float = INTERVAL_SECONDS,
) -> None:
    """A pass every ``interval_seconds`` until cancelled (a background task of the API)."""
    while True:
        try:
            await email_notifications(sessions, sender, settings)
        except Exception:  # Postgres unreachable, say: try again at the next pass
            log.warning("could not email notifications", exc_info=True)
        await asyncio.sleep(interval_seconds)


async def _recipients(session: AsyncSession, user_ids: Collection[str] | None) -> list[_Recipient]:
    """The accounts that may sign in and have email notifications on. An account without a
    settings row gets one now, so its emails start with this pass."""
    users = [
        user for user in await active_users(session) if user_ids is None or user.id in user_ids
    ]
    if not users:
        return []
    new_rows = [{"user_id": user.id} for user in users]
    await session.execute(insert(UserSettings).values(new_rows).on_conflict_do_nothing())
    await session.commit()
    rows = await session.scalars(
        select(UserSettings).where(
            UserSettings.user_id.in_([user.id for user in users]),
            UserSettings.email_notifications.is_(True),
        )
    )
    opted_in = {row.user_id: row for row in rows}
    return [
        _Recipient(user, opted_in[user.id].locale, opted_in[user.id].emails_since)
        for user in users
        if user.id in opted_in
    ]


async def _due(
    session: AsyncSession, recipient: _Recipient, now: datetime
) -> list[tuple[NotificationOut, str | None]]:
    """The user's notifications to email now, oldest first, each with the stage to name."""
    since = max(recipient.emails_since, now - WINDOW)
    items = [
        item
        for item in await derive_notifications(session, recipient.user, now)
        if item.kind in EMAILED_KINDS and item.created_at >= since
    ]
    if not items:
        return []
    # Sent, given up on, or held: by another pass, or for the wait after a failed attempt.
    skipped = set(
        await session.scalars(
            select(NotificationEmail.notification_key).where(
                NotificationEmail.user_id == recipient.user.id,
                NotificationEmail.notification_key.in_([item.key for item in items]),
                or_(
                    NotificationEmail.sent_at.is_not(None),
                    NotificationEmail.attempts >= MAX_ATTEMPTS,
                    NotificationEmail.retry_at > func.now(),
                ),
            )
        )
    )
    due = sorted(
        (item for item in items if item.key not in skipped),
        key=lambda item: (item.created_at, item.key),
    )
    stopped = await _stopped_at(
        session, {item.run_id for item in due if item.kind in _STOPPED_KINDS and item.run_id}
    )
    return [
        (item, item.stage or (stopped.get(item.run_id) if item.run_id else None)) for item in due
    ]


async def _stopped_at(session: AsyncSession, run_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """The stage each run stopped at: the stage of its latest attempt."""
    if not run_ids:
        return {}
    rows = await session.execute(
        select(StageRun.run_id, StageRun.stage)
        .where(StageRun.run_id.in_(run_ids))
        .order_by(StageRun.run_id, StageRun.started_at.desc().nulls_last(), StageRun.attempt.desc())
        .ext(distinct_on(StageRun.run_id))
    )
    return {run_id: stage for run_id, stage in rows}


async def _claim(session: AsyncSession, user_id: str, item: NotificationOut) -> int | None:
    """Claim the email of ``item``; returns the attempt it begins, or None when another pass
    holds the claim, the email went out, or it failed MAX_ATTEMPTS times."""
    lease_end = func.now() + CLAIM_LEASE
    attempt = await session.scalar(
        insert(NotificationEmail)
        .values(user_id=user_id, notification_key=item.key, kind=item.kind, retry_at=lease_end)
        .on_conflict_do_update(
            index_elements=[NotificationEmail.user_id, NotificationEmail.notification_key],
            set_={
                "attempts": NotificationEmail.attempts + 1,
                "claimed_at": func.now(),
                "retry_at": lease_end,
            },
            where=and_(
                NotificationEmail.sent_at.is_(None),
                NotificationEmail.attempts < MAX_ATTEMPTS,
                NotificationEmail.retry_at <= func.now(),
            ),
        )
        .returning(NotificationEmail.attempts)
    )
    await session.commit()  # before sending: other passes must see the claim
    return attempt


async def _give_back(session: AsyncSession, user_id: str, key: str, attempt: int) -> None:
    """Release the claim of a failed attempt, for a pass after the wait."""
    await session.execute(
        update(NotificationEmail)
        .where(NotificationEmail.user_id == user_id, NotificationEmail.notification_key == key)
        .values(retry_at=func.now() + RETRY_DELAY * 2 ** (attempt - 1))
    )
    await session.commit()


async def _record_sent(session: AsyncSession, user_id: str, key: str) -> None:
    await session.execute(
        update(NotificationEmail)
        .where(NotificationEmail.user_id == user_id, NotificationEmail.notification_key == key)
        .values(sent_at=func.now())
    )
    await session.commit()


def _message(email: Email, to: str, mail_from: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = email.subject
    message["From"] = mail_from
    message["To"] = to
    message["Date"] = formatdate(usegmt=True)
    domain = parseaddr(mail_from)[1].rpartition("@")[2] or "localhost"
    message["Message-ID"] = make_msgid(domain=domain)  # a domain of its own: no DNS look-up
    message["Auto-Submitted"] = "auto-generated"  # no out-of-office replies (RFC 3834)
    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")
    # After the parts: setting the content drops the Content-* headers set before.
    message["Content-Language"] = email.language
    return message


def _reason(exc: Exception) -> str:
    """What went wrong, without the addresses some SMTP errors carry (SMTPRecipientsRefused)."""
    code = getattr(exc, "smtp_code", None)
    return f"{type(exc).__name__} {code}" if code else type(exc).__name__
