"""Entrada do aplicativo desktop 2DTruss."""
import sys
from os import environ
from pathlib import Path
from traceback import format_exc


def main():
    if sys.argv[1:] == ['--smoke-test']:
        try:
            from desktop.qt.smoke import run
            run()
        except Exception:
            error = format_exc()
            report = environ.get('TRUSS_SMOKE_REPORT')
            if report:
                Path(report).write_text(error, encoding='utf-8')
            if sys.stderr is not None:
                sys.stderr.write(error)
            return 1
        return 0

    from desktop.qt.app import start
    return start()


if __name__ == '__main__':
    raise SystemExit(main())
