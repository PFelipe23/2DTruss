"""Assistente de concepção de cobertura e estudos planos de travamento."""

from copy import deepcopy
from dataclasses import replace
from math import ceil
from queue import Empty, Queue
from threading import Thread

from PySide6.QtCore import QPointF, QRectF, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QDoubleSpinBox, QFormLayout, QHeaderView,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QWizard, QWizardPage,
)

from poe_truss.engine import run_project
from poe_truss.model import make_model
from poe_truss.roof_wizard import STUDY_LOADS, chord_bracing_planes, chord_bracing_project, preliminary_roof_project, roof_alternatives
from poe_truss.units import FORCE_TO_N
from .ui_theme import WorkspaceComboBox as QComboBox
from .display_units import DisplayUnits, FORCE_DIGITS, LENGTH_DIGITS, LOCALE, format_number
from .ui_theme import WorkspaceCheckBox


def number(value, minimum, maximum, decimals=2):
    field = QDoubleSpinBox()
    field.setLocale(LOCALE)
    field.setDecimals(decimals)
    field.setRange(minimum, maximum)
    field.setValue(value)
    return field


def choices(options, selected):
    selector = QComboBox()
    for label, value in options:
        selector.addItem(label, value)
    selector.setCurrentIndex(max(0, selector.findData(selected)))
    return selector


def result_table(headers):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    return table


def fill_rows(table, rows):
    table.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(str(value)))


def hint(text):
    label = QLabel(text)
    label.setWordWrap(True)
    return label


class RoofPreview(QWidget):
    def __init__(self):
        super().__init__()
        self.model = None
        self.units = DisplayUnits()
        self.setMinimumSize(260, 170)

    def set_model(self, model, units):
        self.model, self.units = model, units
        self.update()

    def paintEvent(self, event):
        with QPainter(self) as painter:
            painter.fillRect(self.rect(), QColor('#F1F6FA'))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QColor('#305069'))
            painter.drawText(12, 24, 'Prévia 2D')
            if self.model is None:
                return
            nodes = self.model.node_map()
            height = max(n.y for n in nodes.values())
            span = self.model.span_mm
            scale = min((self.width() - 36) / span, (self.height() - 80) / height)
            left = (self.width() - span * scale) / 2
            bottom = (self.height() + height * scale) / 2
            for member in self.model.members:
                a, b = nodes[member.i], nodes[member.j]
                color = '#176D9B' if member.group in ('superior', 'inferior') else '#6F8799'
                painter.setPen(QPen(QColor(color), 1.6))
                painter.drawLine(QPointF(left + a.x * scale, bottom - a.y * scale),
                                 QPointF(left + b.x * scale, bottom - b.y * scale))
            painter.setPen(QColor('#305069'))
            painter.drawText(QRectF(0, bottom + 12, self.width(), 26), Qt.AlignmentFlag.AlignCenter,
                             f'{self.units.length_text(span)} · {self.model.panels} painéis')


class RoofGeometryPage(QWizardPage):
    def __init__(self, template, catalog, units):
        super().__init__()
        self.setTitle('1 de 4 · Geometria da cobertura')
        self.template, self.catalog = template, catalog
        self.units = units
        geometry = template['geometry']
        self.slope = geometry['rise_m'] / geometry['span_m'] if geometry['rise_m'] else .075
        self.name = QLineEdit('Estudo de cobertura')
        self.force = choices([(unit, unit) for unit in FORCE_DIGITS], units.force)
        self.length = choices([(unit, unit) for unit in LENGTH_DIGITS], units.length)
        selectors = QHBoxLayout()
        selectors.addWidget(self.force)
        selectors.addWidget(self.length)
        self.shape = choices([
            ('Duas águas', 'gable'), ('Uma água', 'single'), ('Paralela', 'parallel'),
            ('Trapezoidal', 'trapezoid'),
        ], geometry['roof_shape'])
        self.topology = choices([(name, name) for name in ('Pratt', 'Howe', 'Warren')], geometry['truss_type'])
        self.ratio = choices([(f'L/{i}', i) for i in (150, 180, 200, 250, 300, 350, 400, 500)], 250)
        form = QFormLayout()
        form.addRow('Unidades', selectors)
        form.addRow('Título do Projeto', self.name)
        self.fields = {}
        self.span = self.add_length(form, 'Vão da Treliça', geometry['span_m'], .5, 100)
        self.spacing = self.add_length(form, 'Espaçamento entre Treliças', geometry['frame_spacing_m'], .25, 30)
        form.addRow('Tipo de Cobertura', self.shape)
        form.addRow('Modelo', self.topology)
        height = geometry['height_m']
        self.height_max = self.add_length(form, 'Altura Máxima da Treliça', min(10, height + .2), .1, 10)
        self.height_min = self.add_length(form, 'Altura Mínima da Treliça', max(.1, height - .2), .1, 10)
        self.step = self.add_length(form, 'Passo Máximo de Terças', geometry.get('purlin_max_m', 1.2) or 1.2, .05, 20)
        form.addRow('Limite de Flecha', self.ratio)
        form.addRow(hint('As alturas delimitam a faixa de busca. A inclinação acompanha a proporção do modelo de origem.'))
        self.preview = RoofPreview()
        layout = QHBoxLayout(self)
        layout.addWidget(self.preview, 1)
        layout.addLayout(form, 1)
        self.length.currentIndexChanged.connect(self.update_units)
        self.force.currentIndexChanged.connect(self.update_units)
        self.shape.currentIndexChanged.connect(self.refresh_preview)
        self.topology.currentIndexChanged.connect(self.refresh_preview)
        self.update_units()

    def add_length(self, form, name, value, low, high):
        label = QLabel()
        field = number(value, low, high, 3)
        self.fields[field] = (label, name, low, high, value)
        field.valueChanged.connect(lambda value: self.edit_length(field, value))
        form.addRow(label, field)
        return field

    def edit_length(self, field, value):
        label, name, low, high, _ = self.fields[field]
        self.fields[field] = (label, name, low, high, value * self.units.length_scale / 1000)
        self.refresh_preview()

    def update_units(self):
        length, force = self.length.currentData(), self.force.currentData()
        self.units = replace(self.units, length=length, force=force)
        scale = 1000 / self.units.length_scale
        for field, (label, name, low, high, value) in self.fields.items():
            label.setText(f'{name} [{length}]')
            with QSignalBlocker(field):
                field.setDecimals(self.units.length_precision)
                field.setRange(low * scale, high * scale)
                field.setValue(value * scale)
        self.refresh_preview()

    def meters(self, field):
        return self.fields[field][-1]

    def refresh_preview(self):
        geometry = self.geometry()
        count = min(40, max(2, ceil(geometry['span_m'] / geometry['purlin_max_m'])))
        if geometry['roof_shape'] == 'gable' and count % 2:
            count += 1
        geometry['panels'] = count
        project = dict(self.template, geometry=geometry)
        self.preview.set_model(make_model(project, self.catalog), self.units)

    def validatePage(self):
        height_range = self.meters(self.height_max) - self.meters(self.height_min)
        if height_range < 0 or height_range > 3:
            limit = self.units.length_text(3000)
            QMessageBox.warning(self, 'Alturas da treliça',
                                f'Use altura máxima igual ou superior à mínima e uma faixa de até {limit}.')
            return False
        return True

    def geometry(self):
        span = self.meters(self.span)
        shape = self.shape.currentData()
        return {'span_m': span, 'frame_spacing_m': self.meters(self.spacing), 'panels': 2,
                'height_m': self.meters(self.height_min), 'roof_shape': shape,
                'rise_m': 0 if shape == 'parallel' else span * self.slope,
                'truss_type': self.topology.currentData(), 'purlin_max_m': self.meters(self.step),
                'angle_min_deg': 45, 'angle_max_deg': 60}


class RoofLoadsPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle('2 de 4 · Cargas do pré-dimensionamento')
        self.intensities = {identifier: value for identifier, _, value, _ in STUDY_LOADS}
        self.rows = {}
        self.force_scale = 1.
        layout = QFormLayout(self)
        layout.addRow('Peso Próprio de Treliça', QLabel('Calculado automaticamente pelos perfis'))
        for identifier, caption, initial, _ in STUDY_LOADS:
            label = QLabel()
            field = number(initial, 0, 1000000, 5)
            self.rows[identifier] = (label, field, caption)
            field.valueChanged.connect(lambda value, key=identifier: self.intensities.update({key: value / self.force_scale}))
            layout.addRow(label, field)
        layout.addRow(hint('Flecha de serviço com fatores unitários. Estudo ponderado com 1,25 para permanentes '
                           'e 1,50 para sobrecarga. As cargas desta etapa ficam só no estudo.'))

    def initializePage(self):
        units = self.wizard().geometry_page.units
        self.force_scale = FORCE_TO_N['kgf'] / FORCE_TO_N[units.force]
        for identifier, (label, field, caption) in self.rows.items():
            label.setText(f'{caption} [{units.force}/m²]')
            with QSignalBlocker(field):
                field.setDecimals(max(2, units.force_precision, 4 if units.force == 'tf' else 3 if units.force == 'kN' else 2))
                field.setValue(self.intensities[identifier] * self.force_scale)


class RoofCandidatesPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle('3 de 4 · Comparar alternativas')
        self.candidates = []
        self.table = result_table(['Painéis', 'Altura', 'Passo', 'Flecha', 'Massa (kg)', 'Critérios'])
        self.message = hint('')
        self.preview = RoofPreview()
        self.profiles = hint('')
        layout = QVBoxLayout(self)
        layout.addWidget(self.message)
        body = QHBoxLayout()
        visual = QVBoxLayout()
        visual.addWidget(self.preview, 1)
        visual.addWidget(self.profiles)
        body.addLayout(visual, 1)
        body.addWidget(self.table, 2)
        layout.addLayout(body, 1)
        self.table.itemSelectionChanged.connect(self.update_selection)
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.poll)

    def initializePage(self):
        wizard = self.wizard()
        self.candidates = []
        self.table.setRowCount(0)
        self.completeChanged.emit()
        self.message.setText('Calculando alternativas de modulação, flecha e massa…')
        project = wizard.roof()
        catalog = wizard.catalog
        page = wizard.geometry_page
        self.units = page.units
        length = self.units.length
        self.table.setHorizontalHeaderLabels(['Painéis', f'Altura [{length}]', f'Passo [{length}]',
                                             f'Flecha [{length}]', 'Massa [kg]', 'Critérios'])
        criteria = dict(height_min=page.meters(page.height_min), height_max=page.meters(page.height_max),
                        ratio=page.ratio.currentData(), size_profiles=True)
        queue = self.queue = Queue()

        def task():
            try:
                queue.put((roof_alternatives(project, catalog, **criteria), ''))
            except Exception as error:
                queue.put((None, str(error)))

        Thread(target=task, daemon=True).start()
        self.timer.start()

    def cleanupPage(self):
        self.timer.stop()

    def poll(self):
        try:
            outcome, error = self.queue.get_nowait()
        except Empty:
            return
        self.timer.stop()
        if error:
            self.message.setText(error)
            return
        self.candidates = outcome['candidates']
        fill_rows(self.table, [
            (candidate['panels'], self.units.length_text(candidate['height_m'] * 1000, unit=False),
             self.units.length_text(candidate['max_purlin_m'] * 1000, unit=False),
             self.units.displacement_text(candidate['max_abs_roof_mm'], unit=False),
             format_number(candidate['mass_kg'], 2),
             'Atende' if candidate['meets_geometric_service_criteria'] else 'Revisar')
            for candidate in self.candidates
        ])
        limit = self.candidates[0]['displacement_limit_mm']
        status = ('Selecione a geometria para avançar.' if self.candidates[0]['meets_geometric_service_criteria']
                  else 'Nenhuma das alternativas testadas atende aos dois critérios. Revise os dados ou selecione para estudo.')
        self.message.setText(f'{outcome["evaluated"]} alternativas avaliadas. '
                             f'Limite de flecha {self.units.displacement_text(limit)} em serviço. {status}')
        self.table.selectRow(0)
        self.completeChanged.emit()

    def update_selection(self):
        self.completeChanged.emit()
        if not self.isComplete():
            self.profiles.clear()
            self.preview.set_model(None, self.units if hasattr(self, 'units') else DisplayUnits())
            return
        project = self.wizard().selected_roof()
        self.preview.set_model(make_model(project, self.wizard().catalog), self.units)
        captions = dict(superior='BS', inferior='BI', montante='MO', diagonal='DI')
        self.profiles.setText(' · '.join(f'{captions[key]} {spec["profile"]}' for key, spec in project['sections'].items())
                              + '\nMáx. |N| no estudo ponderado: '
                              + self.units.force_text(self.selected()['max_design_axial_kn'] * 1000))

    def isComplete(self):
        return bool(self.candidates) and self.table.currentRow() >= 0

    def selected(self):
        index = self.table.currentRow()
        return self.candidates[index]


class BracingPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle('4 de 4 · Travamento nos planos dos banzos')
        self.enabled = WorkspaceCheckBox('Incluir o estudo de travamento')
        self.bays = choices([(f'{i} módulos', i) for i in (2, 3)], 2)
        self.force = number(0, 0, 1000000, 2)
        self.area = number(1000, 1, 100000, 1)
        self.diameter = choices([(f'{format_number(d, 1)} mm', d) for d in (8, 10, 12.5, 16, 20, 25, 32)], 12.5)
        self.reference = QLineEdit()
        self.reference.setPlaceholderText('Ação e apoios assumidos')
        self.table = result_table(['Plano', 'Largura', 'Máx. tração', 'Máx. compressão', 'Máx. |Ux|'])
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setMinimumHeight(126)
        self.review = QPushButton('Analisar planos')
        self.review.clicked.connect(self.analyze)
        self.notice = hint('')
        self.force_label = QLabel()
        form = QFormLayout()
        form.setVerticalSpacing(4)
        fields = [('Extensão longitudinal', self.bays), (self.force_label, self.force),
                  ('Área dos cordões e montantes [mm²]', self.area),
                  ('Bitola redonda das diagonais', self.diameter), ('Referência', self.reference)]
        for label, field in fields:
            form.addRow(label, field)
        layout = QVBoxLayout(self)
        layout.addWidget(self.enabled)
        layout.addWidget(hint('Quatro faixas em duas águas, uma por lado e banzo. '
                              'Os cordões e as diagonais trabalham à tração. '
                              'O estudo supõe quatro apoios de canto e aplica a força aos nós internos '
                              'de uma borda, nos dois sentidos.'))
        layout.addLayout(form)
        layout.addWidget(self.review)
        layout.addWidget(self.notice)
        layout.addWidget(self.table, 1)
        self.fields = [field for _, field in fields]
        self.enabled.toggled.connect(self.invalidate)
        for field in (self.force, self.area):
            field.valueChanged.connect(self.invalidate)
        for field in (self.bays, self.diameter):
            field.currentIndexChanged.connect(self.invalidate)
        self.reference.textChanged.connect(self.invalidate)
        self.specification = None
        self.units = DisplayUnits()

    def initializePage(self):
        force_n = self.force.value() * FORCE_TO_N[self.units.force]
        self.units = self.wizard().geometry_page.units
        self.force.setValue(force_n / FORCE_TO_N[self.units.force])
        force, length = self.units.force, self.units.length
        self.force_label.setText(f'Força por nó interno [{force}]')
        self.table.setHorizontalHeaderLabels(['Plano', f'Largura [{length}]', f'Máx. tração [{force}]',
                                             f'Máx. compressão [{force}]', f'Máx. |Ux| [{length}]'])
        self.invalidate()

    def invalidate(self):
        self.specification = None
        self.table.setRowCount(0)
        enabled = self.enabled.isChecked()
        for field in [*self.fields, self.review, self.table]:
            field.setEnabled(enabled)
        self.notice.setText('Informe a força e a referência do esquema.' if enabled else 'Prossiga para gerar a cobertura.')
        self.completeChanged.emit()

    def isComplete(self):
        return not self.enabled.isChecked() or self.specification is not None

    def analyze(self):
        roof = self.wizard().selected_roof()
        catalog = self.wizard().catalog
        specification = dict(kind='chord_planes', bays=self.bays.currentData(),
                             area_mm2=self.area.value(), diameter_mm=self.diameter.currentData(),
                             force_kn=self.force.value() * FORCE_TO_N[self.units.force] / 1000,
                             reference=self.reference.text().strip())
        if not specification['reference'] or not specification['force_kn']:
            self.notice.setText('Informe uma força positiva e registre a referência da ação e dos apoios.')
            return
        rows = []
        try:
            for key, width in chord_bracing_planes(roof, catalog).items():
                project = chord_bracing_project(roof, key, width, specification)
                analyses = run_project(project, catalog)['analyses'].values()
                forces = [force for a in analyses for force in a['axial_n'].values()]
                ux = max(abs(d['ux_mm']) for a in analyses for d in a['nodal_displacements'].values())
                rows.append((key, self.units.length_text(width, unit=False),
                             self.units.force_text(max(forces), unit=False),
                             self.units.force_text(min(forces), unit=False),
                             self.units.displacement_text(ux, unit=False)))
        except (ValueError, ArithmeticError) as error:
            self.notice.setText(str(error))
            return
        fill_rows(self.table, rows)
        self.specification = specification
        self.notice.setText('Planos calculados. Abra cada um em Mais comandos → Planos de travamento.')
        self.completeChanged.emit()


class RoofWizard(QWizard):
    def __init__(self, parent, template, catalog, units=DisplayUnits()):
        super().__init__(parent)
        self.template = template
        self.catalog = catalog
        self.setWindowTitle('Assistente de cobertura')
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.setButtonLayout([QWizard.WizardButton.Stretch, QWizard.WizardButton.BackButton,
                              QWizard.WizardButton.NextButton, QWizard.WizardButton.FinishButton,
                              QWizard.WizardButton.CancelButton])
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage)
        self.resize(800, 490)
        for button, label in [
            (QWizard.WizardButton.BackButton, 'Voltar'), (QWizard.WizardButton.NextButton, 'Avançar'),
            (QWizard.WizardButton.FinishButton, 'Gerar projeto'), (QWizard.WizardButton.CancelButton, 'Cancelar'),
        ]:
            self.setButtonText(button, label)
            self.button(button).setMinimumWidth(92)
        self.geometry_page = RoofGeometryPage(template, catalog, units)
        self.loads_page = RoofLoadsPage()
        self.candidates_page = RoofCandidatesPage()
        self.bracing_page = BracingPage()
        for page in (self.geometry_page, self.loads_page, self.candidates_page, self.bracing_page):
            self.addPage(page)

    def roof(self):
        return preliminary_roof_project(
            self.template, name=self.geometry_page.name.text(), geometry=self.geometry_page.geometry(),
            intensities=self.loads_page.intensities,
        )

    def selected_roof(self):
        project = self.roof()
        row = self.candidates_page.selected()
        project['geometry'].update(panels=row['panels'], height_m=row['height_m'])
        project['sections'] = deepcopy(row['sections'])
        return project

    def project(self):
        project = self.selected_roof()
        project.update(load_patterns=[], load_cases=[], combinations=[])
        if self.bracing_page.specification is not None:
            project['transverse_bracing'] = deepcopy(self.bracing_page.specification)
        return project
