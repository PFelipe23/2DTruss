"""Cadastro de valores externos por seção, condição e comprimento-limite."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialogButtonBox, QDoubleSpinBox,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QTableWidget,
                               QTableWidgetItem)

from desktop.manual_resistance import KINDS, resistance_rows, update_manual_resistances
from poe_truss.units import FORCE_TO_N
from .display_units import LOCALE, LoadField
from .ui_theme import WorkspaceCheckBox
from .workspace_dialog import WorkspaceDialog


class ManualResistanceDialog(WorkspaceDialog):
    def __init__(self, session, units, parent):
        super().__init__('Resistências manuais por grupo', parent)
        self.resize(860, 590)
        self.session, self.units = session, units
        self.force_scale = FORCE_TO_N[units.force]
        self.updated_project = None
        self.rows = resistance_rows(session.project, session.model, session.catalog, session.result)
        self.editors = []

        layout = self.body
        subtitle = QLabel('A solicitação vem da envoltória ELU. O comprimento-limite abrange '
                          'barras mais curtas com as mesmas condições cadastradas.')
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        if not (session.result or {}).get('classified_envelopes', {}).get('elu'):
            pending = QLabel('Calcule combinações classificadas como ELU para preencher as solicitações.')
            pending.setWordWrap(True)
            layout.addWidget(pending)
        table = QTableWidget(len(self.rows), 4)
        table.setObjectName('factorTable')
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.setHorizontalHeaderLabels(['Perfil', 'Esforço ELU', f'Comprimento-limite ({units.length})',
                                         f'Resistência manual ({units.force})'])
        header = table.horizontalHeader()
        for column in (0, 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        for column in (2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table = table
        self._populate()
        layout.addWidget(table, 1)

        self.reference = QLineEdit()
        self.reference.setPlaceholderText('Memorial DimPerfil ou referência, ligação e travamento')
        self.reference.setAccessibleName('Referência técnica para os valores alterados')
        layout.addWidget(self.reference)
        self.confirm = WorkspaceCheckBox('Confirmo as condições equivalentes e a aplicação ao comprimento-limite.')
        layout.addWidget(self.confirm)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Salvar no projeto')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        self.add_footer(buttons)

    def _populate(self):
        for index, row in enumerate(self.rows):
            saved = row['rule']
            member_list = ', '.join(row['members'])
            count = len(row['members'])
            scope = (f'{row["group"]} · {count} barras' if count > 1 else
                     f'{row["group"]} · {row["members"][0]}')
            if 'individual_member' in row['conditions']:
                scope = f'{row["members"][0]} · escopo individual'
            profile = QTableWidgetItem(f'{row["profile"]} · {scope}')
            profile.setToolTip(f'Barras da linha: {member_list}\n'
                               f'Maior comprimento atual: {self.units.length_text(row["length_mm"])}')
            self.table.setItem(index, 0, profile)
            value = ('—' if row['demand_n'] is None
                     else self.units.force_text(row['demand_n'], load=True))
            effort = QTableWidgetItem(f'{KINDS[row["kind"]]} · {value}')
            if row['governing']:
                effort.setToolTip('Barra e combinação governantes: ' + ' · '.join(row['governing']))
            self.table.setItem(index, 1, effort)

            original_length = saved['max_length_mm'] if saved else row['length_mm']
            length = QDoubleSpinBox()
            length.setLocale(LOCALE)
            length.setGroupSeparatorShown(True)
            length.setDecimals(max(self.units.length_precision, {'mm': 2, 'cm': 3, 'm': 5}[self.units.length]))
            length.setRange(0, 1e9 / self.units.length_scale)
            length.setValue(original_length / self.units.length_scale)
            length.setMinimumWidth(140)
            length.setAccessibleName(f'Comprimento-limite de {row["profile"]}')
            self.table.setCellWidget(index, 2, length)
            resistance = LoadField(0, 1e9)
            resistance.setMinimumWidth(140)
            resistance.setSpecialValueText('—')
            resistance.setAccessibleName(f'Resistência de {KINDS[row["kind"]].lower()} de {row["profile"]}')
            if saved:
                resistance.set_stored_value(saved['resistance_n'] / self.force_scale)
                resistance.setToolTip(saved['reference'])
            self.table.setCellWidget(index, 3, resistance)
            self.editors.append((length, length.value(), original_length, resistance))

    def _save(self):
        changes = []
        for row, (length, display_length, original_length, resistance) in zip(self.rows, self.editors):
            limit = original_length if length.value() == display_length else length.value() * self.units.length_scale
            capacity = resistance.submitted_value() * self.force_scale or None
            saved = row['rule']
            if capacity is None and not saved:
                continue
            if saved and capacity is not None and abs(capacity - saved['resistance_n']) <= 1e-8 and limit == original_length:
                continue
            changes.append((row, limit, capacity))
        if not changes:
            self.reject()
            return
        if any(capacity is not None for _, _, capacity in changes) and not self.confirm.isChecked():
            QMessageBox.warning(self, 'Resistências manuais', 'Confirme as condições das barras e o comprimento-limite.')
            return
        try:
            self.updated_project = update_manual_resistances(self.session.project, changes, self.reference.text())
        except ValueError as error:
            QMessageBox.warning(self, 'Resistências manuais', str(error))
            return
        self.accept()
