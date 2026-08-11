"""Loading a built directory into the exact bytes an import will send."""

import base64
import pathlib
import tempfile

import pytest

from panos_response_pages.errors import ImportFailed
from panos_response_pages.importer import source

pytestmark = pytest.mark.unit

GOOD = "<html><body><p>blocked <user/> <url/> <category/></p></body></html>"


def build_dir(pages: dict[str, str]) -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp())
    for rel, text in pages.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_loads_known_pages_and_encodes_them():
    root = build_dir({"url-block-page.html": GOOD})
    items = source.load(root)
    assert [i.spec.remote for i in items] == ["url-block-page"]
    assert items[0].payload == GOOD.encode("utf-8")
    assert base64.b64decode(items[0].encoded) == GOOD.encode("utf-8")


def test_ignores_files_that_are_not_importable_pages():
    root = build_dir({"url-block-page.html": GOOD, "notes.html": "<html></html>", "readme.txt": "hi"})
    assert [i.spec.remote for i in source.load(root)] == ["url-block-page"]


def test_finds_portal_pages_in_their_subdirectory():
    root = build_dir({"portal/home.html": "<script>var logo='';</script>"})
    assert [i.spec.remote for i in source.load(root, check=False)] == ["global-protect-portal-custom-home-page"]


def test_only_filters_by_remote_name():
    root = build_dir({"url-block-page.html": GOOD, "file-block-page.html": GOOD})
    items = source.load(root, only={"url-block-page"})
    assert [i.spec.remote for i in items] == ["url-block-page"]


def test_empty_directory_is_an_error_naming_the_path():
    root = build_dir({"readme.txt": "hi"})
    with pytest.raises(ImportFailed) as exc:
        source.load(root)
    assert str(root) in str(exc.value)


def test_missing_directory_is_an_error():
    with pytest.raises(ImportFailed):
        source.load(pathlib.Path(tempfile.mkdtemp()) / "nope")


def test_unknown_only_name_is_rejected_with_the_available_names():
    root = build_dir({"url-block-page.html": GOOD})
    with pytest.raises(ImportFailed) as exc:
        source.load(root, only={"url-block-pge"})
    assert "url-block-page" in str(exc.value)


def test_guard_failures_are_carried_on_the_item():
    # An <a href> to somewhere other than the contact anchor is a documented
    # PAN-OS failure the build already rejects; import must see it too.
    root = build_dir({"url-block-page.html": "<html><body><a href='https://x'>x</a> <user/></body></html>"})
    items = source.load(root)
    assert items[0].errors, "a page that would fail on PAN-OS must be flagged"


def test_check_false_skips_the_guards():
    root = build_dir({"url-block-page.html": "<html><body><a href='https://x'>x</a></body></html>"})
    assert source.load(root, check=False)[0].errors == []
