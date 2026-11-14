"""Compatibilidade: executar o smoke ESM consolidado da versão v0.1."""
from pathlib import Path
import runpy
if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('browser_ui_v09_inmemory.py')),run_name='__main__')
