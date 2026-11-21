"""Seletor de seções compartilhado pelas vistas 2D e 3D."""
from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QSpinBox, QWidget
from .display_units import format_number


class ProfilePicker(QWidget):
    changed = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.catalog = {}
        self.family = QComboBox()
        self.profile = QComboBox()
        self.profile.setPlaceholderText('Escolher bitola')
        self.count = QSpinBox()
        self.count.setRange(1, 2)
        self.count.setKeyboardTracking(False)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow('Biblioteca', self.family)
        layout.addRow('Perfil', self.profile)
        layout.addRow('Quantidade', self.count)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setObjectName('profileDetails')
        layout.addRow(self.details)
        self.family.currentTextChanged.connect(self._filter)
        self.profile.activated.connect(self._select)
        self.count.valueChanged.connect(self._emit)

    def set_section(self, catalog, section):
        if catalog is not self.catalog:
            self.catalog = catalog
            with QSignalBlocker(self.family):
                self.family.clear()
                self.family.addItems(sorted({profile.family for profile in catalog.values()}))
        name = section.get('profile', '')
        if name in self.catalog:
            with QSignalBlocker(self.family):
                self.family.setCurrentText(self.catalog[name].family)
        self._filter(self.family.currentText(), name)
        with QSignalBlocker(self.count):
            self.count.setValue(int(section.get('count', 1)))

    def _filter(self, family, selected=''):
        with QSignalBlocker(self.profile):
            self.profile.clear()
            self.profile.addItems(sorted(p.name for p in self.catalog.values() if p.family == family))
            for index in range(self.profile.count()):
                profile = self.catalog[self.profile.itemText(index)]
                self.profile.setItemData(index, f'{profile.origin}\n{profile.quality}', Qt.ItemDataRole.ToolTipRole)
            self.profile.setCurrentIndex(self.profile.findText(selected))
        self.count.setEnabled(self.profile.currentIndex() >= 0)
        self._describe()

    def _select(self, _index):
        with QSignalBlocker(self.count):
            self.count.setValue(1)
        self.count.setEnabled(True)
        self._emit()

    def _describe(self):
        profile = self.catalog.get(self.profile.currentText())
        self.details.setVisible(profile is not None)
        if profile is None:
            return
        self.details.setText(
            f'{profile.name}\nÁrea por perfil   {format_number(profile.area_mm2, 2)} mm²\n'
            f'Massa por perfil   {format_number(profile.mass_kg_m, 3)} kg/m'
        )
        self.details.setToolTip(f'{profile.origin}\n{profile.quality}')

    def _emit(self, *_):
        self._describe()
        name = self.profile.currentText()
        if name:
            self.changed.emit(name, self.count.value())
