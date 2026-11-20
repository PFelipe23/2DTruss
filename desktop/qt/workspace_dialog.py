"""Estrutura visual compartilhada pelas janelas do 2DTruss."""

from PySide6.QtWidgets import QDialog, QFrame, QLabel, QVBoxLayout


class WorkspaceDialog(QDialog):
    def __init__(self, title, parent):
        super().__init__(parent)
        self.setObjectName('workspaceDialog')
        self.setWindowTitle(title)
        self.shell = QVBoxLayout(self)
        self.shell.setContentsMargins(14, 14, 14, 12)
        self.shell.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName('dialogHeading')
        self.shell.addWidget(heading)
        surface = QFrame()
        surface.setObjectName('dialogSurface')
        self.body = QVBoxLayout(surface)
        self.body.setContentsMargins(12, 10, 12, 10)
        self.body.setSpacing(8)
        self.shell.addWidget(surface, 1)

    def add_footer(self, buttons):
        buttons.setObjectName('dialogActions')
        self.shell.addWidget(buttons)
