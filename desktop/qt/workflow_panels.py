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
    QComboBox,QDoubleSpinBox,QSpinBox,QTableWidget,QTableWidgetItem,
    QHeaderView,QInputDialog,QMessageBox,QLineEdit,QTreeWidget,QTreeWidgetItem,
    QAbstractItemView)
from desktop import editing, workflow
from poe_truss.model import GROUPS,geometry_diagnostics
from poe_truss.loads import load_patterns, resolve_case_loads
from poe_truss.materials import STEEL_GRADES
from poe_truss.search import suggest_geometry
from .action_icons import IconButton
from .display_units import LoadField
from .profile_picker import ProfilePicker


def field(value=0,low=0,high=1e8,dec=2,step=1):
    f=QDoubleSpinBox();f.setRange(low,high);f.setDecimals(dec);f.setSingleStep(step);f.setValue(value)
    return f


def row_buttons(*commands):
    w=QWidget();h=QHBoxLayout(w);h.setContentsMargins(0,0,0,0)
    for label,callback,icon in commands:
        h.addWidget(IconButton(label, callback, icon))
    h.addStretch()
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
        self._build_static_cases_tab()
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
        self.action_case=QComboBox();self.action_case.currentTextChanged.connect(self._populate_case)
        self.action_case.activated.connect(lambda _: self._show_load_case(self.action_case.currentText()))
        command_line = QHBoxLayout()
        command_line.addWidget(self.action_case, 1)
        command_line.addWidget(row_buttons(('Adicionar padrão',self._new_action_case,'add'),
                                          ('Aplicar alterações',self._apply_action_case,'check'),
                                          ('Excluir padrão',self._delete_action_case,'delete'),
                                          ('Conferir distribuição nodal',self._audit_selected_case,'table')))
        v.addLayout(command_line)
        box=QGroupBox('Definição do padrão');f=QFormLayout(box)
        self.action_form = f
        self.action_name=QLineEdit()
        self.action_kind = labeled_combo([('self_weight', 'Peso próprio'), ('surface', 'Superficial'),
                                          ('line', 'Linear por banzo'), ('nodal', 'Nodal'),
                                          ('member_line', 'Linear nas barras selecionadas')])
        self.action_kind.currentIndexChanged.connect(self._case_controls)
        self.action_class = labeled_combo(workflow.ACTION_CLASSES.items())
        self.action_reference = QLabel()
        self.action_reference.setWordWrap(True)
        self.action_class.currentIndexChanged.connect(self._show_action_reference)
        self.action_value=LoadField(0,1e9)
        self.action_force_unit=QComboBox();self.action_force_unit.addItems(['kgf','kN','tf','N'])
        self.action_application = labeled_combo([('top', 'Banzo superior'), ('bottom', 'Banzo inferior')])
        self.action_basis = labeled_combo([('projected', 'Projeção horizontal'),
                                           ('roof_surface', 'Comprimento real')])
        self.action_direction = labeled_combo([
            ('down', 'Para baixo'), ('up', 'Para cima'), ('outward_normal', 'Normal para fora'),
            ('inward_normal', 'Normal para dentro'), ('right', 'Para a direita'), ('left', 'Para a esquerda'),
        ])
        self.action_members = QLineEdit()
        self.action_members.setReadOnly(True)
        self.action_members.setPlaceholderText('Selecione as barras no desenho')
        self.action_member_ids = []
        self.action_member_row = QWidget()
        members_layout = QHBoxLayout(self.action_member_row)
        members_layout.setContentsMargins(0, 0, 0, 0)
        members_layout.addWidget(self.action_members, 1)
        members_layout.addWidget(IconButton('Usar barras selecionadas no desenho', self._take_action_members, 'select'))
        self.action_member_mode = labeled_combo([('nodal', 'Forças nodais equivalentes'),
                                                 ('flexure', 'Forças nodais + cortante e momento local')])
        self.action_zone = labeled_combo([('all', 'Toda a treliça'), ('left', 'Metade esquerda'),
                                         ('right', 'Metade direita')])
        for label,widget in [('Nome',self.action_name),('Natureza',self.action_class),
            ('Referência', self.action_reference), ('Distribuição',self.action_kind),
            ('Intensidade',self.action_value),('Unidade força',self.action_force_unit),
            ('Aplicação',self.action_application),('Base geométrica',self.action_basis),
            ('Direção',self.action_direction),('Região',self.action_zone),
            ('Barras', self.action_member_row), ('Tratamento', self.action_member_mode)]:f.addRow(label,widget)
        v.addWidget(box)
        self.action_audit=QLabel('Casos superficiais são distribuídos aos nós pelo motor.')
        self.action_audit.setWordWrap(True);v.addWidget(self.action_audit)
        v.addStretch(1);self.actions_tab=tab
        self._add_load_dialog(tab, 'Tipos de Carregamentos', height=605)

    def _show_action_reference(self, *_):
        nature = self.action_class.currentData()
        reference = {
            'permanent': 'ABNT NBR 6120 · ações em edificações',
            'variable': 'ABNT NBR 6120 · ações em edificações',
            'wind': 'ABNT NBR 6123 · ações do vento',
            'exceptional': 'ABNT NBR 8681 · ações excepcionais',
        }
        self.action_reference.setText(reference.get(nature, 'Selecione a natureza da ação.'))

    def _case_controls(self,*_):
        kind = self.action_kind.currentData()
        by_members = kind == 'member_line'
        by_chord = kind in ('surface', 'line')
        general = by_members or by_chord
        if kind == 'self_weight':
            self.action_class.setCurrentIndex(self.action_class.findData('permanent'))
        self.action_class.setEnabled(kind != 'self_weight')
        self._show_action_reference()
        self.action_value.setSuffix(' /m²' if kind == 'surface' else ' /m')
        for widget in (self.action_value, self.action_force_unit, self.action_basis, self.action_direction):
            self.action_form.setRowVisible(widget, general)
        for widget in (self.action_application, self.action_zone):
            self.action_form.setRowVisible(widget, by_chord)
        for widget in (self.action_member_row, self.action_member_mode):
            self.action_form.setRowVisible(widget, by_members)
        if kind=='nodal':self.action_audit.setText('Edite as forças em Cargas nodais.')
        elif kind=='self_weight':self.action_audit.setText('Peso próprio: massa das barras e gravidade nominal g=10 m/s².')
        elif kind=='surface':self.action_audit.setText('Intensidade em força/m²; áreas tributárias obtidas do modelo.')
        else:self.action_audit.setText('Intensidade em força/m; comprimento real ou projetado.')

    def _set_action_members(self, members):
        self.action_member_ids = list(members)
        self.action_members.setText(', '.join(members))
        self.action_members.setToolTip(self.action_members.text())

    def _take_action_members(self):
        members = sorted(identifier for kind, identifier in self._selected if kind == 'member')
        if members:
            self._set_action_members(members)
        else:
            self.action_audit.setText('Selecione pelo menos uma barra no desenho para usar a seleção.')

    def open_member_actions(self):
        if self.mode_3d.isChecked():
            self.set_3d_visible(False)
        self.choose_tool('select')
        if self.view.selection_filter not in ('all', 'member'):
            self.selection_filter.setCurrentIndex(self.selection_filter.findData('member'))
        selected = sorted(identifier for kind, identifier in self._selected if kind == 'member')
        patterns = [row for row in load_patterns(self.session.project) if row['kind'] == 'member_line']
        match = next((row for row in reversed(patterns)
                      if set(row.get('member_ids', [])) == set(selected)), None)
        if match or (patterns and not selected):
            self.action_case.setCurrentText((match or patterns[-1])['id'])
        else:
            if not self._new_action_case(preset='member_line'):
                return
        self._open_load_dialog(self.actions_tab, self.action_case)
        if selected:
            self._set_action_members(selected)
        self.action_value.setFocus()
        self.action_value.selectAll()

    def _populate_case(self,*_):
        cid=self.action_case.currentText()
        case=next((x for x in load_patterns(self.session.project) if x['id']==cid),None)
        if not case:
            self.action_name.clear()
            self._set_action_members([])
            self.action_value.set_stored_value(0)
            return
        self.action_force_unit.setCurrentText(case.get('force_unit', 'kgf'))
        pairs=[(self.action_kind,case.get('kind','surface')),
            (self.action_application,case.get('application','top')),
            (self.action_basis,case.get('basis','projected')),
            (self.action_direction,case.get('direction','down')),
            (self.action_zone,case.get('zone','all')),
            (self.action_member_mode, case.get('member_mode','nodal'))]
        for combo, key in pairs:
            with QSignalBlocker(combo):
                combo.setCurrentIndex(combo.findData(key))
        self._set_action_members(case.get('member_ids', []))
        self.action_name.setText(case.get('name',cid))
        self.action_class.setCurrentIndex(self.action_class.findData(workflow.pattern_class(case)))
        self.action_value.set_stored_value(float(case.get('value',0)))
        self._case_controls()

    def _audit_selected_case(self):
        cid=self.action_case.currentText()
        patterns = {pattern['id']: pattern for pattern in load_patterns(self.session.project)}
        case = patterns.get(cid)
        if not case:return
        try:
            _,audit=resolve_case_loads(self.session.model,case,patterns)
            fx = self.units.force_text(audit['sum_fx_n'], signed=True, load=True)
            fy = self.units.force_text(audit['sum_fy_n'], signed=True, load=True)
            self.action_audit.setText(f'{cid} · {audit["n_entries"]} parcelas · ΣFx {fx} · ΣFy {fy}')
            self._show_load_case(cid)
        except Exception as e:QMessageBox.warning(self,'Auditoria de ações',str(e))

    def _new_action_case(self, _checked=False, *, preset=None):
        name, ok = QInputDialog.getText(self, 'Novo padrão', 'Identificador do padrão:')
        if not ok:
            return
        kind = preset
        if kind is None:
            distributions = [self.action_kind.itemText(i) for i in range(self.action_kind.count())]
            choice, ok = QInputDialog.getItem(self, 'Novo padrão', 'Distribuição da carga',
                                              distributions, max(0, self.action_kind.currentIndex()), False)
            if not ok:
                return
            kind = self.action_kind.itemData(distributions.index(choice))
        try:
            project = workflow.add_load_case(self.session.project, name, kind, pattern_only=True)
            if self._apply(project, 'Padrão incluído'):
                self.action_case.setCurrentText(name.strip())
                self._show_load_case(name.strip())
                if kind == 'member_line' and any(kind == 'member' for kind, _ in self._selected):
                    self._take_action_members()
                return True
        except ValueError as error:
            QMessageBox.warning(self, 'Ações', str(error))
        return False

    def _apply_action_case(self):
        cid=self.action_case.currentText()
        if not cid:return
        try:
            original = next(row for row in load_patterns(self.session.project) if row['id'] == cid)
            force_unit = self.action_force_unit.currentText()
            intensity = (self.action_value.submitted_value()
                         if force_unit == original.get('force_unit', 'kgf')
                         else self.action_value.value())
            targeted = self.action_kind.currentData() == 'member_line'
            p=workflow.update_load_case(self.session.project,cid,
                name=self.action_name.text(),kind=self.action_kind.currentData(),
                value=intensity,force_unit=force_unit,
                application=self.action_application.currentData(),basis=self.action_basis.currentData(),
                direction=self.action_direction.currentData(),
                zone='all' if targeted else self.action_zone.currentData(),
                action_class=self.action_class.currentData(), member_ids=self.action_member_ids,
                member_mode=self.action_member_mode.currentData())
            if self._apply(p,'Padrão atualizado'):
                self._show_load_case(cid)
        except Exception as e:QMessageBox.warning(self,'Ações',str(e))

    def _delete_action_case(self):
        if not self.action_case.currentText():return
        try:self._apply(workflow.delete_load_case(self.session.project,self.action_case.currentText()),'Padrão excluído')
        except Exception as e:QMessageBox.warning(self,'Ações',str(e))

    def open_general_actions(self):
        if self.mode_3d.isChecked():
            self.set_3d_visible(False)
        self._open_load_dialog(self.actions_tab, self.action_case)

    def _build_static_cases_tab(self):
        self.static_tab = QWidget()
        layout = QVBoxLayout(self.static_tab)
        self.static_caption = QLabel('Análise estática linear')
        self.static_caption.setWordWrap(True)
        layout.addWidget(self.static_caption)
        self.static_case = QComboBox()
        self.static_case.currentTextChanged.connect(self._populate_static_case)
        self.static_case.activated.connect(lambda _: self._show_load_case(self.static_case.currentText()))
        layout.addWidget(self.static_case)
        form = QFormLayout()
        self.static_name = QLineEdit()
        form.addRow('Nome', self.static_name)
        layout.addLayout(form)
        self.pattern_factors = self._factor_editor('Padrão')
        layout.addWidget(self.pattern_factors, 1)
        commands = QHBoxLayout()
        commands.addWidget(IconButton('Novo caso', self._new_static_case, 'add'))
        self.static_apply = IconButton('Aplicar fatores', self._apply_static_case, 'check')
        self.static_delete = IconButton('Excluir caso', self._delete_static_case, 'delete')
        commands.addWidget(self.static_apply)
        commands.addWidget(self.static_delete)
        commands.addStretch()
        layout.addLayout(commands)
        self._add_load_dialog(self.static_tab, 'Casos de Carregamentos')

    def open_static_cases(self):
        self._open_load_dialog(self.static_tab, self.static_case)

    def _factor_editor(self, source_label):
        table = QTableWidget(0, 2)
        table.setObjectName('factorTable')
        table.setHorizontalHeaderLabels([source_label, 'Fator'])
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _fill_factors(self, table, definitions, factors):
        table.setRowCount(len(definitions))
        for i, row in enumerate(definitions):
            identifier = row['id']
            item = QTableWidgetItem(identifier)
            item.setToolTip(row.get('name', identifier))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            table.setItem(i, 0, item)
            spin = table.cellWidget(i, 1)
            if spin is None:
                spin = LoadField(-1e6, 1e6, .1)
                table.setCellWidget(i, 1, spin)
            spin.set_stored_value(float(factors.get(identifier, 0)))

    def _read_factors(self, table):
        return {table.item(i, 0).text(): table.cellWidget(i, 1).submitted_value()
                for i in range(table.rowCount())}

    def _populate_static_case(self, *_):
        cid = self.static_case.currentText()
        case = next((row for row in self.session.project.get('load_cases', []) if row['id'] == cid), {})
        self.static_name.setText(case.get('name', cid))
        explicit = case.get('kind') == 'static'
        self.static_caption.setText('Caso de arquivo anterior: edite a carga em Padrões.'
                                    if case and not explicit else 'Análise estática linear')
        self.static_name.setEnabled(explicit)
        self.pattern_factors.setEnabled(explicit)
        self.static_apply.setEnabled(explicit)
        self.static_delete.setEnabled(explicit)
        self._fill_factors(self.pattern_factors, load_patterns(self.session.project),
                           case.get('patterns', {cid: 1} if case else {}))

    def _new_static_case(self):
        ident, ok = QInputDialog.getText(self, 'Novo caso estático', 'Identificador do caso')
        if not ok:return
        patterns = [row['id'] for row in load_patterns(self.session.project)]
        if not patterns:
            QMessageBox.warning(self, 'Casos', 'Cadastre um padrão de carga primeiro.')
            return
        pattern, ok = QInputDialog.getItem(self, 'Novo caso estático', 'Padrão inicial (fator 1)', patterns, 0, False)
        if not ok:return
        try:
            p = workflow.update_static_case(self.session.project, ident, ident, {pattern: 1}, create=True)
            if self._apply(p, 'Caso estático criado'):
                self.static_case.setCurrentText(ident.strip())
                self._show_load_case(ident.strip())
        except ValueError as error:
            QMessageBox.warning(self, 'Casos', str(error))

    def _apply_static_case(self):
        cid = self.static_case.currentText()
        if not self.pattern_factors.isEnabled():return
        try:
            p = workflow.update_static_case(self.session.project, cid, self.static_name.text(),
                                            self._read_factors(self.pattern_factors))
            if self._apply(p, 'Caso estático atualizado'):
                self._show_load_case(cid)
        except ValueError as error:
            QMessageBox.warning(self, 'Casos', str(error))

    def _delete_static_case(self):
        cid = self.static_case.currentText()
        if not self.pattern_factors.isEnabled():return
        try:
            self._apply(workflow.delete_load_case(self.session.project, cid), 'Caso estático excluído')
        except ValueError as error:
            QMessageBox.warning(self, 'Casos', str(error))

    def _build_combinations_tab(self):
        tab=QWidget();v=QVBoxLayout(tab)
        self.combination=QComboBox();self.combination.currentTextChanged.connect(self._populate_combination)
        self.combination.activated.connect(lambda _: self._show_load_case(self.combination.currentText()))
        v.addWidget(self.combination)
        self.combination_class = labeled_combo(workflow.COMBINATION_CLASSES.items())
        form = QFormLayout()
        form.addRow('Classificação', self.combination_class)
        v.addLayout(form)
        reference = QLabel('ABNT NBR 8681 · informe os fatores de cada caso.')
        reference.setWordWrap(True)
        v.addWidget(reference)
        self.factor_table = self._factor_editor('Caso')
        v.addWidget(self.factor_table,1)
        v.addWidget(row_buttons(('Nova combinação',self._new_combination,'add'),
                                ('Aplicar fatores',self._apply_combination,'check'),
                                ('Excluir',self._delete_combination,'delete')))
        self.combo_tab=tab;self._add_load_dialog(tab,'Combinações')

    def open_combinations(self):
        self._open_load_dialog(self.combo_tab, self.combination)

    def _populate_combination(self,*_):
        cid=self.combination.currentText()
        combo=next((x for x in self.session.project.get('combinations',[]) if x['id']==cid),{})
        self.combination_class.setCurrentIndex(self.combination_class.findData(combo.get('combination_class', 'manual')))
        self._fill_factors(self.factor_table, self.session.project.get('load_cases', []), combo.get('factors', {}))

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
        factors = self._read_factors(self.factor_table)
        try:self._apply(workflow.update_combination(self.session.project,cid,factors,
                        self.combination_class.currentData()),'Combinação alterada')
        except Exception as e:QMessageBox.warning(self,'Combinações',str(e))

    def _delete_combination(self):
        cid=self.combination.currentText()
        if not cid:return
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
        self.search_button=IconButton('Pesquisar alternativas', self._start_search, 'compare')
        f.addRow(self.search_button);v.addWidget(p)
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
        if p['geometry'] != self.session.project['geometry']:
            editing.review_nodal_restraints(p)
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
        self.action_case.addItems([c['id'] for c in load_patterns(self.session.project)])
        if current in [self.action_case.itemText(i) for i in range(self.action_case.count())]:
            self.action_case.setCurrentText(current)
        self.action_case.blockSignals(False);self._populate_case()
        current = self.static_case.currentText()
        with QSignalBlocker(self.static_case):
            self.static_case.clear()
            self.static_case.addItems([row['id'] for row in self.session.project.get('load_cases', [])])
            if current:
                self.static_case.setCurrentText(current)
        self._populate_static_case()
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
