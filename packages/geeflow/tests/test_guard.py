"""Hardened-fork guards: exec gating and workspace path confinement."""

import asyncio
import importlib
import os

import pytest

from geeflow.mcp import _guard
from geeflow.mcp._guard import PathNotAllowed, confine


def _tool_names(server):
    return {t.name for t in asyncio.run(server.mcp.list_tools())}


def _reload_server(monkeypatch, allow_exec: str | None):
    if allow_exec is None:
        monkeypatch.delenv("GEEFLOW_ALLOW_EXEC", raising=False)
    else:
        monkeypatch.setenv("GEEFLOW_ALLOW_EXEC", allow_exec)
    import geeflow.mcp.server as server

    return importlib.reload(server)


def test_execute_code_absent_by_default(monkeypatch):
    server = _reload_server(monkeypatch, None)
    assert "execute_code" not in _tool_names(server)


@pytest.mark.parametrize("value", ["0", "true", "yes", " 1", ""])
def test_execute_code_needs_exactly_1(monkeypatch, value):
    server = _reload_server(monkeypatch, value)
    assert "execute_code" not in _tool_names(server)


def test_execute_code_registered_when_enabled(monkeypatch):
    server = _reload_server(monkeypatch, "1")
    assert "execute_code" in _tool_names(server)
    _reload_server(monkeypatch, None)  # leave module in default state


def test_gee_init_takes_no_key_path(monkeypatch):
    server = _reload_server(monkeypatch, None)
    tool = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "gee_init")
    assert "service_account_key" not in tool.inputSchema.get("properties", {})


def test_no_workspace_refuses_everything(monkeypatch, tmp_path):
    monkeypatch.delenv("GEEFLOW_WORKSPACE", raising=False)
    with pytest.raises(PathNotAllowed):
        confine(tmp_path / "x.json")


def test_inside_workspace_ok(monkeypatch, tmp_path):
    monkeypatch.setenv("GEEFLOW_WORKSPACE", str(tmp_path))
    assert confine("sub/x.json", for_write=True) == tmp_path / "sub" / "x.json"
    assert confine(tmp_path / "x.json") == tmp_path / "x.json"


@pytest.mark.parametrize("bad", ["../escape.json", "/etc/passwd", "~/.ssh/id_rsa", "a/../../b"])
def test_escapes_refused(monkeypatch, tmp_path, bad):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("GEEFLOW_WORKSPACE", str(ws))
    with pytest.raises(PathNotAllowed):
        confine(bad)


def test_prefix_sibling_refused(monkeypatch, tmp_path):
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws-evil").mkdir()
    monkeypatch.setenv("GEEFLOW_WORKSPACE", str(tmp_path / "ws"))
    with pytest.raises(PathNotAllowed):
        confine(tmp_path / "ws-evil" / "x")


def test_symlink_out_refused(monkeypatch, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "link").symlink_to(tmp_path)
    monkeypatch.setenv("GEEFLOW_WORKSPACE", str(ws))
    with pytest.raises(PathNotAllowed):
        confine("link/outside.txt")


def test_no_overwrite(monkeypatch, tmp_path):
    monkeypatch.setenv("GEEFLOW_WORKSPACE", str(tmp_path))
    (tmp_path / "exists.json").write_text("{}")
    with pytest.raises(FileExistsError):
        confine("exists.json", for_write=True)


def test_multiple_roots(monkeypatch, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("GEEFLOW_WORKSPACE", os.pathsep.join([str(a), str(b)]))
    assert confine(b / "f") == b / "f"
    assert _guard.workspace_roots() == [a, b]


def test_sample_polygons_refuses_outside_before_any_ee_call(monkeypatch, tmp_path):
    server = _reload_server(monkeypatch, None)
    monkeypatch.setenv("GEEFLOW_WORKSPACE", str(tmp_path))
    with pytest.raises(PathNotAllowed):
        server.sample_polygons(class_values=[10], lat=0, lon=0, save_path="/tmp/../etc/x.json")


def _lulc_ws(monkeypatch, tmp_path, extra: str = ""):
    pytest.importorskip("lulc_engine")
    import shutil
    from pathlib import Path

    src = Path(__file__).resolve().parents[3] / "examples" / "forest_monitoring" / "lulc.yaml"
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = ws / "lulc.yaml"
    shutil.copy(src, cfg)
    if extra:
        cfg.write_text(cfg.read_text() + "\n" + extra + "\n")
    monkeypatch.setenv("GEEFLOW_WORKSPACE", str(ws))
    return _reload_server(monkeypatch, None), cfg


def test_lulc_config_inside_workspace_ok(monkeypatch, tmp_path):
    server, cfg = _lulc_ws(monkeypatch, tmp_path)
    assert server.lulc_validate(str(cfg))["project"]


def test_lulc_config_outside_workspace_refused(monkeypatch, tmp_path):
    server, cfg = _lulc_ws(monkeypatch, tmp_path)
    monkeypatch.setenv("GEEFLOW_WORKSPACE", str(tmp_path / "elsewhere"))
    with pytest.raises(PathNotAllowed):
        server.lulc_validate(str(cfg))


def test_lulc_output_dir_escape_refused(monkeypatch, tmp_path):
    server, cfg = _lulc_ws(monkeypatch, tmp_path, "output_dir: ../../escaped")
    with pytest.raises(PathNotAllowed):
        server.lulc_validate(str(cfg))
