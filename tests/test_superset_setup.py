"""Regression checks for installation failures; no network or Superset needed."""
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def scripts(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import superset_runtime
    return superset_runtime, load_script('setup_superset'), load_script('run_superset')


def test_absent_python_is_actionable(scripts, tmp_path):
    runtime, _, _ = scripts
    with pytest.raises(runtime.SetupError, match='python3 scripts/setup_superset.py'):
        runtime.inspect_python(tmp_path / 'missing/bin/python')


def test_rejects_incompatible_python_before_install(scripts, monkeypatch):
    runtime, setup, _ = scripts
    monkeypatch.setattr(setup, 'check_bi_database', lambda: 'run')
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, json.dumps([[3, 15, 1], True]), ''))
    monkeypatch.setattr(setup, 'ensure_uv', lambda *a: pytest.fail('Must reject Python 3.15 before installing'))
    assert setup.main(['--python', sys.executable]) == 1


def test_absent_bi_does_not_create_database(scripts, tmp_path):
    runtime, _, _ = scripts
    path = tmp_path / 'bi.sqlite'
    with pytest.raises(runtime.SetupError, match='site_dss.cli'):
        runtime.check_bi_database(path)
    assert not path.exists()


def test_empty_bi_is_actionable(scripts, tmp_path):
    runtime, _, _ = scripts
    path = tmp_path / 'bi.sqlite'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE selected_run (singleton INTEGER, run_id TEXT)')
    with pytest.raises(runtime.SetupError, match='site_dss.cli'):
        runtime.check_bi_database(path)


def test_credentials_are_private_and_preserved(scripts, tmp_path):
    _, setup, _ = scripts
    state = tmp_path / 'state with spaces'
    setup.create_credentials(state)
    before = {p.name: p.read_bytes() for p in state.iterdir()}
    setup.create_credentials(state)
    assert before == {p.name: p.read_bytes() for p in state.iterdir()}
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in state.iterdir())


def test_venv_path_does_not_resolve_to_base_interpreter(scripts, tmp_path):
    runtime, _, _ = scripts
    path = tmp_path / 'venv python'
    path.symlink_to(sys.executable)
    assert runtime.absolute_path(path) == path
    assert runtime.absolute_path(path) != path.resolve()


def test_runner_uses_recorded_venv_and_loopback(scripts, tmp_path, monkeypatch):
    _, _, runner = scripts
    state = tmp_path / 'state'
    state.mkdir()
    python = tmp_path / 'venv with spaces/bin/python'
    for name in ('secret-key', 'admin.json', 'metadata.sqlite'):
        (state / name).touch()
    (state / 'python-path').write_text(str(python))
    monkeypatch.setattr(runner, 'check_installed', lambda p, env: None)
    monkeypatch.setattr(runner, 'check_bi_database', lambda: 'run')
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(runner.subprocess, 'run', run)
    assert runner.main(['--state-dir', str(state), '--port', '8090']) == 0
    command, kwargs = calls[0]
    assert command[0] == str(python)
    assert command[command.index('--host') + 1] == '127.0.0.1'
    assert command[command.index('--port') + 1] == '8090'
    assert kwargs['env']['SUPERSET_HOME'] == str(state)


def test_uv_version_including_build_id_is_reused(scripts, tmp_path, monkeypatch):
    _, setup, _ = scripts
    tools = tmp_path / '.runtime/superset-tools/bin'
    tools.mkdir(parents=True)
    (tools / 'python').touch()
    (tools / 'uv').touch()
    monkeypatch.setattr(setup, 'ROOT', tmp_path)
    monkeypatch.setattr(setup.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, 'uv 0.9.5 (d5f39331a 2025-10-21)\n', ''))
    monkeypatch.setattr(setup, 'run_step', lambda *a: pytest.fail('No reinstall required'))
    assert setup.ensure_uv({}, tmp_path / 'setup.log') == tools / 'uv'
