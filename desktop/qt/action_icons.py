"""Ícones de linha em uma grade de 16 unidades, desenhados pelo Qt."""
from functools import lru_cache

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QToolButton, QToolTip


# Cada trecho separado por "|" é um traço independente. Os pares são x,y.
GLYPHS = {
    'wizard': '2,12 3.5,13.5 10.5,6.5 9,5 2,12 | 11.5,1.5 11.5,5 | 9.75,3.25 13.25,3.25 | 5.5,2 5.5,5 | 4,3.5 7,3.5 | 13,8 13,11 | 11.5,9.5 14.5,9.5',
    'new': '3,2 9,2 13,6 13,14 3,14 3,2 | 9,2 9,6 13,6 | 5.5,10 10.5,10 | 8,7.5 8,12.5',
    'open': '1.5,12.5 1.5,4 6,4 7.5,5.5 13,5.5 13,7.5 | 1.5,12.5 4,7.5 14.5,7.5 12,12.5 1.5,12.5',
    'save': '2,2 11.5,2 14,4.5 14,14 2,14 2,2 | 5,2 5,6 11,6 11,2 | 5,14 5,9 11,9 11,14',
    'import': '3,8 3,13 13,13 13,8 | 8,1.5 8,10 | 5,7 8,10 11,7',
    'undo': '5,3 2,6 5,9 | 2,6 10,6 12.5,7.5 13,10 11,13 8,13',
    'redo': '11,3 14,6 11,9 | 14,6 6,6 3.5,7.5 3,10 5,13 8,13',
    'node': '6,6 10,6 10,10 6,10 6,6 | 8,1.5 8,4 | 8,12 8,14.5 | 1.5,8 4,8 | 12,8 14.5,8',
    'member': '2,10 5,10 5,13 2,13 2,10 | 11,3 14,3 14,6 11,6 11,3 | 5,10 11,6',
    'split': '1.5,11 6,8.8 | 10,7.2 14.5,5 | 6.5,6.5 9.5,6.5 9.5,9.5 6.5,9.5 6.5,6.5',
    'delete': '2.5,4 13.5,4 | 6,4 6,2 10,2 10,4 | 4,4 5,14 11,14 12,4 | 6.5,7 7,11 | 9.5,7 9,11',
    'group': '2,3 11,3 11,7 2,7 2,3 | 5,9 14,9 14,13 5,13 5,9',
    'profile': '2.5,2.5 13.5,2.5 13.5,4.5 9,4.5 9,11.5 13.5,11.5 13.5,13.5 2.5,13.5 2.5,11.5 7,11.5 7,4.5 2.5,4.5 2.5,2.5',
    'load': '3,2 3,9 | 1.5,7 3,9 4.5,7 | 8,2 8,9 | 6.5,7 8,9 9.5,7 | 13,2 13,9 | 11.5,7 13,9 14.5,7 | 2,13 14,13',
    'member_load': '2,12 14,8 | 3,2 3,9 | 1.5,7 3,9 4.5,7 | 8,1.5 8,7.5 | 6.5,5.5 8,7.5 9.5,5.5 | 13,1 13,6 | 11.5,4 13,6 14.5,4',
    'load_view': '1.5,8 5,4 11,4 14.5,8 11,12 5,12 1.5,8 | 8,6 8,10 | 6.5,8.5 8,10 9.5,8.5',
    'add': '8,2.5 8,13.5 | 2.5,8 13.5,8',
    'support': '2,10.5 8,3 14,10.5 2,10.5 | 3,14 5,12.5 | 7,14 9,12.5 | 11,14 13,12.5',
    'actions': '2,4 14,4 | 5,2 5,6 | 2,8 14,8 | 10,6 10,10 | 2,12 14,12 | 7,10 7,14',
    'combine': '2,4 5,4 10,8 14,8 | 2,12 5,12 10,8 | 11,5 14,8 11,11',
    'table': '2,3 14,3 14,13 2,13 2,3 | 2,7 14,7 | 2,10 14,10 | 7,7 7,13',
    'compare': '2,13 14,13 | 4,10 4,6 | 8,10 8,3 | 12,10 12,5',
    'diagnostic': '1.5,13 8,2 14.5,13 1.5,13 | 8,6 8,9 | 8,11 8,11.2',
    'export': '6,3 2,3 2,13 12,13 12,9 | 7,8 14,2 | 10,2 14,2 14,6',
    'report': '3,2 10,2 13,5 13,14 3,14 3,2 | 10,2 10,5 13,5 | 5,8 11,8 | 5,11 11,11',
    'ids': '2,4 7,4 | 4.5,4 4.5,12 | 2,12 7,12 | 9,4 11.5,4 14,6.5 14,9.5 11.5,12 9,12 9,4',
    'node_ids': '2,6 6,6 6,10 2,10 2,6 | 9,12 9,4 14,12 14,4',
    'bar_ids': '2,11 7,5 | 8.5,12 8.5,4 12,4 13.5,5.5 13.5,6.5 12,8 8.5,8 | 12,8 14,9.5 14,10.5 12.5,12 8.5,12',
    'units': '1.5,5 14.5,5 14.5,11 1.5,11 1.5,5 | 4,5 4,8 | 7,5 7,7 | 10,5 10,8 | 12.5,5 12.5,7',
    'force': '2,8 14,8 | 5,5 2,8 5,11 | 11,5 14,8 11,11',
    'deformed': '2,5 14,5 | 2,8 5,11 8,12 11,11 14,8',
    'reaction': '2,13.5 14,13.5 | 8,11 8,2 | 4.5,5.5 8,2 11.5,5.5 | 3,11 13,11',
    'cube': '8,1.5 14,5 14,11 8,14.5 2,11 2,5 8,1.5 | 2,5 8,8.5 14,5 | 8,8.5 8,14.5',
    'select': '3,2 13,9 8.5,9.5 7,14 3,2',
    'move': '8,2 8,14 | 2,8 14,8 | 6,4 8,2 10,4 | 6,12 8,14 10,12 | 4,6 2,8 4,10 | 12,6 14,8 12,10',
    'pan': '5,13 2,8 3,6.5 5,8 5,3.5 6.5,2.5 8,3.5 8,7 9.5,6 11,7 12.5,6.5 14,8 13,13 5,13',
    'fit': '2,6 2,2 6,2 | 10,2 14,2 14,6 | 14,10 14,14 10,14 | 6,14 2,14 2,10 | 6,6 10,6 10,10 6,10 6,6',
    'focus': '2,6 2,2 6,2 | 10,2 14,2 14,6 | 14,10 14,14 10,14 | 6,14 2,14 2,10',
    'run': '5,2.5 13,8 5,13.5 5,2.5',
    'snap': '2.5,2.5 2.5,9 4.5,12.5 8,14 11.5,12.5 13.5,9 13.5,2.5 10.5,2.5 10.5,9 9,11 7,11 5.5,9 5.5,2.5 2.5,2.5 | 2.5,5.5 5.5,5.5 | 10.5,5.5 13.5,5.5',
    'grid': '2,2 14,2 14,14 2,14 2,2 | 6,2 6,14 | 10,2 10,14 | 2,6 14,6 | 2,10 14,10',
    'panel': '2,3 14,3 14,13 2,13 2,3 | 9,3 9,13 | 11,6 12,6 | 11,9 12,9',
    'check': '2.5,8 6,11.5 13.5,4',
    'color': '8,2 12,7 13,10 11.5,13 8,14 4.5,13 3,10 4,7 8,2 | 5.5,10.5 6.5,12 8,12.5',
    'case': '3,2 10,2 13,5 13,14 3,14 3,2 | 10,2 10,5 13,5 | 5.5,8 10.5,8 | 5.5,11 10.5,11',
    'more': '4,8 4.3,8 | 8,8 8.3,8 | 12,8 12.3,8',
    'collapse': '2,3 14,3 14,13 2,13 2,3 | 9,3 9,13 | 4,6 6,8 4,10',
    'home': '2,8 8,2 14,8 | 4,7 4,14 7,14 7,10 9,10 9,14 12,14 12,7',
}


class IconButton(QToolButton):
    hover_delay_ms = 500

    def __init__(self, label, callback, icon, *, checkable=False):
        super().__init__()
        self.set_label(label)
        self.setCheckable(checkable)
        self.setIcon(action_icon(icon))
        self.setIconSize(QSize(17, 17))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.clicked.connect(callback)
        self._hover_timer = QTimer(self, singleShot=True, interval=self.hover_delay_ms,
                                   timerType=Qt.TimerType.PreciseTimer)
        self._hover_timer.timeout.connect(self._show_tip)

    def set_label(self, label):
        self.setText(label)
        self.setAccessibleName(label)
        self.setToolTip(label)

    def _show_tip(self):
        if self.isVisible() and self.underMouse():
            QToolTip.showText(QCursor.pos(), self.toolTip(), self, self.rect())

    def event(self, event):
        kind = event.type()
        timer = getattr(self, '_hover_timer', None)
        if timer is not None:
            if kind == QEvent.Type.Enter:
                timer.start()
            elif kind in (QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.MouseButtonPress):
                timer.stop()
                if QToolTip.text() == self.toolTip():
                    QToolTip.hideText()
            elif kind == QEvent.Type.ToolTip:
                return True
        return super().event(event)


@lru_cache(maxsize=None)
def action_icon(name):
    path = QPainterPath()
    for stroke in GLYPHS[name].split('|'):
        start, *points = (tuple(map(float, pair.split(','))) for pair in stroke.split())
        path.moveTo(*start)
        for point in points:
            path.lineTo(*point)

    icon = QIcon()
    colors = {
        QIcon.Mode.Normal: '#17658C',
        QIcon.Mode.Disabled: '#8298AA',
    }
    for mode, color in colors.items():
        for scale in (1, 2):
            pixmap = QPixmap(16 * scale, 16 * scale)
            pixmap.fill(Qt.GlobalColor.transparent)
            with QPainter(pixmap) as painter:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.scale(scale, scale)
                pen = QPen(QColor(color), 1.3)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawPath(path)
            pixmap.setDevicePixelRatio(scale)
            icon.addPixmap(pixmap, mode)
    return icon
