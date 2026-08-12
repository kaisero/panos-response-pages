"""What an import did, in a form an operator can act on.

The closing line is load-bearing. A write lands in candidate configuration, and
nothing here pushes it: an operator who reads "11/11 imported" and assumes the
firewalls have the new pages would be wrong. Deploy is deliberately out of
scope for this tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field

STAGED = "These pages are staged in candidate configuration and have not been pushed."


@dataclass
class PageResult:
    """One page's outcome."""

    page: str
    folder: str
    ok: bool
    mutation_id: str = ""
    size: int = 0
    detail: str = ""


@dataclass
class ImportReport:
    """Every page's outcome for one run against one target."""

    target: str
    describe: str
    results: list[PageResult] = field(default_factory=list)
    dry_run: bool = False

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> bool:
        return any(not r.ok for r in self.results)


def format_report(report: ImportReport) -> str:
    """Render a report for a terminal.

    Page names, folders, sizes and outcomes only -- no credential or token
    ever passes through a `PageResult`, so there is nothing here to redact.
    """
    verb = "would import" if report.dry_run else "imported"
    lines = [f"\n  {report.target}: {report.describe}\n"]

    width = max((len(r.page) for r in report.results), default=0)
    for r in report.results:
        mark = "ok  " if r.ok else "FAIL"
        size = f"{r.size:>7,} B" if r.size else " " * 9
        lines.append(f"  {mark} {r.page:<{width}} {size}  {r.folder}")
        if r.detail:
            lines.append(f"       {r.detail}")
        # Only on failure: a mutation id on a successful write is nothing an
        # operator needs to act on, and ScmTarget.upload() only ever attaches
        # one to a result it could not fully verify -- see its own comment on
        # why that id matters when the row is a FAIL.
        if not r.ok and r.mutation_id:
            lines.append(f"       mutation id: {r.mutation_id}")

    lines.append(f"\n  {verb} {report.ok_count}/{len(report.results)} page(s)")
    if report.dry_run:
        lines.append("  dry run: nothing was sent.")
    # STAGED only holds when something was actually written: a dry run never touched
    # candidate config, a failure means at least one page wasn't staged, and an empty
    # result set (unreachable today, but cheap to guard) staged nothing at all. Do not
    # collapse these guards to `else` -- that would claim success on a lie.
    elif report.results and not report.failed:
        lines.append(f"  {STAGED}")
    return "\n".join(lines) + "\n"
