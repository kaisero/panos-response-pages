"""Task runner. Also the CI script -- workflows call these sessions, nothing else.

Keeping one definition of "lint" means a green local run and a green CI run mean
the same thing.
"""

from __future__ import annotations

import os

import nox

nox.options.default_venv_backend = "uv"
nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = ["lint", "type_check", "tests", "docs"]

PYTHON_VERSIONS = ["3.11", "3.12", "3.13", "3.14"]


def _sync(session: nox.Session, *groups: str) -> None:
    """Install only the groups a session needs.

    --frozen under CI so a workflow can never silently re-resolve the lockfile and
    test a dependency set nobody reviewed.
    """
    args = ["uv", "sync", "--no-default-groups"]
    if os.environ.get("CI"):
        args.append("--frozen")
    for group in groups:
        args += ["--group", group]
    session.run_install(*args, env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location})


@nox.session
def lint(session: nox.Session) -> None:
    _sync(session, "lint")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")
    session.run("codespell")


@nox.session
def type_check(session: nox.Session) -> None:
    _sync(session, "typecheck")
    session.run("mypy")


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    _sync(session, "test")
    session.run("pytest", "--cov", "--cov-report=term-missing", *session.posargs)


@nox.session
def audit(session: nox.Session) -> None:
    _sync(session, "audit")
    session.run("pip-audit")


@nox.session
def docs(session: nox.Session) -> None:
    _sync(session, "docs")
    session.run("mkdocs", "build", "--strict")


@nox.session(name="docs-serve")
def docs_serve(session: nox.Session) -> None:
    _sync(session, "docs")
    session.run("mkdocs", "serve")


@nox.session(venv_backend="none")
def gate(session: nox.Session) -> None:
    """Fast offline check against the already-synced env -- no venv work."""
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")
    session.run("mypy")
    session.run("pytest", "-q")
