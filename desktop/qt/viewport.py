"""Editor CAD 2D: coordenadas de engenharia mm, Y positivo para cima.

Qt somente representa/despacha comandos de edição. Todas as mutações passam
por desktop.editing + Session.update_project e são validadas pelo núcleo.
"""
from __future__ import annotations
from math import atan2,ceil,degrees,floor,hypot,isfinite,log10
from PySide6.QtCore import Qt,QLineF,QPointF,QSignalBlocker,Signal,QRectF
from PySide6.QtGui import QColor,QPen,QBrush,QFont,QPainter,QPainterPath,QRegion,QTransform
from PySide6.QtWidgets import (QGraphicsView,QGraphicsScene,QGraphicsEllipseItem,
                               QGraphicsLineItem,QGraphicsPathItem,QGraphicsSimpleTextItem,QGraphicsItem)

NAVY='#1C354D'; BLUE='#1676AF'; TENS='#C53646'; COMP='#2666B8'; GHOST='#9CAAB5'


class NodeItem(QGraphicsEllipseItem):
    def __init__(self,node_id,x,y,*,draft=False):
        super().__init__(-6,-6,12,12)
        self.node_id=node_id;self.draft=draft
        self.setPos(x,-y)
        self.setZValue(30)
        self.setPen(QPen(QColor('#1779A7' if not draft else '#DE8A20'),1.7))
        self.setBrush(QBrush(QColor('white' if not draft else '#FFF1CA')))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,True)
        self.setToolTip(f'Nó {node_id} | X={x:.2f} mm, Y={y:.2f} mm' + (' | rascunho' if draft else ''))

    def paint(self, painter, option, widget=None):
        if not self.isSelected():
            super().paint(painter, option, widget)
            return
        painter.save()
        painter.setPen(self.pen())
        painter.setBrush(QColor('#BCE1F3'))
        painter.drawEllipse(self.rect())
        painter.restore()


class MemberItem(QGraphicsLineItem):
    def __init__(self,m,coords,force=None):
        a,b=coords[m.i],coords[m.j]
        super().__init__(a.x(),a.y(),b.x(),b.y())
        self.member_id=m.id
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True)
        self.setZValue(10)
        color=TENS if force is not None and force>1e-7 else COMP if force is not None and force< -1e-7 else BLUE if m.group in ('superior','inferior') else '#718899'
        pen=QPen(QColor(color),2);pen.setCosmetic(True)
        self.setPen(pen)  # largura cosmética em qualquer zoom
        self.setToolTip(f'{m.id} | {m.group} | {m.profile}' + (f' | N={force/1000:+.2f} kN' if force is not None else ''))

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


class ForceVectorItem(QGraphicsPathItem):
    """Seta proporcional posicionada acima do nó em pixels de tela."""

    def __init__(self, node, position, fx, fy, maximum):
        magnitude = hypot(fx, fy)
        direction = QPointF(fx / magnitude, -fy / magnitude)
        normal = QPointF(-direction.y(), direction.x())
        length = 50 * magnitude / maximum
        tail = QPointF()
        head = direction * length
        wing = min(7, length * .5)
        base = head - direction * wing
        path = QPainterPath(tail)
        path.lineTo(head)
        path.moveTo(base - normal * wing * .55)
        path.lineTo(head)
        path.lineTo(base + normal * wing * .55)
        bounds = path.boundingRect()
        offset = QPointF(-bounds.center().x(), -13 - bounds.bottom())
        path.translate(offset)
        super().__init__(path)
        self.setPos(position)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(25)
        pen = QPen(QColor('#B66217'), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        self.setToolTip(f'{node} · Fx {fx/1000:+.3f} kN · Fy {fy/1000:+.3f} kN')
        anchor = offset + head * .5
        guide = QGraphicsLineItem(0, -7, anchor.x(), anchor.y(), self)
        guide.setPen(QPen(QColor('#AC8A69'), 1, Qt.PenStyle.DotLine))
        guide.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent)
        guide.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.label = QGraphicsSimpleTextItem(f'{magnitude/1000:.2f} kN', self)
        self.label.setFont(QFont('Segoe UI', 9))
        self.label.setBrush(QBrush(QColor('#895019')))
        self.label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)


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
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setBackgroundBrush(QBrush(QColor('#F5F8FB')))
        self.setStyleSheet('border:0;')
        self.tool='select';self.grid_mm=50.;self.snap_enabled=True
        self.grid_visible = True
        self._analysis_id = None
        self.show_ids=False;self.show_efforts=False;self.show_forces=False
        self.show_load_values = False
        self._force_items = []
        self._annotations = []
        self.show_deformed=False;self.show_all_labels=False
        self._members={};self._nodes={};self._drafts={};self._pos={}
        self._analysis=None;self._model=None;self._session=None
        self._pending_first=None;self._drag_start={};self._fit_pending=False
        self._vertical=1.
        self.setRubberBandSelectionMode(Qt.ItemSelectionMode.IntersectsItemShape)
        self.setMouseTracking(True)

    def set_tool(self,tool:str):
        if tool not in ('select','pan','move','node','bar','split'):
            raise ValueError('Ferramenta desconhecida')
        self.tool=tool;self._pending_first=None
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if tool=='pan' else QGraphicsView.DragMode.RubberBandDrag)
        self.setCursor(Qt.CursorShape.OpenHandCursor if tool=='pan' else Qt.CursorShape.CrossCursor if tool in ('node','bar','split') else Qt.CursorShape.ArrowCursor)
        for item in self._nodes.values():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,tool=='move')
        self.status_text.emit({'select':'Selecionar por clique ou retângulo (Ctrl para múltiplos)',
           'pan':'Arrastar para deslocar vista','move':'Arrastar nós (snap configurável)',
           'node':'Clique na vista para criar um nó provisório',
           'bar':'Clique em dois nós para criar uma barra',
           'split':'Clique em uma barra para subdividir'}[tool])

    def _selected(self):
        data=[]
        for item in self.scene().selectedItems():
            if isinstance(item,NodeItem):data.append(('node',item.node_id))
            elif isinstance(item,MemberItem):data.append(('member',item.member_id))
        self.selected.emit(data)

    def selection_item(self, kind, identifier):
        if kind == 'node':
            return self._nodes.get(identifier) or self._drafts.get(identifier)
        return self._members.get(identifier)

    def set_grid_visible(self, visible):
        self.grid_visible = visible
        self.viewport().update()

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        if not self.grid_visible:
            return
        transform = painter.worldTransform()
        target = 32 / max(transform.m11(), 1e-12)
        magnitude = 10 ** floor(log10(target))
        step = next(factor * magnitude for factor in (1, 2, 5, 10)
                    if factor * magnitude >= target)
        y_step = step * self._vertical
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for multiple, color in [(1, '#E5EBF1'), (5, '#D7E1EB')]:
            pen = QPen(QColor(color))
            pen.setCosmetic(True)
            painter.setPen(pen)
            dx, dy = step * multiple, y_step * multiple
            lines = [QLineF(i * dx, rect.top(), i * dx, rect.bottom())
                     for i in range(ceil(rect.left() / dx), floor(rect.right() / dx) + 1)]
            lines.extend(QLineF(rect.left(), i * dy, rect.right(), i * dy)
                         for i in range(ceil(rect.top() / dy), floor(rect.bottom() / dy) + 1))
            painter.drawLines(lines)
        painter.restore()

    def mouseMoveEvent(self, event):
        point = self.mapToScene(event.position().toPoint())
        self.coordinates_changed.emit(point.x(), -point.y() / self._vertical)
        super().mouseMoveEvent(event)

    def _add_text(self,text,pos,color=NAVY,rotation=0,bold=False):
        item=QGraphicsSimpleTextItem(str(text))
        f=QFont('Segoe UI',9)
        f.setBold(bold)
        item.setFont(f);item.setBrush(QBrush(QColor(color)))
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,True)
        item.setRotation(rotation);item.setPos(pos)
        item.setZValue(50)
        self.scene().addItem(item)
        self._annotations.append(item)

    def render(self,session,analysis_id=None,*,fit=False):
        """Renderização sem recalcular ou modificar a estrutura."""
        selection = self.selected_ids() if session is self._session else []
        self._session=session;model=session.model;self._model=model
        self._analysis_id = analysis_id
        self._analysis=(session.result or {}).get('analyses',{}).get(analysis_id) if analysis_id else None
        self._force_items.clear()
        self._annotations.clear()
        scene=self.scene();scene.blockSignals(True);scene.clear()
        self._members={};self._nodes={};self._drafts={}
        self._pos={n.id:QPointF(n.x,-n.y*self._vertical) for n in model.nodes}
        force=(self._analysis or {}).get('axial_n',{})
        for m in model.members:
            item=MemberItem(m,self._pos,force.get(m.id) if self.show_efforts else None)
            scene.addItem(item);self._members[m.id]=item
        # Os esforços de maior magnitude são anotados primeiro.
        if self.show_efforts and self._analysis:
            ranked=sorted(model.members,key=lambda m:abs(force.get(m.id,0)),reverse=True)
            for m in ranked if self.show_all_labels else ranked[:min(24,len(ranked))]:
                axial=force.get(m.id,0)
                if abs(axial)<.0001:continue
                a,b=self._pos[m.i],self._pos[m.j]
                dx=b.x()-a.x();dy=b.y()-a.y()
                ang=degrees(atan2(dy,dx))
                if ang>90:ang-=180
                if ang< -90:ang+=180
                length=hypot(dx,dy)
                if length<1:continue
                mid=QPointF((a.x()+b.x())/2,(a.y()+b.y())/2)
                shift=QPointF(-dy/length*80,dx/length*80)
                self._add_text(f'{axial/1000:+.2f}',mid+shift,TENS if axial>0 else COMP,ang,True)
        for n in model.nodes:
            item=NodeItem(n.id,n.x,n.y*self._vertical)
            scene.addItem(item);self._nodes[n.id]=item
            if self.show_ids:
                self._add_text(n.id,self._pos[n.id]+QPointF(22,-85),'#526A7D')
        for node in session.project.get('cad_drafts',[]):
            item=NodeItem(node['id'],node['x_mm'],node['y_mm']*self._vertical,draft=True)
            scene.addItem(item);self._drafts[node['id']]=item
        for nid,(ux,uy) in model.supports.items():
            p=self._pos[nid]
            sign=('XY' if ux and uy else 'Y' if uy else 'X' if ux else '')
            if sign:self._add_text('△ '+sign,p+QPointF(-80,70),'#62788A',bold=True)
        self._render_forces(analysis_id)
        if self.show_deformed and self._analysis:
            u=self._analysis['nodal_displacements']
            maxu=max((hypot(v['ux_mm'],v['uy_mm']) for v in u.values()),default=0.)
            amp=min(1000.,200/max(maxu,.001))
            deformed={n.id:QPointF(n.x+amp*u[n.id]['ux_mm'],-(n.y+amp*u[n.id]['uy_mm'])*self._vertical) for n in model.nodes}
            for m in model.members:
                a,b=deformed[m.i],deformed[m.j]
                line=QGraphicsLineItem(a.x(),a.y(),b.x(),b.y())
                pen=QPen(QColor('#16A38C'),1.5,Qt.PenStyle.DashLine);line.setPen(pen);line.setZValue(4);scene.addItem(line)
            self._add_text(f'Deformada amplificada ×{amp:.1f}',QPointF(min(n.x for n in model.nodes),-max(n.y for n in model.nodes)*self._vertical-400),'#087C69')
        scene.blockSignals(False)
        with QSignalBlocker(scene):
            for kind, identifier in selection:
                item = self.selection_item(kind, identifier)
                if item is not None:
                    item.setSelected(True)
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-400,-400,400,400))
        self._selected()
        if fit or not self._fit_pending:self.fit()
        else:self._place_force_labels()

    def _render_forces(self, case_id):
        if not self.show_forces or not case_id:
            self.forces_displayed.emit({}, '')
            return
        try:
            forces = self._session.forces_for_case(case_id)
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
                arrow = ForceVectorItem(node, self._pos[node], fx, fy, maximum)
                arrow.label.hide()
                self.scene().addItem(arrow)
                self._force_items.append(arrow)
                item = self._nodes[node]
                item.setToolTip(f'{item.toolTip()}\n{arrow.toolTip()}')
        self.forces_displayed.emit(forces, '')

    def set_load_values(self, visible):
        self.show_load_values = visible
        self._place_force_labels()

    def _place_force_labels(self):
        if not self.show_load_values:
            for arrow in self._force_items:
                arrow.label.hide()
            return
        if not self._force_items:
            return

        viewport = self.viewport().rect()
        transform = self.viewportTransform()
        occupied = QRegion()
        for item in self.items(viewport):
            if (isinstance(item, (NodeItem, ForceVectorItem))
                    or isinstance(item, QGraphicsSimpleTextItem) and item.parentItem() is None):
                rect = item.deviceTransform(transform).mapRect(item.boundingRect())
                occupied += QRegion(rect.toAlignedRect())

        for arrow in self._force_items:
            label = arrow.label
            label.hide()
            device = arrow.deviceTransform(transform)
            shaft = device.mapRect(arrow.boundingRect())
            if not viewport.intersects(shaft.toAlignedRect()):
                continue
            bounds = label.boundingRect()
            left = shaft.center().x() - bounds.width() / 2
            top = shaft.top() - bounds.height() - 4
            # Tenta uma segunda linha alinhada à seta antes de omitir o valor.
            for level in (0, 1):
                position = QPointF(left, top - level * (bounds.height() + 3))
                candidate = QRectF(position, bounds.size()).adjusted(-3, -1, 3, 1).toAlignedRect()
                if viewport.contains(candidate) and not occupied.intersects(candidate):
                    label.setPos(position - device.map(QPointF()) - bounds.topLeft())
                    label.show()
                    occupied += QRegion(candidate)
                    break

    def fit(self):
        if not self._model:return
        self._fit_pending=True
        rect = self.scene().sceneRect()
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        if self._force_items:
            mapped = self.mapFromScene(rect).boundingRect()
            width, height = self.viewport().width(), self.viewport().height()
            factor = min(1, max(1, width - 120) / max(1, mapped.width()),
                         max(1, height - 184) / max(1, mapped.height()))
            self.scale(factor, factor)
            self.centerOn(rect.center())
        self._place_force_labels()

    def wheelEvent(self,e):
        factor=1.16 if e.angleDelta().y()>0 else 1/1.16
        self.scale(factor,factor)
        self._place_force_labels()
        e.accept()

    def set_vertical_factor(self,factor):
        self._vertical=max(1.,min(5.,float(factor)))
        if self._session:self.render(self._session,self._analysis_id,fit=True)

    def _snap(self,pt):
        """Snap por extremidade/ponto médio e por grade, tolerância de 12 pixels.

        Coordenadas são da VISTA, não da estrutura; o exagero vertical da
        visualização continua separado do valor físico de Y.
        """
        x,y=pt.x(),pt.y()
        if not self.snap_enabled:return QPointF(x,y)
        from math import hypot
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

    def _items_at(self,viewport_point):
        return self.items(viewport_point)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.tool in ('node','bar','split'):
            hit=self._items_at(event.position().toPoint())
            if self.tool=='node':
                point=self._snap(self.mapToScene(event.position().toPoint()))
                self.add_node.emit(point.x(),-point.y()/self._vertical)
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
                mb=next((i for i in hit if isinstance(i,MemberItem)),None)
                if mb:
                    segment=mb.line();q=self.mapToScene(event.position().toPoint())
                    dx=segment.dx();dy=segment.dy();L2=dx*dx+dy*dy
                    if L2:
                        t=((q.x()-segment.x1())*dx+(q.y()-segment.y1())*dy)/L2
                        self.split_member.emit(mb.member_id,max(.02,min(.98,t)))
            event.accept();return
        if self.tool=='move' and event.button()==Qt.MouseButton.LeftButton:
            self._drag_start={n.node_id:QPointF(n.pos()) for n in self._nodes.values() if n.isSelected()}
        super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        if self.tool=='move' and self._model:
            changed={}
            originals={n.id:n for n in self._model.nodes}
            for nid,item in self._nodes.items():
                old=originals[nid];p=item.pos()
                if abs(p.x()-old.x)+abs(-p.y()/self._vertical-old.y)>1e-5:
                    pos=self._snap(p)
                    changed[nid]=(pos.x(),-pos.y()/self._vertical)
            if changed:self.moved.emit(changed)
            self._drag_start={}

    def resizeEvent(self,e):
        super().resizeEvent(e)
        if not self._fit_pending:self.fit()
        elif hasattr(self, '_force_items'):
            self._place_force_labels()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        if getattr(self, '_force_items', None) and self.show_load_values:
            self._place_force_labels()

    def selected_ids(self):
        return [( 'node',x.node_id) if isinstance(x,NodeItem) else ('member',x.member_id)
                for x in self.scene().selectedItems() if isinstance(x,(NodeItem,MemberItem))]
