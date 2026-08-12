"""OAuth2 client-credentials token for a service account.

A plain client_credentials grant against the tenant's auth host: no interactive
sign-in, no browser JWT. Tokens last ~899 seconds, which is long enough for a
whole import several times over, so this refreshes on demand rather than on a
timer.

The clock is injected so the refresh margin can be tested without sleeping.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from panos_response_pages.errors import ImportFailed
from panos_response_pages.importer.scm.config import ScmConfig

# Refresh this many seconds before the server's stated expiry, so a token cannot
# expire between the check and the call it was fetched for.
REFRESH_MARGIN = 60


class TokenSource:
    """Fetches and caches one tenant's access token."""

    def __init__(self, config: ScmConfig, client: httpx.Client, *, clock: Callable[[], float] = time.monotonic):
        self._config = config
        self._client = client
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0

    def token(self) -> str:
        if self._token and self._clock() < self._expires_at:
            return self._token
        return self._refresh()

    def _refresh(self) -> str:
        url = f"{self._config.auth_url.rstrip('/')}/oauth2/access_token"
        try:
            response = self._client.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                    "scope": self._config.scope,
                },
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise ImportFailed(f"could not reach {url}: {exc}") from exc

        if response.status_code != 200:
            # response.text, never the request: the request body carries the secret.
            raise ImportFailed(
                f"authentication failed ({response.status_code}) for {self._config.client_id}: {response.text[:200]}"
            )

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise ImportFailed(f"authentication response from {url} carried no access_token")

        self._token = str(token)
        self._expires_at = self._clock() + float(payload.get("expires_in", 899)) - REFRESH_MARGIN
        return self._token
