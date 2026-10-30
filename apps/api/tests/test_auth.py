"""SessionVerifier against a stand-in for Better Auth's get-session endpoint."""

from collections.abc import Callable

import httpx
import pytest
from fastapi import HTTPException

from agentic_api.auth import CurrentUser, SessionVerifier

USER = {"session": {"id": "s1"}, "user": {"id": "u1", "email": "u1@lab.test", "name": "U"}}


def _verifier(answers: list[Callable[[], httpx.Response]]) -> tuple[SessionVerifier, list[int]]:
    """A verifier whose Better Auth gives ``answers`` in turn; the list counts the calls."""
    calls: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["cookie"] == "session=abc"
        calls.append(1)
        return answers[min(len(calls), len(answers)) - 1]()

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    return SessionVerifier("http://auth.test", ttl_seconds=60, client=client), calls


async def test_a_session_is_cached_for_the_ttl() -> None:
    verifier, calls = _verifier([lambda: httpx.Response(200, json=USER)])
    for _ in range(2):
        assert await verifier.verify("session=abc") == CurrentUser(
            id="u1", email="u1@lab.test", name="U", role="user"
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "no_session",
    [
        # Better Auth's answer for no session: a JSON null.
        lambda: httpx.Response(200, content=b"null", headers={"content-type": "application/json"}),
        lambda: httpx.Response(200, json={"session": None, "user": None}),
        lambda: httpx.Response(401, json={"message": "Unauthorized"}),
    ],
)
async def test_no_session_is_a_definite_answer_and_cached(
    no_session: Callable[[], httpx.Response],
) -> None:
    verifier, calls = _verifier([no_session, lambda: httpx.Response(200, json=USER)])
    assert await verifier.verify("session=abc") is None
    assert await verifier.verify("session=abc") is None
    assert len(calls) == 1


@pytest.mark.parametrize(
    "not_an_answer",
    [
        lambda: httpx.Response(500, json={"code": "FAILED_TO_GET_SESSION"}),  # its DB restarting
        lambda: httpx.Response(502, text="Bad Gateway"),
        lambda: httpx.Response(429, json={"message": "Too many requests"}),
        lambda: httpx.Response(200, text="<html>maintenance</html>"),
        lambda: httpx.Response(200, json=["unexpected"]),
        lambda: httpx.Response(200, json={"user": {"email": "no-id@lab.test"}}),
    ],
)
async def test_errors_are_unavailable_and_never_cached(
    not_an_answer: Callable[[], httpx.Response],
) -> None:
    """A minute of cached "signed out" would send every request to the login page and back."""
    verifier, calls = _verifier([not_an_answer, lambda: httpx.Response(200, json=USER)])
    with pytest.raises(HTTPException) as refused:
        await verifier.verify("session=abc")
    assert (refused.value.status_code, refused.value.detail) == (503, "auth.unavailable")
    user = await verifier.verify("session=abc")  # Better Auth has recovered
    assert user is not None and user.id == "u1"
    assert len(calls) == 2


async def test_an_unreachable_better_auth_is_unavailable() -> None:
    def refuse() -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    verifier, _ = _verifier([refuse])
    with pytest.raises(HTTPException) as refused:
        await verifier.verify("session=abc")
    assert (refused.value.status_code, refused.value.detail) == (503, "auth.unavailable")
