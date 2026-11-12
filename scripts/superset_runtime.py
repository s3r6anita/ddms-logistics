"""Standard-library helpers shared by the local Superset entry points."""
import json
import os
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYTHON = ROOT / '.superset-venv/bin/python'
DEFAULT_STATE = ROOT / '.runtime/superset'
SUPERSET_VERSION = '4.1.4'
CLI = ['-c', 'from superset.cli.main import superset; superset()']
BI_COMMAND = '.venv312/bin/python -m site_dss.cli --mvp --allow-demo --request config/reduced_demand.json'


class SetupError(RuntimeError):
    """An actionable installation or prerequisite error."""


def absolute_path(value):
    # Do not resolve symlinks: a venv's python must stay inside the venv.
    path = Path(value).expanduser()
    return path.absolute() if path.is_absolute() else (ROOT / path).absolute()


def environment(state):
    env = dict(os.environ)
    # A caller's Python search path must not mix the two project environments.
    for name in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'FLASK_DEBUG'):
        env.pop(name, None)
    env.update(SUPERSET_CONFIG_PATH=str(ROOT / 'bi/superset_config.py'),
               SUPERSET_HOME=str(state), FLASK_APP='superset', PYTHONNOUSERSITE='1')
    return env


def inspect_python(python):
    if not python.is_file():
        raise SetupError(f'Не найден Python: {python}. Выполните: python3 scripts/setup_superset.py')
    try:
        result = subprocess.run([str(python), '-I', '-c',
                                 'import json,sys; print(json.dumps([list(sys.version_info[:3]), sys.prefix != sys.base_prefix]))'],
                                check=True, capture_output=True, text=True)
        version, is_venv = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise SetupError(f'Не удается запустить {python}. Пересоздайте отдельное окружение Superset.') from exc
    if version[:2] != [3, 11] or not is_venv:
        raise SetupError(f'Нужен отдельный venv Python 3.11; получен {version}, venv={is_venv}: {python}. '
                         'Для автоматической установки используйте python3 scripts/setup_superset.py без --python. '
                         'Если .superset-venv уже создан с другой версией, переименуйте его и повторите установку.')
    return version


def check_bi_database(path=None):
    path = path or ROOT / 'data/processed/bi.sqlite'
    error = f'Нет готовой BI-базы с активным расчетом. Сначала выполните: {BI_COMMAND}'
    if not path.is_file():
        raise SetupError(error)
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
            selected = conn.execute('SELECT run_id FROM selected_run WHERE singleton=1').fetchone()
            if not selected:
                raise SetupError(error)
            for name in ('run_sites', 'scenario_metrics', 'forecast_points', 'forecast_quality', 'rule_trace'):
                conn.execute(f'SELECT run_id FROM active_{name} LIMIT 1')
            if not conn.execute('SELECT 1 FROM active_run_sites LIMIT 1').fetchone():
                raise SetupError(error)
    except sqlite3.Error as exc:
        raise SetupError(error + f' Ошибка SQLite: {exc}') from exc
    return selected[0]


def check_installed(python, env):
    inspect_python(python)
    result = subprocess.run([str(python), '-c',
                             'from importlib.metadata import version; print(version("apache-superset"))'],
                            env=env, cwd=ROOT, capture_output=True, text=True)
    if result.returncode or result.stdout.strip() != SUPERSET_VERSION:
        raise SetupError(f'Не установлен Apache Superset {SUPERSET_VERSION} в {python}. '
                         'Выполните: python3 scripts/setup_superset.py')


def run_step(command, label, env, log_path):
    print(label, flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a') as log:
        log.write('\n' + label + '\n')
        log.flush()
        try:
            result = subprocess.run([str(part) for part in command], env=env, cwd=ROOT,
                                    stdout=log, stderr=subprocess.STDOUT)
        except OSError as exc:
            raise SetupError(f'{label}: {exc}. Журнал: {log_path}') from exc
    if result.returncode:
        tail = '\n'.join(log_path.read_text(errors='replace').splitlines()[-16:])
        raise SetupError(f'{label}: код {result.returncode}.\n{tail}\nПолный журнал: {log_path}')
