"""The scm: block in settings.yaml, parsed as strictly as log: is."""

import pathlib
import tempfile

import pytest

from panos_response_pages import settings

pytestmark = pytest.mark.unit


def write(text: str) -> pathlib.Path:
    path = pathlib.Path(tempfile.mkdtemp()) / "settings.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_absent_block_yields_defaults():
    s = settings.load(write("log:\n  level: debug\n"))
    assert s.scm.client_id is None
    assert s.scm.folder == "Prisma Access"
    assert s.scm.auth_url == "https://auth.apps.paloaltonetworks.com"


def test_values_are_read():
    s = settings.load(write("scm:\n  client_id: a@b.iam.panserviceaccount.com\n  tsg_id: '123'\n  folder: Lab\n"))
    assert s.scm.client_id == "a@b.iam.panserviceaccount.com"
    assert s.scm.tsg_id == "123"
    assert s.scm.folder == "Lab"


def test_numeric_tsg_id_becomes_a_string():
    # YAML reads a bare 1902164213 as an int; it is a scope suffix, not a number.
    s = settings.load(write("scm:\n  tsg_id: 1902164213\n"))
    assert s.scm.tsg_id == "1902164213"


def test_explicit_null_yields_defaults():
    # An explicit `key: null` is a present key whose value is None, not an
    # absent key -- dict.get(key, default) does not catch it. A settings file
    # rendered from a template with an unset variable produces exactly this.
    s = settings.load(write("scm:\n  auth_url: null\n  mfe_url: null\n  folder: null\n"))
    assert s.scm.auth_url == "https://auth.apps.paloaltonetworks.com"
    assert s.scm.mfe_url == "https://api.apps.paloaltonetworks.com/mfe/instances"
    assert s.scm.folder == "Prisma Access"


def test_unknown_key_raises():
    with pytest.raises(ValueError, match="unknown scm setting"):
        settings.load(write("scm:\n  clientid: oops\n"))


def test_non_mapping_raises():
    with pytest.raises(ValueError, match="'scm' must be a mapping"):
        settings.load(write("scm: nope\n"))


def test_repr_masks_the_client_secret():
    # This Settings object lives in ctx.obj for the whole CLI run, so an
    # accidental %r or debug dump anywhere along the way must not leak it --
    # the same rule importer/scm/config.py's ScmConfig obeys.
    scm = settings.ScmSettings(client_id="a@b.iam.panserviceaccount.com", client_secret="hunter2", tsg_id="111")
    text = repr(scm)
    assert "hunter2" not in text
    assert "***" in text
