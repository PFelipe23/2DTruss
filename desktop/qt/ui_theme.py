"""Identidade de interface 2DTruss v0.1 — desktop engineering workspace."""
from PySide6.QtGui import QColor, QPalette


def workspace_palette():
    palette = QPalette()
    role = QPalette.ColorRole
    for name, color in {
        'Window': '#F3F6F9',
        'WindowText': '#263B4D',
        'Base': '#FFFFFF',
        'AlternateBase': '#F3F7FB',
        'Text': '#263B4D',
        'Button': '#F7F9FB',
        'ButtonText': '#263B4D',
        'Light': '#FFFFFF',
        'Midlight': '#E5EDF4',
        'Mid': '#B6C9D8',
        'Dark': '#8198AB',
        'Shadow': '#526A7E',
        'Highlight': '#D6EAF8',
        'HighlightedText': '#143B55',
        'ToolTipBase': '#FFFFFF',
        'ToolTipText': '#263B4D',
    }.items():
        palette.setColor(getattr(role, name), QColor(color))
    for text_role in (role.Text, role.WindowText, role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, text_role, QColor('#728597'))
    return palette


STYLE = r'''
QMainWindow, QWidget {font-family:"Segoe UI",Arial;font-size:9pt;color:#263B4D;}
QMainWindow {background:#F3F6F9;}
QDialog#workspaceDialog, QWidget#loadDialogPage {background:#F3F6F9;}
QScrollArea#loadDialogScroll {background:#F3F6F9;}
QTableWidget#factorTable QDoubleSpinBox {min-height:17px;padding:3px;}
QFrame#quickAccess {background:#182B3C;}
QLabel#appHeader {color:#FFFFFF;font-weight:700;padding:0 14px 0 3px;}
QLabel#unitSummary {color:#D6E8F4;padding:0 5px 0 1px;}
QLabel#unitsSample {background:#EAF4FA;border:1px solid #CFDFEA;border-radius:4px;padding:8px;}
QLabel#dialogHeading {font-weight:700;color:#183850;background:#E6F0F7;padding:8px;border-radius:4px;}
QMenu#memberTagsMenu {background:#F3F7FA;border:1px solid #BCCDD9;}
QFrame#quickAccess QToolButton {color:#F2F7FB;background:#263C50;border-color:#40586C;padding:5px 2px;}
QFrame#quickAccess QToolButton:hover, QFrame#quickAccess QToolButton:checked {background:#3C5C74;}
QFrame#quickAccess QToolButton:checked {border-color:#76C8F4;}
QFrame#quickAccess QToolButton::menu-indicator {image:none;}
QFrame#quickAccess QToolButton#calculateButton {color:#FFFFFF;background:#0A689E;border-color:#3B91BD;font-weight:700;}
QFrame#quickAccess QToolButton#calculateButton:hover {background:#08567F;}
QFrame#toolDivider {background:#587084;margin:0;}
QFrame#statusBar {background:#F3F6F9;border-top:1px solid #D3DEE7;}
QLabel#coordinates {color:#344B60;font-family:"Consolas";font-size:9pt;}
QWidget#taskPanel {background:#FFFFFF;}
QWidget#inspectorPage {background:#FFFFFF;}
QLabel#panelHeading {font-weight:700;color:#183850;padding:4px 5px 6px;}
QTabWidget::pane {border:0;background:#FFFFFF;}
QTabBar::tab {background:#ECF1F5;color:#344B60;padding:5px 12px;border-bottom:2px solid transparent;}
QTabBar::tab:selected {background:#FFFFFF;color:#005987;font-weight:700;border-bottom:2px solid #137CB3;}
QTabWidget#navigator QTabBar::tab, QWidget#taskPanel QTabBar::tab {padding:5px 7px;}
QToolButton {background:#F7F9FB;border:1px solid #D5E0E9;border-radius:4px;padding:4px 8px;}
QToolButton:hover {background:#E8F4FB;border-color:#9DBFD4;}
QToolButton:pressed,QToolButton:checked {background:#DAECF8;color:#124765;border-color:#8CB5D0;}
QToolButton:focus {border-color:#338BBA;}
QToolButton:disabled {color:#728597;}
QPushButton {background:#F6F9FB;border:1px solid #C8D7E4;border-radius:5px;padding:7px 9px;}
QPushButton:hover {background:#EAF5FC;border-color:#7EADC7;}
QPushButton:pressed {background:#D5ECF9;}
QTreeWidget,QTableWidget,QListWidget {background:#FFFFFF;alternate-background-color:#F3F7FB;border:1px solid #DCE6EF;
 selection-background-color:#D6EAF8;selection-color:#143B55;gridline-color:#E7EDF3;}
QTreeWidget::item {padding:3px;}
QTreeWidget::item:selected {background:#D6EAF8;color:#0A5A8C;}
QHeaderView::section {background:#EFF4F8;color:#38586C;padding:6px;border:0;border-bottom:1px solid #D5E3ED;font-weight:600;}
QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit {background:#FFFFFF;border:1px solid #C7D6E3;border-radius:4px;padding:4px;min-height:24px;}
QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QLineEdit:focus {border-color:#1385BA;}
QGroupBox {border:1px solid #D9E5EF;border-radius:5px;margin-top:12px;padding:12px 8px 9px;font-weight:600;background:#FFFFFF;}
QGroupBox::title {subcontrol-origin:margin;left:9px;padding:0 5px;color:#25445C;}
QSplitter::handle {background:#DCE5ED;}
QSplitter::handle:hover {background:#8CB5D0;}
QScrollBar:vertical {background:#F4F7FA;width:9px;}
QScrollBar::handle:vertical {background:#B6C9D8;border-radius:3px;min-height:22px;}
QFrame#viewportBar {background:#EDF3F8;border-top:1px solid #D9E4ED;border-bottom:1px solid #D9E4ED;}
QLabel#viewMode {color:#17658C;font-weight:700;}
QFrame#forceBar {background:#FFF8ED;border-bottom:1px solid #E9D8BD;}
QFrame#forceBar QLabel {color:#784517;}
QLabel#calcPending {color:#78521A;background:#FFF0D5;border-radius:4px;padding:3px 8px;}
QLabel#calcReady {color:#146147;background:#DCF2E8;border-radius:4px;padding:3px 8px;}
'''
