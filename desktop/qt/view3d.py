"""Inspeção geométrica 3D com contornos extrudados.

As peças são EXTRUSÕES dos perfis ideais sobre eixos do modelo 2D.
Sem rotações de ligação, chapas gusset, raios de dobra ou solver espacial.
Renderizador Qt painter: faces opacas em ordem de profundidade (sem z-buffer),
adequado à inspeção de treliças simples e para GPUs corporativas restritas.
"""
from __future__ import annotations
from copy import deepcopy
from math import fsum
from pathlib import Path
from html import escape

from PySide6.QtCore import Qt,QPointF,QRectF,QSignalBlocker,QTimer
from PySide6.QtGui import QColor,QBrush,QPen,QPolygonF,QPainter,QFont
from PySide6.QtWidgets import (
    QVBoxLayout,QHBoxLayout,QLabel,QGraphicsScene,QGraphicsView,
    QGraphicsPolygonItem,QGraphicsEllipseItem,QGraphicsItem,QComboBox,
    QPushButton,QColorDialog,QSlider,QCheckBox,QFormLayout,QWidget,
    QTabWidget,QDoubleSpinBox,QGroupBox,QMessageBox,QFileDialog,
)
from desktop.preview3d import Camera, camera_projection, color_key,palette_keys
from desktop.section_mesh import load_shape_catalog,make_model_meshes,make_section_layout,export_obj,display_scaled_vertices
from desktop.bridge import CATALOG
from poe_truss.model import GROUPS
from .action_icons import action_icon
from .profile_picker import ProfilePicker

DEFAULT={
    'superior':'#1379A5','inferior':'#1E577E','diagonal':'#C3813C',
    'montante':'#6E8B9A','Tração':'#C54850',
    'Compressão':'#2666B8','Nulo / não calculado':'#96A7B6',
}
CYCLE=['#1379A5','#D38440','#4E9182','#9A65A8','#D25962','#748AA9']


class MeshLayer(QGraphicsItem):
    """Desenha as faces ordenadas sem indexar um item de cena por face."""

    def __init__(self):
        super().__init__()
        self._bounds = QRectF()
        self.faces = []
        self.setZValue(-1)

    def boundingRect(self):
        return self._bounds

    def set_faces(self, faces):
        bounds = QRectF()
        for polygon, *_ in faces:
            bounds |= polygon.boundingRect()
        self.prepareGeometryChange()
        self._bounds = bounds
        self.faces = faces
        self.update()

    def paint(self, painter, option, widget=None):
        for polygon, pen, brush, _ in self.faces:
            painter.setPen(pen)
            painter.setBrush(brush)
            painter.drawPolygon(polygon)

    def member_at(self, point):
        for polygon, _, _, member in reversed(self.faces):
            if polygon.containsPoint(point, Qt.FillRule.OddEvenFill):
                return member
        return None


class OrbitView(QGraphicsView):
    """Arraste esquerdo rotaciona, clique direito inspeciona; roda aplica zoom."""
    def __init__(self, dialog):
        super().__init__();self.dialog=dialog
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(QBrush(QColor('#F2F6FA')))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._previous=None
        self._drag_button = None
        self.setStyleSheet('border:1px solid #D6E1EC;border-radius:3px;')
    def wheelEvent(self,e):
        f=1.12 if e.angleDelta().y()>0 else 1/1.12
        self.scale(f,f);e.accept()
    def mousePressEvent(self,e):
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._drag_button = e.button()
            self._previous=e.position();self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept();return
        if e.button()==Qt.MouseButton.RightButton:
            point = e.position().toPoint()
            item = self.itemAt(point)
            mid = (item.data(0) if item is not None else None)
            mid = mid or self.dialog.mesh_layer.member_at(self.mapToScene(point))
            if mid:
                self.dialog.select_member(mid)
                e.accept()
                return
        super().mousePressEvent(e)
    def mouseMoveEvent(self,e):
        if self._previous is not None:
            current=e.position();dx=current.x()-self._previous.x();dy=current.y()-self._previous.y()
            self._previous=current
            if self._drag_button == Qt.MouseButton.MiddleButton:
                horizontal, vertical = self.horizontalScrollBar(), self.verticalScrollBar()
                horizontal.setValue(horizontal.value() - round(dx))
                vertical.setValue(vertical.value() - round(dy))
            else:
                self.dialog.orbit(dx, dy)
            e.accept();return
        super().mouseMoveEvent(e)
    def mouseReleaseEvent(self,e):
        if self._drag_button == e.button():
            self._previous = self._drag_button = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(e)


class Truss3DView(QWidget):
    """Vista de seções extrudadas do modelo plano atual."""
    def __init__(self,session,case_id=None,parent=None):
        super().__init__(parent)
        self.session=session;self.case_id=case_id;self.colors=dict(DEFAULT)
        self._app = parent
        self.shape_catalog=load_shape_catalog(CATALOG)
        self._meshes=[];self._warnings=[];self._member_meta={};self._mesh_revision=None
        self._loading=False;self._selected_member=None
        self._scaled_meshes = []
        self._cached_scale = None
        self._angles = (30., 25.)
        self._orbit_update=QTimer(self);self._orbit_update.setSingleShot(True)
        self._orbit_update.setInterval(16);self._orbit_update.timeout.connect(self.redraw)
        root=QVBoxLayout(self);root.setSpacing(4)
        root.setContentsMargins(4, 4, 4, 4)
        heading=QHBoxLayout()
        self.preset=QComboBox();self.preset.addItems(['Isométrica','Frontal XY','Perfil lateral','Superior'])
        self.preset.currentTextChanged.connect(self.set_preset)
        heading.addWidget(QLabel('Vista'));heading.addWidget(self.preset)
        exporter=QPushButton(action_icon('export'), 'Exportar OBJ');exporter.clicked.connect(self.save_obj)
        exporter.setToolTip('Exporta os perfis extrudados em mm para auditoria geométrica externa')
        heading.addWidget(exporter)
        heading.addStretch()
        controls_button = QPushButton(action_icon('panel'), 'Painel 3D')
        controls_button.clicked.connect(lambda: self._app._show_inspector(self.controls))
        heading.addWidget(controls_button)
        root.addLayout(heading)

        self.view = OrbitView(self)
        self.mesh_layer = MeshLayer()
        self.view.scene().addItem(self.mesh_layer)
        self._overlays = []
        root.addWidget(self.view, 1)
        self.controls = QWidget()
        pcol = QVBoxLayout(self.controls)
        pcol.setContentsMargins(4, 0, 2, 0)
        self.pages=QTabWidget();pcol.addWidget(self.pages,1)

        # Página de visualização.
        colors_page=QWidget();f=QFormLayout(colors_page)
        self.mode=QComboBox()
        for label,id in [('Grupo estrutural','group'),('Família de perfil','family'),('Esforço normal','force')]:
            self.mode.addItem(label,id)
        self.mode.currentIndexChanged.connect(self.reset_keys)
        f.addRow('Cores por',self.mode)
        self.category=QComboBox();f.addRow('Categoria',self.category)
        change_color=QPushButton(action_icon('color'), 'Escolher cor');change_color.clicked.connect(self.choose_color)
        f.addRow(change_color)
        self.show_nodes=QCheckBox('Mostrar nós');self.show_nodes.setChecked(False)
        self.show_nodes.toggled.connect(self.redraw);f.addRow(self.show_nodes)
        self.show_edges=QCheckBox('Contornos das faces');self.show_edges.setChecked(True)
        self.show_edges.toggled.connect(self.redraw);f.addRow(self.show_edges)
        self.surface_style=QComboBox();self.surface_style.addItems(['Sólido','Aramado'])
        self.surface_style.currentTextChanged.connect(self.redraw)
        f.addRow('Modo de desenho',self.surface_style)
        self.section_scale=QSlider(Qt.Orientation.Horizontal)
        self.section_scale.setRange(1,8);self.section_scale.setValue(3)
        self.section_scale.valueChanged.connect(self.schedule_redraw)
        f.addRow('Seção 1×–8× (só visual)',self.section_scale)
        self.show_axes=QCheckBox('Eixos analíticos');self.show_axes.setChecked(False)
        self.show_axes.toggled.connect(self.redraw);f.addRow(self.show_axes)
        self.yaw=QSlider(Qt.Orientation.Horizontal);self.yaw.setRange(0,360);self.yaw.setValue(30)
        self.elevation=QSlider(Qt.Orientation.Horizontal);self.elevation.setRange(-85,85);self.elevation.setValue(25)
        f.addRow('Giro',self.yaw);f.addRow('Elevação',self.elevation)
        for slider in (self.yaw,self.elevation):slider.valueChanged.connect(self._read_angles)
        self.legend=QLabel();self.legend.setWordWrap(True)
        f.addRow('Legenda',self.legend)
        self.pages.addTab(colors_page,'Exibição')

        # Página das SEÇÕES: integra a configuração no JSON, não no solver 3D.
        geom_page=QWidget();g=QFormLayout(geom_page)
        self.arrangement_form = g
        g.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.group=QComboBox();self.group.addItems(GROUPS)
        self.group.currentTextChanged.connect(self.load_group)
        g.addRow('Grupo',self.group)
        self.profile_picker = ProfilePicker()
        self.profile_picker.changed.connect(self._assign_profile)
        g.addRow(self.profile_picker)
        self.layout_type=QComboBox()
        for label,code in [('Costas a costas','back_to_back'),('Frente a frente','face_to_face'),
                           ('Mesma orientação','side_by_side')]:self.layout_type.addItem(label,code)
        g.addRow('Arranjo',self.layout_type)
        self.dx=QDoubleSpinBox();self.dx.setRange(-2000,2000);self.dx.setDecimals(2);self.dx.setSuffix(' mm')
        self.dy=QDoubleSpinBox();self.dy.setRange(-2000,2000);self.dy.setDecimals(2);self.dy.setSuffix(' mm')
        self.rotation = QDoubleSpinBox()
        self.rotation.setRange(-360, 360)
        self.rotation.setSuffix(' °')
        g.addRow('Δ centroide fora do plano',self.dx)
        g.addRow('Δ centroide no plano',self.dy)
        g.addRow('Rotação da seção',self.rotation)
        g.addRow(QLabel('Contorno da seção (mm)'))
        self.section_preview=QGraphicsView();self.section_preview.setScene(QGraphicsScene(self.section_preview))
        self.section_preview.setFixedHeight(132)
        self.section_preview.setBackgroundBrush(QBrush(QColor('#F3F7FA')))
        g.addRow(self.section_preview)
        for widget in (self.dx, self.dy, self.rotation):
            widget.setKeyboardTracking(False)
            widget.valueChanged.connect(self.apply_layout)
        self.layout_type.currentIndexChanged.connect(self.apply_layout)
        help_label=QLabel('Nas seções duplas, informe a distância entre centroides. '
                          'Distâncias nulas recebem uma folga visual.')
        help_label.setWordWrap(True);g.addRow(help_label)
        self.pages.addTab(geom_page,'Arranjo')
        self.pages.setCurrentWidget(geom_page)

        info=QGroupBox('ELEMENTO INSPECIONADO');info_box=QVBoxLayout(info)
        self.selected_label=QLabel('Clique direito sobre uma barra para inspecionar.')
        self.selected_label.setWordWrap(True);info_box.addWidget(self.selected_label)
        pcol.addWidget(info)
        self.issue=QLabel('');self.issue.setWordWrap(True);self.issue.setStyleSheet('color:#995F24;font-size:9pt;')
        pcol.addWidget(self.issue)
        self.disclaimer=QLabel('Contornos sem raios ou ligações. O OBJ mantém escala 1×. A análise estrutural é plana.')
        self.disclaimer.setWordWrap(True);self.disclaimer.setStyleSheet('color:#586D7F;font-size:9pt;')
        root.addWidget(self.disclaimer)
        self.load_group()
        self.reset_keys()
        QTimer.singleShot(0,self.fit)

    def axial(self):
        return ((self.session.result or {}).get('analyses',{}).get(self.case_id,{}).get('axial_n',{}))

    def load_group(self,*_):
        if not hasattr(self,'profile_picker'):return
        group=self.group.currentText()
        spec=self.session.project.get('sections',{}).get(group,{})
        cfg=self.session.project.get('section_arrangements',{}).get(group,{})
        self._loading=True
        try:
            self.profile_picker.set_section(self.session.catalog, spec)
            index=self.layout_type.findData(cfg.get('assembly_type','back_to_back'))
            self.layout_type.setCurrentIndex(index if index>=0 else 0)
            self.dx.setValue(float(cfg.get('centroid_dx_mm',0)))
            self.dy.setValue(float(cfg.get('centroid_dy_mm',0)))
            self.rotation.setValue(float(cfg.get('rotation_deg', 0)))
            for widget in (self.layout_type, self.dx, self.dy):
                self.arrangement_form.setRowVisible(widget, self.profile_picker.count.value() == 2)
        finally:self._loading=False
        self.update_section_preview()

    def _assign_profile(self, profile, count):
        self._app.assign_section(self.group.currentText(), profile, count)

    def update_section_preview(self,*_):
        if self._loading or not hasattr(self,'section_preview'):return
        group=self.group.currentText()
        spec=self.session.project.get('sections',{}).get(group,{})
        shape=self.shape_catalog.get(spec.get('profile'))
        scene=self.section_preview.scene();scene.clear()
        if shape is None:return
        cfg={'centroid_dx_mm':self.dx.value(),'centroid_dy_mm':self.dy.value(),
             'rotation_deg':self.rotation.value(),
             'assembly_type':self.layout_type.currentData()}
        try:polygons,_=make_section_layout(shape,self.profile_picker.count.value(),cfg)
        except (ValueError,TypeError):return
        for polygon in polygons:
            outline=QPolygonF([QPointF(u,-v) for u,v in polygon])
            item=QGraphicsPolygonItem(outline)
            item.setPen(QPen(QColor('#0F5E88'),1.3))
            item.setBrush(QBrush(QColor('#64A1C5')))
            scene.addItem(item)
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-12,-12,12,12))
        self.section_preview.fitInView(scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

    def schedule_redraw(self,*_):
        if not self._orbit_update.isActive():
            self._orbit_update.start()

    def _read_angles(self, *_):
        self._angles = (float(self.yaw.value()), float(self.elevation.value()))
        self.schedule_redraw()

    def orbit(self, dx, dy):
        yaw, elevation = self._angles
        yaw = (yaw + dx * 0.55) % 360
        elevation = max(-85, min(85, elevation - dy * 0.5))
        self._set_angles(yaw, elevation)
        self.schedule_redraw()

    def _set_angles(self, yaw, elevation):
        self._angles = (yaw, elevation)
        with QSignalBlocker(self.yaw), QSignalBlocker(self.elevation):
            self.yaw.setValue(round(yaw))
            self.elevation.setValue(round(elevation))

    def apply_layout(self, *_):
        if self._loading:
            return
        group=self.group.currentText()
        project=deepcopy(self.session.project)
        sections=project.setdefault('sections',{})
        if group not in sections:
            QMessageBox.warning(self,'Perfil','Não há seção atribuída para este grupo.');return
        cfg=project.setdefault('section_arrangements',{})
        cfg.setdefault(group, {}).update({
            'centroid_dx_mm':self.dx.value(), 'centroid_dy_mm':self.dy.value(),
            'rotation_deg':self.rotation.value(),
            'assembly_type':self.layout_type.currentData(),
        })
        if project == self.session.project:
            return
        project.pop('external_resistances', None)
        try:
            self._app._apply(project,f'Arranjo do {group} atualizado')
        except Exception as exc:
            QMessageBox.warning(self,'Arranjo não aplicado',str(exc));return

    def set_preset(self,label):
        angles={'Isométrica':(30,25),'Frontal XY':(0,0),
                'Perfil lateral':(90,0),'Superior':(0,80)}
        if label not in angles:return
        self._set_angles(*angles[label])
        self.redraw();self.fit()

    def refresh_model(self, session, case_id, *, fit=False):
        changed_project = session is not self.session
        if changed_project:
            self.session = session
            self._mesh_revision = None
            self._selected_member = None
        self.case_id = case_id
        if self._mesh_revision != self.session.revision:
            self.load_group()
        self.reset_keys()
        self.inspect_member(self._selected_member)
        if changed_project or fit:
            self.fit()

    def reset_keys(self,*_):
        mode=self.mode.currentData()
        keys=palette_keys(self.session.model,self.session.catalog,mode,self.axial())
        previous = self.category.currentText()
        self.category.clear();self.category.addItems(keys)
        if previous in keys:
            self.category.setCurrentText(previous)
        for i,k in enumerate(keys):self.colors.setdefault(k,CYCLE[i%len(CYCLE)])
        self.redraw()

    def choose_color(self):
        key=self.category.currentText()
        if not key:return
        color=QColorDialog.getColor(QColor(self.colors.get(key,'#748AA9')),self,f'Cor: {key}')
        if color.isValid():self.colors[key]=color.name();self.redraw()

    def _ensure_meshes(self):
        if self._mesh_revision==self.session.revision:return
        self._meshes,self._warnings,self._member_meta=make_model_meshes(
            self.session.model,self.session.project,self.shape_catalog,self.session.catalog)
        self._mesh_revision=self.session.revision
        self._cached_scale = None
        self._members = {member.id: member for member in self.session.model.members}
        self._nodes = self.session.model.node_map()

    def _ensure_scaled_meshes(self):
        self._ensure_meshes()
        scale = self.section_scale.value()
        if self._cached_scale == scale:
            return
        self._scaled_meshes = []
        for mesh in self._meshes:
            member = self._members[mesh.member_id]
            a, b = self._nodes[member.i], self._nodes[member.j]
            vertices = display_scaled_vertices(mesh, (a.x, a.y), (b.x, b.y), scale)
            self._scaled_meshes.append((mesh, member, vertices))
        self._cached_scale = scale

    def select_member(self, mid):
        self.inspect_member(mid)
        if self._selected_member:
            member = self._members[mid]
            self.group.setCurrentText(member.group)
            self.redraw()

    def inspect_member(self,mid):
        self._selected_member=mid
        m = self._members.get(mid)
        if not m:
            self._selected_member = None
            self.selected_label.setText('Clique direito sobre uma barra para inspecionar.')
            return
        meta=self._member_meta.get(mid,{})
        n=self.axial().get(mid)
        lines=[f'<b>{escape(mid)}</b> · {escape(m.group)}',escape(m.profile),
               f'L = {self.session.model.member_length(m):.2f} mm',
               f'Componentes: {meta.get("components","?")}']
        if n is not None:lines.append(f'N = {n/1000:+.2f} kN')
        lines.extend(escape(str(v)) for v in meta.get('notes',[]))
        self.selected_label.setText('<br>'.join(lines))

    def redraw(self,*_):
        if not hasattr(self,'view'):return
        self._ensure_scaled_meshes()
        scene = self.view.scene()
        for item in self._overlays:
            scene.removeItem(item)
        self._overlays.clear()
        mode=self.mode.currentData();forces=self.axial()
        project = camera_projection(Camera(*self._angles))
        all_faces=[];colors={}
        for mesh, member, drawn in self._scaled_meshes:
            key=color_key(member,self.session.catalog,mode,forces)
            base=self.colors.get(key,'#8395A3');colors[key]=base
            projected=[project(v) for v in drawn]
            for index,face in enumerate(mesh.faces):
                pts=[projected[i] for i in face]
                z=fsum(p[2] for p in pts)/len(pts)
                all_faces.append((z,index,mesh,base,pts))
        # Aproximação por painter's algorithm. A interpolação em cruzamentos não
        # dispõe de z-buffer; não utilizar para interferência ou fabricação.
        faces = []
        styles = {}
        solid = self.surface_style.currentText() == 'Sólido'
        edges = self.show_edges.isChecked()
        for _,i,mesh,base,pts in sorted(all_faces,key=lambda x:x[0]):
            poly=QPolygonF([QPointF(p[0],p[1]) for p in pts])
            tint = 127 if i in (0, 1) else 87 if i % 3 == 0 else 100
            selected = self._selected_member == mesh.member_id
            style = (base, tint, selected)
            if style not in styles:
                color = QColor(base).darker(tint)
                if selected:
                    color = color.lighter(130)
                pen = QPen(QColor('#244258') if edges else color, 0.65 if edges else 0)
                brush = QBrush(color) if solid else QBrush(Qt.BrushStyle.NoBrush)
                styles[style] = pen, brush
            faces.append((poly, *styles[style], mesh.member_id))
        self.mesh_layer.set_faces(faces)
        if self.show_axes.isChecked():
            nd = self._nodes
            for m in self.session.model.members:
                a,b=nd[m.i],nd[m.j]
                p,q=project((a.x,a.y,0)),project((b.x,b.y,0))
                line=scene.addLine(p[0],p[1],q[0],q[1],QPen(QColor('#788E9F'),0.7,Qt.PenStyle.DashLine))
                line.setData(0,m.id)
                self._overlays.append(line)
        if self.show_nodes.isChecked():
            for n in self.session.model.nodes:
                x,y,_=project((n.x,n.y,0))
                node=QGraphicsEllipseItem(-3,-3,6,6);node.setPos(x,y)
                node.setPen(QPen(QColor('#1D4259'),1))
                node.setBrush(QBrush(QColor('#FFFFFF')))
                node.setToolTip(f'Nó {n.id} | X={n.x:.2f} Y={n.y:.2f} mm')
                node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,True)
                node.setZValue(9);scene.addItem(node)
                self._overlays.append(node)
        self.legend.setText('  ·  '.join(colors) if colors else 'Nenhuma seção gerada')
        shown=self._warnings[:5]
        if len(self._warnings)>5:shown.append(f'+ {len(self._warnings)-5} avisos semelhantes')
        self.issue.setText('\n'.join(shown) if shown else 'Contornos ideais gerados; conferir catálogo e condições de ligação.')
        if faces or self._overlays:
            scene.setSceneRect(scene.itemsBoundingRect().adjusted(-140,-140,140,140))

    def save_obj(self):
        self._ensure_meshes()
        if not self._meshes:
            QMessageBox.warning(self,'Exportação OBJ','Não há malhas renderizáveis.');return
        path,_=QFileDialog.getSaveFileName(self,'Exportar perfis extrudados','trelica_secoes.obj',
                                            'Wavefront OBJ (*.obj)')
        if not path:return
        try:export_obj(self._meshes,path)
        except Exception as exc:QMessageBox.warning(self,'Exportação',str(exc));return
        QMessageBox.information(self,'OBJ gerado',
            'Malha exportada em milímetros. Seções idealizadas, sem raios ou ligações. '
            'Não é documentação de fabricação.')

    def fit(self):
        scene=self.view.scene()
        if self.mesh_layer.faces or self._overlays:
            self.view.fitInView(scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
