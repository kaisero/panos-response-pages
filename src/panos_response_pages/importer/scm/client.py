"""The Strata Cloud Manager config API, as it actually behaves.

This endpoint is undocumented and was reverse-engineered from the Strata Cloud
Manager UI; prototype/NOTES.md records the evidence for each rule below. Four
things about it are counter-intuitive enough to be worth stating here, because
every one of them produced a wrong implementation first:

1. Two hosts, two auth headers, one token. Instance discovery wants
   `Authorization: Bearer`; the config API answers `401 Invalid/Expired Token`
   to Bearer and requires `x-auth-jwt`. Config calls send both, so accepting
   Bearer later cannot break us.
2. The config host is `runtime_attributes.paas_api_url`. The sibling `api_url`
   and `mtls_api_url` are mTLS endpoints and fail the TLS handshake without a
   client certificate.
3. `folder` and `type` are one unit, not two flags. Mobile Users is `cloud`,
   everything else is `container`; crossing them is a 400.
4. Reads return *effective* config. A child folder inherits from its parent and
   says so in `@loc`, so matching content does not prove the value lives in the
   folder you wrote to.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from panos_response_pages.errors import ImportFailed
from panos_response_pages.importer.scm.config import ScmConfig

CONFIG_PATH = "/api/config/v9.2/Device/BlockPage"

# Folders whose scope type is not the default. Mobile Users is the GlobalProtect
# folder and is the only `cloud` scope this tool writes to.
SCOPE_TYPES = {"Mobile Users": "cloud"}
DEFAULT_SCOPE_TYPE = "container"


class TokenLike(Protocol):
    def token(self) -> str: ...


def scope_type(folder: str) -> str:
    """The `type` that belongs with this folder. Never a caller's choice."""
    return SCOPE_TYPES.get(folder, DEFAULT_SCOPE_TYPE)


@dataclass(frozen=True)
class PageState:
    """What the tenant currently holds for one page in one folder."""

    present: bool
    content: str | None
    loc: str | None
    inherited: bool


class ScmClient:
    """One tenant's config API."""

    def __init__(self, config: ScmConfig, token_source: TokenLike, client: httpx.Client):
        self._config = config
        self._tokens = token_source
        self._client = client
        self._host: str | None = None

    # ---- discovery ----------------------------------------------------------

    def config_host(self) -> str:
        """The host that serves the config API for this tenant."""
        if self._host is not None:
            return self._host

        payload = self._call(
            "GET",
            self._config.mfe_url,
            headers={"Authorization": f"Bearer {self._tokens.token()}", "Accept": "application/json"},
        )
        if not isinstance(payload, list):
            raise ImportFailed(f"{self._config.mfe_url} did not return a list of instances")

        for instance in payload:
            if instance.get("app_id") != "prisma_access":
                continue
            paas = (instance.get("runtime_attributes") or {}).get("paas_api_url")
            if paas:
                self._host = urlparse(paas).netloc
                return self._host

        raise ImportFailed(
            f"no Prisma Access instance with a paas_api_url in tenant {self._config.tsg_id}. "
            "The service account may not have access to Prisma Access."
        )

    # ---- pages --------------------------------------------------------------

    def get_page(self, page: str, folder: str) -> PageState:
        payload = self._call("GET", self._page_url(), headers=self._config_headers(), params=self._params(page, folder))
        node = self._node(payload, page)
        if node is None:
            return PageState(present=False, content=None, loc=None, inherited=False)

        # entry[] before info: a portal page carries an empty `info` placeholder
        # alongside its real content, so info-first reports a good write as a no-op.
        entries = node.get("entry")
        if entries:
            content = entries[0].get("page")
        else:
            info = node.get("info")
            content = info if isinstance(info, str) and info.strip() else None

        loc = node.get("@loc")
        return PageState(
            present=content is not None,
            content=content,
            loc=loc,
            inherited=bool(loc) and loc != folder,
        )

    def put_page(self, page: str, folder: str, encoded: str) -> str:
        """Write one page. Returns the mutation id."""
        payload = self._call(
            "POST",
            self._page_url(),
            headers={**self._config_headers(), "Content-Type": "application/json"},
            content=json.dumps({"fileContent": encoded}).encode(),
            params=self._params(page, folder),
        )
        result = payload.get("result") or {}
        if result.get("@status") != "success":
            raise ImportFailed(f"{page}: write was not accepted: {json.dumps(result)[:200]}")
        return str(result.get("@mutationid", ""))

    # ---- plumbing -----------------------------------------------------------

    def _page_url(self) -> str:
        return f"https://{self.config_host()}{CONFIG_PATH}"

    @staticmethod
    def _params(page: str, folder: str) -> dict[str, str]:
        """The query string. `type` is derived, never taken from a caller."""
        return {"type": scope_type(folder), "folder": folder, "blockPage": page}

    def _config_headers(self) -> dict[str, str]:
        token = self._tokens.token()
        # Both, deliberately: x-auth-jwt is what this endpoint requires today.
        return {"x-auth-jwt": token, "Authorization": f"Bearer {token}", "Accept": "*/*"}

    @staticmethod
    def _node(payload: dict[str, Any], page: str) -> dict[str, Any] | None:
        node = ((payload.get("result") or {}).get("result") or {}).get(page)
        return node if isinstance(node, dict) else None

    def _call(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        content: bytes | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        try:
            response = self._client.request(method, url, headers=headers, content=content, params=params, timeout=60.0)
        except httpx.HTTPError as exc:
            raise ImportFailed(f"could not reach {url}: {exc}") from exc

        if response.status_code >= 400:
            raise ImportFailed(self._explain(response))
        try:
            return response.json()
        except ValueError as exc:
            raise ImportFailed(f"{url} returned a non-JSON body: {response.text[:200]}") from exc

    @staticmethod
    def _explain(response: httpx.Response) -> str:
        """Translate the API's two 400s into something actionable.

        API_I00035 means the blockPage value is not in the enum at all -- also
        what any unexpected query parameter produces, since parameter validation
        is strict. API_I00013 means the name is real but wrong here: wrong scope,
        or a name already taken elsewhere in the folder tree.
        """
        try:
            body = response.json()
        except ValueError:
            return f"HTTP {response.status_code}: {response.text[:200]}"

        code = body.get("errorCode")
        if code == "API_I00035":
            return f"HTTP 400: not a page SCM recognises in this scope ({body.get('message', '')})"
        if code == "API_I00013":
            entries = ((body.get("extra") or {}).get("errors") or {}).get("entry") or []
            if any(e.get("@type") == "UNIQUEIN_ERROR" for e in entries):
                return (
                    "HTTP 400: this page already exists in another folder. GlobalProtect portal page "
                    "names must be unique across the folder tree, and the existing object has to be "
                    "removed before it can be written here."
                )
            return f"HTTP 400: SCM rejected the configuration: {body.get('errorMessage', '')}"
        return f"HTTP {response.status_code}: {json.dumps(body)[:200]}"
