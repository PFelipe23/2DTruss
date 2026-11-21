"""Assistente de concepção de cobertura e estudos planos de travamento."""

from copy import deepcopy
from queue import Empty, Queue
from threading import Thread

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFormLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWizard, QWizardPage,
)

from poe_truss.roof_wizard import analyze_bracing, bracing_stations, roof_alternatives, roof_project
from .display_units import LOCALE, format_number
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


class RoofGeometryPage(QWizardPage):
    def __init__(self, template):
        super().__init__()
        self.setTitle('1 de 4 · Geometria e apoio das telhas')
        geometry = template['geometry']
        previous = template.get('roofing', {})
        self.name = QLineEdit('Estudo de cobertura')
        self.span = number(geometry['span_m'], .5, 100)
        self.spacing = number(geometry['frame_spacing_m'], .25, 30)
        self.shape = choices([
            ('Duas águas', 'gable'), ('Uma água', 'single'), ('Paralela', 'parallel'),
            ('Trapezoidal', 'trapezoid'),
        ], geometry['roof_shape'])
        self.topology = choices([(name, name) for name in ('Pratt', 'Howe', 'Warren')], geometry['truss_type'])
        self.rise = number(geometry['rise_m'], 0, 20)
        self.roof_name = QLineEdit(' '.join(
            str(previous.get(key, '')).strip() for key in ('manufacturer', 'model')
        ).strip())
        self.step = number(geometry.get('purlin_max_m', 1.2) or 1.2, .05, 20, 3)
        height = geometry['height_m']
        self.height_min = number(max(.1, height - .2), .1, 10)
        self.height_max = number(min(10, height + .2), .1, 10)
        self.ratio = QSpinBox()
        self.ratio.setRange(50, 2000)
        self.ratio.setValue(250)
        layout = QFormLayout(self)
        for label, field in [
            ('Nome do projeto', self.name), ('Vão da treliça (m)', self.span),
            ('Entre treliças (m)', self.spacing), ('Cobertura', self.shape),
            ('Triangulação', self.topology), ('Desnível da cobertura (m)', self.rise),
            ('Telha · fabricante e modelo', self.roof_name),
            ('Passo máximo entre apoios da telha (m)', self.step),
            ('Altura mínima da treliça (m)', self.height_min),
            ('Altura máxima da treliça (m)', self.height_max),
            ('Limite de flecha de referência · L /', self.ratio),
        ]:
            layout.addRow(label, field)
        layout.addRow(hint('Informe o passo máximo admissível entre terças para a telha e as condições do fornecedor. '
                           'A busca mede o maior trecho real do banzo superior e usa as seções do projeto de origem.'))
        self.shape.currentIndexChanged.connect(lambda: self.rise.setEnabled(self.shape.currentData() != 'parallel'))
        self.rise.setEnabled(self.shape.currentData() != 'parallel')

    def validatePage(self):
        height_range = self.height_max.value() - self.height_min.value()
        if height_range < 0 or height_range > 3:
            QMessageBox.warning(self, 'Alturas da treliça',
                                'Use altura máxima igual ou superior à mínima e uma faixa de até 3,00 m.')
            return False
        return True

    def geometry(self):
        return {
            'span_m': self.span.value(), 'frame_spacing_m': self.spacing.value(), 'panels': 2,
            'height_m': self.height_min.value(), 'roof_shape': self.shape.currentData(),
            'rise_m': self.rise.value() if self.rise.isEnabled() else 0,
            'truss_type': self.topology.currentData(), 'purlin_max_m': self.step.value(),
            'angle_min_deg': 45, 'angle_max_deg': 60,
        }


class RoofLoadsPage(QWizardPage):
    def __init__(self, template):
        super().__init__()
        self.setTitle('2 de 4 · Cargas na cobertura')
        self.self_weight = WorkspaceCheckBox('Calcular com a massa das barras')
        self.self_weight.setChecked(True)
        self.roof_mass = number(template.get('roofing', {}).get('mass_kg_m2', 0), 0, 200, 3)
        self.additional = number(0, 0, 100, 3)
        self.live = number(0, 0, 100, 3)
        self.pressure = number(0, 0, 100, 3)
        self.suction = number(0, 0, 100, 3)
        layout = QFormLayout(self)
        for label, field in [
            ('Peso próprio', self.self_weight), ('Massa da telha · área inclinada (kg/m²)', self.roof_mass),
            ('Acessórios · área horizontal (kN/m²)', self.additional),
            ('Sobrecarga · área horizontal (kN/m²)', self.live),
            ('Vento de pressão normal (kN/m²)', self.pressure), ('Vento de sucção normal (kN/m²)', self.suction),
        ]:
            layout.addRow(label, field)
        layout.addRow(hint('Informe as intensidades do projeto. Pressão e sucção são valores informados pelo projetista. '
                           'As cargas de superfície usam a largura entre treliças '
                           'como largura tributária. Pressão e sucção geram casos próprios. '
                           'A busca usa apenas REF_GRAV, com fatores unitários nas cargas de gravidade.'))

    def actions(self):
        return dict(self_weight=self.self_weight.isChecked(), additional=self.additional.value(),
                    live=self.live.value(), pressure=self.pressure.value(), suction=self.suction.value())


class RoofCandidatesPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle('3 de 4 · Comparar alternativas')
        self.candidates = []
        self.table = result_table(['Painéis', 'Altura (m)', 'Passo (m)', 'Flecha (mm)', 'Massa (kg)', 'Critérios'])
        self.message = hint('')
        layout = QVBoxLayout(self)
        layout.addWidget(self.message)
        layout.addWidget(self.table, 1)
        self.table.itemSelectionChanged.connect(self.completeChanged)
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
        criteria = dict(height_min=page.height_min.value(), height_max=page.height_max.value(),
                        ratio=page.ratio.value())
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
            (candidate['panels'], format_number(candidate['height_m'], 2),
             format_number(candidate['max_purlin_m'], 3), format_number(candidate['max_abs_roof_mm'], 2),
             format_number(candidate['mass_kg'], 2),
             'Passo e flecha OK' if candidate['meets_geometric_service_criteria'] else 'Revisar')
            for candidate in self.candidates
        ])
        limit = self.candidates[0]['displacement_limit_mm']
        status = ('Selecione a geometria para avançar.' if self.candidates[0]['meets_geometric_service_criteria']
                  else 'Nenhuma das alternativas testadas atende aos dois critérios. Revise os dados ou selecione para estudo.')
        self.message.setText(f'{outcome["evaluated"]} alternativas avaliadas. '
                             f'Limite indicativo de flecha {format_number(limit, 2)} mm em REF_GRAV. {status}')
        self.table.selectRow(0)
        self.completeChanged.emit()

    def isComplete(self):
        return self.table.currentRow() >= 0

    def selected(self):
        index = self.table.currentRow()
        return self.candidates[index]


class BracingPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle('4 de 4 · Planos de travamento transversais')
        self.enabled = WorkspaceCheckBox('Incluir estudo de travamento no projeto')
        self.stations = QListWidget()
        self.stations.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.stations.setMaximumHeight(125)
        self.bays = QSpinBox()
        self.bays.setRange(1, 12)
        self.bays.setValue(1)
        self.force = number(0, 0, 10000, 3)
        self.area = number(1000, 1, 100000, 1)
        self.reference = QLineEdit()
        self.reference.setPlaceholderText('Origem da ação e referência do esquema')
        self.table = result_table(['Estação', 'Altura (m)', 'Máx. |N| (kN)', 'Máx. |Ux| (mm)'])
        self.review = QPushButton('Analisar planos selecionados')
        self.review.clicked.connect(self.analyze)
        self.notice = hint('')
        form = QFormLayout()
        fields = [
            ('Estações · Ctrl para seleção múltipla', self.stations),
            ('Vãos entre treliças por plano', self.bays),
            ('Força horizontal por nó superior (kN)', self.force),
            ('Área elástica por barra (mm²)', self.area), ('Referência', self.reference),
        ]
        for label, field in fields:
            form.addRow(label, field)
        layout = QVBoxLayout(self)
        layout.addWidget(self.enabled)
        layout.addWidget(hint('Estudo plano isolado em X. Adota barras bilaterais e restrições XY / Y nos nós inferiores '
                              'extremos. Aplica a força informada nos dois sentidos em casos separados.'))
        layout.addLayout(form)
        layout.addWidget(self.review)
        layout.addWidget(self.notice)
        layout.addWidget(self.table, 1)
        self.fields = [field for _, field in fields]
        self.enabled.toggled.connect(self.invalidate)
        self.stations.itemSelectionChanged.connect(self.invalidate)
        for field in (self.bays, self.force, self.area):
            field.valueChanged.connect(self.invalidate)
        self.reference.textChanged.connect(self.invalidate)
        self.specification = None

    def initializePage(self):
        project = self.wizard().selected_roof()
        stations = bracing_stations(project, self.wizard().catalog)
        self.stations.clear()
        center = min(stations, key=lambda key: abs(stations[key]['x_mm'] - project['geometry']['span_m'] * 500))
        for identifier, station in stations.items():
            position = format_number(station['x_mm'] / 1000, 3)
            item = QListWidgetItem(f'{identifier} / {station["upper"]} · x = {position} m')
            item.setData(Qt.ItemDataRole.UserRole, identifier)
            self.stations.addItem(item)
            if identifier == center:
                item.setSelected(True)
        self.invalidate()

    def invalidate(self):
        self.specification = None
        self.table.setRowCount(0)
        enabled = self.enabled.isChecked()
        for field in [*self.fields, self.review, self.table]:
            field.setEnabled(enabled)
        self.notice.setText('Selecione estações e informe a força para calcular.' if enabled else
                            'Prossiga para gerar a treliça de cobertura.')
        self.completeChanged.emit()

    def isComplete(self):
        return not self.enabled.isChecked() or self.specification is not None

    def analyze(self):
        project = self.wizard().selected_roof()
        specification = {
            'panels': project['geometry']['panels'],
            'stations': sorted(item.data(Qt.ItemDataRole.UserRole) for item in self.stations.selectedItems()),
            'bays': self.bays.value(), 'force_kn': self.force.value(), 'area_mm2': self.area.value(),
            'reference': self.reference.text().strip(),
        }
        if not specification['stations'] or not specification['reference']:
            self.notice.setText('Selecione ao menos uma estação e registre a referência da ação e dos apoios.')
            return
        try:
            rows = analyze_bracing(project, self.wizard().catalog, specification)
        except (ValueError, ArithmeticError) as error:
            self.notice.setText(str(error))
            return
        fill_rows(self.table, [
            (row['station']['lower'], format_number(row['station']['height_mm'] / 1000, 2),
             format_number(row['max_axial_kn'], 2), format_number(row['max_ux_mm'], 2))
            for row in rows
        ])
        self.specification = specification
        self.notice.setText('Planos calculados. Abra a análise individual em Mais comandos após gerar a cobertura.')
        self.completeChanged.emit()


class RoofWizard(QWizard):
    def __init__(self, parent, template, catalog):
        super().__init__(parent)
        self.template = template
        self.catalog = catalog
        self.setWindowTitle('Assistente de cobertura')
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage)
        self.setStyleSheet(parent.styleSheet())
        self.resize(800, 670)
        for button, label in [
            (QWizard.WizardButton.BackButton, 'Voltar'), (QWizard.WizardButton.NextButton, 'Avançar'),
            (QWizard.WizardButton.FinishButton, 'Gerar projeto'), (QWizard.WizardButton.CancelButton, 'Cancelar'),
        ]:
            self.setButtonText(button, label)
        self.geometry_page = RoofGeometryPage(template)
        self.loads_page = RoofLoadsPage(template)
        self.candidates_page = RoofCandidatesPage()
        self.bracing_page = BracingPage()
        for page in (self.geometry_page, self.loads_page, self.candidates_page, self.bracing_page):
            self.addPage(page)

    def roof(self):
        return roof_project(
            self.template, name=self.geometry_page.name.text(), geometry=self.geometry_page.geometry(),
            roofing={'model': self.geometry_page.roof_name.text().strip(), 'mass_kg_m2': self.loads_page.roof_mass.value()},
            actions=self.loads_page.actions(),
        )

    def selected_roof(self):
        project = self.roof()
        row = self.candidates_page.selected()
        project['geometry'].update(panels=row['panels'], height_m=row['height_m'])
        return project

    def project(self):
        project = self.selected_roof()
        if self.bracing_page.specification is not None:
            project['transverse_bracing'] = deepcopy(self.bracing_page.specification)
        return project
