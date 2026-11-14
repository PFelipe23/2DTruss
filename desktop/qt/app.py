"""2DTruss v0.1 — desktop PySide6 com ribbons e QGraphicsScene.

A lógica estrutural é delegada a desktop.bridge.Session / poe_truss.
Nenhum navegador, servidor HTTP ou webview integra o processo desktop.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import json
import sys

from PySide6.QtCore import Qt,QSignalBlocker,QTimer
from PySide6.QtGui import QAction,QKeySequence,QColor,QFont,QPen
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,
    QLabel,QPushButton,QToolButton,QComboBox,QDoubleSpinBox,QSpinBox,QCheckBox,QSplitter,
    QTreeWidget,QTreeWidgetItem,QTabWidget,QFormLayout,QGroupBox,QLineEdit,QFileDialog,
    QMessageBox,QInputDialog,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,
    QDialog,QDialogButtonBox,QGraphicsView,QGraphicsScene,QGraphicsLineItem,QFrame,QSizePolicy,QStyle)

from desktop.bridge import Session,load_project,write_project
from desktop import editing,cad_io
from poe_truss.export import as_csv,dimperfil_rows,integrated_report_html,ftool_comparison_full_rows
from poe_truss.version import APP_NAME, TAG
from .viewport import TrussView
from .workflow_panels import WorkflowMixin
from .view3d import Truss3DDialog
from .ui_theme import STYLE

APP_TITLE=f'{APP_NAME}  |  {TAG}  ·  Engenharia 2D + Inspeção 3D'
STYLESHEET=STYLE


def _button(label,callback,tooltip=''):
    w=QToolButton();w.setText(label);w.setToolTip(tooltip or label)
    w.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    w.setMinimumWidth(90);w.clicked.connect(callback)
    return w


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
    def __init__(self,session:Session|None=None):
        super().__init__()
        self.session=session or Session()
        self.filepath:Path|None=None
        self.undo_stack=[];self.redo_stack=[]
        self._refreshing=False;self._dirty=False
        self._selected=[];self.case_id=None
        self._view3d=None
        self.setWindowTitle(APP_TITLE)
        self.resize(1600,930);self.setMinimumSize(1100,680)
        self.setStyleSheet(STYLESHEET)
        self._build()
        self.refresh(fit=True)
        self._shortcuts()

    def _build(self):
        central=QWidget();self.setCentralWidget(central)
        main=QVBoxLayout(central);main.setContentsMargins(0,0,0,0);main.setSpacing(0)
        header=QLabel('2DTRUSS     v0.1   |   EDITOR PARAMÉTRICO E CAD 2D')
        header.setObjectName('appHeader');main.addWidget(header)
        self.ribbon=QTabWidget();self.ribbon.setFixedHeight(139)
        main.addWidget(self.ribbon)
        for title,items in [
          ('Arquivo',[('Novo',self.new),('Abrir JSON',self.open),('Salvar',self.save),('Importar DXF/DWG',self.import_cad),('Desfazer',self.undo),('Refazer',self.redo)]),
          ('Modelagem',[('Selecionar',lambda:self.choose_tool('select')),('Mover',lambda:self.choose_tool('move')),('Novo nó',lambda:self.choose_tool('node')),('Criar barra',lambda:self.choose_tool('bar')),('Subdividir',lambda:self.choose_tool('split')),('Excluir',self.delete_selected),('Grupo da barra',self.change_group),('Perfis',lambda:self.info_tabs.setCurrentWidget(self.profile_tab))]),
          ('Ações',[('Adicionar carga',self.add_load),('Novo caso nodal',self.add_case),('Apoios X/Y',lambda:self.info_tabs.setCurrentIndex(1)),('Ver cargas',self.toggle_loads),('Ações gerais',lambda:self.info_tabs.setCurrentWidget(self.actions_tab)),('Combinações',lambda:self.info_tabs.setCurrentWidget(self.combo_tab))]),
          ('Análise',[('Calcular (F5)',self.calculate),('Resultados',lambda:self.info_tabs.setCurrentIndex(3)),('DimPerfil CSV',self.export_csv),('Memorial A3',self.export_memorial),('Alternativas',lambda:self.info_tabs.setCurrentWidget(self.search_tab)),('Diagnóstico',lambda:self.info_tabs.setCurrentWidget(self.diagnostics_tab))]),
          ('Exibição',[('Enquadrar',self.fit),('IDs dos nós',self.toggle_ids),('Esforços',self.toggle_efforts),('Deformada',self.toggle_deformed),('Forças',self.toggle_loads),('Exagero vertical',self.change_vertical),('Vista 3D',self.open_3d)]),
        ]:
            content=QWidget();line=QHBoxLayout(content);line.setContentsMargins(8,2,8,0);line.setSpacing(0)
            # Grupos pequenos no ribbon, com legenda de função.
            group_def=[('Projeto',items[:3]),('Ferramentas',items[3:6]),('Opções',items[6:])]
            for caption,entries in group_def:
                if not entries:continue
                group=QFrame();group.setObjectName('ribbonGroup')
                gv=QVBoxLayout(group);gv.setContentsMargins(5,0,8,0);gv.setSpacing(0)
                tools=QHBoxLayout();tools.setSpacing(1)
                for label,action in entries:
                    button=_button(label,action)
                    icon_name = ('SP_DialogOpenButton' if 'Abrir' in label or 'Importar' in label else
                                 'SP_DialogSaveButton' if 'Salvar' in label else
                                 'SP_MediaPlay' if 'Calcular' in label else
                                 'SP_DialogApplyButton' if 'Aplicar' in label else
                                 'SP_FileIcon')
                    button.setIcon(self.style().standardIcon(getattr(QStyle.StandardPixmap,icon_name)))
                    tools.addWidget(button)
                gv.addLayout(tools)
                cap=QLabel(caption.upper());cap.setObjectName('ribbonCaption')
                cap.setAlignment(Qt.AlignmentFlag.AlignCenter);gv.addWidget(cap)
                line.addWidget(group)
            line.addStretch(1);self.ribbon.addTab(content,title)
        self.splitter=QSplitter(Qt.Orientation.Horizontal)
        main.addWidget(self.splitter,1)
        model_host=QWidget();ml=QVBoxLayout(model_host);ml.setContentsMargins(7,8,7,7);ml.setSpacing(6)
        tree_label=QLabel('NAVEGADOR DO MODELO');tree_label.setObjectName('panelHeading')
        ml.addWidget(tree_label)
        self.model_filter=QLineEdit();self.model_filter.setPlaceholderText('Buscar nó ou barra...')
        self.model_filter.textChanged.connect(self.filter_model_tree)
        ml.addWidget(self.model_filter)
        self.tree=QTreeWidget();self.tree.setHeaderHidden(True);self.tree.setMinimumWidth(145)
        self.tree.itemSelectionChanged.connect(self.on_tree_select)
        ml.addWidget(self.tree,1)
        self.splitter.addWidget(model_host)
        center=QWidget();centcol=QVBoxLayout(center);centcol.setContentsMargins(0,0,0,0);centcol.setSpacing(0)
        bar=QFrame();bar.setObjectName('viewportBar')
        strip=QHBoxLayout(bar);strip.setContentsMargins(12,6,9,6);strip.setSpacing(10)
        strip.addWidget(QLabel('PLANO XY   /   CASO'))
        self.cases=QComboBox();self.cases.setMinimumWidth(200)
        self.cases.currentTextChanged.connect(self.on_case)
        strip.addWidget(self.cases);strip.addStretch()
        self.snap=QCheckBox('Snap 50 mm');self.snap.setChecked(True)
        self.snap.toggled.connect(lambda checked:setattr(self.view,'snap_enabled',checked))
        strip.addWidget(self.snap)
        self.calc_badge=QLabel('NÃO CALCULADO');self.calc_badge.setObjectName('calcPending')
        strip.addWidget(self.calc_badge)
        centcol.addWidget(bar)
        self.center_split=QSplitter(Qt.Orientation.Vertical)
        centcol.addWidget(self.center_split,1)
        self.view=TrussView();self.center_split.addWidget(self.view)
        self.bottom_tabs=QTabWidget();self.bottom_tabs.setObjectName('bottomDock')
        self.quick_table=QTableWidget(0,4)
        self.quick_table.setHorizontalHeaderLabels(['Barra','Família / Grupo','N (kN)','Seção'])
        self.quick_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.quick_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.quick_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.quick_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.quick_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        self.quick_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch)
        self.quick_table.cellClicked.connect(self.quick_select_member)
        self.bottom_tabs.addTab(self.quick_table,'Forças nas barras')
        self.dock_info=QLabel('F5 — calcular para carregar os resultados. Os dados anteriores não são exibidos após edição.')
        self.dock_info.setWordWrap(True);self.dock_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bottom_tabs.addTab(self.dock_info,'Estado da análise')
        self.center_split.addWidget(self.bottom_tabs)
        self.center_split.setSizes([560,175]);self.center_split.setStretchFactor(0,1)
        self.view.selected.connect(self.on_scene_selected)
        self.view.add_node.connect(self.create_node)
        self.view.add_member.connect(self.create_member)
        self.view.split_member.connect(self.split_member)
        self.view.moved.connect(self.move_nodes)
        self.view.status_text.connect(self.status)
        self.splitter.addWidget(center)
        self.task_host=QWidget();self.task_host.setObjectName('taskPanel')
        task_layout=QVBoxLayout(self.task_host);task_layout.setContentsMargins(8,8,8,8);task_layout.setSpacing(6)
        task_title=QLabel('TAREFAS E PROPRIEDADES');task_title.setObjectName('panelHeading')
        task_layout.addWidget(task_title)
        self.task_tree=QTreeWidget();self.task_tree.setHeaderHidden(True)
        self.task_tree.setMaximumHeight(176)
        self.task_tree.itemClicked.connect(self.task_clicked)
        task_layout.addWidget(self.task_tree)
        self.info_tabs=QTabWidget();self.info_tabs.setMinimumWidth(340)
        self.info_tabs.tabBar().hide()
        self.info_tabs.currentChanged.connect(self.update_task_selection)
        task_layout.addWidget(self.info_tabs,1)
        self.splitter.addWidget(self.task_host)
        self.splitter.setSizes([230,895,445]);self.splitter.setStretchFactor(1,1)
        self._build_model_tab();self._build_property_tab();self._build_loads_tab();self._build_results_tab()
        self._build_engineering_tabs()
        self.setup_task_tree()
        self.status_label=QLabel('Pronto · Análise 2D · ELU normativo não verificado')
        self.status_label.setObjectName('status');main.addWidget(self.status_label)

    def _build_model_tab(self):
        tab=QWidget();col=QVBoxLayout(tab)
        self.geometry_box=QGroupBox('Geometria paramétrica');form=QFormLayout(self.geometry_box)
        self.geom_fields={}
        definitions=[('span_m','Vão (m)',16.,.1,500.,5,.25),('frame_spacing_m','Entre pórticos (m)',5.,.1,100.,5,.25),
            ('height_m','Altura (m)',1.,.05,50.,5,.05),('rise_m','Desnível (m)',.5,0.,30.,5,.05)]
        for key,label,default,minimum,maximum,decimals,step in definitions:
            widget=_spin(default,minimum,maximum,decimals,step);self.geom_fields[key]=widget
            widget.editingFinished.connect(self.change_geometry);form.addRow(label,widget)
        self.panels=QSpinBox();self.panels.setRange(2,40);self.panels.editingFinished.connect(self.change_geometry)
        form.addRow('Painéis',self.panels)
        self.shape=QComboBox();self.shape.addItems(['parallel','single','gable','trapezoid'])
        self.shape.currentTextChanged.connect(self.change_geometry);form.addRow('Forma',self.shape)
        self.topology=QComboBox();self.topology.addItems(['Pratt','Howe','Warren'])
        self.topology.currentTextChanged.connect(self.change_geometry);form.addRow('Triangulação',self.topology)
        col.addWidget(self.geometry_box)
        self.cad_notice=QLabel('Edição CAD avançada cria modelo explícito.\n'
            'Voltar ao paramétrico descarta a geometria manual, após confirmação.')
        self.cad_notice.setWordWrap(True);col.addWidget(self.cad_notice)
        self.revert_button=QPushButton('Voltar ao modo paramétrico')
        self.revert_button.clicked.connect(self.revert_parametric);col.addWidget(self.revert_button)
        col.addStretch(1);self.info_tabs.addTab(tab,'Geometria')

    def _build_property_tab(self):
        tab=QWidget();col=QVBoxLayout(tab)
        self.selection_label=QLabel('Selecione um nó ou barra no viewport')
        self.selection_label.setWordWrap(True);col.addWidget(self.selection_label)
        g=QGroupBox('Propriedades do nó');f=QFormLayout(g)
        self.node_id=QLineEdit();self.node_id.setReadOnly(True);f.addRow('ID',self.node_id)
        self.node_x=_spin(0,-1e9,1e9,2,50);self.node_y=_spin(0,-1e9,1e9,2,50)
        f.addRow('X (mm)',self.node_x);f.addRow('Y (mm)',self.node_y)
        self.support_x=QCheckBox('Restringir UX');self.support_y=QCheckBox('Restringir UY')
        f.addRow('Apoio',self.support_x);f.addRow('',self.support_y)
        self.apply_node=QPushButton('Aplicar posição e apoios');self.apply_node.clicked.connect(self.apply_node_properties)
        f.addRow(self.apply_node);col.addWidget(g)
        g2=QGroupBox('Propriedades das barras');ff=QFormLayout(g2)
        self.member_info=QLabel('Selecione uma barra');self.member_info.setWordWrap(True)
        ff.addRow(self.member_info)
        self.group=QComboBox();self.group.addItems(['superior','inferior','montante','diagonal'])
        ff.addRow('Grupo',self.group)
        change=QPushButton('Aplicar grupo às barras selecionadas');change.clicked.connect(self.change_group)
        ff.addRow(change);col.addWidget(g2)
        col.addStretch(1);self.info_tabs.addTab(tab,'Propriedades')

    def _build_loads_tab(self):
        tab=QWidget();col=QVBoxLayout(tab)
        row=QHBoxLayout();self.load_case=QComboBox()
        self.load_case.currentTextChanged.connect(self.refresh_load_table)
        row.addWidget(self.load_case,1)
        button=QPushButton('Novo caso');button.clicked.connect(self.add_case);row.addWidget(button)
        col.addLayout(row)
        self.load_table=QTableWidget(0,4)
        self.load_table.setHorizontalHeaderLabels(['Nó','Fx','Fy','Unid.'])
        self.load_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.load_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.load_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.load_table.itemSelectionChanged.connect(self.load_row_selected)
        col.addWidget(self.load_table,1)
        nodal=QGroupBox('Inserção/edição nodal');fields=QFormLayout(nodal)
        self.load_node=QComboBox();fields.addRow('Nó',self.load_node)
        self.fx=_spin(0,-1e9,1e9,2,10);self.fy=_spin(0,-1e9,1e9,2,10)
        fields.addRow('Fx',self.fx);fields.addRow('Fy',self.fy)
        self.force_unit=QComboBox();self.force_unit.addItems(['kgf','tf','kN','N'])
        fields.addRow('Unidade',self.force_unit)
        btn=QHBoxLayout();new_load=QPushButton('Nova');new_load.clicked.connect(self.clear_load_selection)
        a=QPushButton('Inserir/atualizar');a.clicked.connect(self.add_load)
        b=QPushButton('Remover');b.clicked.connect(self.remove_load)
        btn.addWidget(new_load);btn.addWidget(a);btn.addWidget(b);fields.addRow(btn)
        col.addWidget(nodal)
        self.load_note=QLabel('Forças explícitas por nó. Para ações superficiais, lineares e vento, acesse Ações gerais.');self.load_note.setWordWrap(True)
        col.addWidget(self.load_note)
        self.info_tabs.addTab(tab,'Cargas')

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
        self.result_table.setHorizontalHeaderLabels(['Barra','Grupo','N (kN)','Perfil'])
        self.result_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_table.itemSelectionChanged.connect(self.select_result)
        col.addWidget(self.result_table,1)
        self.critical_detail=QLabel('Compressão azul · Tração vermelha');self.critical_detail.setWordWrap(True)
        col.addWidget(self.critical_detail)
        self.info_tabs.addTab(tab,'Resultados')

    def open_3d(self):
        """Janela não modal: visualização tridimensional, sem solver 3D."""
        if self._view3d is not None and self._view3d.isVisible():
            self._view3d.raise_();self._view3d.activateWindow();return
        self._view3d=Truss3DDialog(self.session,self.case_id,self)
        self._view3d.show()

    def _shortcuts(self):
        for key,func in [('Ctrl+O',self.open),('Ctrl+S',self.save),('Ctrl+Z',self.undo),('Ctrl+Y',self.redo),
                         ('F5',self.calculate),('Delete',self.delete_selected),('F',self.fit)]:
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
        if self._view3d is not None and self._view3d.isVisible():
            self._view3d.case_id=None
            self._view3d.refresh_model()
        self.status(f'{reason} · análise anterior invalidada');return True

    def refresh(self,fit=False):
        self._refreshing=True
        try:
            model=self.session.model;project=self.session.project
            self.tree.blockSignals(True);self.tree.clear()
            nodes_root=QTreeWidgetItem(['Nós']);members_root=QTreeWidgetItem(['Barras']);drafts_root=QTreeWidgetItem(['Nós em criação'])
            self.tree.addTopLevelItems([nodes_root,members_root,drafts_root])
            for n in model.nodes:
                node=QTreeWidgetItem([n.id]);node.setData(0,Qt.ItemDataRole.UserRole,('node',n.id));nodes_root.addChild(node)
            for m in model.members:
                item=QTreeWidgetItem([f'{m.id} · {m.group}']);item.setData(0,Qt.ItemDataRole.UserRole,('member',m.id));members_root.addChild(item)
            for n in project.get('cad_drafts',[]):
                item=QTreeWidgetItem([n['id']+' (rascunho)']);item.setData(0,Qt.ItemDataRole.UserRole,('node',n['id']));drafts_root.addChild(item)
            nodes_root.setExpanded(False);members_root.setExpanded(False);drafts_root.setExpanded(True)
            self.tree.blockSignals(False)
            options=[x['id'] for x in project.get('load_cases',[])]+[x['id'] for x in project.get('combinations',[])]
            previous=self.case_id
            self.cases.blockSignals(True);self.cases.clear();self.cases.addItems(options)
            self.case_id=previous if previous in options else next(iter(options),None)
            if self.case_id:self.cases.setCurrentText(self.case_id)
            self.cases.blockSignals(False)
            self.load_case.blockSignals(True);self.load_case.clear()
            self.load_case.addItems([x['id'] for x in project.get('load_cases',[]) if x.get('kind')=='nodal'])
            self.load_case.blockSignals(False)
            self.load_node.clear();self.load_node.addItems([n.id for n in model.nodes]+[n['id'] for n in project.get('cad_drafts',[])])
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
            self.view.set_tool(self.view.tool)
            self.refresh_load_table();self.refresh_result_table();self.refresh_engineering_tabs()
            self.calc_badge.setText('CALCULADO' if self.session.result else 'NÃO CALCULADO')
            self.calc_badge.setObjectName('calcReady' if self.session.result else 'calcPending')
            self.calc_badge.style().unpolish(self.calc_badge);self.calc_badge.style().polish(self.calc_badge)
            self.setWindowTitle(APP_TITLE+('  *' if self._dirty else '')+(f'  — {self.filepath.name}' if self.filepath else ''))
        finally:self._refreshing=False

    def choose_tool(self,tool):
        self.view.set_tool(tool)
        if tool in ('node','bar','split','move'):self.info_tabs.setCurrentIndex(1)

    def on_case(self,text):
        if self._refreshing:return
        self.case_id=text;self.view.render(self.session,self.case_id)
        self.refresh_result_table()
        if self._view3d is not None and self._view3d.isVisible():
            self._view3d.case_id=self.case_id;self._view3d.redraw()

    def on_tree_select(self):
        if self._refreshing:return
        selected=[item.data(0,Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()]
        self._update_selection([x for x in selected if x],from_tree=True)

    def on_scene_selected(self,selected):
        if self._refreshing:return
        self._update_selection(selected)

    def _update_selection(self,selected,from_tree=False):
        self._selected=selected
        if not selected:self.selection_label.setText('Selecione um nó ou barra');return
        kind,id=selected[0]
        if kind=='node':
            nodes={n.id:n for n in self.session.model.nodes}
            nodes.update({n['id']:type('Draft',(),{'x':n['x_mm'],'y':n['y_mm']})() for n in self.session.project.get('cad_drafts',[])})
            if id in nodes:
                n=nodes[id];self.node_id.setText(id);self.node_x.setValue(n.x);self.node_y.setValue(n.y)
                ux,uy=self.session.model.supports.get(id,(False,False))
                self.support_x.setChecked(ux);self.support_y.setChecked(uy)
                self.load_node.setCurrentText(id)
                self.selection_label.setText(f'Nó {id}  |  X={n.x:.2f} mm  Y={n.y:.2f} mm')
                self.info_tabs.setCurrentIndex(1)
        else:
            m=next((m for m in self.session.model.members if m.id==id),None)
            if m:
                self.member_info.setText(f'{m.id} · {m.i} → {m.j}\n{m.profile}\nL={self.session.model.member_length(m):.2f} mm')
                self.group.setCurrentText(m.group)
                self.selection_label.setText(f'{len(selected)} elemento(s) selecionado(s)')
                self.info_tabs.setCurrentIndex(1)

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
            p=editing.move_nodes(self.session.project,self.session.model,{nid:(self.node_x.value(),self.node_y.value())})
            if nid not in {n['id'] for n in p.get('cad_drafts',[])}:
                d=p['model_override'];d['supports']=[s for s in d['supports'] if s['node']!=nid]
                if self.support_x.isChecked() or self.support_y.isChecked():
                    d['supports'].append({'node':nid,'ux':self.support_x.isChecked(),'uy':self.support_y.isChecked()})
        except Exception as exc:QMessageBox.warning(self,'Propriedades',str(exc));return
        self._apply(p,f'Propriedades de {nid} atualizadas')

    def change_geometry(self,*_):
        if self._refreshing or 'model_override' in self.session.project:return
        p=deepcopy(self.session.project);geo=p['geometry']
        for key,widget in self.geom_fields.items():geo[key]=widget.value()
        geo['panels']=self.panels.value();geo['roof_shape']=self.shape.currentText()
        geo['truss_type']=self.topology.currentText()
        self._apply(p,'Geometria paramétrica',fit=True)

    def revert_parametric(self):
        if QMessageBox.question(self,'Retornar ao paramétrico',
          'Descartar edições CAD, nós criados e subdivisões?')!=QMessageBox.StandardButton.Yes:return
        p=deepcopy(self.session.project);p.pop('model_override',None);p.pop('cad_drafts',None);p.pop('cad_import',None)
        # hipóteses particulares a nós e barras precisam ser revisadas
        p['stability']={};self._apply(p,'Modo paramétrico restaurado',fit=True)

    def add_case(self):
        name,ok=QInputDialog.getText(self,'Caso nodal','Identificador, sem espaços:')
        if not ok:return
        try:
            p=deepcopy(self.session.project)
            if not name or len(name)>32 or not name.replace('_','').isalnum():raise ValueError('ID inválido')
            if name in [x['id'] for x in p['load_cases']]:raise ValueError('ID já existe')
            p['load_cases'].append({'id':name,'name':name,'kind':'nodal','loads':[]})
        except Exception as exc:QMessageBox.warning(self,'Caso nodal',str(exc));return
        if self._apply(p,'Caso de carga adicionado'):self.load_case.setCurrentText(name)

    def clear_load_selection(self):
        self.load_table.clearSelection();self.load_table.setCurrentCell(-1,-1)
        self.fx.setValue(0);self.fy.setValue(0)

    def load_row_selected(self):
        row=self.load_table.currentRow()
        if row<0:return
        cid=self.load_case.currentText()
        case=next((x for x in self.session.project.get('load_cases',[]) if x['id']==cid),None)
        if case and row<len(case.get('loads',[])):
            r=case['loads'][row];self.load_node.setCurrentText(r['node'])
            self.fx.setValue(r['fx']);self.fy.setValue(r['fy']);self.force_unit.setCurrentText(r['force_unit'])

    def add_load(self):
        cid=self.load_case.currentText()
        if not cid:
            QMessageBox.information(self,'Cargas','Crie primeiro um caso de carga nodal.');return
        try:
            case=next(x for x in self.session.project['load_cases'] if x['id']==cid)
            row=self.load_table.currentRow();idx=row if row>=0 and row<len(case['loads']) else None
            p=deepcopy(self.session.project)
            target=next(x for x in p['load_cases'] if x['id']==cid)
            load={'node':self.load_node.currentText(),'fx':self.fx.value(),'fy':self.fy.value(),
                  'force_unit':self.force_unit.currentText()}
            if idx is None:target['loads'].append(load)
            else:target['loads'][idx]=load
        except Exception as exc:QMessageBox.warning(self,'Carga nodal',str(exc));return
        self._apply(p,'Carga nodal alterada');self.view.show_forces=True;self.view.render(self.session,self.case_id)

    def remove_load(self):
        cid=self.load_case.currentText();row=self.load_table.currentRow()
        if row<0:return
        p=deepcopy(self.session.project)
        case=next((x for x in p['load_cases'] if x['id']==cid),None)
        if not case or row>=len(case.get('loads',[])):return
        case['loads'].pop(row);self._apply(p,'Carga removida')

    def refresh_load_table(self,*_):
        if not hasattr(self,'load_table'):return
        cid=self.load_case.currentText();case=next((x for x in self.session.project.get('load_cases',[]) if x['id']==cid),None)
        rows=case.get('loads',[]) if case else []
        self.load_table.blockSignals(True);self.load_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,key in enumerate(('node','fx','fy','force_unit')):
                val=r.get(key,'');self.load_table.setItem(i,j,QTableWidgetItem(f'{val:.2f}' if isinstance(val,float) else str(val)))
        self.load_table.blockSignals(False)

    def calculate(self):
        try:
            self.session.calculate()
        except Exception as exc:
            QMessageBox.warning(self,'Não foi possível analisar',str(exc));return
        self.status('Análise concluída · verificar estados-limites e travamentos separadamente')
        self.refresh();self.info_tabs.setCurrentIndex(3)

    def refresh_result_table(self,*_):
        if not hasattr(self,'result_table'):return
        res=self.session.result
        if not res:
            self.result_table.setRowCount(0);self.results_info.setText('Análise desatualizada — pressione F5');self.refresh_quick_table();return
        cid=self.case_id or next(iter(res['analyses']),None)
        if cid not in res['analyses']:return
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
            for j,val in enumerate((m.id,m.group,f'{force(m.id)/1000:+.2f}',m.profile)):
                item=QTableWidgetItem(str(val))
                if j==2:item.setForeground(QColor('#C53646' if force(m.id)>0 else '#2666B8'))
                self.result_table.setItem(i,j,item)
        self.result_table.blockSignals(False)
        self.results_info.setText(f'{mode} · {cid} · {len(records)} barras · N>0 tração · N<0 compressão')
        self.refresh_quick_table()

    def select_result(self):
        row=self.result_table.currentRow()
        if row<0:return
        item=self.result_table.item(row,0)
        if not item:return
        mid=item.text()
        self.view.scene().blockSignals(True)
        for x in self.view.scene().selectedItems():x.setSelected(False)
        if mid in self.view._members:self.view._members[mid].setSelected(True)
        self.view.scene().blockSignals(False)
        self._selected=[('member',mid)]
        e=self.session.result['envelope'][mid]
        self.critical_detail.setText(f'{mid}\nTração máxima: {e["max_tension_n"]/1000:.2f} kN ({e["tension_case"]})\n'
            f'Compressão máxima: {e["max_compression_n"]/1000:.2f} kN ({e["compression_case"]})')

    def toggle_ids(self):self.view.show_ids=not self.view.show_ids;self.view.render(self.session,self.case_id)
    def toggle_efforts(self):self.view.show_efforts=not self.view.show_efforts;self.view.render(self.session,self.case_id)
    def toggle_deformed(self):self.view.show_deformed=not self.view.show_deformed;self.view.render(self.session,self.case_id)
    def toggle_loads(self):self.view.show_forces=not self.view.show_forces;self.view.render(self.session,self.case_id)
    def change_vertical(self):
        values=[1.,1.5,2.,3.,4.];current=self.view._vertical
        nxt=values[(values.index(current)+1)%len(values)] if current in values else 1.
        self.view.set_vertical_factor(nxt);self.status(f'Escala vertical de exibição ×{nxt:g} (não afeta cálculos)')
    def fit(self):self.view.fit()

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
        self._dirty=False;self.refresh(fit=True)
    def open(self):
        if not self._maybe_save():return
        name,_=QFileDialog.getOpenFileName(self,'Abrir projeto','','2DTruss (*.json)')
        if not name:return
        try:new_session=Session(load_project(name))
        except Exception as exc:QMessageBox.warning(self,'Abrir',str(exc));return
        self.session=new_session;self.filepath=Path(name);self.undo_stack.clear();self.redo_stack.clear()
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
            '01 · CONCEPÇÃO':('Geometria','Telha / modulação','Perfis'),
            '02 · MODELAGEM':('Propriedades','Estabilidade'),
            '03 · AÇÕES':('Cargas','Ações gerais','Combinações'),
            '04 · ANÁLISE':('Resultados','Alternativas','Diagnóstico'),
        }
        assigned=set()
        for title,labels in groups.items():
            root=QTreeWidgetItem([title]);self.task_tree.addTopLevelItem(root)
            root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for i in range(self.info_tabs.count()):
                label=self.info_tabs.tabText(i)
                if label in labels:
                    item=QTreeWidgetItem([label]);item.setData(0,Qt.ItemDataRole.UserRole,i)
                    root.addChild(item);self._task_by_index[i]=item;assigned.add(i)
            root.setExpanded(True)
        others=[i for i in range(self.info_tabs.count()) if i not in assigned]
        if others:
            root=QTreeWidgetItem(['05 · OUTROS']);self.task_tree.addTopLevelItem(root)
            for i in others:
                item=QTreeWidgetItem([self.info_tabs.tabText(i)])
                item.setData(0,Qt.ItemDataRole.UserRole,i);root.addChild(item)
                self._task_by_index[i]=item
            root.setExpanded(True)
        self.task_tree.blockSignals(False)
        self.update_task_selection(self.info_tabs.currentIndex())

    def task_clicked(self,item,column):
        index=item.data(0,Qt.ItemDataRole.UserRole)
        if isinstance(index,int):self.info_tabs.setCurrentIndex(index)

    def update_task_selection(self,index):
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

    def quick_select_member(self,row,column):
        item=self.quick_table.item(row,0)
        if not item:return
        mid=item.text();self._update_selection([('member',mid)])
        target=self.view._members.get(mid)
        if target is not None:
            self.view.scene().clearSelection();target.setSelected(True)

    def refresh_quick_table(self):
        if not hasattr(self,'quick_table'):return
        self.quick_table.blockSignals(True)
        try:
            data=self.session.result
            if not data or not self.case_id or self.case_id not in data.get('analyses',{}):
                self.quick_table.setRowCount(0)
                self.dock_info.setText('Modelo não calculado ou editado após a última análise.')
                return
            axial=data['analyses'][self.case_id].get('axial_n',{})
            records=sorted(self.session.model.members,key=lambda m:abs(axial.get(m.id,0)),reverse=True)
            self.quick_table.setRowCount(len(records))
            for i,m in enumerate(records):
                f=axial.get(m.id,0)
                for j,val in enumerate((m.id,m.group,f'{f/1000:+.2f}',m.profile)):
                    cell=QTableWidgetItem(str(val))
                    if j==2:cell.setForeground(QColor('#BC3D4E' if f>0 else '#2766A7'))
                    self.quick_table.setItem(i,j,cell)
            self.dock_info.setText(f'{len(records)} barras · {self.case_id} · valores do modelo calculado')
        finally:self.quick_table.blockSignals(False)



def start():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('2DTruss');app.setStyle('Fusion')
    window=DesktopApp();window.show()
    QTimer.singleShot(0,window.view.fit)
    return app.exec()
