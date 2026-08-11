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


def test_unknown_key_raises():
    with pytest.raises(ValueError, match="unknown scm setting"):
        settings.load(write("scm:\n  clientid: oops\n"))


def test_non_mapping_raises():
    with pytest.raises(ValueError, match="'scm' must be a mapping"):
        settings.load(write("scm: nope\n"))
