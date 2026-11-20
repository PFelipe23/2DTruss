"""Preferências de apresentação. O projeto continua em N, mm e MPa."""
from dataclasses import asdict, dataclass

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QLabel, QSpinBox, QVBoxLayout)

from poe_truss.units import FORCE_TO_N, LENGTH_TO_MM


FORCE_DIGITS = {'tf': 2, 'kgf': 0, 'kN': 2, 'N': 0}
LENGTH_DIGITS = {'m': 3, 'mm': 0, 'cm': 1}
LOCALE = QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil)


def format_number(value, digits, signed=False):
    rounded = round(float(value), digits) or 0.0
    text = LOCALE.toString(rounded, 'f', digits)
    return '+' + text if signed and rounded >= 0 else text


@dataclass(frozen=True)
class DisplayUnits:
    force: str = 'kN'
    length: str = 'mm'
    stress_mode: str = 'MPa'
    force_digits: int | None = None
    length_digits: int | None = None
    stress_digits: int = 2

    @classmethod
    def load(cls, settings):
        try:
            units = cls(**settings.value('displayUnits', {}))
            digits = (units.force_digits, units.length_digits, units.stress_digits)
            if (units.force in FORCE_DIGITS and units.length in LENGTH_DIGITS
                    and units.stress_mode in ('MPa', 'derived') and units.stress_digits is not None
                    and all(value is None or type(value) is int and 0 <= value <= 6 for value in digits)):
                return units
        except (TypeError, ValueError):
            pass
        return cls()

    def save(self, settings):
        settings.setValue('displayUnits', asdict(self))

    @property
    def force_precision(self):
        return FORCE_DIGITS[self.force] if self.force_digits is None else self.force_digits

    @property
    def length_precision(self):
        return LENGTH_DIGITS[self.length] if self.length_digits is None else self.length_digits

    @property
    def length_scale(self):
        return LENGTH_TO_MM[self.length]

    @property
    def stress(self):
        return 'MPa' if self.stress_mode == 'MPa' else f'{self.force}/{self.length}²'

    def force_text(self, value, *, signed=False, unit=True):
        text = format_number(value / FORCE_TO_N[self.force], self.force_precision, signed)
        return f'{text} {self.force}' if unit else text

    def length_text(self, value):
        return f'{format_number(value / self.length_scale, self.length_precision)} {self.length}'

    def stress_text(self, value_mpa, *, signed=False, unit=True):
        scale = 1 if self.stress_mode == 'MPa' else self.length_scale ** 2 / FORCE_TO_N[self.force]
        text = format_number(value_mpa * scale, self.stress_digits, signed)
        return f'{text} {self.stress}' if unit else text


class UnitsDialog(QDialog):
    def __init__(self, units, parent):
        super().__init__(parent)
        self.setObjectName('workspaceDialog')
        self.setWindowTitle('Unidades de exibição')
        layout = QVBoxLayout(self)
        heading = QLabel('Unidades de exibição')
        heading.setObjectName('dialogHeading')
        layout.addWidget(heading)
        layout.addWidget(QLabel('1,00 tf = 1.000 kgf = 10,00 kN\n1,000 m = 1.000 mm = 100,0 cm'))
        form = QFormLayout()
        self.force = QComboBox()
        self.force.addItems(FORCE_DIGITS)
        self.force.setCurrentText(units.force)
        self.length = QComboBox()
        self.length.addItems(LENGTH_DIGITS)
        self.length.setCurrentText(units.length)
        self.stress = QComboBox()
        self.stress.addItem('MPa', 'MPa')
        self.stress.addItem('Força / comprimento²', 'derived')
        self.stress.setCurrentIndex(self.stress.findData(units.stress_mode))
        self.custom = QCheckBox('Personalizar casas decimais')
        self.custom.setChecked(units.force_digits is not None or units.length_digits is not None
                               or units.stress_digits != 2)
        self.force_digits, self.length_digits, self.stress_digits = [QSpinBox() for _ in range(3)]
        for spin in (self.force_digits, self.length_digits, self.stress_digits):
            spin.setRange(0, 6)
        self.force_digits.setValue(units.force_precision)
        self.length_digits.setValue(units.length_precision)
        self.stress_digits.setValue(units.stress_digits)
        form.addRow('Força', self.force)
        form.addRow('Comprimento', self.length)
        form.addRow('Tensão', self.stress)
        form.addRow(self.custom)
        form.addRow('Casas da força', self.force_digits)
        form.addRow('Casas do comprimento', self.length_digits)
        form.addRow('Casas da tensão', self.stress_digits)
        layout.addLayout(form)
        self.sample = QLabel()
        self.sample.setObjectName('unitsSample')
        self.sample.setWordWrap(True)
        layout.addWidget(self.sample)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Aplicar')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for combo in (self.force, self.length, self.stress):
            combo.currentIndexChanged.connect(self._update_sample)
        for spin in (self.force_digits, self.length_digits, self.stress_digits):
            spin.valueChanged.connect(self._update_sample)
        self.custom.toggled.connect(self._update_sample)
        self._update_sample()

    def units(self):
        custom = self.custom.isChecked()
        return DisplayUnits(self.force.currentText(), self.length.currentText(), self.stress.currentData(),
                            self.force_digits.value() if custom else None,
                            self.length_digits.value() if custom else None,
                            self.stress_digits.value() if custom else 2)

    def _update_sample(self, *_):
        units = self.units()
        if not self.custom.isChecked():
            self.force_digits.setValue(units.force_precision)
            self.length_digits.setValue(units.length_precision)
            self.stress_digits.setValue(2)
        for spin in (self.force_digits, self.length_digits, self.stress_digits):
            spin.setEnabled(self.custom.isChecked())
        self.sample.setText(f'Força  {units.force_text(10000)}\n'
                            f'Comprimento  {units.length_text(1000)}\n'
                            f'Tensão  {units.stress_text(25)}')
