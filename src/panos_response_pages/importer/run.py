"""Running one import against one backend.

This is the orchestration every `import <backend>` command shares: build the
dry-run report, or connect, upload every page, close, and hand back an
`ImportReport` either way. It lived inline in `cli.import_scm` until a second
backend was in sight; keeping it there would have meant the next backend
copying the dry-run branch, the per-page loop and the close-on-every-path
handling, and one of those copies eventually drifting.

The dry-run branch is the part that matters most. It constructs no `Target` and
makes no call -- `Backend.describe` and `Backend.scope_for` are pure, and this
function is where that promise is kept -- while reporting the exact scope a real
run would write to.
"""

from __future__ import annotations

from collections.abc import Sequence

from panos_response_pages import logs
from panos_response_pages.importer.backend import Backend, C, Target
from panos_response_pages.importer.report import ImportReport, PageResult
from panos_response_pages.importer.source import ImportItem


def run_import(
    backend: Backend[C],
    config: C,
    items: Sequence[ImportItem],
    *,
    dry_run: bool = False,
    json_logs: bool = False,
) -> ImportReport:
    """Import every item, or describe what importing them would do.

    `json_logs` says the caller will not print a human report -- `--log-json`
    promises exactly one machine-readable stream -- so a failed page is
    escalated to a log event here instead. In text mode the report is that
    channel, and logging the failure as well would print it twice.

    Raises `ImportFailed` only from `connect` and `describe`; a page that fails
    to upload comes back as a failed `PageResult`, and the target is closed
    whichever way it ends.
    """
    log = logs.get()

    if dry_run:
        report = ImportReport(
            target=backend.name,
            describe=backend.describe(config),
            results=[
                PageResult(
                    page=i.spec.remote,
                    folder=backend.scope_for(config, i),
                    ok=True,
                    size=len(i.payload),
                )
                for i in items
            ],
            dry_run=True,
        )
        # Every dry run item is ok=True by construction, so there is nothing to
        # escalate to warning/error -- the debug line is the JSON-mode record.
        for r in report.results:
            log.debug("%s -> %s: dry_run size=%d", r.page, r.folder, r.size)
        return report

    # The try starts at connect(), not after describe(): describe() may make a
    # network request (SCM's resolves the tenant's API host), so a bad
    # credential or an unreachable tenant must close the target too, not just a
    # failure during upload. Closing here rather than leaving it to process exit
    # keeps the guarantee with the code that opened the connection.
    target: Target | None = None
    try:
        target = backend.connect(config)
        report = ImportReport(target=target.name, describe=target.describe())
        for item in items:
            result = target.upload(item)
            log.debug("%s -> %s: ok=%s %s", item.spec.remote, result.folder, result.ok, result.detail)
            if json_logs and not result.ok:
                log.error(
                    "%s -> %s: %s",
                    result.page,
                    result.folder,
                    result.detail,
                    extra={"mutation_id": result.mutation_id} if result.mutation_id else {},
                )
            report.results.append(result)
    finally:
        if target is not None:
            target.close()
    return report
