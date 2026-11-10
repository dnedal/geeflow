"""Safety guards for the MCP server (hardened fork).

The MCP server acts on instructions from an AI model, which can be steered by text it
reads (dataset descriptions, files, web pages). These guards keep tool calls inside
boundaries the *user* sets through environment variables in the MCP server config —
never through tool arguments, so the model cannot widen them.

Environment variables
---------------------
GEEFLOW_WORKSPACE
    One or more directories (separated by os.pathsep, i.e. ":" on Linux/macOS) that
    tools may read from and write to. Unset = every path-taking tool argument is refused.
GEEFLOW_ALLOW_EXEC
    Set to "1" to register the `execute_code` tool. Anything else = not registered.
"""

from __future__ import annotations

import os
from pathlib import Path

WORKSPACE_ENV = "GEEFLOW_WORKSPACE"
ALLOW_EXEC_ENV = "GEEFLOW_ALLOW_EXEC"


class PathNotAllowed(PermissionError):
    """A tool argument pointed outside the configured workspace."""


def exec_allowed() -> bool:
    return os.environ.get(ALLOW_EXEC_ENV, "") == "1"


def workspace_roots() -> list[Path]:
    raw = os.environ.get(WORKSPACE_ENV, "")
    roots = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if part:
            roots.append(Path(part).expanduser().resolve())
    return roots


def confine(path: str | Path, *, for_write: bool = False) -> Path:
    """Resolve `path` (following symlinks) and require it to sit inside the workspace.

    Relative paths resolve against the first workspace root, not the server's cwd.
    For writes, the target must not already exist (no silent overwrites).
    """
    roots = workspace_roots()
    if not roots:
        raise PathNotAllowed(
            f"file access is disabled: set {WORKSPACE_ENV} in the MCP server config to "
            "the directory (or directories) geeflow may read and write"
        )
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = roots[0] / p
    resolved = p.resolve()  # follows symlinks, collapses '..'
    if not any(resolved == r or resolved.is_relative_to(r) for r in roots):
        raise PathNotAllowed(
            f"{path!s} resolves to {resolved}, outside {WORKSPACE_ENV} "
            f"({', '.join(map(str, roots))})"
        )
    if for_write and resolved.exists():
        raise FileExistsError(f"refusing to overwrite existing file {resolved}")
    return resolved
