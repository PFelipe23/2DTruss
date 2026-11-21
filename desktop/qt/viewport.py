"""Editor CAD 2D: coordenadas de engenharia mm, Y positivo para cima.

Qt somente representa/despacha comandos de edição. Todas as mutações passam
por desktop.editing + Session.update_project e são validadas pelo núcleo.
"""
from __future__ import annotations
from html import escape
from itertools import chain
from math import ceil,floor,hypot,isclose,isfinite
from PySide6.QtCore import Qt,QLineF,QPointF,QSignalBlocker,Signal,QRect,QRectF
from PySide6.QtGui import QColor,QPen,QBrush,QFont,QFontMetricsF,QPainter,QPainterPath,QRegion
from PySide6.QtWidgets import (QGraphicsView,QGraphicsScene,QGraphicsEllipseItem,
                               QGraphicsLineItem,QGraphicsPathItem,QGraphicsSimpleTextItem,QGraphicsItem,
                               QApplication,QFrame,QLabel,QRubberBand,QVBoxLayout)
from .display_units import DisplayUnits
from .result_display import (displacement_peaks, displacement_resultant, envelope_details,
                             envelope_rank, envelope_values, nodal_displacement_text, selected_envelope)

GROUP_COLORS = {'superior': '#1379A5', 'inferior': '#175477',
                'montante': '#546D85', 'diagonal': '#A05A18', 'outro': '#647C8E'}
TENS='#C53646'; COMP='#2666B8'
NODE_RADIUS = 6
DEFAULT_UNITS = DisplayUnits()
DEFORMED = '#087C69'
DISPLACEMENT_PEAK = '#985215'


class NodeItem(QGraphicsEllipseItem):
    def __init__(self,node_id,x,y,*,draft=False, units=DEFAULT_UNITS, physical_y=None, restraint=None):
        super().__init__(-NODE_RADIUS,-NODE_RADIUS,2 * NODE_RADIUS,2 * NODE_RADIUS)
        self.node_id=node_id;self.draft=draft
        self.restraint = restraint
        self.setPos(x,-y)
        self.setZValue(30)
        self.setPen(QPen(QColor('#1779A7' if not draft else '#DE8A20'),1.7))
        self.setBrush(QBrush(QColor('white' if not draft else '#FFF1CA')))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,True)
        xy = f'X={units.length_text(x)}, Y={units.length_text(y if physical_y is None else physical_y)}'
        tip = f'Nó {node_id} | {xy}' + (' | rascunho' if draft else '')
        if restraint:
            state = 'Declarado' if restraint['confirmed'] else 'Rever'
            tip += f'\nTravamento fora do plano · {state} · {restraint["reference"]}'
        self.setToolTip(tip)

    def boundingRect(self):
        rect = super().boundingRect()
        return rect.adjusted(0, -5, 5, 0) if getattr(self, 'restraint', None) else rect

    def paint(self, painter, option, widget=None):
        if not self.isSelected():
            super().paint(painter, option, widget)
        else:
            painter.save()
            painter.setPen(self.pen())
            painter.setBrush(QColor('#BCE1F3'))
            painter.drawEllipse(self.rect())
            painter.restore()
        if self.restraint:
            confirmed = self.restraint['confirmed']
            painter.save()
            painter.setPen(QPen(QColor('#67449B' if confirmed else '#945719'), 1))
            painter.setBrush(QColor('#67449B' if confirmed else '#FFF1C2'))
            painter.drawRoundedRect(QRectF(4, -10, 5, 5), 1, 1)
            painter.restore()


class MemberItem(QGraphicsLineItem):
    def __init__(self,m,coords,force=None,units=DEFAULT_UNITS,*,ghost=False,extremes=None):
        a,b=coords[m.i],coords[m.j]
        super().__init__(a.x(),a.y(),b.x(),b.y())
        self.member_id=m.id
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True)
        self.setZValue(10)
        chord = m.group in ('superior','inferior')
        color=TENS if force is not None and force>1e-7 else COMP if force is not None and force< -1e-7 else GROUP_COLORS.get(m.group, GROUP_COLORS['outro'])
        width = 2.4 if chord else 1.6
        if ghost:
            color, width = '#A6B3BF', 1.4
        elif extremes is not None:
            traction = extremes['max_tension_n'] > 0
            compression = extremes['max_compression_n'] < 0
            color = TENS if traction and not compression else COMP if compression and not traction else '#647C8E'
            width = 2.8 if traction or compression else 1.4
        elif force is not None:
            width = 3 if abs(force) > 1e-7 else 1.4
            if abs(force) <= 1e-7:
                color = '#91A4B4'
        pen=QPen(QColor(color), width);pen.setCosmetic(True)
        self.setPen(pen)  # largura cosmética em qualquer zoom
        description = f'{m.id} | {m.group} | {m.profile}'
        if extremes is not None:
            description += '\n' + '\n'.join(f'{key} {value}' for key, value in envelope_details(extremes, units))
        elif force is not None:
            description += f' | N={units.force_text(force, signed=True)}'
        self.setToolTip(description)

    def paint(self, painter, option, widget=None):
        painter.save()
        if self.isSelected():
            outline = QPen(QColor('#F9BF58'), 6)
            outline.setCosmetic(True)
            painter.setPen(outline)
            painter.drawLine(self.line())
        painter.setPen(self.pen())
        painter.drawLine(self.line())
        painter.restore()


class BoxedLabel(QGraphicsSimpleTextItem):
    def __init__(self, text, color, parent=None, *, bold=False):
        super().__init__(text, parent)
        self.setFont(QFont('Segoe UI', 9, QFont.Weight.DemiBold if bold else QFont.Weight.Normal))
        self.setBrush(QColor(color))
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self):
        return super().boundingRect().adjusted(-3, -1, 3, 1)

    def _paint_box(self, painter):
        painter.save()
        painter.setBrush(QColor('#FCFDFE'))
        painter.setPen(QPen(QColor('#AABCCB'), 1))
        painter.drawRoundedRect(self.boundingRect().adjusted(.5, .5, -.5, -.5), 2, 2)
        painter.restore()

    def paint(self, painter, option, widget=None):
        self._paint_box(painter)
        super().paint(painter, option, widget)


class ForceVectorItem(QGraphicsPathItem):
    """Seta de carga ou reação em coordenadas do dispositivo."""

    def __init__(self, node, position, fx, fy, maximum, units=DEFAULT_UNITS, *, reaction=False):
        magnitude = hypot(fx, fy)
        direction = QPointF(fx / magnitude, -fy / magnitude)
        normal = QPointF(-direction.y(), direction.x())
        self.node_id = node
        self.reaction = reaction
        length = max(10, 50 * magnitude / maximum)
        outward = (fy if abs(fy) > magnitude * 1e-9 else fx) > 0
        radius = NODE_RADIUS + 1
        origin = QPointF(0, 25) if reaction else QPointF()
        tail = origin + direction * (-length - radius if reaction else radius if outward else -radius - length)
        head = tail + direction * length
        wing = min(7, length * .5)
        base = head - direction * wing
        path = QPainterPath(tail)
        path.lineTo(head)
        path.moveTo(base - normal * wing * .55)
        path.lineTo(head)
        path.lineTo(base + normal * wing * .55)
        super().__init__(path)
        self.setPos(position)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(25)
        color = '#68369C' if reaction else '#B66217'
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not reaction)
        pen = QPen(QColor(color), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        x, y = ('Rx', 'Ry') if reaction else ('Fx', 'Fy')
        self.setToolTip(f'{node} · {x} {units.force_text(fx, signed=True, load=True)} · '
                        f'{y} {units.force_text(fy, signed=True, load=True)}')
        self.label = BoxedLabel(units.force_text(magnitude, load=True), color, self)

    def paint(self, painter, option, widget=None):
        if self.isSelected():
            painter.setPen(QPen(QColor('#F9BF58'), 5))
            painter.drawPath(self.path())
        painter.setPen(self.pen())
        painter.drawPath(self.path())


def support_symbol(point, ux, uy):
    path = QPainterPath(QPointF(0, NODE_RADIUS))
    path.lineTo(-8, 18)
    path.lineTo(8, 18)
    path.closeSubpath()
    if ux != uy:
        for x in (-5, 5):
            path.addEllipse(QPointF(x, 21), 2, 2)
    base = 24 if ux != uy else 19
    path.moveTo(-10, base)
    path.lineTo(10, base)
    for x in (-8, -3, 2, 7):
        path.moveTo(x, base)
        path.lineTo(x - 3, base + 4)
    item = QGraphicsPathItem(path)
    item.setPos(point)
    item.setZValue(12)
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
    item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    item.setPen(QPen(QColor('#435F79'), 1.25))
    if ux and not uy:
        item.setRotation(90)
    item.setToolTip('Apoio · ' + ('UX e UY' if ux and uy else 'UX' if ux else 'UY'))
    return item


class AnchoredLabel(BoxedLabel):
    def __init__(self, text, anchor, node, color, *, bold=False, below=False):
        super().__init__(text, color, bold=bold)
        self.anchor = anchor
        self.node = node
        self.below = below
        self.setPos(anchor)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(42)
        self.hide()


class EnvelopeLabel(AnchoredLabel):
    """Uma caixa por barra, com os dois extremos em linhas independentes."""

    def __init__(self, member, values, details, anchor, *, peak=False):
        super().__init__('\n'.join(values), anchor, False, '#647C8E', bold=True)
        self.member_id = member
        self.details = details
        self.values = values
        self.peak = peak
        font = self.font()
        font.setPointSize(10)
        self.setFont(font)
        metrics = QFontMetricsF(self.font())
        width = max(map(metrics.horizontalAdvance, values)) + 10
        self._rect = QRectF(0, 0, width, 2 * (metrics.height() + 1))
        self.leader = QGraphicsLineItem(self)
        self.leader.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent)
        self.leader.setPen(QPen(QColor('#879CAE'), 1))
        self.leader.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self):
        return self._rect if hasattr(self, '_rect') else super().boundingRect()

    def shape(self):
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def popup(self, position, widget):
        lines = '<br>'.join(f'<span style="color:{color}">{escape(title)} {escape(value)}</span>'
                            for (title, value), color in zip(self.details, (TENS, COMP)))
        popup = QFrame(widget, Qt.WindowType.Popup)
        popup.setObjectName('envelopeDetails')
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(10, 7, 10, 8)
        title = QLabel(f'Barra {self.member_id}')
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setObjectName('envelopeTitle')
        layout.addWidget(title)
        layout.addWidget(QLabel(f'<div style="font-size:10pt">{lines}</div>'))
        popup.adjustSize()
        screen = widget.screen().availableGeometry()
        x = min(position.x() + 10, screen.right() - popup.width())
        y = min(position.y() + 10, screen.bottom() - popup.height())
        popup.move(max(screen.left(), x), max(screen.top(), y))
        popup.show()

    def paint(self, painter, option, widget=None):
        self._paint_box(painter)
        height = self._rect.height() / 2
        painter.save()
        painter.setFont(self.font())
        painter.setPen(QPen(QColor('#D8E3EB')))
        painter.drawLine(QLineF(1, height, self._rect.width() - 1, height))
        for index, (value, color) in enumerate(zip(self.values, (TENS, COMP))):
            painter.setPen(QColor(color if value != '—' else '#768997'))
            painter.drawText(QRectF(0, index * height, self._rect.width(), height),
                             Qt.AlignmentFlag.AlignCenter, value)
        painter.restore()


class DeformedNodeItem(QGraphicsEllipseItem):
    def __init__(self, node, position, *, peak):
        radius = 5.5 if peak else 2.8
        super().__init__(-radius, -radius, 2 * radius, 2 * radius)
        self.node_id = node
        self.peak = peak
        self.setPos(position)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(32 if peak else 28)
        color = DISPLACEMENT_PEAK if peak else DEFORMED
        self.setBrush(QColor('#FFE3BD' if peak else '#D7F5EE'))
        self.setPen(QPen(QColor(color), 1.7 if peak else 1.2))


class TrussView(QGraphicsView):
    selected=Signal(list)            # [(kind, id)]
    add_node=Signal(float,float)
    add_member=Signal(str,str)
    split_member=Signal(str,float)
    moved=Signal(object)             # {id: (x_mm,y_mm)}
    status_text=Signal(str)
    coordinates_changed = Signal(float, float)
    forces_displayed = Signal(dict, str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self));self.scene().selectionChanged.connect(self._selected)
        self.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setBackgroundBrush(QBrush(QColor('#F5F8FB')))
        self.setStyleSheet('border:0;')
        self.tool='select';self.grid_mm=50.;self.snap_enabled=True
        self.grid_visible = True
        self.grid_major = 5
        self.selection_filter = 'all'
        self.show_reactions = False
        self._reaction_items = []
        self._pan_position = None
        self._selection_origin = None
        self._marquee = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())
        self._analysis_id = None
        self.units = DEFAULT_UNITS
        self.show_ids=False;self.show_efforts=False;self.show_forces=False
        self.member_id_groups = set()
        self.show_load_values = False
        self._force_items = []
        self._support_items = set()
        self._identifiers = []
        self._axial_labels = []
        self.show_axial_values = True
        self.show_envelope = False
        self.envelope_scope = 'general'
        self.show_deformed = False
        self._deformed_nodes = {}
        self._peak_labels = {}
        self._displacement_callout = None
        self._inspected_node = None
        self.deformation_factor = None
        self.effective_deformation_factor = None
        self._members={};self._nodes={};self._drafts={};self._pos={}
        self._analysis=None;self._model=None;self._session=None
        self._pending_first=None;self._fit_pending=False
        self.setMouseTracking(True)

    def set_tool(self,tool:str):
        if tool not in ('select','pan','move','node','bar','split'):
            raise ValueError('Ferramenta desconhecida')
        self.tool = tool
        self._pending_first = None
        self._selection_origin = None
        self._marquee.hide()
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if tool=='pan' else QGraphicsView.DragMode.NoDrag)
        self.setCursor(Qt.CursorShape.OpenHandCursor if tool=='pan' else Qt.CursorShape.CrossCursor if tool in ('node','bar','split') else Qt.CursorShape.ArrowCursor)
        for item in self._nodes.values():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,tool=='move')
        self.status_text.emit({'select':'Selecionar por clique ou retângulo (Ctrl para múltiplos)',
           'pan':'Arrastar para deslocar vista','move':'Arrastar nós (snap configurável)',
           'node':'Clique na vista para criar um nó provisório',
           'bar':'Clique em dois nós para criar uma barra',
           'split':'Clique em uma barra para dividir em duas metades'}[tool])

    def _selected(self):
        self.sync_displacement_selection()
        self.selected.emit(self.selected_ids())

    def selection_item(self, kind, identifier):
        if kind == 'node':
            return self._nodes.get(identifier) or self._drafts.get(identifier)
        if kind == 'member':
            return self._members.get(identifier)
        return next((arrow for arrow in self._force_items if arrow.node_id == identifier), None)

    def configure_grid(self, step_mm, major_every):
        self.grid_mm = step_mm
        self.grid_major = major_every
        self.viewport().update()

    def set_grid_visible(self, visible):
        self.grid_visible = visible
        self.viewport().update()

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        if not self.grid_visible:
            return
        transform = painter.worldTransform()
        # Reduz a densidade em zoom distante sem deslocar a malha de snap.
        step = self.grid_mm
        scale = max(transform.m11(), 1e-12)
        while step * scale < 8:
            step *= self.grid_major
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for multiple, color in [(1, '#E5EBF1'), (self.grid_major, '#D7E1EB')]:
            pen = QPen(QColor(color))
            pen.setCosmetic(True)
            painter.setPen(pen)
            dx = dy = step * multiple
            lines = [QLineF(i * dx, rect.top(), i * dx, rect.bottom())
                     for i in range(ceil(rect.left() / dx), floor(rect.right() / dx) + 1)]
            lines.extend(QLineF(rect.left(), i * dy, rect.right(), i * dy)
                         for i in range(ceil(rect.top() / dy), floor(rect.bottom() / dy) + 1))
            painter.drawLines(lines)
        painter.restore()

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        if self._pan_position is not None:
            delta = position - self._pan_position
            self._pan_position = position
            viewport = self.viewport().rect()
            target = self.mapToScene(viewport.center()) - QPointF(delta) / self.transform().m11()
            exposed = self.mapToScene(viewport).boundingRect()
            exposed.moveCenter(target)
            self.scene().setSceneRect(self.scene().sceneRect().united(exposed.adjusted(-25, -25, 25, 25)))
            self.centerOn(target)
            event.accept()
            return
        point = self.mapToScene(position)
        self.coordinates_changed.emit(point.x(), -point.y())
        if self._selection_origin is not None:
            rect = QRect(self._selection_origin, position).normalized()
            if (position - self._selection_origin).manhattanLength() >= QApplication.startDragDistance():
                crossing = self._crossing(position)
                color = '#168063' if crossing else '#176DAD'
                self._marquee.setStyleSheet(f'border: 1px solid {color}; background: rgba(55, 145, 199, 30);')
                self._marquee.setGeometry(rect)
                self._marquee.show()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _add_identifier(self, text, anchor, *, node):
        item = AnchoredLabel(text, anchor, node, '#245376' if node else '#326C66')
        self.scene().addItem(item)
        self._identifiers.append(item)

    def render(self,session,analysis_id=None,*,fit=False):
        """Renderização sem recalcular ou modificar a estrutura."""
        selection = self.selected_ids() if session is self._session else []
        self._session=session;model=session.model;self._model=model
        self._analysis_id = analysis_id
        self._analysis=(session.result or {}).get('analyses',{}).get(analysis_id) if analysis_id else None
        self._force_items.clear()
        self._reaction_items.clear()
        self._support_items.clear()
        self._identifiers.clear()
        self._axial_labels.clear()
        self._deformed_nodes.clear()
        self._peak_labels.clear()
        self._displacement_callout = None
        self._inspected_node = None
        self.effective_deformation_factor = None
        scene=self.scene();scene.blockSignals(True);scene.clear()
        self._members={};self._nodes={};self._drafts={}
        self._pos={n.id:QPointF(n.x,-n.y) for n in model.nodes}
        force=(self._analysis or {}).get('axial_n',{})
        envelope = (selected_envelope(session.result or {}, self.envelope_scope)
                    if self.show_efforts and self.show_envelope else {})
        deforming = self.show_deformed and self._analysis is not None
        for m in model.members:
            current = force.get(m.id) if self.show_efforts and not self.show_envelope else None
            item = MemberItem(m, self._pos, current, self.units, ghost=deforming, extremes=envelope.get(m.id))
            scene.addItem(item);self._members[m.id]=item
        if self.show_efforts and self.show_axial_values:
            self._draw_axial_labels(scene, model, envelope, {} if self.show_envelope else force)
        markings = (session.project.get('stability') or {}).get('nodal_restraints', {})
        for n in model.nodes:
            item=NodeItem(n.id,n.x,n.y,units=self.units,physical_y=n.y,restraint=markings.get(n.id))
            scene.addItem(item);self._nodes[n.id]=item
            if deforming:
                delta = self._analysis['nodal_displacements'][n.id]
                item.setToolTip(f'{item.toolTip()}\n{nodal_displacement_text(n.id, delta, self.units)}')
            if self.show_ids:
                self._add_identifier(n.id,self._pos[n.id],node=True)
        for node in session.project.get('cad_drafts',[]):
            item=NodeItem(node['id'],node['x_mm'],node['y_mm'],
                          draft=True,units=self.units,physical_y=node['y_mm'])
            scene.addItem(item);self._drafts[node['id']]=item
            if self.show_ids:
                self._add_identifier(node['id'],item.pos(),node=True)
        for member in model.members:
            if member.group in self.member_id_groups:
                self._add_identifier(member.id, (self._pos[member.i] + self._pos[member.j]) / 2, node=False)
        for nid, (ux, uy) in model.supports.items():
            if ux or uy:
                symbol = support_symbol(self._pos[nid], ux, uy)
                scene.addItem(symbol)
                self._support_items.add(symbol)
        self._render_forces(analysis_id)
        self._render_reactions()
        if deforming:
            self._draw_deformed(scene, model)
        scene.blockSignals(False)
        with QSignalBlocker(scene):
            for kind, identifier in selection:
                item = self.selection_item(kind, identifier)
                if item is not None and self._accepts(kind):
                    item.setSelected(True)
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-400,-400,400,400))
        self._selected()
        if fit or not self._fit_pending:self.fit()
        else:self._place_labels()

    def _draw_axial_labels(self, scene, model, envelope, force):
        def magnitude(member):
            return envelope_rank(envelope[member.id]) if envelope else abs(force.get(member.id, 0))

        tensile_peak = max((entry['max_tension_n'] for entry in envelope.values()), default=0.)
        compression_peak = min((entry['max_compression_n'] for entry in envelope.values()), default=0.)
        for member in sorted(model.members, key=magnitude, reverse=True):
            if not envelope and magnitude(member) < .0001:
                continue
            mid = (self._pos[member.i] + self._pos[member.j]) / 2
            if envelope:
                entry = envelope[member.id]
                peak = (tensile_peak > .0001 and isclose(entry['max_tension_n'], tensile_peak)
                        or compression_peak < -.0001 and isclose(entry['max_compression_n'], compression_peak))
                label = EnvelopeLabel(member.id, envelope_values(entry, self.units, unit=False),
                                      envelope_details(entry, self.units), mid, peak=peak)
            else:
                axial = force[member.id]
                label = AnchoredLabel(self.units.force_text(axial, signed=True, unit=False),
                                      mid, False, TENS if axial > 0 else COMP, bold=True)
            scene.addItem(label)
            self._axial_labels.append(label)

    def _draw_deformed(self, scene, model):
        displacements = self._analysis['nodal_displacements']
        peak = max(map(displacement_resultant, displacements.values()), default=0.)
        extent = max(model.span_mm, max(n.y for n in model.nodes) - min(n.y for n in model.nodes))
        automatic = min(10_000., max(1., extent * .035 / peak)) if peak else 1.
        amp = automatic if self.deformation_factor is None else self.deformation_factor
        self.effective_deformation_factor = amp
        deformed = {}
        for node, original in self._pos.items():
            delta = displacements[node]
            deformed[node] = original + QPointF(amp * delta['ux_mm'], -amp * delta['uy_mm'])
        pen = QPen(QColor(DEFORMED), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        for member in model.members:
            line = scene.addLine(QLineF(deformed[member.i], deformed[member.j]), pen)
            line.setZValue(13)
            line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        peaks = displacement_peaks(displacements)
        for node, position in deformed.items():
            marker = DeformedNodeItem(node, position, peak=node in peaks)
            marker.setToolTip(nodal_displacement_text(node, displacements[node], self.units))
            scene.addItem(marker)
            self._deformed_nodes[node] = marker
        for node, extremes in peaks.items():
            values = [f'{kind} {self.units.displacement_text(value, signed=signed)}'
                      for kind, value, signed in extremes]
            label = AnchoredLabel(f'{node} · ' + ' · '.join(values), deformed[node], True,
                                  DISPLACEMENT_PEAK, bold=True)
            scene.addItem(label)
            self._peak_labels[node] = label

    def sync_displacement_selection(self):
        if not self._deformed_nodes:
            if self.show_envelope and self._axial_labels:
                self._place_labels()
            return
        selected = self.selected_ids()
        node = selected[0][1] if len(selected) == 1 and selected[0][0] == 'node' else None
        if node == self._inspected_node:
            return
        self._inspected_node = node
        if self._displacement_callout is not None:
            self.scene().removeItem(self._displacement_callout)
            self._displacement_callout = None
        if node in self._deformed_nodes:
            delta = self._analysis['nodal_displacements'][node]
            value = nodal_displacement_text(node, delta, self.units, compact=True)
            marker = self._deformed_nodes[node]
            label = AnchoredLabel(value, marker.pos(), True, '#155B51', bold=True, below=True)
            label.leader = QGraphicsLineItem(label)
            label.leader.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent)
            label.leader.setPen(QPen(QColor('#428C80'), 1.2))
            label.leader.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene().addItem(label)
            self._displacement_callout = label
        self._place_labels()

    def _render_forces(self, case_id):
        if not self.show_forces or not case_id:
            self.forces_displayed.emit({}, '')
            return
        try:
            forces = ({node: (load['fx_n'], load['fy_n']) for node, load in self._analysis['loads'].items()}
                      if self._analysis else self._session.forces_for_case(case_id))
            vectors = []
            for node, (fx, fy) in forces.items():
                magnitude = hypot(fx, fy)
                if not isfinite(magnitude):
                    raise ValueError(f'Força nodal não finita em {node}.')
                if node in self._pos and magnitude > 1e-8:
                    vectors.append((magnitude, node, fx, fy))
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            self.forces_displayed.emit({}, str(error))
            return
        vectors.sort(key=lambda vector: (-vector[0], self._pos[vector[1]].x()))
        if vectors:
            maximum = vectors[0][0]
            for _, node, fx, fy in vectors:
                arrow = ForceVectorItem(node, self._pos[node], fx, fy, maximum, self.units)
                arrow.label.hide()
                self.scene().addItem(arrow)
                self._force_items.append(arrow)
                item = self._nodes[node]
                item.setToolTip(f'{item.toolTip()}\n{arrow.toolTip()}')
        self.forces_displayed.emit(forces, '')

    def _render_reactions(self):
        if not self.show_reactions or not self._analysis:
            return
        values = [(node, vector['fx_n'], vector['fy_n'])
                  for node, vector in self._analysis['reactions'].items()
                  if hypot(vector['fx_n'], vector['fy_n']) > 1e-7]
        maximum = max((hypot(fx, fy) for _, fx, fy in values), default=1.)
        for node, fx, fy in values:
            arrow = ForceVectorItem(node, self._pos[node], fx, fy, maximum, self.units, reaction=True)
            arrow.label.hide()
            self.scene().addItem(arrow)
            self._reaction_items.append(arrow)
            item = self._nodes[node]
            item.setToolTip(f'{item.toolTip()}\n{arrow.toolTip()}')
            text = ' · '.join(f'{axis} {self.units.force_text(value, signed=True, load=True)}'
                              for axis, value in (('Rx', fx), ('Ry', fy)) if abs(value) > 1e-7)
            arrow.label.setText(text)

    def set_load_values(self, visible):
        self.show_load_values = visible
        self._place_labels()

    def _place_labels(self):
        if not self.show_load_values:
            for arrow in self._force_items:
                arrow.label.hide()
        inspection = [self._displacement_callout] if self._displacement_callout else []
        for node, label in self._peak_labels.items():
            if node == self._inspected_node:
                label.hide()
            else:
                inspection.append(label)
        axial = self._axial_labels
        if axial and isinstance(axial[0], EnvelopeLabel):
            selected = {member for kind, member in self.selected_ids() if kind == 'member'}
            displayed = []
            for label in axial:
                if label.peak or label.member_id in selected:
                    displayed.append(label)
                else:
                    label.hide()
            axial = sorted(displayed, key=lambda label: label.member_id not in selected)
        anchored = axial + self._identifiers
        arrows = self._reaction_items + (self._force_items if self.show_load_values else [])
        if not (arrows or anchored or inspection):
            return

        viewport = self.viewport().rect()
        transform = self.viewportTransform()
        occupied = QRegion()
        for item in self.items(viewport):
            if isinstance(item, (NodeItem, ForceVectorItem, DeformedNodeItem)) or item in self._support_items:
                rect = item.deviceTransform(transform).mapRect(item.boundingRect())
                occupied += QRegion(rect.toAlignedRect())
        self._place_anchored_labels(inspection, viewport, transform, occupied, allow_extra_rows=True)

        for arrow in arrows:
            label = arrow.label
            label.hide()
            device = arrow.deviceTransform(transform)
            shaft = device.mapRect(arrow.boundingRect())
            if not viewport.intersects(shaft.toAlignedRect()):
                continue
            bounds = label.boundingRect()
            left = shaft.center().x() - bounds.width() / 2
            if arrow.reaction:
                left = max(viewport.left() + 4, min(left, viewport.right() - bounds.width() - 4))
            top = shaft.bottom() + 5 if arrow.reaction else shaft.top() - bounds.height() - 4
            direction = 1 if arrow.reaction else -1
            for level in (0, 1):
                position = QPointF(left, top + direction * level * (bounds.height() + 3))
                candidate = QRectF(position, bounds.size()).adjusted(-3, -1, 3, 1).toAlignedRect()
                if viewport.contains(candidate) and not occupied.intersects(candidate):
                    label.setPos(position - device.map(QPointF()) - bounds.topLeft())
                    label.show()
                    occupied += QRegion(candidate)
                    break
        self._place_anchored_labels(anchored, viewport, transform, occupied)

    def _place_anchored_labels(self, labels, viewport, transform, occupied, *, allow_extra_rows=False):
        inverse, _ = transform.inverted()
        for label in labels:
            label.hide()
            point = transform.map(label.anchor)
            if not viewport.contains(point.toPoint()):
                continue
            bounds = label.boundingRect()
            w, h = bounds.width(), bounds.height()
            gap = 9 if label.node else 5
            above, below = (-w/2, -gap-h), (-w/2, gap)
            vertical = (below, above) if label.below else (above, below)
            offsets = (*vertical, (gap, -h/2), (-gap-w, -h/2))
            room = allow_extra_rows or isinstance(label, EnvelopeLabel)
            if room:
                offsets = chain(offsets, ((x, y + (h + 4) * step * direction)
                                          for (x, y), direction in ((above, -1), (below, 1))
                                          for step in (1, 2)))
            for dx, dy in offsets:
                x = point.x() + dx
                if room:
                    x = max(viewport.left() + 2, min(x, viewport.right() - w - 2))
                position = QPointF(x, point.y() + dy)
                candidate = QRectF(position, bounds.size()).adjusted(-2, -1, 2, 1).toAlignedRect()
                if viewport.contains(candidate) and not occupied.intersects(candidate):
                    label.setPos(inverse.map(position - bounds.topLeft()))
                    if label is self._displacement_callout or isinstance(label, EnvelopeLabel):
                        base = transform.map(label.pos())
                        edge = QPointF(max(position.x(), min(point.x(), position.x() + w)),
                                       max(position.y(), min(point.y(), position.y() + h)))
                        label.leader.setLine(QLineF(edge - base, point - base))
                        label.leader.setVisible(label is self._displacement_callout or hypot(
                            edge.x() - point.x(), edge.y() - point.y()) >= 18)
                    label.show()
                    occupied += QRegion(candidate)
                    break

    def fit(self):
        if not self._model:return
        self._fit_pending=True
        rect = self.scene().itemsBoundingRect().adjusted(-400, -400, 400, 400)
        self.scene().setSceneRect(rect)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        if self._force_items or self._reaction_items:
            mapped = self.mapFromScene(rect).boundingRect()
            width, height = self.viewport().width(), self.viewport().height()
            factor = min(1, max(1, width - 120) / max(1, mapped.width()),
                         max(1, height - 184) / max(1, mapped.height()))
            self.scale(factor, factor)
            self.centerOn(rect.center())
        self._place_labels()

    def wheelEvent(self,e):
        factor=1.16 if e.angleDelta().y()>0 else 1/1.16
        self.scale(factor,factor)
        self._place_labels()
        e.accept()

    def _snap(self, pt):
        """Snap por extremidade, ponto médio ou malha de desenho."""
        x,y=pt.x(),pt.y()
        if not self.snap_enabled:return QPointF(x,y)
        reference=self.mapToScene(0,0)
        other=self.mapToScene(12,0)
        tol=max(1e-6,hypot(other.x()-reference.x(),other.y()-reference.y()))
        candidates=list(self._pos.values())
        for m in self._model.members if self._model else []:
            a,b=self._pos[m.i],self._pos[m.j]
            candidates.append(QPointF((a.x()+b.x())*.5,(a.y()+b.y())*.5))
        nearby=[(hypot(x-c.x(),y-c.y()),c) for c in candidates]
        if nearby:
            distance,point=min(nearby,key=lambda z:z[0])
            if distance<=tol:return QPointF(point)
        if self.grid_mm>0:
            x=round(x/self.grid_mm)*self.grid_mm
            y=round(y/self.grid_mm)*self.grid_mm
        return QPointF(x,y)

    def _items_at(self, viewport_point):
        return self.items(viewport_point)

    def _nearby_member(self, point):
        rect = QRect(point.x() - 7, point.y() - 7, 15, 15)
        transform = self.viewportTransform()
        nearest = None
        distance = 7.
        for item in self.items(rect):
            if not isinstance(item, MemberItem):
                continue
            a, b = transform.map(item.line().p1()), transform.map(item.line().p2())
            dx, dy = b.x() - a.x(), b.y() - a.y()
            length2 = dx * dx + dy * dy
            if not length2:
                continue
            t = max(0., min(1., ((point.x() - a.x()) * dx + (point.y() - a.y()) * dy) / length2))
            delta = hypot(point.x() - a.x() - t * dx, point.y() - a.y() - t * dy)
            if delta < distance:
                nearest, distance = item, delta
        return nearest

    def _accepts(self, kind):
        return self.selection_filter in ('all', kind)

    def _crossing(self, position):
        origin = self._selection_origin
        return position.x() < origin.x() or position.y() < origin.y()

    def _rectangle_hits(self, rect, crossing):
        transform = self.viewportTransform()
        if self._accepts('node'):
            for node in chain(self._nodes.values(), self._drafts.values()):
                if rect.contains(self.mapFromScene(node.pos())):
                    yield node
        if self._accepts('member'):
            bounds = QRectF(rect)
            corners = (bounds.topLeft(), bounds.topRight(), bounds.bottomRight(), bounds.bottomLeft())
            sides = tuple(QLineF(corners[i - 1], point) for i, point in enumerate(corners))
            for member in self._members.values():
                a, b = transform.map(member.line().p1()), transform.map(member.line().p2())
                contains_a, contains_b = bounds.contains(a), bounds.contains(b)
                segment = QLineF(a, b)
                if (contains_a and contains_b) or (crossing and (
                        contains_a or contains_b or any(
                            segment.intersects(side)[0] == QLineF.IntersectionType.BoundedIntersection for side in sides))):
                    yield member
        if self._accepts('load'):
            for arrow in self._force_items:
                bounds = arrow.deviceTransform(transform).mapRect(arrow.boundingRect()).toAlignedRect()
                if rect.contains(bounds) or (crossing and rect.intersects(bounds)):
                    yield arrow

    def _click_hit(self, point):
        hit = self._items_at(point)
        if self._accepts('member'):
            label = next((item for item in hit if isinstance(item, EnvelopeLabel)), None)
            if label is not None:
                return self._members[label.member_id], label
        if self._accepts('node'):
            node = next((item for item in hit if isinstance(item, (NodeItem, DeformedNodeItem))), None)
            if isinstance(node, DeformedNodeItem):
                node = self._nodes[node.node_id]
            if node is not None:
                return node, None
        if self._accepts('load'):
            for item in self.items(QRect(point.x() - 3, point.y() - 3, 7, 7)):
                arrow = item.parentItem() if isinstance(item, BoxedLabel) else item
                if isinstance(arrow, ForceVectorItem) and not arrow.reaction:
                    return arrow, None
        return self._nearby_member(point) if self._accepts('member') else None, None

    def _select_hits(self, items, additive, toggle):
        with QSignalBlocker(self.scene()):
            if not additive:
                self.scene().clearSelection()
            for item in items:
                item.setSelected(not item.isSelected() if additive and toggle else True)
        self._selected()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_position = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.tool == 'select':
            self._selection_origin = event.position().toPoint()
            event.accept()
            return
        if event.button()==Qt.MouseButton.LeftButton and self.tool in ('node','bar','split'):
            hit=self._items_at(event.position().toPoint())
            if self.tool=='node':
                point=self._snap(self.mapToScene(event.position().toPoint()))
                self.add_node.emit(point.x(), -point.y())
            elif self.tool=='bar':
                nd=next((i for i in hit if isinstance(i,NodeItem)),None)
                if nd:
                    if self._pending_first is None:
                        self._pending_first=nd.node_id
                        self.status_text.emit(f'Primeiro nó {nd.node_id}; selecione o segundo')
                    else:
                        a=self._pending_first;self._pending_first=None
                        self.add_member.emit(a,nd.node_id)
            else:
                member = self._nearby_member(event.position().toPoint())
                if member is not None:
                    self.split_member.emit(member.member_id, .5)
            event.accept();return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and self._pan_position is not None:
            self._pan_position = None
            self.viewport().unsetCursor()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._selection_origin is not None:
            point = event.position().toPoint()
            origin = self._selection_origin
            crossing = self._crossing(point)
            self._selection_origin = None
            self._marquee.hide()
            additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if (point - origin).manhattanLength() >= QApplication.startDragDistance():
                hits = self._rectangle_hits(QRect(origin, point).normalized(), crossing)
                self._select_hits(hits, additive, False)
            else:
                item, label = self._click_hit(point)
                self._select_hits([item] if item is not None else (), additive, True)
                if label is not None:
                    label.popup(event.globalPosition().toPoint(), self.viewport())
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.tool == 'move' and self._model and event.button() == Qt.MouseButton.LeftButton:
            changed={}
            originals={n.id:n for n in self._model.nodes}
            for nid,item in self._nodes.items():
                old=originals[nid];p=item.pos()
                if abs(p.x()-old.x)+abs(-p.y()-old.y)>1e-5:
                    pos=self._snap(p)
                    changed[nid]=(pos.x(),-pos.y())
            if changed:self.moved.emit(changed)

    def resizeEvent(self,e):
        super().resizeEvent(e)
        if not self._fit_pending:self.fit()
        elif hasattr(self, '_force_items'):
            self._place_labels()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        if (getattr(self, '_force_items', None) or getattr(self, '_identifiers', None)
                or getattr(self, '_axial_labels', None) or getattr(self, '_reaction_items', None)
                or getattr(self, '_deformed_nodes', None)):
            self._place_labels()

    def selected_ids(self):
        selected = []
        for item in self.scene().selectedItems():
            if isinstance(item, NodeItem):
                selected.append(('node', item.node_id))
            elif isinstance(item, MemberItem):
                selected.append(('member', item.member_id))
            elif isinstance(item, ForceVectorItem) and not item.reaction:
                selected.append(('load', item.node_id))
        return selected
