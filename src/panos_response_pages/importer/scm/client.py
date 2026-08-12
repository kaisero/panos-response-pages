"""The Strata Cloud Manager config API, as it actually behaves.

This endpoint is undocumented and was reverse-engineered from the Strata Cloud
Manager UI; prototype/NOTES.md records the evidence for each rule below. Five
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
5. Error bodies are inconsistent even within one `errorCode`: the field that
   actually carries the human-readable reason is sometimes `errorMessage` and
   sometimes `message`. Treat every response body as untrusted shape, not just
   untrusted content -- this endpoint has been observed returning arrays,
   strings, and objects with the wrong nesting where a JSON object was expected.
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

# This is an exception table, not the set of folders that exist: it holds only
# the one folder whose scope type differs from the default, and must not be
# iterated to enumerate folders. Mobile Users is the GlobalProtect folder and
# is the only `cloud` scope this tool writes to.
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
            if not isinstance(instance, dict) or instance.get("app_id") != "prisma_access":
                continue
            runtime_attributes = instance.get("runtime_attributes")
            if not isinstance(runtime_attributes, dict):
                continue
            paas = runtime_attributes.get("paas_api_url")
            if not paas:
                continue
            try:
                host = urlparse(paas).netloc
            except ValueError:
                # urlparse itself can raise on a malformed URL (e.g. an
                # unterminated IPv6 literal) before the empty-netloc check
                # below ever runs. Same failure, same message either way.
                host = ""
            if not host:
                # Do not cache an empty host: that would make every subsequent
                # config call fail with an opaque "unknown url type" instead of
                # this clear message.
                raise ImportFailed(
                    f"paas_api_url {paas!r} for the Prisma Access instance in tenant "
                    f"{self._config.tsg_id} has no host; expected a full URL such as "
                    "https://paas-4.example.com/"
                )
            self._host = host
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
        # Same falsy-vs-truthy split as _node: a falsy 'entry' (e.g. "") is
        # absent, not broken, and falls through to the 'info' branch below.
        if entries and not isinstance(entries, list):
            raise ImportFailed(f"{page}: expected 'entry' to be a list, got {type(entries).__name__}")
        if entries:
            first = entries[0]
            if not isinstance(first, dict):
                raise ImportFailed(f"{page}: expected entry[0] to be a JSON object, got {type(first).__name__}")
            page_value = first.get("page")
            content = page_value if isinstance(page_value, str) and page_value.strip() else None
        else:
            info = node.get("info")
            content = info if isinstance(info, str) and info.strip() else None

        loc_value = node.get("@loc")
        loc = loc_value if isinstance(loc_value, str) else None
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
        if not isinstance(payload, dict):
            raise ImportFailed(f"{page}: expected a JSON object in the write response, got {type(payload).__name__}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ImportFailed(f"{page}: write response had no usable result: {json.dumps(payload)[:200]}")
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
    def _node(payload: Any, page: str) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            raise ImportFailed(f"{page}: expected a JSON object in the response, got {type(payload).__name__}")
        outer = payload.get("result")
        # A falsy value here (e.g. "" -- how an empty XML element serialises
        # for this endpoint, per fact 5) carries no information: read it as
        # "nothing here", the same as a missing key. Only a *truthy* value of
        # the wrong type is a genuinely broken response worth raising on.
        if not outer:
            return None
        if not isinstance(outer, dict):
            raise ImportFailed(f"{page}: expected 'result' to be a JSON object, got {type(outer).__name__}")
        inner = outer.get("result")
        if not inner:
            return None
        if not isinstance(inner, dict):
            raise ImportFailed(f"{page}: expected 'result.result' to be a JSON object, got {type(inner).__name__}")
        node = inner.get(page)
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
        status = response.status_code
        try:
            body = response.json()
        except ValueError:
            return f"HTTP {status}: {response.text[:200]}"
        if not isinstance(body, dict):
            return f"HTTP {status}: {json.dumps(body)[:200]}"

        code = body.get("errorCode")
        if code == "API_I00035":
            message = body.get("message")
            detail = f" ({message})" if message else ""
            return f"HTTP {status}: not a page SCM recognises in this scope{detail}"
        if code == "API_I00013":
            raw_entries = ((body.get("extra") or {}).get("errors") or {}).get("entry")
            entries = [e for e in raw_entries if isinstance(e, dict)] if isinstance(raw_entries, list) else []
            if any(e.get("@type") == "UNIQUEIN_ERROR" for e in entries):
                return (
                    f"HTTP {status}: this page already exists in another folder. GlobalProtect portal page "
                    "names must be unique across the folder tree, and the existing object has to be "
                    "removed before it can be written here."
                )
            # errorMessage is the documented field name, but real responses carry
            # the reason under `message`; entry[].{@type,msg} is where the actual
            # cause of a crossed folder/type 400 lives.
            reason = body.get("errorMessage") or body.get("message") or ""
            detail = "; ".join(f"{e.get('@type', 'error')}: {e.get('msg', '')}" for e in entries if e.get("msg"))
            if detail:
                reason = f"{reason} ({detail})" if reason else detail
            return f"HTTP {status}: SCM rejected the configuration: {reason}"
        return f"HTTP {status}: {json.dumps(body)[:200]}"
