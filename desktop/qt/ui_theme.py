"""Identidade de interface 2DTruss v0.1 — desktop engineering workspace."""
STYLE = r'''
QMainWindow, QWidget {font-family:"Segoe UI",Arial;font-size:10pt;color:#263B4D;}
QMainWindow {background:#EEF2F6;}
QLabel#appHeader {background:#102D45;color:#F8FBFF;font-size:13pt;font-weight:700;padding:10px 19px;}
QLabel#status {background:#E5EDF4;border-top:1px solid #C9D6E1;color:#38566D;padding:7px 12px;}
QWidget#taskPanel {background:#FFFFFF;border-left:1px solid #D7E3ED;}
QLabel#panelHeading {font-size:10pt;font-weight:700;color:#153B55;padding:8px 5px 2px 5px;}
QTabWidget::pane {border:0;background:#FFFFFF;}
QTabBar::tab {background:#E9F1F7;color:#547084;padding:8px 19px;border-right:1px solid #D8E3ED;}
QTabBar::tab:selected {background:white;color:#0871A7;font-weight:700;border-top:2px solid #0871A7;}
QToolButton {background:#FFFFFF;border:1px solid transparent;border-radius:5px;padding:6px 9px;min-height:40px;}
QToolButton:hover {background:#E8F4FB;border:1px solid #B7D9EB;}
QToolButton:pressed {background:#D2E9F6;}
QPushButton {background:#F6F9FB;border:1px solid #C8D7E4;border-radius:5px;padding:7px 9px;}
QPushButton:hover {background:#EAF5FC;border-color:#7EADC7;}
QPushButton:pressed {background:#D5ECF9;}
QTreeWidget,QTableWidget,QListWidget {background:#FFFFFF;border:1px solid #DCE6EF;
 selection-background-color:#D6EAF8;selection-color:#143B55;gridline-color:#E7EDF3;}
QTreeWidget::item {padding:4px 3px;}
QTreeWidget::item:selected {background:#D6EAF8;color:#0A5A8C;}
QHeaderView::section {background:#EFF4F8;color:#38586C;padding:6px;border:0;border-bottom:1px solid #D5E3ED;font-weight:600;}
QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit {background:#FFFFFF;border:1px solid #C7D6E3;border-radius:4px;padding:4px;min-height:24px;}
QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QLineEdit:focus {border-color:#1385BA;}
QGroupBox {border:1px solid #D9E5EF;border-radius:5px;margin-top:12px;padding:12px 8px 9px;font-weight:600;background:#FFFFFF;}
QGroupBox::title {subcontrol-origin:margin;left:9px;padding:0 5px;color:#25445C;}
QSplitter::handle {background:#E0E8EE;}
QScrollBar:vertical {background:#F4F7FA;width:9px;}
QScrollBar::handle:vertical {background:#B6C9D8;border-radius:3px;min-height:22px;}
QFrame#ribbonGroup {border-right:1px solid #D7E1EA;background:#FFFFFF;}
QLabel#ribbonCaption {color:#6B8294;font-size:8pt;}
QFrame#viewportBar {background:#FFFFFF;border-bottom:1px solid #D9E4ED;}
QLabel#calcPending {color:#925F2B;background:#FFF2DD;border-radius:4px;padding:4px 9px;}
QLabel#calcReady {color:#146147;background:#E0F5EB;border-radius:4px;padding:4px 9px;}
'''
