"""Painéis nativos PySide6 para o fluxo completo do projetista.

Todos os cálculos continuam no poe_truss (Python, solver axial XY).
Sem aprovação ELU, geração automática de coeficientes normativos ou análise 3D.
"""
from __future__ import annotations
from copy import deepcopy
from queue import Queue, Empty
from threading import Thread
from PySide6.QtCore import Qt,QSignalBlocker,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGroupBox,QFormLayout,QLabel,
    QComboBox,QPushButton,QDoubleSpinBox,QSpinBox,QTableWidget,QTableWidgetItem,
    QHeaderView,QInputDialog,QMessageBox,QLineEdit,QTreeWidget,QTreeWidgetItem,
    QCheckBox,QAbstractItemView)
from desktop import workflow
from poe_truss.model import GROUPS,geometry_diagnostics
from poe_truss.materials import STEEL_GRADES
from poe_truss.search import suggest_geometry
from .action_icons import action_icon
from .profile_picker import ProfilePicker


def field(value=0,low=0,high=1e8,dec=2,step=1):
    f=QDoubleSpinBox();f.setRange(low,high);f.setDecimals(dec);f.setSingleStep(step);f.setValue(value)
    return f


def row_buttons(*commands):
    w=QWidget();h=QHBoxLayout(w);h.setContentsMargins(0,0,0,0)
    for label,callback,icon in commands:
        b=QPushButton(action_icon(icon), label);b.clicked.connect(callback);h.addWidget(b)
    return w


def labeled_combo(options):
    combo = QComboBox()
    for key, label in options:
        combo.addItem(label, key)
    return combo


class WorkflowMixin:
    def _build_engineering_tabs(self):
        self._build_profiles_tab()
        self._build_cases_tab()
        self._build_combinations_tab()
        self._build_stability_tab()
        self._build_search_tab()
        self._build_diagnostics_tab()
        self.info_tabs.setUsesScrollButtons(True)
        self._search_queue=Queue();self._search_running=False
        self._search_timer=QTimer(self);self._search_timer.setInterval(100)
        self._search_timer.timeout.connect(self._poll_search)

    def _build_profiles_tab(self):
        tab=QWidget();v=QVBoxLayout(tab)
        box=QGroupBox('Seção do grupo');f=QFormLayout(box)
        self.section_group=QComboBox();self.section_group.addItems(GROUPS)
        self.section_group.currentTextChanged.connect(self._populate_section)
        self.section_picker = ProfilePicker()
        self.section_picker.changed.connect(self._apply_section)
        f.addRow('Grupo', self.section_group)
        f.addRow(self.section_picker)
        self.section_details = QLabel()
        self.section_details.setWordWrap(True)
        f.addRow(self.section_details)
        v.addWidget(box)
        steel_box = QGroupBox('Aço do projeto')
        steel_layout = QVBoxLayout(steel_box)
        self.steel_grade = QComboBox()
        self.steel_grade.addItem('Propriedades do arquivo', None)
        for grade_id, grade in STEEL_GRADES.items():
            self.steel_grade.addItem(f'{grade.name} · {grade.standard}', grade_id)
        self.steel_grade.activated.connect(self._apply_steel)
        steel_layout.addWidget(self.steel_grade)
        self.steel_details = QLabel()
        self.steel_details.setWordWrap(True)
        steel_layout.addWidget(self.steel_details)
        v.addWidget(steel_box)
        box=QGroupBox('Modulação geométrica');f=QFormLayout(box)
        self.purlin_step=field(1.2,0.1,20,3,.1)
        self.angle_min=field(45,0,90,1,1);self.angle_max=field(60,0,90,1,1)
        f.addRow('Passo máximo das terças (m)',self.purlin_step)
        f.addRow('Diagonal mínima (°)',self.angle_min)
        f.addRow('Diagonal máxima (°)',self.angle_max)
        f.addRow(row_buttons(('Aplicar critérios',self._apply_modulation,'check')))
        v.addWidget(box)
        roof=QGroupBox('Telha e terças · dados informados pelo projetista')
        rf=QFormLayout(roof)
        self.roof_vendor=QLineEdit();self.roof_model=QLineEdit()
        self.roof_mass=field(8,0,200,2,1)
        rf.addRow('Fabricante',self.roof_vendor);rf.addRow('Modelo',self.roof_model)
        rf.addRow('Massa da telha (kg/m²)',self.roof_mass)
        rf.addRow(row_buttons(('Registrar telha + ação G2',self._apply_roof,'check')))
        v.addWidget(roof)
        v.addStretch(1)
        self.profile_tab=tab;self._add_inspector_page(tab,'Perfis')

    def _populate_section(self,*_):
        g=self.section_group.currentText() if hasattr(self,'section_group') else ''
        if not g:return
        spec=self.session.project.get('sections',{}).get(g,{})
        self.section_picker.set_section(self.session.catalog, spec)
        p = self.session.catalog.get(spec.get('profile'))
        if p is not None:
            self.section_details.setText(f'{p.family}  |  A = {p.area_mm2:.2f} mm²  |  '
                f'massa = {p.mass_kg_m:.3f} kg/m\nOrigem: {p.origin}\nQualidade: {p.quality}')
        else:
            self.section_details.clear()

    def _apply_section(self, profile, count):
        self.assign_section(self.section_group.currentText(), profile, count)

    def assign_section(self, group, profile, count):
        current = self.session.project.get('sections', {}).get(group, {})
        if ('model_override' not in self.session.project
                and current.get('profile') == profile and current.get('count', 1) == count):
            return
        try:
            p=workflow.update_section(self.session.project,self.session.model,self.session.catalog,
                group, profile, count)
            self._apply(p,'Perfis atualizados; peso próprio será recalculado na próxima análise')
        except Exception as e:QMessageBox.warning(self,'Perfis',str(e))

    def _populate_steel(self):
        material = self.session.project.get('material', {})
        grade = STEEL_GRADES.get(material.get('grade_id'))
        if grade and any(material.get(key) != value for key, value in
                         [('E_MPa', grade.E), ('fy_MPa', grade.fy), ('fu_MPa', grade.fu)]):
            grade = None
        with QSignalBlocker(self.steel_grade):
            index = self.steel_grade.findData(material['grade_id']) if grade else 0
            self.steel_grade.setCurrentIndex(index)
        fu = f"{material['fu_MPa']} MPa" if 'fu_MPa' in material else 'em aberto'
        text = (f"E = {material.get('E_MPa', 200000)} MPa · "
                f"fy = {material.get('fy_MPa', 250)} MPa · fu {fu}")
        if grade:
            text += f'\n{grade.product} · {grade.source}'
        self.steel_details.setText(text)

    def _apply_steel(self, _index):
        grade_id = self.steel_grade.currentData()
        if grade_id is None:
            self._populate_steel()
            return
        updated = workflow.update_steel(self.session.project, grade_id)
        if updated != self.session.project:
            self._apply(updated, 'Aço do projeto atualizado')

    def _apply_roof(self):
        try:
            p=workflow.update_roof(self.session.project,self.roof_vendor.text(),
                self.roof_model.text(),self.roof_mass.value(),self.purlin_step.value())
            self._apply(p,'Telha e passo cadastrados: capacidade da telha NÃO verificada')
        except Exception as e:QMessageBox.warning(self,'Telhas',str(e))

    def _apply_modulation(self):
        if self.angle_min.value()>=self.angle_max.value():
            QMessageBox.warning(self,'Modulação','Ângulo mínimo deve ser inferior ao máximo');return
        p=deepcopy(self.session.project);g=p.setdefault('geometry',{})
        g.update(purlin_max_m=self.purlin_step.value(),angle_min_deg=self.angle_min.value(),
                 angle_max_deg=self.angle_max.value())
        self._apply(p,'Critérios de modulação atualizados')

    def _build_cases_tab(self):
        tab=QWidget();v=QVBoxLayout(tab)
        v.addWidget(QLabel('Ações: G, Q e vento · valores fornecidos pelo projetista'))
        self.action_case=QComboBox();self.action_case.currentTextChanged.connect(self._populate_case)
        self.action_case.activated.connect(lambda _: self._show_load_case(self.action_case.currentText()))
        v.addWidget(self.action_case)
        box=QGroupBox('Parâmetros do caso');f=QFormLayout(box)
        self.action_form = f
        self.action_name=QLineEdit()
        self.action_kind = labeled_combo([('self_weight', 'Peso próprio'), ('surface', 'Superficial'),
                                          ('line', 'Linear'), ('nodal', 'Nodal')])
        self.action_kind.currentIndexChanged.connect(self._case_controls)
        self.action_value=field(0,0,1e9,3,1)
        self.action_force_unit=QComboBox();self.action_force_unit.addItems(['kgf','kN','tf','N'])
        self.action_application = labeled_combo([('top', 'Banzo superior'), ('bottom', 'Banzo inferior')])
        self.action_basis = labeled_combo([('projected', 'Projeção horizontal'),
                                           ('roof_surface', 'Inclinação da cobertura')])
        self.action_direction = labeled_combo([
            ('down', 'Para baixo'), ('up', 'Para cima'), ('outward_normal', 'Normal para fora'),
            ('inward_normal', 'Normal para dentro'), ('right', 'Para a direita'), ('left', 'Para a esquerda'),
        ])
        self.action_zone = labeled_combo([('all', 'Toda a treliça'), ('left', 'Metade esquerda'),
                                         ('right', 'Metade direita')])
        for label,widget in [('Nome',self.action_name),('Tipo',self.action_kind),
            ('Intensidade',self.action_value),('Unidade força',self.action_force_unit),
            ('Aplicação',self.action_application),('Base geométrica',self.action_basis),
            ('Direção',self.action_direction),('Região',self.action_zone)]:f.addRow(label,widget)
        f.addRow(row_buttons(('Adicionar',self._new_action_case,'add'),('Aplicar',self._apply_action_case,'check'),
                              ('Excluir',self._delete_action_case,'delete')))
        f.addRow(row_buttons(('Conferir distribuição nodal',self._audit_selected_case,'table')))
        v.addWidget(box)
        self.action_audit=QLabel('Casos superficiais são distribuídos aos nós pelo motor.')
        self.action_audit.setWordWrap(True);v.addWidget(self.action_audit)
        v.addStretch(1);self.actions_tab=tab;self._add_inspector_page(tab,'Ações gerais')

    def _case_controls(self,*_):
        kind = self.action_kind.currentData()
        general = kind in ('surface', 'line')
        self.action_value.setSuffix(' /m²' if kind == 'surface' else ' /m')
        for w in (self.action_value,self.action_force_unit,self.action_application,self.action_basis,
                  self.action_direction,self.action_zone):
            self.action_form.setRowVisible(w, general)
        if kind=='nodal':self.action_audit.setText('Edite as forças em Cargas nodais.')
        elif kind=='self_weight':self.action_audit.setText('Peso próprio: massa das barras e gravidade nominal g=10 m/s².')
        elif kind=='surface':self.action_audit.setText('Intensidade em força/m²; áreas tributárias obtidas do modelo.')
        else:self.action_audit.setText('Intensidade em força/m; comprimento inclinado ou projetado.')

    def _populate_case(self,*_):
        cid=self.action_case.currentText()
        case=next((x for x in self.session.project.get('load_cases',[]) if x['id']==cid),None)
        if not case:return
        self.action_force_unit.setCurrentText(case.get('force_unit', 'kgf'))
        pairs=[(self.action_kind,case.get('kind','surface')),
            (self.action_application,case.get('application','top')),
            (self.action_basis,case.get('basis','projected')),
            (self.action_direction,case.get('direction','down')),
            (self.action_zone,case.get('zone','all'))]
        for combo, key in pairs:
            with QSignalBlocker(combo):
                combo.setCurrentIndex(combo.findData(key))
        self.action_name.setText(case.get('name',cid))
        self.action_value.setValue(float(case.get('value',0)))
        self._case_controls()

    def _audit_selected_case(self):
        cid=self.action_case.currentText()
        case=next((r for r in self.session.project.get('load_cases',[]) if r['id']==cid),None)
        if not case:return
        try:
            from poe_truss.loads import build_case_loads
            _,audit=build_case_loads(self.session.model,case)
            self.action_audit.setText(f'{cid}: {audit["n_entries"]} parcelas; '
                f'ΣFx = {audit["sum_fx_n"]/1000:+.3f} kN; '
                f'ΣFy = {audit["sum_fy_n"]/1000:+.3f} kN')
            self._show_load_case(cid)
        except Exception as e:QMessageBox.warning(self,'Auditoria de ações',str(e))

    def _new_action_case(self):
        name,ok=QInputDialog.getText(self,'Novo caso','Identificador do caso:')
        if not ok:return
        try:
            p=workflow.add_load_case(self.session.project,name,'surface')
            if self._apply(p,'Caso incluído'):
                self.action_case.setCurrentText(name.strip())
                self._show_load_case(name.strip())
        except Exception as e:QMessageBox.warning(self,'Ações',str(e))

    def _apply_action_case(self):
        cid=self.action_case.currentText()
        if not cid:return
        try:
            p=workflow.update_load_case(self.session.project,cid,
                name=self.action_name.text(),kind=self.action_kind.currentData(),
                value=self.action_value.value(),force_unit=self.action_force_unit.currentText(),
                application=self.action_application.currentData(),basis=self.action_basis.currentData(),
                direction=self.action_direction.currentData(),zone=self.action_zone.currentData())
            if self._apply(p,'Caso de carga modificado'):
                self._show_load_case(cid)
        except Exception as e:QMessageBox.warning(self,'Ações',str(e))

    def _delete_action_case(self):
        try:self._apply(workflow.delete_load_case(self.session.project,self.action_case.currentText()),'Caso excluído')
        except Exception as e:QMessageBox.warning(self,'Ações',str(e))

    def open_general_actions(self):
        if self.mode_3d.isChecked():
            self.set_3d_visible(False)
        if self.focus_button.isChecked():
            self._set_drawing_only(False)
        self._show_inspector(self.actions_tab)
        if self.action_case.findText(self.case_id or '') >= 0:
            self.action_case.setCurrentText(self.case_id)
        self._show_load_case(self.action_case.currentText())

    def _build_combinations_tab(self):
        tab=QWidget();v=QVBoxLayout(tab)
        v.addWidget(QLabel('Combinações com fatores manuais assinados. Sem geração normativa automática.'))
        self.combination=QComboBox();self.combination.currentTextChanged.connect(self._populate_combination)
        v.addWidget(self.combination)
        self.factor_table=QTableWidget(0,2)
        self.factor_table.setHorizontalHeaderLabels(['Caso','Fator'])
        self.factor_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.factor_table,1)
        v.addWidget(row_buttons(('Nova combinação',self._new_combination,'add'),
                                ('Aplicar fatores',self._apply_combination,'check'),
                                ('Excluir',self._delete_combination,'delete')))
        self.combo_tab=tab;self._add_inspector_page(tab,'Combinações')

    def _populate_combination(self,*_):
        cid=self.combination.currentText()
        combo=next((x for x in self.session.project.get('combinations',[]) if x['id']==cid),{})
        cases=self.session.project.get('load_cases',[])
        self.factor_table.setRowCount(len(cases))
        for i,c in enumerate(cases):
            item=QTableWidgetItem(c['id']);item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.factor_table.setItem(i,0,item)
            sp=field(float(combo.get('factors',{}).get(c['id'],0)),-100,100,4,.1)
            self.factor_table.setCellWidget(i,1,sp)

    def _new_combination(self):
        cid,ok=QInputDialog.getText(self,'Combinação','ID da combinação:')
        if not ok:return
        try:
            if self._apply(workflow.add_combination(self.session.project,cid),'Combinação criada'):
                self.combination.setCurrentText(cid.strip())
        except Exception as e:QMessageBox.warning(self,'Combinações',str(e))

    def _apply_combination(self):
        cid=self.combination.currentText()
        if not cid:return
        factors={}
        for i in range(self.factor_table.rowCount()):
            key=self.factor_table.item(i,0).text()
            factors[key]=self.factor_table.cellWidget(i,1).value()
        try:self._apply(workflow.update_combination(self.session.project,cid,factors),'Combinação alterada')
        except Exception as e:QMessageBox.warning(self,'Combinações',str(e))

    def _delete_combination(self):
        cid=self.combination.currentText()
        p=deepcopy(self.session.project);p['combinations']=[c for c in p.get('combinations',[]) if c['id']!=cid]
        self._apply(p,'Combinação excluída')

    def _build_stability_tab(self):
        tab=QWidget();v=QVBoxLayout(tab)
        v.addWidget(QLabel('Comprimentos de flambagem DECLARADOS, sem comprovar travamentos.'))
        b=QGroupBox('Hipóteses por grupo');f=QFormLayout(b)
        self.stab_group=QComboBox();self.stab_group.addItems(GROUPS)
        self.stab_group.currentTextChanged.connect(self._populate_stability)
        self.kin=field(1,.05,10,2,.05);self.kout=field(1,.05,10,2,.05)
        self.stab_lin=field(0,0,1000000,1,100)
        self.stab_lout=field(0,0,1000000,1,100)
        self.stab_torsion=field(0,0,1000000,1,100)
        self.stab_axis_in=QComboBox();self.stab_axis_in.addItems(['x','y'])
        self.stab_axis_out=QComboBox();self.stab_axis_out.addItems(['y','x'])
        self.stab_rot=field(0,-180,180,1,5)
        self.stab_ref=QLineEdit()
        for label,widget in [('Grupo',self.stab_group),('K no plano',self.kin),('K fora do plano',self.kout),
            ('L no plano (mm; 0=barra)',self.stab_lin),('L lateral (mm; 0=pendente)',self.stab_lout),
            ('L torsional (mm; 0=pendente)',self.stab_torsion),('Eixo no plano',self.stab_axis_in),
            ('Eixo lateral',self.stab_axis_out),('Rotação (°)',self.stab_rot),
            ('Referência do travamento',self.stab_ref)]:f.addRow(label,widget)
        f.addRow(row_buttons(('Aplicar hipóteses',self._apply_stability,'check')))
        v.addWidget(b)
        self.stability_status=QLabel('Sem dimensionamento resistente.');self.stability_status.setWordWrap(True)
        v.addWidget(self.stability_status);v.addStretch(1)
        self.stability_tab=tab;self._add_inspector_page(tab,'Estabilidade')

    def _populate_stability(self,*_):
        spec=self.session.project.get('stability',{}).get('groups',{}).get(self.stab_group.currentText(),{})
        for widget,key,default in ((self.kin,'k_in_plane',1),(self.kout,'k_out_of_plane',1),
            (self.stab_lin,'unbraced_in_plane_mm',0),(self.stab_lout,'unbraced_out_of_plane_mm',0),
            (self.stab_torsion,'torsion_unbraced_mm',0),(self.stab_rot,'rotation_deg',0)):
            widget.setValue(float(spec.get(key,default)))
        self.stab_axis_in.setCurrentText(spec.get('axis_in_plane','x'))
        self.stab_axis_out.setCurrentText(spec.get('axis_out_of_plane','y'))
        self.stab_ref.setText(spec.get('restraint_reference',''))

    def _apply_stability(self):
        try:
            p=workflow.update_stability_group(self.session.project,self.stab_group.currentText(),
                kin=self.kin.value(),kout=self.kout.value(),inplane_mm=self.stab_lin.value(),
                lateral_mm=self.stab_lout.value(),torsion_mm=self.stab_torsion.value(),
                axis_in=self.stab_axis_in.currentText(),axis_out=self.stab_axis_out.currentText(),
                rotation=self.stab_rot.value(),reference=self.stab_ref.text())
            self._apply(p,'Hipóteses de estabilidade alteradas')
        except Exception as e:QMessageBox.warning(self,'Estabilidade',str(e))

    def _build_search_tab(self):
        tab=QWidget();v=QVBoxLayout(tab)
        v.addWidget(QLabel('Até 3 alternativas por massa, flecha e modulação; sem resistência ELU.'))
        p=QGroupBox('Parâmetros da pesquisa');f=QFormLayout(p)
        self.search_case=QComboBox();f.addRow('Combinação/caso',self.search_case)
        self.search_flecha=field(250,50,2000,0,50);f.addRow('Limite L /',self.search_flecha)
        self.search_button=QPushButton(action_icon('compare'), 'Pesquisar alternativas')
        self.search_button.clicked.connect(self._start_search);f.addRow(self.search_button);v.addWidget(p)
        self.search_table=QTableWidget(0,5)
        self.search_table.setHorizontalHeaderLabels(['Painéis','Altura m','Massa kg','Flecha mm','Status'])
        self.search_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.search_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        v.addWidget(self.search_table,1)
        self.search_candidates=[]
        v.addWidget(row_buttons(('Adotar selecionada',self._adopt_search,'check'),
                                 ('Aplicar valores manuais',self._apply_manual,'check')))
        self.search_note=QLabel('Não altera parâmetros manuais fora das sugestões.');v.addWidget(self.search_note)
        self.search_tab=tab;self._add_inspector_page(tab,'Alternativas')

    def _start_search(self):
        if 'model_override' in self.session.project:
            QMessageBox.information(self,'Pesquisa','Otimize apenas geometrias paramétricas.');return
        if self._search_running:return
        self._search_running=True;self.search_button.setEnabled(False)
        project=deepcopy(self.session.project);catalog=self.session.catalog
        options={'case':self.search_case.currentText(),'flecha_rel':self.search_flecha.value()}
        def task():
            try:self._search_queue.put((project, suggest_geometry(project,catalog,options),None))
            except Exception as e:self._search_queue.put((project,None,str(e)))
        Thread(target=task,daemon=True).start()
        self._search_timer.start();self.search_note.setText('Pesquisa em execução…')

    def _poll_search(self):
        try:base,out,err=self._search_queue.get_nowait()
        except Empty:return
        self._search_timer.stop();self._search_running=False;self.search_button.setEnabled(True)
        if err:QMessageBox.warning(self,'Pesquisa geométrica',err);self.search_note.setText(err);return
        if base!=self.session.project:
            self.search_note.setText('Pesquisa desatualizada: modelo foi alterado.');return
        self.search_candidates=out['candidates'][:3]
        self.search_table.setRowCount(len(self.search_candidates))
        for i,c in enumerate(self.search_candidates):
            for j,val in enumerate((c['panels'],f'{c["height_m"]:.3f}',f'{c["mass_kg"]:.2f}',
                f'{c["max_abs_roof_mm"]:.2f}','Geom./ELS ok' if c['meets_geometric_service_criteria'] else 'Revisar')):
                item=QTableWidgetItem(str(val));item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
                self.search_table.setItem(i,j,item)
        self.search_note.setText(f'{out["evaluated"]} alternativas avaliadas; até 3 exibidas. Sem ELU.')

    def _adopt_search(self):
        i=self.search_table.currentRow()
        if i<0 or i>=len(self.search_candidates):return
        c=self.search_candidates[i]
        p=deepcopy(self.session.project)
        p['geometry'].update(panels=c['panels'],height_m=c['height_m'])
        self._apply(p,'Geometria sugerida adotada')

    def _apply_manual(self):
        self.info_tabs.setCurrentIndex(0)
        self.status('Informe livremente painéis e altura na aba Geometria; sugestões não são obrigatórias.')

    def _build_diagnostics_tab(self):
        tab=QWidget();v=QVBoxLayout(tab)
        v.addWidget(QLabel('Erros, avisos e pendências do modelo e da análise.'))
        self.diag_tree=QTreeWidget();self.diag_tree.setHeaderLabels(['Estado','Diagnóstico'])
        self.diag_tree.header().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.diag_tree.itemDoubleClicked.connect(self._locate_diagnostic)
        v.addWidget(self.diag_tree,1)
        v.addWidget(row_buttons(('Atualizar diagnóstico',self._populate_diagnostics,'diagnostic'),
                                 ('Calcular e conferir',self.calculate,'run')))
        v.addWidget(QLabel('Verificações de ELU, contraventamento e ligações seguem pendentes.'))
        self.diagnostics_tab=tab;self._add_inspector_page(tab,'Diagnóstico')

    def _populate_diagnostics(self):
        issues=workflow.project_diagnostics(self.session.project,self.session.model,self.session.result)
        self.diag_tree.clear()
        for x in issues:
            it=QTreeWidgetItem([x['level'].upper(),x['message']])
            if x['ref']:it.setData(0,Qt.ItemDataRole.UserRole,x['ref'])
            self.diag_tree.addTopLevelItem(it)

    def _locate_diagnostic(self,item,*_):
        ref=item.data(0,Qt.ItemDataRole.UserRole)
        if not ref:return
        kind,mid=ref
        member=self.view._members.get(mid) if kind=='member' else self.view._nodes.get(mid)
        if member:
            self.view.scene().clearSelection();member.setSelected(True)
            self.view.centerOn(member)

    def refresh_engineering_tabs(self):
        self.action_case.blockSignals(True)
        current=self.action_case.currentText();self.action_case.clear()
        self.action_case.addItems([c['id'] for c in self.session.project.get('load_cases',[])])
        if current in [self.action_case.itemText(i) for i in range(self.action_case.count())]:
            self.action_case.setCurrentText(current)
        self.action_case.blockSignals(False);self._populate_case()
        self.combination.blockSignals(True)
        current=self.combination.currentText();self.combination.clear()
        self.combination.addItems([c['id'] for c in self.session.project.get('combinations',[])])
        if current:self.combination.setCurrentText(current)
        self.combination.blockSignals(False);self._populate_combination()
        self.search_case.clear()
        self.search_case.addItems([c['id'] for c in self.session.project.get('combinations',[])]+[
            c['id'] for c in self.session.project.get('load_cases',[])])
        self._populate_section();self._populate_steel();self._populate_stability()
        geo=self.session.project.get('geometry',{})
        self.purlin_step.setValue(float(geo.get('purlin_max_m',1.2)))
        self.angle_min.setValue(float(geo.get('angle_min_deg',45)))
        self.angle_max.setValue(float(geo.get('angle_max_deg',60)))
        roof=self.session.project.get('roofing',{})
        self.roof_vendor.setText(str(roof.get('manufacturer','')))
        self.roof_model.setText(str(roof.get('model','')))
        self.roof_mass.setValue(float(roof.get('mass_kg_m2',8)))
        if self.session.result:
            pending=self.session.result.get('stability',{}).get('summary',{}).get('pending',0)
            self.stability_status.setText(f'{pending} barras com estabilidade pendente. Não equivale a ELU.')
        self._populate_diagnostics()
