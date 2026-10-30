"""Generated stand-ins for the parts of the platform that are not built yet.

Every generator here is pure and deterministic: its output depends only on its arguments (ids,
dates, the instant asked about), never on hidden randomness or I/O, so the front end can be
built against stable data and tests can pin it. Responses that carry anything generated here
set ``demo: true``; real figures (spend, call counts, run state) are never generated.
"""


def is_demo_reason(reason: str | None) -> bool:
    """Whether a stage output's degraded reason marks generated demo content.

    The worker flags generated outputs with codes such as ``literature.demo_search`` and
    ``stage.demo``: any dotted part that is ``demo`` or starts with ``demo_``.
    """
    if not reason:
        return False
    return any(part == "demo" or part.startswith("demo_") for part in reason.split("."))
