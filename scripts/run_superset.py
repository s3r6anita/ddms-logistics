"""Run or verify the project-local Superset without activating its environment."""
import argparse
import subprocess
import sys

from superset_runtime import (CLI, DEFAULT_PYTHON, DEFAULT_STATE, ROOT, SetupError,
                              absolute_path, check_bi_database, check_installed, environment)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', help='Python отдельного окружения Superset')
    parser.add_argument('--state-dir', default=str(DEFAULT_STATE))
    parser.add_argument('--port', type=int, default=8089)
    parser.add_argument('--verify', action='store_true', help='Проверить REST-запросы и обновить экспорт без запуска сервера')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('--port должен быть от 1 до 65535')
    state = absolute_path(args.state_dir)
    recorded = state / 'python-path'
    python = absolute_path(args.python or (recorded.read_text().strip() if recorded.is_file() else DEFAULT_PYTHON))
    env = environment(state)
    try:
        check_installed(python, env)
        check_bi_database()
        if not all((state / name).is_file() for name in ('secret-key', 'admin.json', 'metadata.sqlite', 'python-path')):
            raise SetupError('Настройка Superset не завершена. Выполните: python3 scripts/setup_superset.py')
        command = [python, ROOT / 'bi/verify_dashboard.py'] if args.verify else [python, *CLI, 'run', '--host', '127.0.0.1', '--port', str(args.port), '--with-threads']
        if not args.verify:
            print(f'Дашборд: http://127.0.0.1:{args.port}/superset/dashboard/site-dss/', flush=True)
        return subprocess.run([str(part) for part in command], env=env, cwd=ROOT).returncode
    except (SetupError, OSError) as exc:
        print(f'Ошибка: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())
