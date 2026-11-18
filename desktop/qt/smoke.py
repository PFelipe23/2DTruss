"""Teste de inicialização e dos recursos incluídos no aplicativo empacotado."""
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication

from desktop.bridge import ROOT, load_project, write_project
from desktop.cad_io import load_cad
from .app import DesktopApp


def run():
    app = QApplication([])
    window = DesktopApp()
    try:
        window.show()
        app.processEvents()
        window.session.calculate()
        window.refresh()
        window.open_3d()
        app.processEvents()
        dialog = window._view3d
        if not dialog.isVisible() or not dialog.axial() or not dialog.view.scene().items():
            raise RuntimeError('A inspeção 3D não apresentou o projeto calculado')

        dxf = ROOT / 'examples' / 'trelica_triangular_analitica_dxf_mm.dxf'
        preview = load_cad(dxf)
        if len(preview.nodes) != 3 or len(preview.members) != 3:
            raise RuntimeError('O DXF triangular não gerou três nós e três barras')

        with TemporaryDirectory() as directory:
            path = Path(directory) / 'projeto.json'
            write_project(path, window.session.project)
            if load_project(path) != window.session.project:
                raise RuntimeError('O projeto salvo diverge do projeto em memória')

        window.new()
        if window._view3d is not None or window.session.result is not None:
            raise RuntimeError('O novo projeto conservou o visualizador ou a análise anterior')
    finally:
        if window._view3d is not None:
            window._view3d.close()
        window.close()
