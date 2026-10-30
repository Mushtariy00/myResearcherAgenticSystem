import asyncio
import logging
import smtplib
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any, ClassVar

import httpx
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api import mailer
from agentic_api.emails import notification_email
from agentic_api.mailer import MAX_ATTEMPTS, SmtpSender, email_forever, email_notifications
from agentic_api.schemas import NotificationKind, NotificationOut
from agentic_api.settings import Settings
from agentic_core.enums import RunStatus, StageStatus
from agentic_db.models import NotificationEmail, Run, UserSettings
from api_testkit import (
    METHOD_OUTPUT,
    ORIGIN,
    add_output,
    add_stage_run,
    as_user,
    awaiting_output,
    set_run_status,
    start_run,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]
SETTINGS_URL = "/api/v1/me/settings"
# The clock of a WSL machine steps back by a second or two now and then, so these tests put the
# moments they compare (when emails start, when a notification came) this far apart.
MARGIN = timedelta(hours=1)


@dataclass
class FakeSender:
    """Keeps what the mailer sends. The next ``failures`` sends are refused the way a mail server
    refuses them (the address is in the error); each send takes ``delay`` seconds."""

    messages: list[EmailMessage] = field(default_factory=list)
    failures: int = 0
    delay: float = 0.0

    async def send(self, message: EmailMessage) -> None:
        await asyncio.sleep(self.delay)
        if self.failures:
            self.failures -= 1
            raise smtplib.SMTPRecipientsRefused({str(message["To"]): (550, b"no such mailbox")})
        self.messages.append(message)

    def to(self, address: str) -> list[EmailMessage]:
        return [message for message in self.messages if message["To"] == address]


def _parts(message: EmailMessage) -> tuple[str, str]:
    """The plain-text and HTML parts."""
    plain, page = message.get_body(("plain",)), message.get_body(("html",))
    assert plain is not None and page is not None
    return plain.get_content(), page.get_content()


async def _rows(db: Factory) -> dict[tuple[str, str], NotificationEmail]:
    async with db() as session:
        rows = await session.scalars(select(NotificationEmail))
        return {(row.user_id, row.notification_key): row for row in rows}


async def _emails_started(db: Factory, sender: FakeSender, settings: Settings) -> None:
    """The first pass writes every user's settings row, so emails start there; the start is
    then moved MARGIN back, before anything the test makes next."""
    assert await email_notifications(db, sender, settings) == []
    async with db() as session:
        await session.execute(update(UserSettings).values(emails_since=func.now() - MARGIN))
        await session.commit()


async def _approval(
    client: httpx.AsyncClient, db: Factory, project_id: str, ready_at: datetime | None = None
) -> tuple[str, str]:
    """A run of bob's waiting for a decision on its literature output, ready now or at
    ``ready_at``: (run id, the notification's key)."""
    run_id = await start_run(client, project_id)
    stage_run_id = await add_stage_run(db, run_id)
    fields: dict[str, Any] = {} if ready_at is None else {"created_at": ready_at}
    output_id, _ = await add_output(db, stage_run_id, {"summary": "two papers"}, **fields)
    await set_run_status(db, run_id, RunStatus.AWAITING_APPROVAL)
    return run_id, f"approval:{output_id}"


async def _finished_run(db: Factory, project_id: str, finished_at: datetime) -> str:
    async with db() as session:
        run = Run(
            project_id=uuid.UUID(project_id),
            owner_id="bob",
            topic="Finished run",
            status=RunStatus.COMPLETED,
        )
        session.add(run)
        await session.flush()
        await session.execute(update(Run).where(Run.id == run.id).values(updated_at=finished_at))
        await session.commit()
        return str(run.id)


async def test_notifications_are_emailed_once_to_whoever_they_are_for(
    client: httpx.AsyncClient, db: Factory, settings: Settings
) -> None:
    sender = FakeSender()
    await _emails_started(db, sender, settings)
    async with db() as session:  # a suspended account gets nothing
        await session.execute(text("UPDATE auth.\"user\" SET banned = true WHERE id = 'root'"))
        await session.commit()
    project_id = await team_project(client)
    run_id, key = await _approval(client, db, project_id)

    # The owner and the researcher whose run it is may decide; the viewer may not.
    assert sorted(await email_notifications(db, sender, settings)) == [("alice", key), ("bob", key)]
    [message] = sender.to("bob@lab.test")
    assert message["Subject"] == "Review needed: Literature for “Monocular depth”"
    assert (message["From"], message["Content-Language"]) == (settings.mail_from, "en")
    assert message["Auto-Submitted"] == "auto-generated"
    plain, page = _parts(message)
    assert plain == (
        "Hello Bob,\n\n"
        "The Literature stage of “Monocular depth” in the project Depth is ready for your "
        "review. The run waits until its output is approved, sent back for changes or "
        "rejected.\n\n"
        f"Open the run: {ORIGIN}/runs/{run_id}\n\n"
        "-- \n"
        "You get this email because email notifications are on for your account. You can "
        f"turn them off on your profile page: {ORIGIN}/profile\n"
    )
    assert '<html lang="en">' in page
    assert f'href="{ORIGIN}/runs/{run_id}"' in page and f'href="{ORIGIN}/profile"' in page

    assert await email_notifications(db, sender, settings) == []  # each email goes out once
    assert len(sender.messages) == 2
    rows = await _rows(db)
    assert sorted(rows) == [("alice", key), ("bob", key)]
    assert all(
        (row.kind, row.attempts, row.sent_at is not None) == ("approval_needed", 1, True)
        for row in rows.values()
    )


async def test_two_passes_at_once_send_each_email_once(
    client: httpx.AsyncClient, db: Factory, settings: Settings
) -> None:
    sender = FakeSender(delay=0.05)  # long enough for the passes to overlap
    await _emails_started(db, sender, settings)
    project_id = await team_project(client)
    keys = [(await _approval(client, db, project_id))[1] for _ in range(2)]

    first, second = await asyncio.gather(
        email_notifications(db, sender, settings), email_notifications(db, sender, settings)
    )
    expected = sorted((user, key) for user in ("alice", "bob", "root") for key in keys)
    assert first and second  # both passes sent some
    assert sorted(first + second) == expected  # every email, none twice
    assert len(sender.messages) == len(expected)


async def test_who_turns_emails_off_gets_none_and_no_backlog_after(
    client: httpx.AsyncClient, db: Factory, settings: Settings
) -> None:
    sender = FakeSender()
    await _emails_started(db, sender, settings)
    bob = as_user("bob")
    off = await client.put(SETTINGS_URL, json={"email_notifications": False}, headers=bob)
    assert off.status_code == 200, off.text
    project_id = await team_project(client)
    _, key = await _approval(client, db, project_id, ready_at=datetime.now(UTC) - MARGIN / 2)
    assert sorted(await email_notifications(db, sender, settings)) == [
        ("alice", key),
        ("root", key),
    ]

    on = await client.put(SETTINGS_URL, json={"email_notifications": True}, headers=bob)
    assert on.status_code == 200, on.text
    assert await email_notifications(db, sender, settings) == []  # nothing from while it was off
    later = await _finished_run(db, project_id, datetime.now(UTC) + MARGIN)
    assert await email_notifications(db, sender, settings) == [("bob", f"run.finished:{later}")]


async def test_emails_come_in_each_users_language(
    client: httpx.AsyncClient, db: Factory, settings: Settings
) -> None:
    sender = FakeSender()
    await _emails_started(db, sender, settings)
    await client.put(SETTINGS_URL, json={"locale": "ko"}, headers=as_user("bob"))
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    await awaiting_output(db, run_id, "method", METHOD_OUTPUT)
    await email_notifications(db, sender, settings)

    [english] = sender.to("alice@lab.test")
    [korean] = sender.to("bob@lab.test")
    assert english["Subject"] == "Review needed: Method for “Monocular depth”"
    assert korean["Subject"] == "검토 요청: “Monocular depth”의 방법론 단계"
    assert korean["Content-Language"] == "ko"
    plain, page = _parts(korean)
    assert plain.startswith(
        "Bob님, 안녕하세요.\n\n"
        "Depth 프로젝트의 “Monocular depth” 실행에서 방법론 단계가 검토를 기다리고 있습니다."
    )
    assert f"실행 열기: {ORIGIN}/runs/{run_id}" in plain
    assert f"프로필 페이지에서 알림을 끌 수 있습니다: {ORIGIN}/profile" in plain
    assert '<html lang="ko">' in page

    # A failed run names the stage it stopped at.
    await add_stage_run(db, run_id, "coding", StageStatus.FAILED, started_at=datetime.now(UTC))
    await set_run_status(db, run_id, RunStatus.FAILED, "stage.error")
    assert await email_notifications(db, sender, settings) == [("bob", f"run.finished:{run_id}")]
    failed = sender.messages[-1]
    assert failed["Subject"] == "실행 실패: “Monocular depth”"
    assert (
        "Depth 프로젝트의 “Monocular depth” 실행이 코딩 단계에서 실패했습니다." in _parts(failed)[0]
    )


async def test_old_notifications_are_never_emailed(
    client: httpx.AsyncClient, db: Factory, settings: Settings
) -> None:
    sender = FakeSender()
    now = datetime.now(UTC)
    project_id = await team_project(client)
    _, key = await _approval(client, db, project_id, ready_at=now - MARGIN)
    yesterday = await _finished_run(db, project_id, now - timedelta(days=1))
    await _finished_run(db, project_id, now - timedelta(days=3))

    # Emails ship: what came before stays in the app.
    assert await email_notifications(db, sender, settings) == []
    # Even a settings row from long ago gets nothing older than two days.
    async with db() as session:
        await session.execute(
            update(UserSettings)
            .where(UserSettings.user_id == "bob")
            .values(emails_since=now - timedelta(days=10))
        )
        await session.commit()
    assert sorted(await email_notifications(db, sender, settings)) == [
        ("bob", key),
        ("bob", f"run.finished:{yesterday}"),
    ]


async def test_a_failed_send_is_tried_again_after_a_wait_and_at_last_given_up(
    client: httpx.AsyncClient, db: Factory, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="agentic_api.mailer")
    sender = FakeSender()
    await _emails_started(db, sender, settings)
    project_id = await team_project(client)
    _, key = await _approval(client, db, project_id)

    sender.failures = 1  # alice's email is refused, and the pass ends there
    assert await email_notifications(db, sender, settings) == []
    refused = (await _rows(db))[("alice", key)]
    assert (refused.attempts, refused.sent_at) == (1, None)
    wait = refused.retry_at - refused.claimed_at  # a minute, give or take a clock step
    assert timedelta(seconds=30) < wait < timedelta(seconds=90)
    # The next pass sends the others; alice's waits until the minute is up.
    assert sorted(await email_notifications(db, sender, settings)) == [("bob", key), ("root", key)]
    async with db() as session:
        await session.execute(
            update(NotificationEmail)
            .where(NotificationEmail.user_id == "alice")
            .values(retry_at=func.now() - MARGIN)
        )
        await session.commit()
    assert await email_notifications(db, sender, settings) == [("alice", key)]
    sent = (await _rows(db))[("alice", key)]
    assert (sent.attempts, sent.sent_at is not None) == (2, True)

    # After MAX_ATTEMPTS failed attempts, an email is given up on.
    _, later = await _approval(client, db, project_id)
    async with db() as session:
        session.add(
            NotificationEmail(
                user_id="bob",
                notification_key=later,
                kind="approval_needed",
                attempts=MAX_ATTEMPTS,
                retry_at=datetime.now(UTC) - MARGIN,
            )
        )
        await session.commit()
    assert sorted(await email_notifications(db, sender, settings)) == [
        ("alice", later),
        ("root", later),
    ]

    logged = [record for record in caplog.records if record.name == "agentic_api.mailer"]
    assert any("attempt 1 of 8" in record.getMessage() for record in logged)
    assert not any("@" in record.getMessage() for record in logged)  # no addresses


async def test_text_from_people_and_models_is_escaped_in_the_html_part(
    client: httpx.AsyncClient, db: Factory, settings: Settings
) -> None:
    sender = FakeSender()
    await _emails_started(db, sender, settings)
    project_id = await team_project(client, "Depth & <b>Co</b>")
    topic = '<script>alert("hi")</script>\nand depth'
    run_id = await start_run(client, project_id, topic=topic)
    await awaiting_output(db, run_id)
    await email_notifications(db, sender, settings)

    [message] = sender.to("bob@lab.test")
    plain, page = _parts(message)
    assert "<script" not in page and "<b>" not in page
    assert "“&lt;script&gt;alert(&quot;hi&quot;)&lt;/script&gt;\nand depth”" in page
    assert "the project Depth &amp; &lt;b&gt;Co&lt;/b&gt;" in page
    assert topic in plain  # plain text is shown as it is
    # A header holds no line break.
    assert (
        message["Subject"]
        == 'Review needed: Literature for “<script>alert("hi")</script> and depth”'
    )


async def test_a_retried_run_is_emailed_again_when_it_finishes(
    client: httpx.AsyncClient, db: Factory, settings: Settings
) -> None:
    sender = FakeSender()
    await _emails_started(db, sender, settings)
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    await add_stage_run(db, run_id, "literature", StageStatus.FAILED, started_at=datetime.now(UTC))
    await set_run_status(db, run_id, RunStatus.FAILED, "stage.error")
    key = f"run.finished:{run_id}"
    assert await email_notifications(db, sender, settings) == [("bob", key)]

    retried = await client.post(
        f"/api/v1/runs/{run_id}/retry", params={"stage": "literature"}, headers=as_user("bob")
    )
    assert retried.status_code == 202, retried.text
    await set_run_status(db, run_id, RunStatus.COMPLETED)
    assert await email_notifications(db, sender, settings) == [("bob", key)]
    assert [message["Subject"] for message in sender.messages] == [
        "Run failed: “Monocular depth”",
        "Run finished: “Monocular depth”",
    ]
    assert "failed at the Literature stage." in _parts(sender.messages[0])[0]


async def test_the_background_task_keeps_passing(
    client: httpx.AsyncClient, db: Factory, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mailer, "RETRY_DELAY", timedelta(0))
    sender = FakeSender(failures=2)  # the first passes fail; the task carries on
    await _emails_started(db, sender, settings)
    project_id = await team_project(client)
    await _approval(client, db, project_id)
    task = asyncio.create_task(email_forever(db, sender, settings, interval_seconds=0.01))
    try:
        for _ in range(1000):  # up to 10 s: a retry may wait out a clock step
            if len(sender.messages) == 3:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    assert sorted(str(message["To"]) for message in sender.messages) == [
        "alice@lab.test",
        "bob@lab.test",
        "root@lab.test",
    ]


# --- What the emails say -------------------------------------------------------------------

RUN_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


def _notification(
    kind: NotificationKind, stage: str | None = None, **params: str | int | None
) -> NotificationOut:
    return NotificationOut(
        key=f"{kind}:test",
        kind=kind,
        created_at=datetime(2026, 10, 30, 5, 0, tzinfo=UTC),
        read=False,
        run_id=None if kind == "budget_alert" else RUN_ID,
        project_id=None,
        stage=stage,
        params={"topic": "Monocular depth", "project": "Depth", **params},
    )


EXPIRING = _notification(
    "approval_expiring", "method", days=7, expires_at="2026-10-31T05:05:00+00:00"
)
BUDGET = {"month": "2026-10", "budget_usd": "10.000000"}


@pytest.mark.parametrize(
    ("item", "stage", "english", "korean"),
    [
        (
            EXPIRING,
            "method",
            (
                "Reminder: decide on Method for “Monocular depth” by October 31, 2026, 14:05 KST",
                "If it is not approved, sent back for changes or rejected by October 31, 2026, "
                "14:05 KST, the run is cancelled.",
            ),
            (
                "알림: “Monocular depth”의 방법론 단계를 "
                "2026년 10월 31일 14:05 KST까지 결정해 주세요",
                "2026년 10월 31일 14:05 KST까지 승인, 수정 요청, 반려 중 아무것도 하지 않으면",
            ),
        ),
        (
            _notification("run_completed"),
            None,
            (
                "Run finished: “Monocular depth”",
                "“Monocular depth” in the project Depth finished: every stage is approved.",
            ),
            (
                "실행 완료: “Monocular depth”",
                "Depth 프로젝트의 “Monocular depth” 실행이 끝났습니다.",
            ),
        ),
        (
            _notification("run_failed"),
            None,
            ("Run failed: “Monocular depth”", "“Monocular depth” in the project Depth failed."),
            ("실행 실패: “Monocular depth”", "“Monocular depth” 실행이 실패했습니다."),
        ),
        (
            _notification("run_paused"),
            "literature",
            (
                "Run paused: “Monocular depth”",
                "is paused at the Literature stage because the lab's OpenRouter balance",
            ),
            ("실행 일시 중지: “Monocular depth”", "실행이 문헌 조사 단계에서 일시 중지되었습니다."),
        ),
        (
            _notification("budget_alert", percent=80, spent_usd="8.500000", **BUDGET),
            None,
            (
                "You have used 80% of your LLM budget for October 2026",
                "You have used $8.50 of your $10.00 paid-model budget for October 2026.",
            ),
            (
                "2026년 10월 LLM 예산의 80%를 사용했습니다",
                "2026년 10월 유료 모델 예산의 80%를 사용했습니다($10.00 중 $8.50).",
            ),
        ),
        (
            _notification("budget_alert", percent=100, spent_usd="10.250000", **BUDGET),
            None,
            ("Your LLM budget for October 2026 is used up", "until the budget starts again"),
            ("2026년 10월 LLM 예산을 모두 사용했습니다", "($10.00 중 $10.25)"),
        ),
    ],
)
def test_every_kind_reads_well_in_both_languages(
    item: NotificationOut,
    stage: str | None,
    english: tuple[str, str],
    korean: tuple[str, str],
) -> None:
    for locale, (subject, phrase) in (("en", english), ("ko", korean)):
        email = notification_email(item, locale=locale, name="Ada", stage=stage, origin=ORIGIN)
        assert email.subject == subject, locale
        assert phrase in email.text, locale
        link = f"{ORIGIN}/profile" if item.kind == "budget_alert" else f"{ORIGIN}/runs/{RUN_ID}"
        assert f'href="{link}"' in email.html and link in email.text, locale


def test_subjects_stay_short_and_a_missing_name_is_left_out() -> None:
    item = _notification("run_completed", topic="Depth " * 100)
    email = notification_email(item, locale="fr", name=" ", stage=None, origin=ORIGIN)
    assert email.language == "en"  # anything but Korean is English
    topic = email.subject.removeprefix("Run finished: “").removesuffix("”")
    assert len(topic) == 80 and topic.endswith("…")
    assert email.text.startswith("Hello,\n\n")
    korean = notification_email(item, locale="ko", name="", stage=None, origin=ORIGIN)
    assert korean.text.startswith("안녕하세요.\n\n")


class _FakeSmtp:
    """Stands in for smtplib.SMTP and SMTP_SSL: a server that offers STARTTLS."""

    sessions: ClassVar[list["_FakeSmtp"]] = []

    def __init__(self, host: str, port: int, **_: Any) -> None:
        self.address = (host, port)
        self.calls: list[str] = []
        _FakeSmtp.sessions.append(self)

    def __enter__(self) -> "_FakeSmtp":
        return self

    def __exit__(self, *_: object) -> None:
        self.calls.append("quit")

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def has_extn(self, name: str) -> bool:
        return name == "starttls"

    def starttls(self, **_: Any) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login {user} {password}")

    def send_message(self, message: EmailMessage) -> None:
        self.calls.append(f"send to {message['To']}")


async def test_smtp_urls_are_read_as_the_web_reads_them(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSmtp)
    message = EmailMessage()
    message["To"] = "bob@lab.test"

    plain = SmtpSender.from_url("smtp://ada%40lab:p%3Ass@mail.lab.test")
    assert (plain.host, plain.port, plain.secure) == ("mail.lab.test", 587, False)
    assert "p:ss" not in repr(plain)
    await plain.send(message)
    assert _FakeSmtp.sessions[-1].calls == [
        "ehlo",
        "starttls",
        "login ada@lab p:ss",
        "send to bob@lab.test",
        "quit",
    ]

    secure = SmtpSender.from_url("smtps://mail.lab.test")
    await secure.send(message)
    assert _FakeSmtp.sessions[-1].address == ("mail.lab.test", 465)
    assert _FakeSmtp.sessions[-1].calls == ["send to bob@lab.test", "quit"]

    for invalid in ("mail.lab.test:25", "http://mail.lab.test", "smtp://"):
        with pytest.raises(ValueError, match="SMTP_URL"):
            SmtpSender.from_url(invalid)
