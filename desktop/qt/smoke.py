"""Teste de inicialização e dos recursos incluídos no aplicativo empacotado."""
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QColorDialog, QFileDialog, QInputDialog, QListView, QMessageBox

from desktop.bridge import ROOT, Session, blank_project, load_project, write_project
from desktop.cad_io import load_cad
from poe_truss.roof_wizard import chord_bracing_planes, chord_bracing_project, roof_alternatives
from .app import DesktopApp
from .roof_wizard import RoofWizard
from .ui_theme import workspace_application


def verify_light_dialogs(window):
    if not QApplication.testAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs):
        raise RuntimeError('As janelas de arquivo e cor ainda seguem o estilo do Windows')

    file_dialog = QFileDialog(window, 'Abrir projeto')
    dialogs = [file_dialog, QColorDialog(window), QInputDialog(window), QMessageBox(window)]
    dialogs[-1].setText('Verificação do tema claro')
    window.open_general_actions()
    dialogs.append(window._load_dialogs[window.actions_tab])
    try:
        for dialog in dialogs:
            dialog.show()
            QApplication.processEvents()
            colors = dialog.palette()
            image = dialog.grab().toImage()
            if (colors.color(QPalette.ColorRole.Base).lightness() < 230
                    or colors.color(QPalette.ColorRole.Text).lightness() > 110
                    or image.isNull() or image.pixelColor(5, 5).lightness() < 200):
                raise RuntimeError(f'Fundo ou texto fora do tema claro em {type(dialog).__name__}')
            if dialog is file_dialog and dialog.findChild(QListView) is None:
                raise RuntimeError('A janela de arquivos deve usar os controles do aplicativo')
            dialog.hide()
    finally:
        for dialog in dialogs:
            dialog.close()


def run():
    app = workspace_application([])
    window = DesktopApp()
    try:
        window.show()
        app.processEvents()
        verify_light_dialogs(window)
        window.session.calculate()
        window.refresh()
        window.open_3d()
        app.processEvents()
        dialog = window._view3d
        if not dialog.isVisible() or not dialog.axial() or not dialog.mesh_layer.faces:
            raise RuntimeError('A inspeção 3D não apresentou o projeto calculado')

        profile = 'HP 200 x 53,0 (H)'
        window.assign_section('superior', profile, 1)
        if not any(mesh.profile == profile for mesh in dialog._meshes) or dialog.axial():
            raise RuntimeError('A vista 3D não acompanhou a troca de perfil')

        dxf = ROOT / 'examples' / 'trelica_triangular_analitica_dxf_mm.dxf'
        preview = load_cad(dxf)
        if len(preview.nodes) != 3 or len(preview.members) != 3:
            raise RuntimeError('O DXF triangular não gerou três nós e três barras')

        example = load_project(ROOT / 'examples' / 'manual_pratt_16m.json')
        wizard = RoofWizard(window, example, window.session.catalog)
        roof = wizard.roof()
        alternatives = roof_alternatives(roof, window.session.catalog, height_min=1.1, height_max=1.1, ratio=250)
        candidate = alternatives['candidates'][0]
        if not candidate['purlin_ok']:
            raise RuntimeError('O assistente portátil não encontrou a modulação de referência')
        roof['geometry'].update(panels=candidate['panels'], height_m=candidate['height_m'])
        plans = chord_bracing_planes(roof, window.session.catalog)
        if len(plans) != 4:
            raise RuntimeError('O assistente portátil não gerou os quatro planos')
        plane = chord_bracing_project(roof, 'BS-E', plans['BS-E'], {
            'bays': 2, 'area_mm2': 1000., 'diameter_mm': 12.5, 'force_kn': 1.,
            'reference': 'Teste do pacote portátil',
        })
        result = Session(plane, window.session.catalog).calculate()
        if max(result['analyses']['H_POS']['axial_n'].values()) <= 0:
            raise RuntimeError('O assistente portátil não calculou o plano de travamento')
        wizard.close()

        with TemporaryDirectory() as directory:
            path = Path(directory) / 'projeto.json'
            write_project(path, window.session.project)
            if load_project(path) != window.session.project:
                raise RuntimeError('O projeto salvo diverge do projeto em memória')

        window._dirty = False
        window._replace_project(Session(blank_project(), window.session.catalog))
        if window.session.model.nodes or dialog.session is not window.session or dialog.axial() or window.session.result is not None:
            raise RuntimeError('O novo projeto conservou o visualizador ou a análise anterior')
    finally:
        window._dirty = False
        window.close()
