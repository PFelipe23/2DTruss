"""2DTruss v0.1 — desktop PySide6 com barra de ferramentas e QGraphicsScene.

A lógica estrutural é delegada a desktop.bridge.Session / poe_truss.
Nenhum navegador, servidor HTTP ou webview integra o processo desktop.
"""
from __future__ import annotations
from copy import deepcopy
from math import fsum, hypot
from pathlib import Path
import sys

from PySide6.QtCore import QPoint,QSettings,Qt,QSignalBlocker,QTimer
from PySide6.QtGui import QAction,QKeySequence,QColor,QPen
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QLabel,QToolButton,QComboBox,QDoubleSpinBox,QSpinBox,QCheckBox,QSplitter,
    QTreeWidget,QTreeWidgetItem,QTabWidget,QFormLayout,QGroupBox,QLineEdit,QFileDialog,
    QMessageBox,QInputDialog,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,
    QDialog,QDialogButtonBox,QGraphicsView,QGraphicsScene,QFrame,QSizePolicy,
    QButtonGroup,QScrollArea,QStackedWidget,QTabBar,QMenu,QWidgetAction)

from desktop.bridge import Session,load_project,write_project
from desktop import editing,cad_io,workflow
from poe_truss.export import as_csv,dimperfil_rows,integrated_report_html,ftool_comparison_full_rows
from poe_truss.loads import load_patterns
from poe_truss.model import GROUPS
from poe_truss.units import FORCE_TO_N
from poe_truss.version import APP_NAME, TAG
from .action_icons import action_icon, IconButton as _button
from .display_units import DisplayUnits, LOCALE, LoadField, UnitsDialog, format_number
from .viewport import COMP, DEFORMED, TENS, TrussView
from .workflow_panels import WorkflowMixin
from .view3d import Truss3DView
from .ui_theme import STYLE,workspace_palette

APP_TITLE=f'{APP_NAME} {TAG}'
STYLESHEET=STYLE


def _spin(value,minimum,maximum,decimals=2,step=1):
    e=QDoubleSpinBox();e.setRange(minimum,maximum);e.setDecimals(decimals);e.setSingleStep(step);e.setValue(value)
    e.setMinimumWidth(135)
    return e


class CadDialog(QDialog):
    """Conferência obrigatória: unidades, layers e malha importada."""
    def __init__(self,preview:cad_io.CadPreview,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Conferência da importação CAD — confirmar topologia')
        self.resize(920,650);self.preview=preview
        layout=QVBoxLayout(self)
        title=QLabel(f'<b>{preview.source}</b> — {len(preview.nodes)} nós · {len(preview.members)} barras · {preview.units_source}')
        layout.addWidget(title)
        self.scene=QGraphicsScene(self);view=QGraphicsView(self.scene)
        coords={n['id']:(n['x_mm'],-n['y_mm']) for n in preview.nodes}
        for m in preview.members:
            ax,ay=coords[m['i']];bx,by=coords[m['j']]
            item=self.scene.addLine(ax,ay,bx,by)
            item.setPen(QPen(QColor('#2674A5'),2))
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-200,-200,200,200))
        layout.addWidget(view,3)
        QTimer.singleShot(0,lambda:view.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio))
        layout.addWidget(QLabel('Mapeamento de layers para grupos de barras (confira todos):'))
        self.layers=QTableWidget(len(preview.layers),3)
        self.layers.setHorizontalHeaderLabels(['Layer CAD','Barras','Grupo estrutural'])
        self.layers.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.layers.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.layers.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        self.selectors={}
        for i,(layer,count) in enumerate(sorted(preview.layers.items())):
            self.layers.setItem(i,0,QTableWidgetItem(layer));self.layers.setItem(i,1,QTableWidgetItem(str(count)))
            cb=QComboBox();cb.addItems(['superior','inferior','montante','diagonal'])
            cb.setCurrentText(next((m['group'] for m in preview.members if m['layer']==layer),'diagonal'))
            self.layers.setCellWidget(i,2,cb);self.selectors[layer]=cb
        layout.addWidget(self.layers,2)
        for warning in preview.warnings:
            lab=QLabel('ATENÇÃO: '+warning);lab.setStyleSheet('color:#946018;');lab.setWordWrap(True);layout.addWidget(lab)
        layout.addWidget(QLabel('<b>Apoios, cargas e combinações anteriores serão redefinidos.</b> '
                                'A análise ficará bloqueada até configurar vínculos e ações.'))
        if preview.ignored:
            ignored='; '.join(f'{k}: {v}' for k,v in sorted(preview.ignored.items()))
            ignored_label=QLabel('Elementos ignorados: '+ignored)
            ignored_label.setWordWrap(True);layout.addWidget(ignored_label)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Importar eixos, confirmar')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def mapping(self):return {layer:cb.currentText() for layer,cb in self.selectors.items()}


class DesktopApp(WorkflowMixin,QMainWindow):
    def __init__(self,session:Session|None=None, *, settings=None):
        super().__init__()
        self.session=session or Session()
        self.filepath:Path|None=None
        self.undo_stack=[];self.redo_stack=[]
        self._refreshing=False;self._dirty=False
        self._selected=[];self.case_id=None
        self._view3d=None
        self._settings = settings
        self.units = DisplayUnits() if settings is None else DisplayUnits.load(settings)
        self._cursor_xy = None
        self._node_display_values = (0., 0.)
        self._load_dialogs = {}
        self.setWindowTitle(APP_TITLE)
        self.resize(1320, 700)
        self.setMinimumSize(1000, 560)
        self.setPalette(workspace_palette())
        self.setStyleSheet(STYLESHEET)
        self._build()
        self.refresh(fit=True)
        self._shortcuts()


    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        self.tool_buttons = QButtonGroup(self)
        self._cad_buttons = {}
        self._overlay_buttons = {}
        self._drawing_only = False
        self._inspector_collapsed = False

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)
        main.addWidget(self.splitter, 1)

        self.navigator = QTabWidget()
        self.navigator.setObjectName('navigator')
        self.navigator.setDocumentMode(True)
        self.navigator.setMinimumWidth(182)
        self.property_summary = QTreeWidget()
        self.property_summary.setColumnCount(2)
        self.property_summary.setHeaderLabels(['Propriedade', 'Valor'])
        self.property_summary.setIndentation(12)
        self.property_summary.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.property_summary.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.property_summary.setAlternatingRowColors(True)
        self.property_summary.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.navigator.addTab(self.property_summary, 'Propriedades')
        model = QWidget()
        model_layout = QVBoxLayout(model)
        model_layout.setContentsMargins(9, 10, 9, 9)
        self.model_filter = QLineEdit()
        self.model_filter.setPlaceholderText('Filtrar por ID ou grupo')
        self.model_filter.setAccessibleName('Filtrar nós e barras')
        self.model_filter.setClearButtonEnabled(True)
        self.model_filter.textChanged.connect(self.filter_model_tree)
        model_layout.addWidget(self.model_filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self.on_tree_select)
        model_layout.addWidget(self.tree, 1)
        self.navigator.addTab(model, 'Modelo')
        self.task_tree = QTreeWidget()
        self.task_tree.setHeaderHidden(True)
        self.task_tree.itemClicked.connect(self.task_clicked)
        self.navigator.addTab(self.task_tree, 'Tarefas')
        self.splitter.addWidget(self.navigator)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        self.view = TrussView()
        self.view.units = self.units
        bar = QFrame()
        bar.setObjectName('viewportBar')
        strip = QHBoxLayout(bar)
        strip.setContentsMargins(8, 4, 8, 4)
        strip.setSpacing(4)
        self.mode_3d = _button('Alternar entre 2D e 3D', self.set_3d_visible, 'cube', checkable=True)
        strip.addWidget(self.mode_3d)
        self.view_mode_label = QLabel('2D')
        self.view_mode_label.setObjectName('viewMode')
        strip.addWidget(self.view_mode_label)
        strip.addStretch()
        self.cases = QComboBox()
        self.cases.setAccessibleName('Tipo, caso ou combinação exibida')
        self.cases.setMinimumContentsLength(8)
        self.cases.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cases.currentTextChanged.connect(self.on_case)
        strip.addWidget(QLabel('Carregamento'))
        strip.addWidget(self.cases)
        self.forces_button = _button('Cargas', lambda visible: self._set_overlay('show_forces', visible),
                                     'load_view', checkable=True, light=True)
        self.results_button = _button('Resultados', self._set_results_visible, 'table', checkable=True)
        self.inspector_toggle = _button('Recolher ou expandir o painel direito',
                                        self._set_inspector_collapsed, 'panel', checkable=True)
        strip.addWidget(self.inspector_toggle)
        center_layout.addWidget(bar)
        self.force_bar = QFrame()
        self.force_bar.setObjectName('forceBar')
        force_layout = QHBoxLayout(self.force_bar)
        force_layout.setContentsMargins(9, 3, 8, 3)
        self.force_summary = QLabel()
        self.force_summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        force_layout.addWidget(self.force_summary, 1)
        self.force_values = _button('Valores', self.view.set_load_values, 'ids', checkable=True)
        self.force_values.setToolTip('Exibir a magnitude das resultantes nodais')
        force_layout.addWidget(self.force_values)
        self.force_bar.hide()
        self.view.forces_displayed.connect(self._show_force_summary)
        center_layout.addWidget(self.force_bar)

        self.center_split = QSplitter(Qt.Orientation.Vertical)
        self.center_split.setChildrenCollapsible(False)
        self.canvas_stack = QStackedWidget()
        self.canvas_stack.addWidget(self.view)
        self.center_split.addWidget(self.canvas_stack)
        center_layout.addWidget(self.center_split, 1)
        self.results_panel = QWidget()
        self.results_panel.setObjectName('resultsPanel')
        result_layout = QVBoxLayout(self.results_panel)
        result_layout.setContentsMargins(7, 5, 7, 6)
        result_layout.setSpacing(4)
        result_header = QHBoxLayout()
        self.result_views = QTabBar()
        self.result_views.setDrawBase(False)
        self.result_views.setExpanding(False)
        self.result_views.addTab('Esforços axiais')
        self.result_views.addTab('Deformações')
        result_header.addWidget(self.result_views)
        result_header.addStretch()
        self.axial_values = QCheckBox('Valores no diagrama')
        self.axial_values.setChecked(True)
        self.axial_values.toggled.connect(self._set_axial_values)
        result_header.addWidget(self.axial_values)
        self.result_detail_button = _button('Detalhar esforços e envoltórias',
                                             lambda: self._open_inspector_index(3), 'report')
        result_header.addWidget(self.result_detail_button)
        self.deformation_controls = QWidget()
        deformation_layout = QHBoxLayout(self.deformation_controls)
        deformation_layout.setContentsMargins(0, 0, 0, 0)
        self.auto_deformation = QCheckBox('Escala automática')
        self.auto_deformation.setChecked(True)
        self.deformation_scale = _spin(1, 1, 10_000, 1, 10)
        self.deformation_scale.setMinimumWidth(82)
        self.deformation_scale.setLocale(LOCALE)
        self.deformation_scale.setPrefix('×')
        self.deformation_scale.setAccessibleName('Fator de amplificação da deformada')
        self.deformation_scale.setEnabled(False)
        deformation_layout.addWidget(self.auto_deformation)
        deformation_layout.addWidget(self.deformation_scale)
        self.deformation_controls.hide()
        result_header.addWidget(self.deformation_controls)
        result_layout.addLayout(result_header)
        result_legend = QHBoxLayout()
        self.dock_info = QLabel()
        self.result_legend = QLabel()
        result_legend.addWidget(self.dock_info, 1)
        result_legend.addWidget(self.result_legend)
        result_layout.addLayout(result_legend)
        self.quick_table = QTableWidget(0, 4)
        self.quick_table.setHorizontalHeaderLabels(self._result_headers('Seção'))
        self.quick_table.setAlternatingRowColors(True)
        self.quick_table.verticalHeader().hide()
        self.quick_table.verticalHeader().setDefaultSectionSize(24)
        self.quick_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.quick_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for column in range(3):
            self.quick_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.quick_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.quick_table.cellClicked.connect(self.quick_select_result)
        self.result_views.currentChanged.connect(self._result_view_changed)
        self.auto_deformation.toggled.connect(self._deformation_scale_changed)
        self.deformation_scale.valueChanged.connect(self._deformation_scale_changed)
        result_layout.addWidget(self.quick_table, 1)
        self.center_split.addWidget(self.results_panel)
        self.center_split.setStretchFactor(0, 1)
        self._set_results_visible(False)
        self.view.selected.connect(self.on_scene_selected)
        self.view.add_node.connect(self.create_node)
        self.view.add_member.connect(self.create_member)
        self.view.split_member.connect(self.split_member)
        self.view.moved.connect(self.move_nodes)
        self.splitter.addWidget(center)

        self.task_host = QWidget()
        self.task_host.setObjectName('taskPanel')
        self.task_host.setMinimumWidth(300)
        inspector = QVBoxLayout(self.task_host)
        inspector.setContentsMargins(8, 8, 8, 6)
        inspector.setSpacing(4)
        self.inspector_title = QLabel('Editor')
        self.inspector_title.setObjectName('panelHeading')
        inspector.addWidget(self.inspector_title)
        self.context_tabs = QTabBar()
        self.context_tabs.setDrawBase(False)
        self.context_tabs.setExpanding(False)
        self.context_tabs.setUsesScrollButtons(True)
        self.context_tabs.currentChanged.connect(self._context_changed)
        inspector.addWidget(self.context_tabs)
        self.info_tabs = QTabWidget()
        self.info_tabs.tabBar().hide()
        self._inspector_pages = {}
        self.info_tabs.currentChanged.connect(self.update_task_selection)
        inspector.addWidget(self.info_tabs, 1)
        self.splitter.addWidget(self.task_host)
        self.splitter.setSizes([220, 770, 330])
        self.splitter.setStretchFactor(1, 1)
        self._build_model_tab()
        self._build_property_tab()
        self._build_loads_tab()
        self._build_results_tab()
        self._build_engineering_tabs()
        self.setup_task_tree()

        footer = QFrame()
        footer.setObjectName('statusBar')
        status = QHBoxLayout(footer)
        status.setContentsMargins(9, 3, 9, 3)
        status.setSpacing(8)
        self.status_label = QLabel()
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        status.addWidget(self.status_label, 1)
        self.coordinates = QLabel(f'X —    Y —    {self.units.length}')
        self.coordinates.setObjectName('coordinates')
        self.coordinates.setMinimumWidth(226)
        self.view.coordinates_changed.connect(self._show_coordinates)
        self.view.status_text.connect(self.status)
        status.addWidget(self.coordinates)
        self.snap = _button(f'Snap {self.units.length_text(self.view.grid_mm)}', self._set_snap, 'snap', checkable=True)
        self.snap.setChecked(self.view.snap_enabled)
        self.grid = _button('Grade', self.view.set_grid_visible, 'grid', checkable=True)
        self.grid.setChecked(self.view.grid_visible)
        self.calc_badge = QLabel('Não calculado')
        self.calc_badge.setObjectName('calcPending')
        status.addWidget(self.calc_badge)
        main.addWidget(footer)
        self._build_toolbar(main)

    def _build_toolbar(self, main):
        self.toolbar = QFrame()
        self.toolbar.setObjectName('quickAccess')
        line = QHBoxLayout(self.toolbar)
        line.setContentsMargins(8, 5, 8, 5)
        line.setSpacing(2)
        brand = QLabel(APP_TITLE)
        brand.setObjectName('appHeader')
        line.addWidget(brand)
        groups = (
            (('Novo', self.new, 'new'), ('Abrir projeto', self.open, 'open'),
             ('Salvar', self.save, 'save'), ('Desfazer', self.undo, 'undo'), ('Refazer', self.redo, 'redo')),
            (('Selecionar', 'select', 'select'), ('Mover nós', 'move', 'move'), ('Deslocar vista', 'pan', 'pan'),
             ('Enquadrar', self.fit, 'fit'), ('Criar nó', 'node', 'node'), ('Criar barra', 'bar', 'member'),
             ('Subdividir barra', 'split', 'split'), ('Excluir seleção', self.delete_selected, 'delete')),
            (('Tipos de Carregamentos', self.open_general_actions, 'actions'),
             ('Casos de Carregamentos', self.open_static_cases, 'case'),
             ('Combinações', self.open_combinations, 'combine'),
             ('Inserir cargas nodais', self.open_nodal_loads, 'load'),
             ('Perfis e aço', self._open_profiles, 'profile')),
        )
        for group in groups:
            for label, command, icon in group:
                line.addWidget(self._workspace_button(label, command, icon, light=True))
            divider = QFrame()
            divider.setObjectName('toolDivider')
            divider.setFixedSize(1, 19)
            line.addWidget(divider)

        line.addWidget(self._workspace_button('Identificadores dos nós', 'show_ids', 'node_ids', light=True))
        line.addWidget(self._build_member_tags_button())
        for label, flag, icon in [
                                  ('Esforços', 'show_efforts', 'force'),
                                  ('Deformada', 'show_deformed', 'deformed')]:
            line.addWidget(self._workspace_button(label, flag, icon, light=True))
        self._overlay_buttons['show_forces'] = self.forces_button
        for button, icon in [(self.forces_button, 'load_view'), (self.results_button, 'table'),
                             (self.snap, 'snap'), (self.grid, 'grid')]:
            button.setIcon(action_icon(icon, light=True))
            line.addWidget(button)
        self.focus_button = _button('Só desenho (Ctrl+0)', self._set_drawing_only,
                                    'focus', checkable=True, light=True)
        line.addWidget(self.focus_button)

        more = _button('Mais comandos', lambda: None, 'more', light=True)
        menu = QMenu(more)
        for label, command, icon in [
            ('Importar DXF / DWG', self.import_cad, 'import'),
            ('Apoios e seleção', lambda: self._open_inspector_index(1), 'support'),
            ('Alternativas', lambda: self._show_inspector(self.search_tab), 'compare'),
            ('Diagnóstico', lambda: self._show_inspector(self.diagnostics_tab), 'diagnostic'),
            ('Exportar DimPerfil CSV', self.export_csv, 'export'),
            ('Exportar memorial A3', self.export_memorial, 'report'),
            ('Escala vertical', self.change_vertical, 'vertical'),
        ]:
            menu.addAction(action_icon(icon), label, command)
        more.setMenu(menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        line.addWidget(more)
        line.addStretch(1)
        self.unit_button = _button('Unidades de exibição', self.open_units, 'units', light=True)
        line.addWidget(self.unit_button)
        self.unit_summary = QLabel()
        self.unit_summary.setObjectName('unitSummary')
        self._update_unit_summary()
        line.addWidget(self.unit_summary)
        run = _button('Calcular (F5)', self.calculate, 'run', light=True)
        run.setObjectName('calculateButton')
        line.addWidget(run)
        main.insertWidget(0, self.toolbar)

    def _build_member_tags_button(self):
        button = _button('Identificadores por tipo de barra', lambda: None, 'bar_ids',
                         checkable=True, light=True)
        menu = QMenu(button)
        menu.setObjectName('memberTagsMenu')
        form = QWidget(menu)
        layout = QVBoxLayout(form)
        layout.setContentsMargins(12, 8, 14, 8)
        label = QLabel('Identificadores das barras')
        label.setObjectName('panelHeading')
        layout.addWidget(label)
        options = {'superior': 'Banzo superior', 'inferior': 'Banzo inferior',
                   'montante': 'Montantes', 'diagonal': 'Diagonais'}
        self.member_tag_checks = {}
        for group in GROUPS:
            choice = QCheckBox(options[group], form)
            choice.toggled.connect(lambda checked, name=group: self._set_member_tags(name, checked))
            layout.addWidget(choice)
            self.member_tag_checks[group] = choice
        action = QWidgetAction(menu)
        action.setDefaultWidget(form)
        menu.addAction(action)
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.member_tags_button = button
        return button

    def _set_member_tags(self, group, checked):
        if checked:
            self.view.member_id_groups.add(group)
        else:
            self.view.member_id_groups.discard(group)
        self.member_tags_button.setChecked(bool(self.view.member_id_groups))
        self.view.render(self.session, self.case_id)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'unit_summary'):
            self._fit_toolbar(event.size().width())

    def _fit_toolbar(self, width):
        layout = self.toolbar.layout()
        required = layout.minimumSize().width()
        if self.unit_summary.isHidden():
            required += self.unit_summary.sizeHint().width() + layout.spacing()
        self.unit_summary.setVisible(width >= required)

    def _workspace_button(self, label, command, icon, *, light=False):
        if not isinstance(command, str):
            return _button(label, command, icon, light=light)
        if command.startswith('show_'):
            button = _button(label, lambda enabled: self._set_overlay(command, enabled),
                             icon, checkable=True, light=light)
            self._overlay_buttons[command] = button
            return button
        button = _button(label, lambda: self.choose_tool(command), icon, checkable=True, light=light)
        self.tool_buttons.addButton(button)
        self._cad_buttons[command] = button
        button.setChecked(command == 'select')
        return button

    def _add_inspector_page(self, page, title):
        page.setObjectName('inspectorPage')
        page.setAutoFillBackground(True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        self._inspector_pages[page] = scroll
        self.info_tabs.addTab(scroll, title)

    def _add_load_dialog(self, page, title, *, height=560):
        dialog = QDialog(self)
        dialog.setObjectName('workspaceDialog')
        dialog.setWindowTitle(title)
        dialog.resize(465, height)
        layout = QVBoxLayout(dialog)
        heading = QLabel(title)
        heading.setObjectName('dialogHeading')
        layout.addWidget(heading)
        scroll = QScrollArea()
        scroll.setObjectName('loadDialogScroll')
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page.setObjectName('loadDialogPage')
        scroll.setWidget(page)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('Fechar')
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        self._load_dialogs[page] = dialog

    def _open_load_dialog(self, page, selector):
        dialog = self._load_dialogs[page]
        for other in self._load_dialogs.values():
            if other is not dialog:
                other.hide()
        if not dialog.isVisible() and selector.findText(self.case_id or '') >= 0:
            selector.setCurrentText(self.case_id)
        self._show_load_case(selector.currentText())
        if not dialog.testAttribute(Qt.WidgetAttribute.WA_Moved):
            self._position_dialog(dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _show_inspector(self, page):
        self._open_inspector_index(self.info_tabs.indexOf(self._inspector_pages[page]))

    def _open_inspector_index(self, index):
        if self._drawing_only:
            self._set_drawing_only(False)
        self._set_inspector_collapsed(False)
        self.info_tabs.setCurrentIndex(index)

    def _set_inspector_collapsed(self, collapsed):
        self._inspector_collapsed = collapsed
        self.inspector_toggle.setChecked(collapsed)
        self.inspector_toggle.setIcon(action_icon('collapse' if collapsed else 'panel'))
        tip = 'Expandir o painel direito' if collapsed else 'Recolher o painel direito'
        self.inspector_toggle.setToolTip(tip)
        self.inspector_toggle.setAccessibleName(tip)
        self.task_host.setVisible(not collapsed and not self._drawing_only)

    def _sync_context_tabs(self):
        current = self.info_tabs.currentIndex()
        if current < 0 or not hasattr(self, 'combo_tab'):
            return
        entries = {}
        kind = {item[0] for item in self._selected}
        if self.mode_3d.isChecked() and self._view3d is not None:
            view_index = self.info_tabs.indexOf(self._inspector_pages.get(self._view3d.controls))
            entries[view_index] = 'Inspeção 3D'
        else:
            entries[0] = 'Geometria'
        if not self.mode_3d.isChecked():
            if kind:
                entries[1] = 'Nó' if kind == {'node'} and len(self._selected) == 1 else (
                    'Barras' if kind == {'member'} else 'Seleção')
            nodes = self.session.model.node_map()
            if any(node in nodes for item, node in self._selected if item == 'node'):
                entries[self.info_tabs.indexOf(self._inspector_pages[self.loads_tab])] = 'Cargas nodais'
            if kind == {'member'}:
                entries[self.info_tabs.indexOf(self._inspector_pages[self.profile_tab])] = 'Perfis'
        entries.setdefault(current, self.info_tabs.tabText(current))
        with QSignalBlocker(self.context_tabs):
            while self.context_tabs.count():
                self.context_tabs.removeTab(0)
            for index, title in entries.items():
                tab = self.context_tabs.addTab(title)
                self.context_tabs.setTabData(tab, index)
                if index == current:
                    self.context_tabs.setCurrentIndex(tab)

    def _context_changed(self, tab):
        if tab < 0:
            return
        index = self.context_tabs.tabData(tab)
        if self.info_tabs.widget(index) is self._inspector_pages.get(self.loads_tab):
            self.open_nodal_loads()
        elif self.info_tabs.widget(index) is self._inspector_pages.get(self.profile_tab):
            self._open_profiles()
        else:
            self.info_tabs.setCurrentIndex(index)

    def _open_profiles(self):
        selected = {identifier for kind, identifier in self._selected if kind == 'member'}
        groups = {member.group for member in self.session.model.members if member.id in selected}
        if len(groups) == 1:
            self.section_group.setCurrentText(next(iter(groups)))
        self._show_inspector(self.profile_tab)

    def _set_results_visible(self, visible):
        was_hidden = self.results_panel.isHidden()
        self.results_button.setChecked(visible)
        self.results_panel.setVisible(visible and not self._drawing_only)
        if was_hidden and self.results_panel.isVisible():
            height = self.center_split.height()
            results_height = min(235, height * 2 // 5)
            self.center_split.setSizes([height - results_height, results_height])
            if self.session.result and not self.mode_3d.isChecked():
                self._result_view_changed(self.result_views.currentIndex())

    def _result_view_changed(self, index):
        deform = index == 1
        self.deformation_controls.setVisible(deform)
        self.axial_values.setVisible(not deform)
        self.result_detail_button.setVisible(not deform)
        if deform and self.mode_3d.isChecked():
            self.set_3d_visible(False)
        self.view.show_efforts = not deform
        self.view.show_deformed = deform
        self._overlay_buttons['show_efforts'].setChecked(not deform)
        self._overlay_buttons['show_deformed'].setChecked(deform)
        self.view.render(self.session, self.case_id, fit=True)
        self.refresh_quick_table()

    def _set_axial_values(self, visible):
        self.view.show_axial_values = visible
        if self.view.show_efforts:
            self.view.render(self.session, self.case_id)

    def _deformation_scale_changed(self, *_):
        automatic = self.auto_deformation.isChecked()
        self.deformation_scale.setEnabled(not automatic)
        self.view.deformation_factor = None if automatic else self.deformation_scale.value()
        if self.view.show_deformed:
            self.view.render(self.session, self.case_id, fit=True)
            self.refresh_quick_table()

    def _set_drawing_only(self, enabled):
        self._drawing_only = enabled
        self.focus_button.setChecked(enabled)
        self.navigator.setVisible(not enabled)
        self.task_host.setVisible(not enabled and not self._inspector_collapsed)
        self.inspector_toggle.setEnabled(not enabled)
        self.results_button.setEnabled(not enabled)
        self.results_panel.setVisible(self.results_button.isChecked() and not enabled)

    def _set_snap(self, enabled):
        self.view.snap_enabled = enabled

    def _show_coordinates(self, x, y):
        self._cursor_xy = x, y
        self.coordinates.setText(f'X {self.units.length_text(x)}    Y {self.units.length_text(y)}')

    def _update_unit_summary(self):
        self.unit_summary.setText(f'{self.units.force} · {self.units.length}')
        self.unit_button.setToolTip(f'Unidades de exibição · {self.units.force} · '
                                    f'{self.units.length} · {self.units.stress}')

    def open_units(self):
        dialog = UnitsDialog(self.units, self)
        dialog.adjustSize()
        self._position_dialog(dialog)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_units(dialog.units())

    def _position_dialog(self, dialog):
        size = dialog.size().expandedTo(dialog.sizeHint())
        screen = self.screen().availableGeometry()
        anchor = self.mapToGlobal(QPoint(self.width() - size.width() - 28, 74))
        x = max(screen.left(), min(anchor.x(), screen.right() - size.width()))
        y = max(screen.top(), min(anchor.y(), screen.bottom() - size.height() - 40))
        dialog.move(x, y)

    def set_units(self, units):
        if self.units == units:
            return
        default_load = self.load_table.currentRow() < 0 and not (self.fx.value() or self.fy.value())
        editing_node = self.node_properties.isVisibleTo(self)
        if editing_node:
            coordinates = self._node_position()
            supports = self.support_x.isChecked(), self.support_y.isChecked()
        self.units = self.view.units = units
        if self._settings is not None:
            units.save(self._settings)
        self._update_unit_summary()
        self._fit_toolbar(self.width())
        self.snap.set_label(f'Snap {units.length_text(self.view.grid_mm)}')
        if default_load:
            self.force_unit.setCurrentText(units.force)
        if self._cursor_xy is not None:
            self._show_coordinates(*self._cursor_xy)
        else:
            self.coordinates.setText(f'X —    Y —    {units.length}')
        self.view.render(self.session, self.case_id)
        self._update_selection(self._selected, show_properties=False)
        if editing_node:
            self._set_node_position_fields(*coordinates)
            self.support_x.setChecked(supports[0])
            self.support_y.setChecked(supports[1])
        self.refresh_load_table(reset_selection=False)
        self.refresh_result_table()
        if self.result_table.currentRow() >= 0 and self.session.result:
            item = self.result_table.item(self.result_table.currentRow(), 0)
            if item:
                self._show_result_detail(item.text())
        self._sync_view3d()

    def _show_force_summary(self, forces, error):
        self.force_bar.setVisible(self.view.show_forces and not self.mode_3d.isChecked())
        if error:
            self.force_summary.setText(f'{self.case_id} · Falha ao exibir as cargas')
            self.force_summary.setToolTip(error)
            return
        active = [(fx, fy) for fx, fy in forces.values() if hypot(fx, fy) > 1e-8]
        if active:
            fx = self.units.force_text(fsum(x for x, _ in active), signed=True, unit=False, load=True)
            fy = self.units.force_text(fsum(y for _, y in active), signed=True, load=True)
            self.force_summary.setText(
                f'{self.case_id} · {len(active)} nós com carga · ΣFx {fx} · ΣFy {fy}'
            )
        else:
            self.force_summary.setText(f'{self.case_id or "Caso"} · Sem cargas nodais resultantes')
        self.force_summary.setToolTip(
            'Resultantes nodais do caso ou combinação selecionada. Setas em escala relativa.'
        )


    def _build_model_tab(self):
        tab=QWidget();col=QVBoxLayout(tab)
        self.geometry_box=QGroupBox('Geometria paramétrica');form=QFormLayout(self.geometry_box)
        self.geom_fields={}
        definitions=[('span_m','Vão (m)',16.,.1,500.,5,.25),('frame_spacing_m','Entre pórticos (m)',5.,.1,100.,5,.25),
            ('height_m','Altura (m)',1.,.05,50.,5,.05),('rise_m','Desnível (m)',.5,0.,30.,5,.05)]
        for key,label,default,minimum,maximum,decimals,step in definitions:
            widget=_spin(default,minimum,maximum,decimals,step);self.geom_fields[key]=widget
            widget.setKeyboardTracking(False)
            widget.valueChanged.connect(self.change_geometry);form.addRow(label,widget)
        self.panels=QSpinBox();self.panels.setRange(2,40)
        self.panels.setKeyboardTracking(False)
        self.panels.valueChanged.connect(self.change_geometry)
        form.addRow('Painéis',self.panels)
        self.shape=QComboBox();self.shape.addItems(['parallel','single','gable','trapezoid'])
        self.shape.currentTextChanged.connect(self.change_geometry);form.addRow('Forma',self.shape)
        self.topology=QComboBox();self.topology.addItems(['Pratt','Howe','Warren'])
        self.topology.currentTextChanged.connect(self.change_geometry);form.addRow('Triangulação',self.topology)
        col.addWidget(self.geometry_box)
        self.cad_notice=QLabel('Edição CAD avançada cria modelo explícito.\n'
            'Voltar ao paramétrico descarta a geometria manual, após confirmação.')
        self.cad_notice.setWordWrap(True);col.addWidget(self.cad_notice)
        self.revert_button=_button('Voltar ao modo paramétrico', self.revert_parametric, 'undo')
        col.addWidget(self.revert_button, 0, Qt.AlignmentFlag.AlignLeft)
        col.addStretch(1);self._add_inspector_page(tab,'Geometria')

    def _build_property_tab(self):
        tab=QWidget();col=QVBoxLayout(tab)
        self.selection_label=QLabel('Selecione um nó ou barra no viewport')
        self.selection_label.setWordWrap(True);col.addWidget(self.selection_label)
        g=QGroupBox('Propriedades do nó');f=QFormLayout(g)
        self.node_properties = g
        self.node_id=QLineEdit();self.node_id.setReadOnly(True);f.addRow('ID',self.node_id)
        self.node_x=_spin(0,-1e9,1e9,2,50);self.node_y=_spin(0,-1e9,1e9,2,50)
        for axis, spin in zip(('X', 'Y'), (self.node_x, self.node_y)):
            spin.setLocale(LOCALE)
            spin.setGroupSeparatorShown(True)
            f.addRow(axis, spin)
        self._set_node_position_fields(0., 0.)
        self.support_x=QCheckBox('Restringir UX');self.support_y=QCheckBox('Restringir UY')
        f.addRow('Apoio',self.support_x);f.addRow('',self.support_y)
        self.apply_node=_button('Aplicar posição e apoios', self.apply_node_properties, 'check')
        f.addRow('Aplicar ao nó', self.apply_node);col.addWidget(g)
        g2=QGroupBox('Propriedades das barras');ff=QFormLayout(g2)
        self.member_properties = g2
        self.member_info=QLabel('Selecione uma barra');self.member_info.setWordWrap(True)
        ff.addRow(self.member_info)
        self.group=QComboBox();self.group.addItems(['superior','inferior','montante','diagonal'])
        ff.addRow('Grupo',self.group)
        change=_button('Aplicar grupo às barras selecionadas', self.change_group, 'check')
        ff.addRow('Aplicar às barras', change);col.addWidget(g2)
        col.addStretch(1);self._add_inspector_page(tab,'Propriedades')

    def _build_loads_tab(self):
        self.loads_tab = QWidget()
        col = QVBoxLayout(self.loads_tab)
        row = QHBoxLayout()
        self.load_case = QComboBox()
        self.load_case.setPlaceholderText('Escolher padrão nodal')
        self.load_case.setAccessibleName('Padrão nodal para edição')
        self.load_case.currentTextChanged.connect(self._load_case_changed)
        row.addWidget(self.load_case, 1)
        row.addWidget(_button('Novo padrão nodal', self.add_case, 'add'))
        col.addLayout(row)

        nodal = QGroupBox('Força por nó')
        fields = QFormLayout(nodal)
        fields.setVerticalSpacing(4)
        self.load_node = QComboBox()
        self.load_node.setPlaceholderText('Escolher nó')
        self.load_node.currentTextChanged.connect(self._refresh_load_controls)
        fields.addRow('Nó', self.load_node)
        self.fx = LoadField(-1e9, 1e9)
        self.fy = LoadField(-1e9, 1e9)
        self.fx.valueChanged.connect(self._refresh_load_controls)
        self.fy.valueChanged.connect(self._refresh_load_controls)
        components = QHBoxLayout()
        for title, spin in (('Fx (+ direita)', self.fx), ('Fy (+ acima)', self.fy)):
            component = QVBoxLayout()
            component.setSpacing(3)
            label = QLabel(title)
            label.setBuddy(spin)
            spin.setMinimumWidth(0)
            spin.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            component.addWidget(label)
            component.addWidget(spin)
            components.addLayout(component)
        fields.addRow(components)
        self.force_unit = QComboBox()
        self.force_unit.addItems(['kN', 'N', 'kgf', 'tf'])
        self.force_unit.setCurrentText(self.units.force)
        fields.addRow('Unidade', self.force_unit)
        self.commit_load = _button('Adicionar', self.add_load, 'add')
        fields.addRow(self.commit_load)
        self.batch_load = _button('Aplicar aos nós selecionados', self.add_load_batch, 'group')
        self.batch_load.setToolTip('Adicionar uma parcela com os valores do formulário em cada nó selecionado')
        fields.addRow(self.batch_load)
        col.addWidget(nodal)

        self.load_note = QLabel()
        self.load_note.setWordWrap(True)
        col.addWidget(self.load_note)
        parcels = QHBoxLayout()
        parcels.addWidget(QLabel('Parcelas'))
        parcels.addStretch()
        self.new_load = _button('Nova', self.clear_load_selection, 'new')
        self.delete_load = _button('Remover', self.remove_load, 'delete')
        parcels.addWidget(self.new_load)
        parcels.addWidget(self.delete_load)
        col.addLayout(parcels)
        self.load_table=QTableWidget(0,4)
        self.load_table.setHorizontalHeaderLabels(['Nó','Fx','Fy','Unid.'])
        self.load_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.load_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.load_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.load_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.load_table.verticalHeader().hide()
        self.load_table.verticalHeader().setDefaultSectionSize(23)
        self.load_table.setAlternatingRowColors(True)
        self.load_table.setMinimumHeight(96)
        self.load_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.load_table.currentCellChanged.connect(self.load_row_selected)
        col.addWidget(self.load_table,1)
        self._add_inspector_page(self.loads_tab, 'Cargas nodais')

    def _build_results_tab(self):
        tab=QWidget();col=QVBoxLayout(tab)
        self.results_info=QLabel('Resultados pendentes · executar F5');col.addWidget(self.results_info)
        filter_row=QHBoxLayout();self.results_group=QComboBox()
        self.results_group.addItems(['Todos','superior','inferior','montante','diagonal'])
        self.results_group.currentTextChanged.connect(self.refresh_result_table)
        self.critical_only=QCheckBox('10 críticas');self.critical_only.toggled.connect(self.refresh_result_table)
        filter_row.addWidget(self.results_group);filter_row.addWidget(self.critical_only)
        self.result_mode=QComboBox();self.result_mode.addItems(['Caso atual','Envoltória tração','Envoltória compressão'])
        self.result_mode.currentTextChanged.connect(self.refresh_result_table)
        col.addWidget(self.result_mode)
        col.addLayout(filter_row)
        self.result_table=QTableWidget(0,4)
        self.result_table.setHorizontalHeaderLabels(self._result_headers('Perfil'))
        for col_idx in range(3):
            self.result_table.horizontalHeader().setSectionResizeMode(col_idx,QHeaderView.ResizeMode.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_table.itemSelectionChanged.connect(self.select_result)
        col.addWidget(self.result_table,1)
        self.critical_detail=QLabel('Compressão azul · Tração vermelha');self.critical_detail.setWordWrap(True)
        col.addWidget(self.critical_detail)
        self._add_inspector_page(tab,'Resultados')

    def open_3d(self):
        self.set_3d_visible(True)

    def set_3d_visible(self, visible):
        self.mode_3d.setChecked(visible)
        self.view_mode_label.setText('3D' if visible else '2D')
        if visible:
            if self._view3d is None:
                self._view3d = Truss3DView(self.session, self.case_id, self)
                self.canvas_stack.addWidget(self._view3d)
                self._add_inspector_page(self._view3d.controls, 'Inspeção 3D')
                self.setup_task_tree()
            self.canvas_stack.setCurrentWidget(self._view3d)
            self._sync_view3d()
            self.info_tabs.setCurrentWidget(self._inspector_pages[self._view3d.controls])
            self.status('Arraste para orbitar · botão central desloca · clique para inspecionar a barra')
        else:
            self.canvas_stack.setCurrentWidget(self.view)
            if self._view3d and self.info_tabs.currentWidget() == self._inspector_pages[self._view3d.controls]:
                self.info_tabs.setCurrentIndex(0)
            self.view.set_tool(self.view.tool)
        for command in ('select', 'move', 'pan', 'node', 'bar', 'split'):
            self._cad_buttons[command].setEnabled(not visible)
        self.snap.setEnabled(not visible)
        self.grid.setEnabled(not visible)
        self.forces_button.setEnabled(not visible)
        for overlay in ('show_ids', 'show_deformed'):
            self._overlay_buttons[overlay].setEnabled(not visible)
        self.member_tags_button.setEnabled(not visible)
        self.force_bar.setVisible(self.view.show_forces and not visible)
        self._sync_context_tabs()
        self._refresh_property_summary()

    def _sync_view3d(self, *, fit=False):
        if self._view3d is not None and self.mode_3d.isChecked():
            self._view3d.units = self.units
            self._view3d.refresh_model(self.session, self.case_id, fit=fit)

    def _shortcuts(self):
        for key,func in [('Ctrl+N',self.new),('Ctrl+O',self.open),('Ctrl+S',self.save),
                         ('Ctrl+Z',self.undo),('Ctrl+Y',self.redo),('F5',self.calculate),
                         ('Delete',self._delete_focused_selection),('F',self.fit),
                         ('Esc',lambda:self.choose_tool('select')),('Ctrl+0',self.focus_button.click)]:
            action=QAction(self);action.setShortcut(QKeySequence(key));action.triggered.connect(func);self.addAction(action)

    def status(self,message):self.status_label.setText(str(message))

    def _apply(self,new_project,reason='Alteração do modelo',*,fit=False):
        old=deepcopy(self.session.project)
        try:self.session.update_project(new_project)
        except Exception as exc:
            self.refresh(fit=False)
            QMessageBox.warning(self,'Modelo não alterado',str(exc));return False
        self.undo_stack.append(old);self.undo_stack=self.undo_stack[-100:]
        self.redo_stack.clear();self._dirty=True
        self.refresh(fit=fit)
        self.status(f'{reason} · análise anterior invalidada');return True

    def refresh(self,fit=False):
        self._refreshing=True
        try:
            model=self.session.model;project=self.session.project
            self.tree.blockSignals(True);self.tree.clear()
            self._model_items = {}
            nodes_root=QTreeWidgetItem(['Nós']);members_root=QTreeWidgetItem(['Barras']);drafts_root=QTreeWidgetItem(['Nós em criação'])
            self.tree.addTopLevelItems([nodes_root,members_root,drafts_root])
            for n in model.nodes:
                node=QTreeWidgetItem([n.id]);node.setData(0,Qt.ItemDataRole.UserRole,('node',n.id));nodes_root.addChild(node)
                self._model_items['node', n.id] = node
            for m in model.members:
                item=QTreeWidgetItem([f'{m.id} · {m.group}']);item.setData(0,Qt.ItemDataRole.UserRole,('member',m.id));members_root.addChild(item)
                self._model_items['member', m.id] = item
            for n in project.get('cad_drafts',[]):
                item=QTreeWidgetItem([n['id']+' (rascunho)']);item.setData(0,Qt.ItemDataRole.UserRole,('node',n['id']));drafts_root.addChild(item)
                self._model_items['node', n['id']] = item
            nodes_root.setExpanded(False);members_root.setExpanded(False);drafts_root.setExpanded(True)
            self.tree.blockSignals(False)
            self.filter_model_tree(self.model_filter.text())
            options = [row['id'] for key in ('load_cases', 'combinations', 'load_patterns')
                       for row in project.get(key, [])]
            previous=self.case_id
            self.cases.blockSignals(True);self.cases.clear();self.cases.addItems(options)
            self.case_id=previous if previous in options else next(iter(options),None)
            if self.case_id:self.cases.setCurrentText(self.case_id)
            self.cases.blockSignals(False)
            self._populate_load_choices()
            geo=project.get('geometry',{})
            for key,field in self.geom_fields.items():
                field.blockSignals(True);field.setValue(float(geo.get(key,0)));field.blockSignals(False)
            self.panels.blockSignals(True);self.panels.setValue(int(geo.get('panels',2)));self.panels.blockSignals(False)
            for widget,key in ((self.shape,'roof_shape'),(self.topology,'truss_type')):
                widget.blockSignals(True)
                idx=widget.findText(str(geo.get(key,'')))
                if idx>=0:widget.setCurrentIndex(idx)
                widget.blockSignals(False)
            explicit='model_override' in project
            self.geometry_box.setEnabled(not explicit);self.revert_button.setEnabled(explicit)
            self.view.render(self.session,self.case_id,fit=fit)
            self._set_canvas_selection(self._selected)
            self._update_selection(self.view.selected_ids(), show_properties=False)
            self.view.set_tool(self.view.tool)
            self.refresh_load_table();self.refresh_result_table();self.refresh_engineering_tabs()
            if self.session.result:
                self.calc_badge.setText('Calculado')
            elif self.session.calculated_revision >= 0:
                self.calc_badge.setText('Recalcular (F5)')
            else:
                self.calc_badge.setText('Não calculado')
            self.calc_badge.setObjectName('calcReady' if self.session.result else 'calcPending')
            self.calc_badge.style().unpolish(self.calc_badge);self.calc_badge.style().polish(self.calc_badge)
            self.setWindowTitle(APP_TITLE+('  *' if self._dirty else '')+(f'  — {self.filepath.name}' if self.filepath else ''))
            self._sync_view3d(fit=fit)
        finally:self._refreshing=False

    def choose_tool(self,tool):
        if self.mode_3d.isChecked():
            self.set_3d_visible(False)
        self._cad_buttons[tool].setChecked(True)
        self.view.set_tool(tool)
        self._show_selection_controls()
        if tool in ('node','bar','split','move'):self.info_tabs.setCurrentIndex(1)

    def on_case(self,text):
        if self._refreshing:return
        index = self.load_case.findText(text)
        if index >= 0 and index != self.load_case.currentIndex():
            with QSignalBlocker(self.load_case):
                self.load_case.setCurrentIndex(index)
            self.refresh_load_table()
        for page, selector in ((self.actions_tab, self.action_case), (self.static_tab, self.static_case),
                               (self.combo_tab, self.combination)):
            if self._load_dialogs[page].isVisible() and selector.findText(text) >= 0:
                selector.setCurrentText(text)
        self.case_id=text;self.view.render(self.session,self.case_id)
        self._refresh_property_summary()
        self.refresh_result_table()
        self._sync_view3d()

    def on_tree_select(self):
        if self._refreshing:return
        selected=[item.data(0,Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()]
        selected = [entry for entry in selected if entry]
        if self._nodal_editor_active():
            self.clear_load_selection()
        self._set_canvas_selection(selected)
        self._update_selection(selected)

    def on_scene_selected(self,selected):
        if self._refreshing or selected == self._selected:return
        if self._nodal_editor_active():
            self.clear_load_selection()
        self._update_selection(selected)

    def _set_canvas_selection(self, selected):
        with QSignalBlocker(self.view.scene()):
            self.view.scene().clearSelection()
            for kind, identifier in selected:
                item = self.view.selection_item(kind, identifier)
                if item is not None:
                    item.setSelected(True)

    def _update_selection(self, selected, *, show_properties=True):
        self._selected=selected
        self._sync_quick_selection()
        if self._nodal_editor_active():
            if not selected or self._selected_load_nodes():
                self._follow_load_selection()
                show_properties = False
        with QSignalBlocker(self.tree):
            self.tree.clearSelection()
            for key in selected:
                item = self._model_items.get(key)
                if item is not None:
                    item.setSelected(True)
            if selected and show_properties:
                item = self._model_items.get(selected[0])
                if item is not None and not item.isHidden() and not item.parent().isHidden():
                    self.tree.scrollToItem(item)
        self._show_selection_controls()
        self._refresh_property_summary()
        self._sync_context_tabs()
        if not selected:
            self.selection_label.setText('Selecione um nó ou uma barra no desenho ou na árvore.')
            self.member_info.clear()
            return
        kind,id=selected[0]
        if kind=='node':
            nodes={n.id:n for n in self.session.model.nodes}
            nodes.update({n['id']:type('Draft',(),{'x':n['x_mm'],'y':n['y_mm']})() for n in self.session.project.get('cad_drafts',[])})
            if id in nodes:
                n=nodes[id];self.node_id.setText(id);self._set_node_position_fields(n.x,n.y)
                ux,uy=self.session.model.supports.get(id,(False,False))
                self.support_x.setChecked(ux);self.support_y.setChecked(uy)
                self.selection_label.setText(f'Nó {id}  |  X={self.units.length_text(n.x)}  '
                                             f'Y={self.units.length_text(n.y)}')
                if show_properties:self.info_tabs.setCurrentIndex(1)
        else:
            m=next((m for m in self.session.model.members if m.id==id),None)
            if m:
                length = self.units.length_text(self.session.model.member_length(m))
                self.member_info.setText(f'{m.id} · {m.i} → {m.j}\n{m.profile}\nL={length}')
                self.group.setCurrentText(m.group)
                self.selection_label.setText(f'Barra {id}' if len(selected) == 1 else
                                             f'{len(selected)} elementos selecionados')
                if show_properties:self.info_tabs.setCurrentIndex(1)

    def _show_selection_controls(self):
        kinds = {kind for kind, _ in self._selected}
        self.node_properties.setVisible(kinds == {'node'} and len(self._selected) == 1)
        self.member_properties.setVisible('member' in kinds or self.view.tool == 'bar')
        if 'member' not in kinds:
            self.member_info.clear()

    def _refresh_property_summary(self):
        model = self.session.model
        selected = self._selected
        if self.mode_3d.isChecked() and self._view3d:
            member = self._view3d._selected_member
            selected = [('member', member)] if member else []
        table = self.property_summary
        table.clear()
        analysis = (self.session.result or {}).get('analyses', {}).get(self.case_id, {})

        def group(title, values):
            parent = QTreeWidgetItem(table, [title])
            parent.setFirstColumnSpanned(True)
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            for key, value in values:
                row = QTreeWidgetItem(parent, [key, str(value)])
                row.setToolTip(1, str(value))
            parent.setExpanded(True)

        if len(selected) == 1:
            kind, identifier = selected[0]
            if kind == 'node':
                node = model.node_map().get(identifier)
                if node is not None:
                    ux, uy = model.supports.get(identifier, (False, False))
                    axes = ', '.join(axis for axis, active in [('UX', ux), ('UY', uy)] if active)
                    values = [('ID', identifier), ('X', self.units.length_text(node.x)),
                              ('Y', self.units.length_text(node.y)), ('Apoio', axes or 'Livre')]
                    delta = analysis.get('nodal_displacements', {}).get(identifier)
                    if delta is not None:
                        values.extend([('Ux', self.units.displacement_text(delta['ux_mm'], signed=True)),
                                       ('Uy', self.units.displacement_text(delta['uy_mm'], signed=True))])
                    group('Nó selecionado', values)
                else:
                    draft = next((row for row in self.session.project.get('cad_drafts', [])
                                  if row['id'] == identifier), None)
                    if draft:
                        group('Nó provisório', [('ID', identifier), ('X', self.units.length_text(draft['x_mm'])),
                                                ('Y', self.units.length_text(draft['y_mm']))])
            else:
                member = next((item for item in model.members if item.id == identifier), None)
                if member:
                    values = [('ID', identifier), ('Nós', f'{member.i} → {member.j}'),
                              ('Grupo', member.group), ('Perfil', member.profile),
                              ('Comprimento', self.units.length_text(model.member_length(member)))]
                    force = analysis.get('axial_n', {}).get(identifier)
                    if force is not None:
                        values.append(('Esforço normal', self.units.force_text(force, signed=True)))
                    group('Barra selecionada', values)
        elif selected:
            groups = [kind for kind, _ in selected]
            group('Seleção', [('Nós', groups.count('node')), ('Barras', groups.count('member'))])
        group('Modelo', [('Nós', len(model.nodes)), ('Barras', len(model.members)),
                        ('Apoios', len(model.supports))])

    def create_node(self,x,y):
        try:p,nid=editing.add_draft(self.session.project,self.session.model,x,y)
        except Exception as exc:QMessageBox.warning(self,'Novo nó',str(exc));return
        self._apply(p,f'Nó provisório {nid}',fit=False)

    def create_member(self,a,b):
        group=self.group.currentText()
        try:p,mid=editing.add_member(self.session.project,self.session.model,a,b,group=group)
        except Exception as exc:QMessageBox.warning(self,'Criar barra',str(exc));return
        self._apply(p,f'Barra criada {mid}')

    def split_member(self,mid,t):
        try:p,nids=editing.split_members(self.session.project,self.session.model,[mid],t)
        except Exception as exc:QMessageBox.warning(self,'Subdividir',str(exc));return
        self._apply(p,f'Subdividida {mid} → {nids[0]}')

    def move_nodes(self,updates):
        try:p=editing.move_nodes(self.session.project,self.session.model,updates)
        except Exception as exc:QMessageBox.warning(self,'Mover nós',str(exc));self.refresh();return
        self._apply(p,'Coordenadas alteradas')

    def delete_selected(self):
        selected=self.view.selected_ids() or self._selected
        nodes=[id for kind,id in selected if kind=='node']
        members=[id for kind,id in selected if kind=='member']
        if not nodes and not members:return
        try:p=editing.delete_elements(self.session.project,self.session.model,nodes,members)
        except Exception as exc:QMessageBox.warning(self,'Exclusão',str(exc));return
        if self._apply(p,'Elementos excluídos'):self._selected=[]

    def change_group(self):
        ids=[id for kind,id in (self.view.selected_ids() or self._selected) if kind=='member']
        if not ids:return
        try:p=editing.update_member_group(self.session.project,self.session.model,ids,self.group.currentText())
        except Exception as exc:QMessageBox.warning(self,'Perfis',str(exc));return
        self._apply(p,'Grupo e perfil alterados')

    def apply_node_properties(self):
        nid=self.node_id.text()
        if not nid:return
        try:
            p=editing.move_nodes(self.session.project,self.session.model,{nid: self._node_position()})
            if nid not in {n['id'] for n in p.get('cad_drafts',[])}:
                d=p['model_override'];d['supports']=[s for s in d['supports'] if s['node']!=nid]
                if self.support_x.isChecked() or self.support_y.isChecked():
                    d['supports'].append({'node':nid,'ux':self.support_x.isChecked(),'uy':self.support_y.isChecked()})
        except Exception as exc:QMessageBox.warning(self,'Propriedades',str(exc));return
        self._apply(p,f'Propriedades de {nid} atualizadas')

    def _node_position(self):
        return tuple(original if spin.value() == display else spin.value() * self.units.length_scale
                     for spin, (display, original) in
                     zip((self.node_x, self.node_y), self._node_display_values))

    def _set_node_position_fields(self, x, y):
        scale = self.units.length_scale
        baseline = []
        for spin, value in zip((self.node_x, self.node_y), (x, y)):
            spin.setDecimals(self.units.length_precision)
            spin.setRange(-1e9 / scale, 1e9 / scale)
            spin.setSingleStep(50 / scale)
            spin.setSuffix(f' {self.units.length}')
            spin.setValue(value / scale)
            baseline.append((spin.value(), value))
        self._node_display_values = tuple(baseline)

    def change_geometry(self,*_):
        if self._refreshing or 'model_override' in self.session.project:return
        p=deepcopy(self.session.project);geo=p['geometry']
        for key,widget in self.geom_fields.items():geo[key]=widget.value()
        geo['panels']=self.panels.value();geo['roof_shape']=self.shape.currentText()
        geo['truss_type']=self.topology.currentText()
        if geo != self.session.project['geometry']:
            self._apply(p,'Geometria paramétrica',fit=True)

    def revert_parametric(self):
        if QMessageBox.question(self,'Retornar ao paramétrico',
          'Descartar edições CAD, nós criados e subdivisões?')!=QMessageBox.StandardButton.Yes:return
        p=deepcopy(self.session.project);p.pop('model_override',None);p.pop('cad_drafts',None);p.pop('cad_import',None)
        # hipóteses particulares a nós e barras precisam ser revisadas
        p['stability']={};self._apply(p,'Modo paramétrico restaurado',fit=True)

    def add_case(self):
        name,ok=QInputDialog.getText(self,'Padrão nodal','Identificador, sem espaços:')
        if not ok:return
        try:
            p = workflow.add_load_case(self.session.project, name, 'nodal', pattern_only=True)
        except ValueError as exc:QMessageBox.warning(self,'Padrão nodal',str(exc));return
        if self._apply(p,'Padrão nodal adicionado'):
            self.open_nodal_loads()
            self.load_case.setCurrentText(name.strip())


    def open_nodal_loads(self):
        if self.mode_3d.isChecked():
            self.set_3d_visible(False)
        if self.focus_button.isChecked():
            self._set_drawing_only(False)
        self.choose_tool('select')
        self._show_inspector(self.loads_tab)
        self.refresh_load_table()
        self._show_load_case(self.load_case.currentText())

    def _nodal_editor_active(self):
        return self.info_tabs.currentWidget() is self._inspector_pages.get(self.loads_tab)

    def _populate_load_choices(self):
        case = self.case_id if self.load_case.findText(self.case_id or '') >= 0 else self.load_case.currentText()
        with QSignalBlocker(self.load_case):
            self.load_case.clear()
            self.load_case.addItems([item['id'] for item in self.session.nodal_cases()])
            if self.load_case.findText(case) >= 0:
                self.load_case.setCurrentText(case)
        node = self.load_node.currentText()
        with QSignalBlocker(self.load_node):
            self.load_node.clear()
            self.load_node.addItems([node.id for node in self.session.model.nodes])
            self.load_node.setCurrentIndex(self.load_node.findText(node))

    def _reset_load_fields(self):
        with QSignalBlocker(self.load_case), QSignalBlocker(self.load_node):
            self.load_case.setCurrentIndex(-1)
            self.load_node.setCurrentIndex(-1)
        self.fx.set_stored_value(0)
        self.fy.set_stored_value(0)
        self.force_unit.setCurrentText(self.units.force)

    def _load_case_changed(self, case):
        self.refresh_load_table()
        if self._nodal_editor_active():
            self._show_load_case(case)

    def _show_load_case(self, case):
        if not case:
            return
        self.cases.setCurrentText(case)
        if not self.view.show_forces:
            self._set_overlay('show_forces', True)

    def _selected_load_nodes(self):
        return sorted(node for kind, node in self._selected
                      if kind == 'node' and self.load_node.findText(node) >= 0)

    def _follow_load_selection(self):
        nodes = self._selected_load_nodes()
        if nodes and self.load_table.currentRow() < 0:
            self.load_node.setCurrentText(nodes[0])
        self._refresh_load_controls()

    def _refresh_load_controls(self, *_):
        case = self.load_case.currentText()
        editing_row = self.load_table.currentRow() >= 0
        has_force = bool(self.fx.value() or self.fy.value())
        self.commit_load.set_label('Salvar edição da parcela' if editing_row else 'Adicionar parcela')
        self.commit_load.setEnabled(bool(case and self.load_node.currentText() and (has_force or editing_row)))
        self.delete_load.setEnabled(editing_row)
        self.new_load.setEnabled(editing_row)
        count = len(self._selected_load_nodes())
        self.batch_load.set_label(f'Aplicar a {count} nós selecionados' if count > 1
                                  else 'Aplicar aos nós selecionados')
        self.batch_load.setEnabled(bool(case and count > 1 and has_force and not editing_row))
        if not case:
            note = 'Crie um padrão nodal para começar.'
        elif editing_row:
            note = f'Editando a parcela {self.load_table.currentRow() + 1}.'
        else:
            note = 'Clique num nó ou use Ctrl+clique para selecionar vários.'
        self.load_note.setText(note)

    def clear_load_selection(self):
        with QSignalBlocker(self.load_table):
            self.load_table.clearSelection()
            self.load_table.setCurrentCell(-1, -1)
        self._follow_load_selection()

    def _active_nodal_case(self):
        return next((case for case in self.session.nodal_cases()
                     if case['id'] == self.load_case.currentText()), {})

    def load_row_selected(self, row, *_):
        case = self._active_nodal_case()
        rows = case.get('loads', [])
        if 0 <= row < len(rows):
            load = rows[row]
            node = str(load['node'])
            self.load_node.setCurrentIndex(self.load_node.findText(node))
            self.fx.set_stored_value(float(load.get('fx', 0)))
            self.fy.set_stored_value(float(load.get('fy', 0)))
            self.force_unit.setCurrentText(load.get('force_unit', case.get('force_unit', 'kgf')))
            selection = [('node', node)]
            self._set_canvas_selection(selection)
            self._update_selection(self.view.selected_ids(), show_properties=False)
        self._refresh_load_controls()

    def add_load(self):
        row = self.load_table.currentRow()
        self._save_nodal_loads([self.load_node.currentText()], index=row if row >= 0 else None)

    def add_load_batch(self):
        nodes = self._selected_load_nodes()
        if self.batch_load.isEnabled() and len(nodes) > 1:
            self._save_nodal_loads(nodes)

    def _save_nodal_loads(self, nodes, *, index=None):
        case = self.load_case.currentText()
        unit = self.force_unit.currentText()
        source = self._active_nodal_case()
        original = source['loads'][index] if index is not None else {}
        preserve = index is not None and unit == original.get('force_unit', source.get('force_unit', 'kgf'))
        fx, fy = (field.submitted_value() if preserve else field.value() for field in (self.fx, self.fy))
        try:
            updated = workflow.update_nodal_loads(
                self.session.project, self.session.model, case, nodes,
                fx, fy, unit, index,
            )
        except (ValueError, IndexError) as error:
            QMessageBox.warning(self, 'Carga nodal', str(error))
            return
        message = (f'Carga adicionada a {len(nodes)} nós' if len(nodes) > 1
                   else 'Carga nodal atualizada' if index is not None else 'Carga nodal adicionada')
        if self._apply(updated, message):
            self._show_load_case(case)
            if index is not None:
                self.load_table.selectRow(index)

    def remove_load(self):
        cid = self.load_case.currentText()
        row = self.load_table.currentRow()
        if row < 0:
            return
        updated = deepcopy(self.session.project)
        case = next((entry for entry in load_patterns(updated) if entry['id'] == cid), None)
        if case and row < len(case.get('loads', [])):
            case['loads'].pop(row)
            self._apply(updated, 'Carga removida')

    def _delete_focused_selection(self):
        if self._nodal_editor_active():
            focus = self.focusWidget()
            if focus is self.load_table or (focus is not None and self.load_table.isAncestorOf(focus)):
                self.remove_load()
        else:
            self.delete_selected()

    def refresh_load_table(self, *, reset_selection=True):
        case = self._active_nodal_case()
        rows = case.get('loads', [])
        with QSignalBlocker(self.load_table):
            self.load_table.setRowCount(len(rows))
            for index, load in enumerate(rows):
                input_unit = load.get('force_unit', case.get('force_unit', 'kgf'))
                try:
                    scale = FORCE_TO_N[input_unit]
                    values = (str(load['node']),
                              self.units.force_text(float(load.get('fx', 0)) * scale, unit=False, load=True),
                              self.units.force_text(float(load.get('fy', 0)) * scale, unit=False, load=True),
                              self.units.force)
                except (KeyError, TypeError, ValueError):
                    values = (str(load['node']), str(load.get('fx', 0)), str(load.get('fy', 0)), str(input_unit))
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column in (1, 2):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.load_table.setItem(index, column, item)
        if reset_selection:
            self.clear_load_selection()


    def calculate(self):
        try:
            self.session.calculate()
        except Exception as exc:
            QMessageBox.warning(self,'Não foi possível analisar',str(exc));return
        self.refresh()
        self._set_results_visible(True)
        self.status('Análise concluída · verifique estados-limites e travamentos separadamente')

    def _result_headers(self, profile_title):
        return ['Barra', 'Grupo', f'N ({self.units.force})', profile_title]

    def _result_row(self, member, force):
        return (member.id, member.group, self.units.force_text(force, signed=True, unit=False), member.profile)

    def refresh_result_table(self,*_):
        if not hasattr(self,'result_table'):return
        self.result_table.setHorizontalHeaderLabels(self._result_headers('Perfil'))
        res=self.session.result
        if not res:
            self.result_table.setRowCount(0);self.results_info.setText('Análise desatualizada — pressione F5');self.refresh_quick_table();return
        cid=self.case_id or next(iter(res['analyses']),None)
        if cid not in res['analyses']:
            self.result_table.setRowCount(0)
            self.results_info.setText('O caso selecionado não tem resultados disponíveis.')
            self.refresh_quick_table()
            return
        axial=res['analyses'][cid]['axial_n']
        mode=self.result_mode.currentText() if hasattr(self,'result_mode') else 'Caso atual'
        def force(mid):
            env=res.get('envelope',{}).get(mid,{})
            if mode=='Envoltória tração':return env.get('max_tension_n',0)
            if mode=='Envoltória compressão':return env.get('max_compression_n',0)
            return axial[mid]
        records=[m for m in self.session.model.members if self.results_group.currentText() in ('Todos',m.group)]
        if self.critical_only.isChecked():records=sorted(records,key=lambda m:abs(force(m.id)),reverse=True)[:10]
        self.result_table.blockSignals(True);self.result_table.setRowCount(len(records))
        for i,m in enumerate(records):
            axial_force = force(m.id)
            for j,val in enumerate(self._result_row(m, axial_force)):
                item=QTableWidgetItem(str(val))
                if j == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if axial_force:
                        item.setForeground(QColor('#C53646' if axial_force>0 else '#2666B8'))
                self.result_table.setItem(i,j,item)
        self.result_table.blockSignals(False)
        self.results_info.setText(f'{mode} · {cid} · {len(records)} barras · Tração (+) · Compressão (−)')
        self.refresh_quick_table()

    def select_result(self):
        row=self.result_table.currentRow()
        if row<0:return
        item=self.result_table.item(row,0)
        if not item:return
        mid=item.text()
        selection = [('member', mid)]
        self._set_canvas_selection(selection)
        self._update_selection(selection, show_properties=False)
        self._show_result_detail(mid)

    def _show_result_detail(self, member_id):
        envelope = self.session.result['envelope'][member_id]
        tension = self.units.force_text(envelope['max_tension_n'])
        compression = self.units.force_text(envelope['max_compression_n'])
        self.critical_detail.setText(
            f'{member_id}\nTração máxima: {tension} ({envelope["tension_case"]})\n'
            f'Compressão máxima: {compression} ({envelope["compression_case"]})')

    def _set_overlay(self, flag, visible):
        if visible and flag in ('show_deformed', 'show_efforts') and not self.mode_3d.isChecked():
            index = int(flag == 'show_deformed')
            with QSignalBlocker(self.result_views):
                self.result_views.setCurrentIndex(index)
            self._result_view_changed(index)
            return
        setattr(self.view, flag, visible)
        self._overlay_buttons[flag].setChecked(visible)
        if flag == 'show_forces':
            self.forces_button.setChecked(visible)
        self.view.render(self.session, self.case_id)
        if flag in ('show_deformed', 'show_efforts'):
            self.refresh_quick_table()
    def change_vertical(self):
        values=[1.,1.5,2.,3.,4.];current=self.view._vertical
        nxt=values[(values.index(current)+1)%len(values)] if current in values else 1.
        self.view.set_vertical_factor(nxt);self.status(f'Escala vertical de exibição ×{nxt:g} (não afeta cálculos)')
    def fit(self):
        if self.mode_3d.isChecked():
            self._view3d.fit()
        else:
            self.view.fit()

    def undo(self):
        if not self.undo_stack:return
        self.redo_stack.append(deepcopy(self.session.project))
        project=self.undo_stack.pop();self.session.update_project(project);self._dirty=True;self.refresh()
    def redo(self):
        if not self.redo_stack:return
        self.undo_stack.append(deepcopy(self.session.project))
        project=self.redo_stack.pop();self.session.update_project(project);self._dirty=True;self.refresh()

    def new(self):
        if not self._maybe_save():return
        self.session=Session();self.undo_stack.clear();self.redo_stack.clear();self.filepath=None
        self._selected = []
        self._reset_load_fields()
        self._dirty=False;self.refresh(fit=True)
    def open(self):
        if not self._maybe_save():return
        name,_=QFileDialog.getOpenFileName(self,'Abrir projeto','','2DTruss (*.json)')
        if not name:return
        try:new_session=Session(load_project(name))
        except Exception as exc:QMessageBox.warning(self,'Abrir',str(exc));return
        self.session=new_session;self.filepath=Path(name);self.undo_stack.clear();self.redo_stack.clear()
        self._selected = []
        self._reset_load_fields()
        self._dirty=False;self.refresh(fit=True)
    def save(self):
        if self.filepath is None:return self.save_as()
        try:write_project(self.filepath,self.session.project)
        except Exception as exc:QMessageBox.warning(self,'Salvar',str(exc));return False
        self._dirty=False;self.refresh();self.status(f'Salvo: {self.filepath.name}');return True
    def save_as(self):
        name,_=QFileDialog.getSaveFileName(self,'Salvar projeto','','2DTruss (*.json)')
        if not name:return False
        self.filepath=Path(name);return self.save()
    def _maybe_save(self):
        if not self._dirty:return True
        choice=QMessageBox.question(self,'Alterações não salvas','Salvar projeto antes de continuar?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No|QMessageBox.StandardButton.Cancel)
        if choice==QMessageBox.StandardButton.Cancel:return False
        if choice==QMessageBox.StandardButton.Yes:return self.save()
        return True

    def import_cad(self):
        if not self._maybe_save():return
        name,_=QFileDialog.getOpenFileName(self,'Importar eixos DXF/DWG','','Arquivos CAD (*.dxf *.dwg)')
        if not name:return
        unit='mm'
        if Path(name).suffix.lower()=='.dxf':
            unit,ok=QInputDialog.getItem(self,'Unidade para DXF sem INSUNITS',
               'Se o desenho não possui unidade, interpretar 1 unidade CAD como:', ['mm','cm','m','in'],0,False)
            if not ok:return
        tol,ok=QInputDialog.getDouble(self,'Tolerância de nós','Unir extremidades a até (mm):',1.,.001,100.,3)
        if not ok:return
        try:preview=cad_io.load_cad(name,unitless_unit=unit,merge_tolerance_mm=tol)
        except Exception as exc:QMessageBox.warning(self,'Importação não concluída',str(exc));return
        dialog=CadDialog(preview,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        try:p=cad_io.make_import_project(self.session.project,preview,self.session.catalog,dialog.mapping())
        except Exception as exc:QMessageBox.warning(self,'Importar',str(exc));return
        if self._apply(p,f'{len(preview.members)} barras importadas de {preview.source}',fit=True):
            self.info_tabs.setCurrentIndex(1)
            QMessageBox.information(self,'Modelo importado','Defina os apoios e confira os eixos, cargas, perfis e nós.\n'
                'Nenhuma verificação resistente foi executada; todos os resultados anteriores foram invalidados.')

    def export_csv(self):
        if not self.session.result:QMessageBox.information(self,'Exportar','Calcule antes de exportar.');return
        name,_=QFileDialog.getSaveFileName(self,'DimPerfil CSV','','CSV (*.csv)')
        if name:Path(name).write_text(as_csv(dimperfil_rows(self.session.result)),encoding='utf-8')
    def export_memorial(self):
        if not self.session.result:return
        name,_=QFileDialog.getSaveFileName(self,'Memorial A3','','HTML (*.html)')
        if not name:return
        cid=self.case_id or next(iter(self.session.result['analyses']))
        Path(name).write_text(integrated_report_html(self.session.result,self.session.project,cid),encoding='utf-8')
    def closeEvent(self,event):
        if self._maybe_save():event.accept()
        else:event.ignore()


    def setup_task_tree(self):
        self.task_tree.blockSignals(True);self.task_tree.clear();self._task_by_index={}
        groups={
            'Concepção':('Geometria','Telha / modulação','Perfis'),
            'Modelagem':('Propriedades','Estabilidade'),
            'Ações':('Cargas nodais',),
            'Análise':('Resultados','Alternativas','Diagnóstico','Inspeção 3D'),
        }
        assigned=set()
        for title,labels in groups.items():
            root=QTreeWidgetItem([title]);self.task_tree.addTopLevelItem(root)
            root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            if title == 'Ações':
                for label in self._load_dialog_commands():
                    entry = QTreeWidgetItem(root, [label])
                    entry.setData(0, Qt.ItemDataRole.UserRole, label)
            for i in range(self.info_tabs.count()):
                label=self.info_tabs.tabText(i)
                if label in labels:
                    item=QTreeWidgetItem([label]);item.setData(0,Qt.ItemDataRole.UserRole,i)
                    root.addChild(item);self._task_by_index[i]=item;assigned.add(i)
            root.setExpanded(True)
        others=[i for i in range(self.info_tabs.count()) if i not in assigned]
        if others:
            root=QTreeWidgetItem(['Outros']);self.task_tree.addTopLevelItem(root)
            for i in others:
                item=QTreeWidgetItem([self.info_tabs.tabText(i)])
                item.setData(0,Qt.ItemDataRole.UserRole,i);root.addChild(item)
                self._task_by_index[i]=item
            root.setExpanded(True)
        self.task_tree.blockSignals(False)
        self.update_task_selection(self.info_tabs.currentIndex())

    def task_clicked(self,item,column):
        index=item.data(0,Qt.ItemDataRole.UserRole)
        if isinstance(index, str):
            self._load_dialog_commands()[index]()
            return
        if isinstance(index, int):
            if self.info_tabs.tabText(index) == 'Inspeção 3D':
                self.open_3d()
            elif self.info_tabs.widget(index) is self._inspector_pages[self.loads_tab]:
                self.open_nodal_loads()
            else:
                self._open_inspector_index(index)

    def _load_dialog_commands(self):
        return {'Tipos de Carregamentos': self.open_general_actions,
                'Casos de Carregamentos': self.open_static_cases,
                'Combinações': self.open_combinations}

    def update_task_selection(self,index):
        self._sync_context_tabs()
        if not hasattr(self,'task_tree'):return
        target=getattr(self,'_task_by_index',{}).get(index)
        if target is None:return
        self.task_tree.blockSignals(True)
        self.task_tree.setCurrentItem(target)
        self.task_tree.blockSignals(False)

    def filter_model_tree(self,pattern):
        if not hasattr(self,'tree'):return
        q=pattern.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            root=self.tree.topLevelItem(i);found=not q or q in root.text(0).lower()
            for j in range(root.childCount()):
                child=root.child(j);hit=not q or q in child.text(0).lower()
                child.setHidden(not hit);found=found or hit
            root.setHidden(not found)
            if q:root.setExpanded(True)

    def quick_select_result(self, row, column):
        item = self.quick_table.item(row, 0)
        if item is None:
            return
        kind = 'node' if self.result_views.currentIndex() == 1 else 'member'
        selection = [(kind, item.text())]
        self._set_canvas_selection(selection)
        self._update_selection(selection, show_properties=False)

    def _sync_quick_selection(self):
        table = self.quick_table
        with QSignalBlocker(table):
            table.clearSelection()
            table.setCurrentCell(-1, -1)
            kind = 'node' if self.result_views.currentIndex() == 1 else 'member'
            if len(self._selected) != 1 or self._selected[0][0] != kind:
                return
            identifier = self._selected[0][1]
            for item in table.findItems(identifier, Qt.MatchFlag.MatchExactly):
                if item.column() == 0:
                    table.selectRow(item.row())
                    break

    def refresh_quick_table(self):
        if not hasattr(self, 'quick_table'):
            return
        deform = self.result_views.currentIndex() == 1
        analysis = (self.session.result or {}).get('analyses', {}).get(self.case_id)
        with QSignalBlocker(self.quick_table):
            if deform:
                unit = self.units.length
                headers = ['Nó', f'Ux ({unit})', f'Uy ({unit})', f'|u| ({unit})']
            else:
                headers = self._result_headers('Seção')
            self.quick_table.setHorizontalHeaderLabels(headers)
            header = self.quick_table.horizontalHeader()
            for column in range(len(headers)):
                mode = QHeaderView.ResizeMode.Stretch if deform or column == 3 else QHeaderView.ResizeMode.ResizeToContents
                header.setSectionResizeMode(column, mode)
                if deform and column > 0:
                    alignment = Qt.AlignmentFlag.AlignRight
                else:
                    alignment = Qt.AlignmentFlag.AlignLeft
                self.quick_table.horizontalHeaderItem(column).setTextAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
            if analysis is None:
                self.quick_table.setRowCount(0)
                self.dock_info.setText('Calcule o modelo ou selecione um caso com resultados.')
                self.result_legend.clear()
                return

            if deform:
                records = self._displacement_rows(analysis['nodal_displacements'])
            else:
                axial = analysis['axial_n']
                members = sorted(self.session.model.members, key=lambda m: abs(axial[m.id]), reverse=True)
                records = [(self._result_row(member, axial[member.id]),
                            TENS if axial[member.id] > 0 else COMP if axial[member.id] < 0 else None)
                           for member in members]
                self.dock_info.setText(f'{self.case_id} · {len(members)} barras')
                self.result_legend.setText(
                    f'<span style="color:{TENS}">● Tração (+)</span> &nbsp;'
                    f'<span style="color:{COMP}">● Compressão (−)</span> &nbsp;'
                    f'<span style="color:#60788C">● Nulo</span>')

            self.quick_table.setRowCount(len(records))
            for row, (values, color) in enumerate(records):
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(str(value))
                    if (deform and column > 0) or (not deform and column == 2):
                        cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        if color:
                            cell.setForeground(QColor(color))
                    self.quick_table.setItem(row, column, cell)
            self._sync_quick_selection()

    def _displacement_rows(self, displacements):
        rows = sorted(displacements.items(),
                      key=lambda row: hypot(row[1]['ux_mm'], row[1]['uy_mm']), reverse=True)
        records = []
        for node, delta in rows:
            ux, uy = delta['ux_mm'], delta['uy_mm']
            records.append(((node,
                             self.units.displacement_text(ux, signed=True, unit=False),
                             self.units.displacement_text(uy, signed=True, unit=False),
                             self.units.displacement_text(hypot(ux, uy), unit=False)), None))
        title = f'{self.case_id} · {len(rows)} nós'
        if rows:
            node, delta = max(rows, key=lambda row: abs(row[1]['uy_mm']))
            peak = self.units.displacement_text(delta['uy_mm'], signed=True)
            title += f' · Máx. |Uy| em {node} ({peak})'
        self.dock_info.setText(title)
        amp = self.view.effective_deformation_factor
        if amp is None or self.mode_3d.isChecked():
            self.result_legend.clear()
        else:
            with QSignalBlocker(self.deformation_scale):
                self.deformation_scale.setValue(amp)
            self.result_legend.setText(
                f'<span style="color:#60788C">━ Original</span> &nbsp;'
                f'<span style="color:{DEFORMED}">┄ Deformada ×{format_number(amp, 1)}</span>')
        return records



def start():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('2DTruss');app.setStyle('Fusion')
    window=DesktopApp(settings=QSettings('2DTruss', 'Desktop'));window.show()
    QTimer.singleShot(0,window.view.fit)
    return app.exec()
