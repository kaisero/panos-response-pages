"""The report an operator reads to decide whether the import worked."""

import pytest

from panos_response_pages.importer.report import STAGED, ImportReport, PageResult, format_report

pytestmark = pytest.mark.unit


def report(*results: PageResult, dry_run: bool = False) -> ImportReport:
    return ImportReport(target="scm", describe="tenant 111", results=list(results), dry_run=dry_run)


def test_counts_and_failure_flag():
    r = report(PageResult("a", "F", True), PageResult("b", "F", False, detail="nope"))
    assert r.ok_count == 1
    assert r.failed is True
    assert report(PageResult("a", "F", True)).failed is False


def test_report_lists_every_page_with_its_folder():
    text = format_report(report(PageResult("url-block-page", "Prisma Access", True, "21643", 7594)))
    assert "url-block-page" in text
    assert "Prisma Access" in text


def test_failure_detail_is_shown():
    text = format_report(report(PageResult("url-block-page", "Prisma Access", False, detail="HTTP 400: nope")))
    assert "HTTP 400: nope" in text


def test_a_successful_run_says_the_pages_are_staged_not_live():
    text = format_report(report(PageResult("url-block-page", "Prisma Access", True)))
    assert "not been pushed" in text


def test_a_dry_run_says_nothing_was_sent():
    text = format_report(report(PageResult("url-block-page", "Prisma Access", True), dry_run=True))
    assert "dry run" in text.lower()
    assert "nothing was sent" in text


def test_a_failed_run_does_not_claim_staged():
    text = format_report(report(PageResult("url-block-page", "Prisma Access", False, detail="HTTP 400: nope")))
    assert STAGED not in text


def test_a_dry_run_does_not_claim_staged():
    text = format_report(report(PageResult("url-block-page", "Prisma Access", True), dry_run=True))
    assert STAGED not in text


def test_an_empty_report_does_not_claim_staged():
    text = format_report(report())
    assert STAGED not in text


def test_a_failed_result_with_a_mutation_id_shows_it():
    # ScmTarget.upload() attaches the mutation id to a "written, but could not
    # be verified" failure specifically so an operator can correlate the write
    # against the tenant. If format_report drops it, that justification is
    # false.
    text = format_report(
        report(
            PageResult(
                "url-block-page",
                "Prisma Access",
                False,
                mutation_id="21643",
                detail="written, but could not be read back: HTTP 500",
            )
        )
    )
    assert "21643" in text


def test_a_successful_result_does_not_show_a_mutation_id():
    # Noise, not signal: a successful write needs no correlation id in the
    # report an operator reads.
    text = format_report(report(PageResult("url-block-page", "Prisma Access", True, mutation_id="21643")))
    assert "21643" not in text
