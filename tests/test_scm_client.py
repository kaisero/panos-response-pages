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
        # Both headers are sent deliberately (fact 1): dropping Bearer must not
        # go unnoticed even though the API currently only checks x-auth-jwt.
        assert request.headers["authorization"] == "Bearer tok-1", "config calls also send Bearer"
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
    # A portal page carries BOTH: a stale `info` blob left over from before the
    # page moved to entry[], and the real content under entry[0].page. `info`
    # here is deliberately non-whitespace junk -- if it were just whitespace,
    # an info-first implementation would still fall through to entry and this
    # test would pass for the wrong reason.
    body = {
        "result": {
            "result": {
                "global-protect-portal-custom-home-page": {
                    "info": "c3RhbGUtcGxhY2Vob2xkZXI=",
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


def test_local_value_with_loc_matching_the_queried_folder_is_not_inherited():
    # Present-and-local-with-provenance: @loc is set, but it names the very
    # folder that was queried, so this is not inheritance.
    body = {
        "result": {
            "result": {"url-block-page": {"@uuid": "u", "@loc": "Prisma Access", "@type": "container", "info": "QUJD"}}
        }
    }

    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(200, json=body)

    state = make(handler).get_page("url-block-page", "Prisma Access")
    assert state.loc == "Prisma Access"
    assert state.inherited is False


def test_put_page_posts_file_content_and_returns_the_mutation_id():
    seen = {}

    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        seen["method"] = request.method
        seen["body"] = request.content.decode()
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"ok": True, "result": {"@status": "success", "@mutationid": "21643"}})

    assert make(handler).put_page("url-block-page", "Prisma Access", "QUJD") == "21643"
    assert seen["method"] == "POST"
    assert '"fileContent": "QUJD"' in seen["body"] or '"fileContent":"QUJD"' in seen["body"]
    # A write with no folder at all would still pass method/body/mutation-id
    # assertions above -- this is the check that actually pins the query string.
    assert seen["params"] == {"type": "container", "folder": "Prisma Access", "blockPage": "url-block-page"}


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


def test_crossed_scope_error_names_the_reason():
    # API_I00013 without a UNIQUEIN_ERROR entry is the "name is real but wrong
    # for this scope" case -- e.g. writing Mobile Users content under type
    # container. errorMessage does not appear in the recorded evidence; real
    # bodies carry the reason under `message`, and extra.errors.entry[] carries
    # the specific field-level cause.
    body = {
        "errorCode": "API_I00013",
        "message": "Invalid Object",
        "extra": {"errors": {"entry": [{"@type": "INVALID_OBJECT", "msg": "type does not match folder scope"}]}},
    }

    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(400, json=body)

    with pytest.raises(ImportFailed) as exc:
        make(handler).put_page("url-block-page", "Prisma Access", "QUJD")
    message = str(exc.value)
    assert message != ""
    assert "HTTP 400" in message
    assert "type does not match folder scope" in message


# ---- malformed response bodies -------------------------------------------


def test_entry_as_a_dict_instead_of_a_list_raises_import_failed():
    # A plausible shape for a PAN-OS-lineage JSON API: a single entry collapsed
    # to an object instead of a one-element list. Must not crash with KeyError.
    body = {
        "result": {
            "result": {
                "global-protect-portal-custom-home-page": {
                    "entry": {"@name": "x", "@uuid": "u", "page": "UEFZTE9BRA=="},
                }
            }
        }
    }

    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(200, json=body)

    with pytest.raises(ImportFailed, match="expected 'entry' to be a list"):
        make(handler).get_page("global-protect-portal-custom-home-page", "Mobile Users")


def test_400_body_that_is_not_a_json_object_does_not_crash_explain():
    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(400, json=["not", "an", "object"])

    with pytest.raises(ImportFailed, match="HTTP 400"):
        make(handler).put_page("url-block-page", "Prisma Access", "QUJD")


def test_400_body_that_is_a_json_string_does_not_crash_explain():
    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(400, json="boom")

    with pytest.raises(ImportFailed, match="HTTP 400"):
        make(handler).put_page("url-block-page", "Prisma Access", "QUJD")


def test_get_result_as_a_string_raises_import_failed():
    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(200, json={"result": "oops"})

    with pytest.raises(ImportFailed, match="expected 'result' to be a JSON object"):
        make(handler).get_page("url-block-page", "Prisma Access")


def test_get_top_level_array_raises_import_failed():
    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(200, json=["oops"])

    with pytest.raises(ImportFailed, match="expected a JSON object"):
        make(handler).get_page("url-block-page", "Prisma Access")


def test_post_top_level_array_raises_import_failed():
    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(200, json=["oops"])

    with pytest.raises(ImportFailed, match="expected a JSON object"):
        make(handler).put_page("url-block-page", "Prisma Access", "QUJD")


def test_post_result_as_a_string_raises_import_failed():
    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(200, json={"result": "boom"})

    with pytest.raises(ImportFailed, match="no usable result"):
        make(handler).put_page("url-block-page", "Prisma Access", "QUJD")


def test_entry_zero_as_a_string_raises_import_failed():
    body = {
        "result": {
            "result": {
                "global-protect-portal-custom-home-page": {"entry": ["not-a-dict"]},
            }
        }
    }

    def handler(request):
        if "mfe" in str(request.url):
            return httpx.Response(200, json=INSTANCES)
        return httpx.Response(200, json=body)

    with pytest.raises(ImportFailed, match=r"entry\[0\] to be a JSON object"):
        make(handler).get_page("global-protect-portal-custom-home-page", "Mobile Users")


def test_instances_list_of_non_dicts_is_skipped_not_a_crash():
    def handler(request):
        return httpx.Response(200, json=["not-a-dict", "also-not-a-dict"])

    with pytest.raises(ImportFailed, match="no Prisma Access instance"):
        make(handler).config_host()


def test_runtime_attributes_as_a_string_is_skipped_not_a_crash():
    def handler(request):
        return httpx.Response(200, json=[{"app_id": "prisma_access", "runtime_attributes": "not-a-dict"}])

    with pytest.raises(ImportFailed, match="no Prisma Access instance"):
        make(handler).config_host()


def test_schemeless_paas_api_url_is_rejected_not_cached():
    instances = [
        {
            "app_id": "prisma_access",
            "runtime_attributes": {"paas_api_url": "paas-4.example/api"},
        }
    ]

    def handler(request):
        return httpx.Response(200, json=instances)

    client = make(handler)
    with pytest.raises(ImportFailed, match="has no host"):
        client.config_host()
    # Confirm nothing was cached: a second call must hit the same failure, not
    # silently succeed with an empty host cached from the first attempt.
    with pytest.raises(ImportFailed, match="has no host"):
        client.config_host()
