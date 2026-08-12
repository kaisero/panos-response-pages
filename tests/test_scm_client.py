"""The SCM config API, pinned to what the endpoint actually does.

Every assertion here corresponds to a behaviour verified against a live tenant
and recorded in prototype/NOTES.md. They are regression tests for the API's
surprises, not for our code's preferences.
"""

import httpx
import pytest

from panos_response_pages.errors import ImportFailed
from panos_response_pages.importer.scm import client as scm_client
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

INSTANCES = [
    {"app_id": "logging_service", "runtime_attributes": {}},
    {
        "app_id": "prisma_access",
        "tenant_instance_name": "LAB - Prisma Access",
        "runtime_attributes": {
            "api_url": "https://us-prod-paas-4.api.prismaaccess.paloaltonetworks.com/",
            "mtls_api_url": "https://us-prod-paas-4.api.prismaaccess.paloaltonetworks.com/",
            "paas_api_url": "https://paas-4.prod.panorama.paloaltonetworks.com/",
        },
    },
]


class FakeToken:
    def token(self) -> str:
        return "tok-1"


def make(handler):
    return scm_client.ScmClient(CFG, FakeToken(), httpx.Client(transport=httpx.MockTransport(handler)))


def test_scope_type_is_bound_to_the_folder():
    assert scm_client.scope_type("Prisma Access") == "container"
    assert scm_client.scope_type("Mobile Users") == "cloud"
    assert scm_client.scope_type("Some Custom Folder") == "container"


def test_config_host_comes_from_paas_api_url_not_api_url():
    def handler(request):
        assert request.headers["authorization"] == "Bearer tok-1", "discovery uses Bearer"
        return httpx.Response(200, json=INSTANCES)

    assert make(handler).config_host() == "paas-4.prod.panorama.paloaltonetworks.com"


def test_config_host_is_cached():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=INSTANCES)

    c = make(handler)
    c.config_host()
    c.config_host()
    assert len(calls) == 1


def test_missing_prisma_access_instance_is_a_clear_failure():
    def handler(request):
        return httpx.Response(200, json=[{"app_id": "logging_service", "runtime_attributes": {}}])

    with pytest.raises(ImportFailed, match="no Prisma Access instance"):
        make(handler).config_host()


def test_config_calls_send_the_x_auth_jwt_header():
    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        assert request.headers["x-auth-jwt"] == "tok-1", "the config API rejects Bearer alone"
        return httpx.Response(200, json={"result": {"result": {"url-block-page": {"info": "QUJD"}}}})

    assert make(handler).get_page("url-block-page", "Prisma Access").content == "QUJD"


def test_get_page_sends_folder_and_the_matching_type():
    seen = {}

    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"result": {"result": {"url-block-page": {"info": "QUJD"}}}})

    make(handler).get_page("url-block-page", "Mobile Users")
    assert seen == {"type": "cloud", "folder": "Mobile Users", "blockPage": "url-block-page"}


def test_portal_content_is_read_from_entry_not_info():
    # A portal page carries BOTH: an empty predefined `info` placeholder and the
    # real content under entry[0].page. Reading `info` reports a good write as
    # a no-op.
    body = {
        "result": {
            "result": {
                "global-protect-portal-custom-home-page": {
                    "info": "\n    ",
                    "entry": [{"@name": "x", "@uuid": "u", "page": "UEFZTE9BRA=="}],
                }
            }
        }
    }

    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(200, json=body)

    state = make(handler).get_page("global-protect-portal-custom-home-page", "Mobile Users")
    assert state.content == "UEFZTE9BRA=="
    assert state.present is True


def test_whitespace_only_info_reads_as_absent():
    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(200, json={"result": {"result": {"url-block-page": {"info": "\n    "}}}})

    state = make(handler).get_page("url-block-page", "Prisma Access")
    assert state.present is False
    assert state.content is None


def test_inherited_values_are_flagged_with_their_source_folder():
    body = {
        "result": {
            "result": {"url-block-page": {"@uuid": "u", "@loc": "Prisma Access", "@type": "container", "info": "QUJD"}}
        }
    }

    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(200, json=body)

    state = make(handler).get_page("url-block-page", "Mobile Users")
    assert state.loc == "Prisma Access"
    assert state.inherited is True


def test_local_value_without_loc_is_not_inherited():
    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(200, json={"result": {"result": {"url-block-page": {"@uuid": "u", "info": "QUJD"}}}})

    assert make(handler).get_page("url-block-page", "Prisma Access").inherited is False


def test_put_page_posts_file_content_and_returns_the_mutation_id():
    seen = {}

    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        seen["method"] = request.method
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"ok": True, "result": {"@status": "success", "@mutationid": "21643"}})

    assert make(handler).put_page("url-block-page", "Prisma Access", "QUJD") == "21643"
    assert seen["method"] == "POST"
    assert '"fileContent": "QUJD"' in seen["body"] or '"fileContent":"QUJD"' in seen["body"]


def test_unknown_page_name_error_is_translated():
    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(400, json={"errorCode": "API_I00035", "message": "Invalid Request Payload"})

    with pytest.raises(ImportFailed, match="not a page SCM recognises"):
        make(handler).put_page("nope", "Prisma Access", "QUJD")


def test_name_collision_error_is_translated():
    body = {
        "errorCode": "API_I00013",
        "extra": {"errors": {"entry": [{"@type": "UNIQUEIN_ERROR", "msg": "already in use"}]}},
    }

    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(400, json=body)

    with pytest.raises(ImportFailed, match="already exists in another folder"):
        make(handler).put_page("global-protect-portal-custom-login-page", "Mobile Users", "QUJD")
