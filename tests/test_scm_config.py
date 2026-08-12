"""Credential precedence: CLI flag > environment > settings.yaml > default."""

import pytest

from panos_response_pages.errors import ImportFailed
from panos_response_pages.importer.scm import config
from panos_response_pages.settings import ScmSettings

pytestmark = pytest.mark.unit

FILE = ScmSettings(client_id="file@x.iam.panserviceaccount.com", client_secret="file-secret", tsg_id="111")


def test_settings_file_is_used_when_nothing_else_is_set():
    cfg = config.resolve(FILE, env={})
    assert cfg.client_id == "file@x.iam.panserviceaccount.com"
    assert cfg.tsg_id == "111"


def test_environment_beats_the_settings_file():
    cfg = config.resolve(FILE, env={"SCM_CLIENT_ID": "env@x.iam.panserviceaccount.com", "SCM_TSG_ID": "222"})
    assert cfg.client_id == "env@x.iam.panserviceaccount.com"
    assert cfg.tsg_id == "222"
    assert cfg.client_secret == "file-secret", "an unset layer must not blank a set one"


def test_flag_beats_the_environment():
    cfg = config.resolve(FILE, client_id="flag@x.iam.panserviceaccount.com", env={"SCM_CLIENT_ID": "env@x"})
    assert cfg.client_id == "flag@x.iam.panserviceaccount.com"


def test_scope_is_derived_from_the_tsg_id():
    assert config.resolve(FILE, env={}).scope == "tsg_id:111"


def test_folder_default_and_override():
    assert config.resolve(FILE, env={}).folder == "Prisma Access"
    assert config.resolve(FILE, env={}, folder="Lab").folder == "Lab"
    assert config.resolve(FILE, env={"SCM_FOLDER": "EnvLab"}).folder == "EnvLab"


def test_missing_credentials_are_reported_together_and_name_every_source():
    with pytest.raises(ImportFailed) as exc:
        config.resolve(ScmSettings(), env={})
    message = str(exc.value)
    assert "client_id" in message and "client_secret" in message and "tsg_id" in message
    assert "SCM_CLIENT_ID" in message, "the error must say which environment variable to set"
    assert "--client-id" in message, "and which flag"


def test_the_secret_never_appears_in_the_error():
    with pytest.raises(ImportFailed) as exc:
        config.resolve(ScmSettings(client_secret="hunter2"), env={})
    assert "hunter2" not in str(exc.value)
