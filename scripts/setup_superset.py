"""Provision a project-local Python 3.11, install pinned Superset, and verify BI."""
import argparse
import json
import os
import secrets
import subprocess
import sys

from superset_runtime import (CLI, DEFAULT_PYTHON, DEFAULT_STATE, ROOT, SetupError,
                              absolute_path, check_bi_database, check_installed,
                              environment, inspect_python, run_step)

UV_VERSION = '0.9.5'
PYTHON_VERSION = '3.11.14'
LOCK = ROOT / 'bi/requirements-superset.lock'
BUILD_LOCK = ROOT / 'bi/requirements-superset-build.lock'


def ensure_uv(env, log_path):
    tools = ROOT / '.runtime/superset-tools'
    python = tools / 'bin/python'
    uv = tools / 'bin/uv'
    if not python.is_file():
        run_step([sys.executable, '-m', 'venv', tools], 'Создание окружения установщика…', env, log_path)
    current = subprocess.run([str(uv), '--version'], capture_output=True, text=True, env=env) if uv.is_file() else None
    if current is None or current.returncode or current.stdout.split()[:2] != ['uv', UV_VERSION]:
        run_step([python, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-deps', f'uv=={UV_VERSION}'],
                 f'Установка uv {UV_VERSION}…', env, log_path)
    return uv


def provision_python(uv, env, log_path):
    if not DEFAULT_PYTHON.is_file():
        if DEFAULT_PYTHON.parent.parent.exists():
            raise SetupError('Каталог .superset-venv существует, но его Python не работает. '
                             'Переименуйте каталог и повторите установку; данные .runtime/superset сохраните.')
        run_step([uv, 'python', 'install', PYTHON_VERSION, '--no-bin'],
                 f'Загрузка отдельного Python {PYTHON_VERSION} в .runtime/python…', env, log_path)
        run_step([uv, 'venv', '--no-project', '--python', PYTHON_VERSION, DEFAULT_PYTHON.parent.parent],
                 'Создание .superset-venv…', env, log_path)
    inspect_python(DEFAULT_PYTHON)
    return DEFAULT_PYTHON


def create_credentials(state):
    state.mkdir(parents=True, exist_ok=True)
    values = {'secret-key': secrets.token_urlsafe(48),
              'admin.json': json.dumps(dict(username='localadmin', password=secrets.token_urlsafe(24)))}
    for name, content in values.items():
        path = state / name
        try:
            # Exclusive creation preserves credentials and creates new secrets with mode 0600.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(fd, 'w') as out:
            out.write(content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', help='Готовый отдельный venv Python 3.11; по умолчанию создается .superset-venv')
    parser.add_argument('--state-dir', default=str(DEFAULT_STATE), help='Каталог метаданных и учетных данных')
    args = parser.parse_args(argv)
    state = absolute_path(args.state_dir)
    log_path = ROOT / '.runtime/superset-setup.log'
    env = environment(state)
    env.update(UV_PYTHON_INSTALL_DIR=str(ROOT / '.runtime/python'),
               UV_CACHE_DIR=str(ROOT / '.runtime/uv-cache'),
               PIP_CACHE_DIR=str(ROOT / '.runtime/pip-cache'), UV_PYTHON_PREFERENCE='only-managed')
    try:
        active = check_bi_database()
        print(f'Активный расчет BI: {active}', flush=True)
        # Reject an explicit incompatible interpreter before changing anything.
        python = absolute_path(args.python) if args.python else DEFAULT_PYTHON
        if args.python or python.is_file():
            inspect_python(python)
        uv = ensure_uv(env, log_path)
        if not args.python:
            python = provision_python(uv, env, log_path)
        # uv 0.9.5 splits absolute build-constraint paths on spaces; cwd is always ROOT.
        run_step([uv, 'pip', 'sync', '--python', python, '--build-constraints', BUILD_LOCK.relative_to(ROOT), LOCK.relative_to(ROOT)],
                 'Синхронизация закрепленных зависимостей Superset…', env, log_path)
        run_step([uv, 'pip', 'check', '--python', python], 'Проверка совместимости зависимостей…', env, log_path)
        check_installed(python, env)
        create_credentials(state)
        for command in (['db', 'upgrade'], ['init']):
            run_step([python, *CLI, *command], 'Superset: ' + ' '.join(command) + '…', env, log_path)
        run_step([python, ROOT / 'bi/create_dashboard.py'], 'Создание/обновление шести представлений…', env, log_path)
        run_step([python, ROOT / 'bi/verify_dashboard.py'], 'Проверка входа, запросов всех диаграмм и экспорта…', env, log_path)
        (state / 'python-path').write_text(str(python))
        print(f'Superset настроен и проверен. Учетные данные: {state / "admin.json"}')
        print('Запуск: python3 scripts/run_superset.py' + (f' --state-dir "{state}"' if state != DEFAULT_STATE else '')
              + (f' --python "{python}"' if args.python else ''))
    except (SetupError, OSError) as exc:
        print(f'Ошибка: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
