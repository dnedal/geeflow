"""Service-account key loading from GEEFLOW_SA_KEY (ee is mocked by conftest)."""

import json

import pytest

from geeflow import session


def _fake_key(path, kind="service_account"):
    path.write_text(json.dumps({"type": kind, "project_id": "proj-from-key",
                                "client_email": "sa@proj.iam.gserviceaccount.com"}))
    return path


def test_env_key_used_with_earthengine_scope_only(monkeypatch, tmp_path):
    key = _fake_key(tmp_path / "k.json")
    monkeypatch.setenv("GEEFLOW_SA_KEY", str(key))
    seen = {}

    def fake_from_info(info, scopes):
        seen["scopes"] = scopes
        return "CREDS"

    from google.oauth2 import service_account
    monkeypatch.setattr(service_account.Credentials, "from_service_account_info",
                        staticmethod(fake_from_info))
    session.ee.Initialize.reset_mock()
    session.init_ee()
    assert seen["scopes"] == ["https://www.googleapis.com/auth/earthengine"]
    session.ee.Initialize.assert_called_once_with("CREDS", project="proj-from-key")


def test_missing_key_raises_not_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("GEEFLOW_SA_KEY", str(tmp_path / "nope.json"))
    session.ee.Initialize.reset_mock()
    with pytest.raises(FileNotFoundError):
        session.init_ee("p")
    session.ee.Initialize.assert_not_called()


def test_non_service_account_json_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("GEEFLOW_SA_KEY", str(_fake_key(tmp_path / "k.json", "authorized_user")))
    with pytest.raises(ValueError):
        session.init_ee("p")


def test_no_env_uses_user_creds(monkeypatch):
    monkeypatch.delenv("GEEFLOW_SA_KEY", raising=False)
    session.ee.Initialize.reset_mock()
    session.init_ee("p")
    session.ee.Initialize.assert_called_once_with(project="p")
