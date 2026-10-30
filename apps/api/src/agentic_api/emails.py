"""What notification emails say (agentic_api.mailer sends them), in English and Korean.

Each email names the run's topic, its project and the stage, links to the page to act on, and
ends with how to turn these emails off. Topics, project names and user names come from people
and models, so the HTML part escapes every one of them.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from html import escape

from agentic_api.schemas import NotificationKind, NotificationOut

# The kinds that are emailed; cancelled and rejected runs only show in the app (their owner
# did that, or saw it coming).
EMAILED_KINDS: frozenset[NotificationKind] = frozenset(
    {
        "approval_needed",
        "approval_expiring",
        "run_completed",
        "run_failed",
        "run_paused",
        "budget_alert",
    }
)
# Dates are in the lab's time zone, as in the web (apps/web/src/i18n/config.ts). Asia/Seoul is
# UTC+9 all year, so a fixed offset needs no time zone database in the container.
LAB_TIME = timezone(timedelta(hours=9), "KST")
SUBJECT_TOPIC_LENGTH = 80  # topics may have 500 characters; subjects stay readable

_EN_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# As the web names the stages (apps/web/messages/<locale>/core.json, "stages").
_STAGES = {
    "en": {
        "literature": "Literature",
        "method": "Method",
        "coding": "Coding",
        "experiment": "Experiment",
        "writing": "Writing",
    },
    "ko": {
        "literature": "문헌 조사",
        "method": "방법론",
        "coding": "코딩",
        "experiment": "실험",
        "writing": "논문 작성",
    },
}

_COPY = {
    "en": {
        "hello": "Hello {name},",
        "hello_unnamed": "Hello,",
        "approval_needed.subject": "Review needed: {stage} for “{topic}”",
        "approval_needed.body": (
            "The {stage} stage of “{topic}” in the project {project} is ready for your review. "
            "The run waits until its output is approved, sent back for changes or rejected."
        ),
        "approval_expiring.subject": "Reminder: decide on {stage} for “{topic}” by {expires}",
        "approval_expiring.body": (
            "The {stage} stage of “{topic}” in the project {project} is still waiting for a "
            "decision. If it is not approved, sent back for changes or rejected by {expires}, "
            "the run is cancelled."
        ),
        "run_completed.subject": "Run finished: “{topic}”",
        "run_completed.body": (
            "“{topic}” in the project {project} finished: every stage is approved."
        ),
        "run_failed.subject": "Run failed: “{topic}”",
        "run_failed.body": (
            "“{topic}” in the project {project} failed at the {stage} stage. The run page shows "
            "what went wrong, and you can retry the run from there."
        ),
        "run_failed.body_without_stage": (
            "“{topic}” in the project {project} failed. The run page shows what went wrong, and "
            "you can retry the run from there."
        ),
        "run_paused.subject": "Run paused: “{topic}”",
        "run_paused.body": (
            "“{topic}” in the project {project} is paused at the {stage} stage because the "
            "lab's OpenRouter balance is used up. It continues by itself once a lab admin tops "
            "the balance up."
        ),
        "run_paused.body_without_stage": (
            "“{topic}” in the project {project} is paused because the lab's OpenRouter balance "
            "is used up. It continues by itself once a lab admin tops the balance up."
        ),
        "budget_warning.subject": "You have used {percent}% of your LLM budget for {month}",
        "budget_warning.body": (
            "You have used {spent} of your {budget} paid-model budget for {month}. Once it is "
            "used up, your runs continue on free models."
        ),
        "budget_exhausted.subject": "Your LLM budget for {month} is used up",
        "budget_exhausted.body": (
            "You have used {spent} of your {budget} paid-model budget for {month}. Your runs "
            "continue on free models until the budget starts again next month or a lab admin "
            "raises it."
        ),
        "open_run": "Open the run",
        "open_budget": "See your budget and spend",
        "footer": "You get this email because email notifications are on for your account.",
        "turn_off": "You can turn them off on your profile page",
    },
    "ko": {
        "hello": "{name}님, 안녕하세요.",
        "hello_unnamed": "안녕하세요.",
        "approval_needed.subject": "검토 요청: “{topic}”의 {stage} 단계",
        "approval_needed.body": (
            "{project} 프로젝트의 “{topic}” 실행에서 {stage} 단계가 검토를 기다리고 있습니다. "
            "결과물을 승인하거나, 수정을 요청하거나, 반려할 때까지 실행은 멈춰 있습니다."
        ),
        "approval_expiring.subject": "알림: “{topic}”의 {stage} 단계를 {expires}까지 결정해 주세요",
        "approval_expiring.body": (
            "{project} 프로젝트의 “{topic}” 실행에서 {stage} 단계가 아직 결정을 기다리고 "
            "있습니다. {expires}까지 승인, 수정 요청, 반려 중 아무것도 하지 않으면 실행이 "
            "취소됩니다."
        ),
        "run_completed.subject": "실행 완료: “{topic}”",
        "run_completed.body": (
            "{project} 프로젝트의 “{topic}” 실행이 끝났습니다. 모든 단계가 승인되었습니다."
        ),
        "run_failed.subject": "실행 실패: “{topic}”",
        "run_failed.body": (
            "{project} 프로젝트의 “{topic}” 실행이 {stage} 단계에서 실패했습니다. 실행 "
            "페이지에서 원인을 확인하고 다시 시도할 수 있습니다."
        ),
        "run_failed.body_without_stage": (
            "{project} 프로젝트의 “{topic}” 실행이 실패했습니다. 실행 페이지에서 원인을 "
            "확인하고 다시 시도할 수 있습니다."
        ),
        "run_paused.subject": "실행 일시 중지: “{topic}”",
        "run_paused.body": (
            "랩의 OpenRouter 잔액이 소진되어 {project} 프로젝트의 “{topic}” 실행이 {stage} "
            "단계에서 일시 중지되었습니다. 랩 관리자가 잔액을 충전하면 자동으로 이어서 "
            "진행됩니다."
        ),
        "run_paused.body_without_stage": (
            "랩의 OpenRouter 잔액이 소진되어 {project} 프로젝트의 “{topic}” 실행이 일시 "
            "중지되었습니다. 랩 관리자가 잔액을 충전하면 자동으로 이어서 진행됩니다."
        ),
        "budget_warning.subject": "{month} LLM 예산의 {percent}%를 사용했습니다",
        "budget_warning.body": (
            "{month} 유료 모델 예산의 {percent}%를 사용했습니다({budget} 중 {spent}). 예산을 "
            "모두 쓰면 실행은 무료 모델로 계속됩니다."
        ),
        "budget_exhausted.subject": "{month} LLM 예산을 모두 사용했습니다",
        "budget_exhausted.body": (
            "{month} 유료 모델 예산을 모두 사용했습니다({budget} 중 {spent}). 다음 달에 예산이 "
            "다시 시작되거나 랩 관리자가 예산을 늘릴 때까지 실행은 무료 모델로 계속됩니다."
        ),
        "open_run": "실행 열기",
        "open_budget": "예산과 사용액 보기",
        "footer": "계정의 이메일 알림이 켜져 있어 이 메일을 보냈습니다.",
        "turn_off": "프로필 페이지에서 알림을 끌 수 있습니다",
    },
}

_PAGE_STYLE = (
    "margin:0;padding:24px;background:#f5f6f8;color:#1f2328;line-height:1.55;"
    "font-family:-apple-system,'Segoe UI',Roboto,'Noto Sans KR','Apple SD Gothic Neo',sans-serif"
)
_CARD_STYLE = (
    "max-width:560px;margin:0 auto;padding:8px 24px;background:#ffffff;"
    "border:1px solid #e3e5e8;border-radius:8px"
)
_BUTTON_STYLE = (
    "display:inline-block;padding:9px 16px;border-radius:6px;background:#2f5bd3;"
    "color:#ffffff;text-decoration:none;font-weight:600"
)
_FOOTER_STYLE = "max-width:560px;margin:16px auto 0;font-size:12px;color:#6a737d"


@dataclass(frozen=True)
class Email:
    language: str  # en or ko
    subject: str
    text: str
    html: str


def notification_email(
    item: NotificationOut, *, locale: str, name: str, stage: str | None, origin: str
) -> Email:
    """The email for ``item`` (a kind of EMAILED_KINDS) in ``locale``, English unless it is
    "ko". ``stage`` is the stage to name: the notification's own, or for a failed or paused run,
    the stage it stopped at (None when it never started one). Links open the app at ``origin``.
    """
    language = locale if locale in _COPY else "en"
    copy = _COPY[language]
    values = {
        "topic": _param(item, "topic"),
        "project": _param(item, "project"),
        "stage": _STAGES[language].get(stage, stage) if stage else "",
    }
    if item.kind == "budget_alert":
        percent = int(_param(item, "percent"))
        template = "budget_exhausted" if percent >= 100 else "budget_warning"
        values |= {
            "percent": str(percent),
            "month": _month(_param(item, "month"), language),
            "spent": _usd(_param(item, "spent_usd")),
            "budget": _usd(_param(item, "budget_usd")),
        }
        action, url = copy["open_budget"], f"{origin}/profile"
    else:
        template = item.kind
        if item.kind == "approval_expiring":
            expires_at = datetime.fromisoformat(_param(item, "expires_at"))
            values["expires"] = _when(expires_at, language)
        action, url = copy["open_run"], f"{origin}/runs/{item.run_id}"
    body_key = f"{template}.body"
    if not stage and f"{body_key}_without_stage" in copy:
        body_key += "_without_stage"

    short_topic = _one_line(values["topic"], SUBJECT_TOPIC_LENGTH)
    subject = _one_line(copy[f"{template}.subject"].format(**{**values, "topic": short_topic}))
    paragraphs = [
        copy["hello"].format(name=name.strip()) if name.strip() else copy["hello_unnamed"],
        copy[body_key].format(**values),
    ]
    profile = f"{origin}/profile"
    text = "\n\n".join([*paragraphs, f"{action}: {url}"])
    text += f"\n\n-- \n{copy['footer']} {copy['turn_off']}: {profile}\n"
    page = "".join(
        [
            f'<!doctype html>\n<html lang="{language}">\n',
            '<head><meta charset="utf-8"></head>\n',
            f'<body style="{_PAGE_STYLE}">\n<div style="{_CARD_STYLE}">\n',
            *(f"<p>{escape(paragraph)}</p>\n" for paragraph in paragraphs),
            f'<p><a href="{escape(url)}" style="{_BUTTON_STYLE}">{escape(action)}</a></p>\n',
            "</div>\n",
            f'<p style="{_FOOTER_STYLE}">{escape(copy["footer"])} ',
            f'<a href="{escape(profile)}" style="color:#6a737d">{escape(copy["turn_off"])}</a>.',
            "</p>\n</body>\n</html>\n",
        ]
    )
    return Email(language=language, subject=subject, text=text, html=page)


def _param(item: NotificationOut, name: str) -> str:
    value = item.params.get(name)
    return "" if value is None else str(value)


def _one_line(text: str, limit: int | None = None) -> str:
    """``text`` on one line (a header can't hold a line break), cut to ``limit`` characters."""
    line = " ".join(text.split())
    if limit is None or len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + "…"


def _when(at: datetime, language: str) -> str:
    local = at.astimezone(LAB_TIME)
    clock = f"{local:%H:%M} KST"
    if language == "ko":
        return f"{local.year}년 {local.month}월 {local.day}일 {clock}"
    return f"{_EN_MONTHS[local.month - 1]} {local.day}, {local.year}, {clock}"


def _month(month: str, language: str) -> str:
    """A UTC month, "2026-10", as people write it."""
    year, number = month.split("-")
    if language == "ko":
        return f"{year}년 {int(number)}월"
    return f"{_EN_MONTHS[int(number) - 1]} {year}"


def _usd(amount: str) -> str:
    return f"${Decimal(amount):,.2f}"
