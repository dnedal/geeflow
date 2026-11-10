"""Earth Engine session setup (interactive user auth or service account)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import ee

#: Path to a service-account JSON key. Set by the user in the MCP server environment —
#: never accepted as a tool argument, so the model cannot point it at another file.
SA_KEY_ENV = "GEEFLOW_SA_KEY"

#: Service-account sessions request only the Earth Engine scope (no Drive, no general
#: cloud-platform). What the account can actually do is further bounded by its IAM roles.
SA_SCOPES = ["https://www.googleapis.com/auth/earthengine"]


def _service_account_credentials(key_path: Path):
    from google.oauth2 import service_account

    if not key_path.is_file():
        raise FileNotFoundError(f"service-account key not found: {key_path}")
    with open(key_path, encoding="utf-8") as f:
        info = json.load(f)
    if info.get("type") != "service_account":
        raise ValueError(f"{key_path} is not a service-account key")
    creds = service_account.Credentials.from_service_account_info(info, scopes=SA_SCOPES)
    return creds, info.get("project_id")


def init_ee(project_id: str | None = None, service_account_key: str | Path | None = None) -> None:
    """Initialize Earth Engine.

    Credential source, in order:
      1. `service_account_key` argument (Python/CLI use only; the MCP tool doesn't expose it)
      2. the GEEFLOW_SA_KEY environment variable
      3. cached user credentials from `earthengine authenticate`

    If a service-account key is configured but unusable, this raises instead of silently
    falling back to (broader) user credentials. With a key, `project_id` defaults to the
    key's own project.
    """
    key = service_account_key or os.environ.get(SA_KEY_ENV) or None
    if key is not None:
        creds, key_project = _service_account_credentials(Path(key).expanduser())
        ee.Initialize(creds, project=project_id or key_project)
    else:
        ee.Initialize(project=project_id)


def authenticate() -> None:
    """Run the interactive Earth Engine authentication flow."""
    ee.Authenticate()
