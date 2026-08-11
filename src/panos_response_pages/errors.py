"""The one exception the build raises.

Core modules raise; the CLI decides how to render it. That separation is what
lets the same code back a Typer command and an in-process test without either
one calling sys.exit inside a library function.
"""

from __future__ import annotations


class BuildError(Exception):
    """A condition that must stop the build.

    Every instance corresponds to a documented PAN-OS failure mode: an oversize
    page, an unavailable token, an unresolved placeholder. PAN-OS accepts all of
    them without complaint, so the build is the only thing that can object.
    """


class ImportFailed(Exception):  # noqa: N818 -- "ImportError" is a builtin; this must not shadow it
    """A condition that must stop an import.

    Separate from BuildError because the failures are unrelated: a build fails
    on what a page contains, an import fails on what a management plane says
    back. Sharing one type would make `except` clauses in the CLI lie about
    which half went wrong.
    """
