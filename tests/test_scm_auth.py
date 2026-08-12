"""Token acquisition, caching and refresh -- without a network."""

import httpx
import pytest

from panos_response_pages.errors import ImportFailed
from panos_response_pages.importer.scm import auth
from panos_response_pages.importer.scm.config import ScmConfig

pytestmark = pytest.mark.unit

CFG = ScmConfig(
    client_id="a@b.iam.panserviceaccount.com",
    client_secret="s3cret",
    tsg_id="111",
    auth_url="https://auth.example",
    mfe_url="https://api.example/mfe/instances",
    folder="Prisma Access",
)


def source(handler, clock=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return auth.TokenSource(CFG, client, clock=clock or (lambda: 1000.0))


def test_posts_client_credentials_and_returns_the_token():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 899})

    assert source(handler).token() == "tok-1"
    assert seen["url"] == "https://auth.example/oauth2/access_token"
    assert "grant_type=client_credentials" in seen["body"]
    assert "scope=tsg_id%3A111" in seen["body"]


def test_token_is_cached_and_not_refetched():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 899})

    src = source(handler)
    assert src.token() == src.token()
    assert len(calls) == 1


def test_token_is_refetched_once_inside_the_refresh_margin():
    tokens = iter(["tok-1", "tok-2"])
    now = [1000.0]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": next(tokens), "expires_in": 899})

    src = auth.TokenSource(CFG, httpx.Client(transport=httpx.MockTransport(handler)), clock=lambda: now[0])
    assert src.token() == "tok-1"
    now[0] += 899 - auth.REFRESH_MARGIN + 1
    assert src.token() == "tok-2"


def test_rejection_raises_without_leaking_the_secret():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    with pytest.raises(ImportFailed) as exc:
        source(handler).token()
    assert "401" in str(exc.value)
    assert "s3cret" not in str(exc.value)


def test_transport_failure_is_reported_as_an_import_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(ImportFailed, match=r"auth\.example"):
        source(handler).token()
