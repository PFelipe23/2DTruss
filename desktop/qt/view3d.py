"""Janela de inspeção geométrica 3D com contornos de perfis U, UE e L.

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

from PySide6.QtCore import Qt,QPointF,QTimer
from PySide6.QtGui import QColor,QBrush,QPen,QPolygonF,QPainter,QFont
from PySide6.QtWidgets import (
    QDialog,QVBoxLayout,QHBoxLayout,QLabel,QGraphicsScene,QGraphicsView,
    QGraphicsPolygonItem,QGraphicsEllipseItem,QGraphicsItem,QComboBox,
    QPushButton,QColorDialog,QSlider,QCheckBox,QFormLayout,QWidget,
    QTabWidget,QDoubleSpinBox,QSpinBox,QGroupBox,QFrame,QMessageBox,
    QScrollArea,QAbstractItemView,QSplitter,QFileDialog,
)
from desktop.preview3d import Camera, project, color_key,palette_keys
from desktop.section_mesh import load_shape_catalog,make_model_meshes,make_section_layout,section_polygon,export_obj,display_scaled_vertices
from desktop.bridge import CATALOG

DEFAULT={
    'superior':'#1379A5','inferior':'#1E577E','diagonal':'#C3813C',
    'montante':'#6E8B9A','Tração':'#C54850',
    'Compressão':'#2666B8','Nulo / não calculado':'#96A7B6',
}
CYCLE=['#1379A5','#D38440','#4E9182','#9A65A8','#D25962','#748AA9']


class OrbitView(QGraphicsView):
    """Arraste esquerdo rotaciona, clique direito inspeciona; roda aplica zoom."""
    def __init__(self, dialog):
        super().__init__();self.dialog=dialog
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(QBrush(QColor('#F2F6FA')))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._previous=None
        self.setStyleSheet('border:1px solid #D6E1EC;border-radius:3px;')
    def wheelEvent(self,e):
        f=1.12 if e.angleDelta().y()>0 else 1/1.12
        self.scale(f,f);e.accept()
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:
            self._previous=e.position();self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept();return
        if e.button()==Qt.MouseButton.RightButton:
            item=self.itemAt(e.position().toPoint())
            if item is not None:
                mid=item.data(0)
                if mid:self.dialog.inspect_member(mid);e.accept();return
        super().mousePressEvent(e)
    def mouseMoveEvent(self,e):
        if self._previous is not None:
            current=e.position();dx=current.x()-self._previous.x();dy=current.y()-self._previous.y()
            self._previous=current
            self.dialog.yaw.setValue((self.dialog.yaw.value()+round(dx*.55))%361)
            self.dialog.elevation.setValue(max(-85,min(85,self.dialog.elevation.value()-round(dy*.5))))
            e.accept();return
        super().mouseMoveEvent(e)
    def mouseReleaseEvent(self,e):
        self._previous=None;self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(e)


class Truss3DDialog(QDialog):
    """Seção extrudada em 3D, separada do solver; edição de layout é explícita."""
    def __init__(self,session,case_id=None,parent=None):
        super().__init__(parent)
        self.session=session;self.case_id=case_id;self.colors=dict(DEFAULT)
        self._app=parent if hasattr(parent,'_apply') else None
        self.shape_catalog=load_shape_catalog(CATALOG)
        self._meshes=[];self._warnings=[];self._member_meta={};self._mesh_revision=None
        self._loading=False;self._selected_member=None
        self._orbit_update=QTimer(self);self._orbit_update.setSingleShot(True)
        self._orbit_update.setInterval(35);self._orbit_update.timeout.connect(self.redraw)
        self.setWindowTitle('2DTruss | Inspeção 3D de seções — v0.1')
        self.resize(1330,830);self.setMinimumSize(980,660)
        self.setStyleSheet('QDialog{background:#F4F7FA;}QGroupBox{font-weight:600;border:1px solid #D9E3EB;'
                           'border-radius:5px;margin-top:9px;padding-top:10px;}'
                           'QPushButton{padding:6px 9px;}QLabel{color:#213C52;}')
        root=QVBoxLayout(self);root.setSpacing(8)
        heading=QHBoxLayout()
        h=QLabel('VISTA 3D  /  PERFIS EXTRUDADOS');h.setStyleSheet('font-size:13pt;font-weight:700;color:#173B54;')
        heading.addWidget(h);heading.addStretch()
        self.preset=QComboBox();self.preset.addItems(['Isométrica','Frontal XY','Perfil lateral','Superior'])
        self.preset.currentTextChanged.connect(self.set_preset)
        heading.addWidget(QLabel('Vista'));heading.addWidget(self.preset)
        fit=QPushButton('Enquadrar');fit.clicked.connect(self.fit);heading.addWidget(fit)
        exporter=QPushButton('Exportar malha OBJ');exporter.clicked.connect(self.save_obj)
        exporter.setToolTip('Exporta os perfis extrudados em mm para auditoria geométrica externa')
        heading.addWidget(exporter)
        root.addLayout(heading)

        split=QSplitter(Qt.Orientation.Horizontal);root.addWidget(split,1)
        self.view=OrbitView(self);split.addWidget(self.view)
        panel=QWidget();panel.setMinimumWidth(285);pcol=QVBoxLayout(panel)
        pcol.setContentsMargins(4,0,2,0)
        self.pages=QTabWidget();pcol.addWidget(self.pages,1)
        split.addWidget(panel);split.setSizes([930,345]);split.setStretchFactor(0,1)

        # Página de visualização.
        colors_page=QWidget();f=QFormLayout(colors_page)
        self.mode=QComboBox()
        for label,id in [('Grupo estrutural','group'),('Família de perfil','family'),('Esforço normal','force')]:
            self.mode.addItem(label,id)
        self.mode.currentIndexChanged.connect(self.reset_keys)
        f.addRow('Cores por',self.mode)
        self.category=QComboBox();f.addRow('Categoria',self.category)
        change_color=QPushButton('Escolher cor');change_color.clicked.connect(self.choose_color)
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
        for slider in (self.yaw,self.elevation):slider.valueChanged.connect(self.schedule_redraw)
        self.legend=QLabel();self.legend.setWordWrap(True)
        f.addRow('Legenda',self.legend)
        self.pages.addTab(colors_page,'Exibição')

        # Página das SEÇÕES: integra a configuração no JSON, não no solver 3D.
        geom_page=QWidget();g=QFormLayout(geom_page)
        self.group=QComboBox();self.group.addItems(['superior','inferior','diagonal','montante'])
        self.group.currentTextChanged.connect(self.load_group)
        g.addRow('Grupo',self.group)
        self.profile_label=QLabel('');self.profile_label.setWordWrap(True)
        g.addRow('Perfil atribuído',self.profile_label)
        self.count=QSpinBox();self.count.setRange(1,2);g.addRow('Componentes',self.count)
        self.layout_type=QComboBox()
        for label,code in [('Costas a costas','back_to_back'),('Frente a frente','face_to_face'),
                           ('Mesma orientação','side_by_side')]:self.layout_type.addItem(label,code)
        g.addRow('Arranjo',self.layout_type)
        self.dx=QDoubleSpinBox();self.dx.setRange(-2000,2000);self.dx.setDecimals(2);self.dx.setSuffix(' mm')
        self.dy=QDoubleSpinBox();self.dy.setRange(-2000,2000);self.dy.setDecimals(2);self.dy.setSuffix(' mm')
        self.rotation=QComboBox();self.rotation.addItems(['0','90','180','-90'])
        g.addRow('Δ centroide fora do plano',self.dx)
        g.addRow('Δ centroide no plano',self.dy)
        g.addRow('Rotação da seção',self.rotation)
        g.addRow(QLabel('CONTORNO IDEALIZADO DA SEÇÃO (mm)'))
        self.section_preview=QGraphicsView();self.section_preview.setScene(QGraphicsScene(self.section_preview))
        self.section_preview.setFixedHeight(172)
        self.section_preview.setBackgroundBrush(QBrush(QColor('#F3F7FA')))
        g.addRow(self.section_preview)
        for widget in (self.count,self.dx,self.dy):widget.valueChanged.connect(self.update_section_preview)
        self.layout_type.currentIndexChanged.connect(self.update_section_preview)
        self.rotation.currentTextChanged.connect(self.update_section_preview)
        self.apply_button=QPushButton('Aplicar ao projeto e atualizar')
        self.apply_button.setStyleSheet('background:#166F9F;color:white;font-weight:bold;')
        self.apply_button.clicked.connect(self.apply_layout);g.addRow(self.apply_button)
        help_label=QLabel('Zero em ambos os espaçamentos ativa APENAS uma separação gráfica '
                          'ilustrativa, identificada como hipótese.\n\n'
                          'As cotas são de centroide a centroide. As alterações invalidam '
                          'os resultados da análise anterior.')
        help_label.setWordWrap(True);g.addRow(help_label)
        self.pages.addTab(geom_page,'Arranjo')

        info=QGroupBox('ELEMENTO INSPECIONADO');info_box=QVBoxLayout(info)
        self.selected_label=QLabel('Clique direito sobre uma barra para inspecionar.')
        self.selected_label.setWordWrap(True);info_box.addWidget(self.selected_label)
        pcol.addWidget(info)
        self.issue=QLabel('');self.issue.setWordWrap(True);self.issue.setStyleSheet('color:#995F24;font-size:9pt;')
        pcol.addWidget(self.issue)
        self.disclaimer=QLabel('Visualização das paredes ideais dos perfis, sem raios, ligações ou seções '
                               'laminadas completas quando o catálogo não fornece todas as dimensões. '
                               'Escala de seção pode ser exagerada SOMENTE no desenho (3× inicialmente); OBJ mantém 1×. Sem análise 3D ou aprovação ELU.')
        self.disclaimer.setWordWrap(True);self.disclaimer.setStyleSheet('color:#586D7F;font-size:9pt;')
        root.addWidget(self.disclaimer)
        self.load_group()
        self.reset_keys()
        QTimer.singleShot(0,self.fit)

    def axial(self):
        return ((self.session.result or {}).get('analyses',{}).get(self.case_id,{}).get('axial_n',{}))

    def load_group(self,*_):
        if not hasattr(self,'count'):return
        group=self.group.currentText()
        spec=self.session.project.get('sections',{}).get(group,{})
        cfg=self.session.project.get('section_arrangements',{}).get(group,{})
        self._loading=True
        try:
            self.profile_label.setText(str(spec.get('profile','Catálogo não atribuído')))
            self.count.setValue(int(spec.get('count',1)))
            index=self.layout_type.findData(cfg.get('assembly_type','back_to_back'))
            self.layout_type.setCurrentIndex(index if index>=0 else 0)
            self.dx.setValue(float(cfg.get('centroid_dx_mm',0)))
            self.dy.setValue(float(cfg.get('centroid_dy_mm',0)))
            self.rotation.setCurrentText(str(cfg.get('rotation_deg',0)))
        finally:self._loading=False
        self.update_section_preview()

    def update_section_preview(self,*_):
        if self._loading or not hasattr(self,'section_preview'):return
        group=self.group.currentText()
        spec=self.session.project.get('sections',{}).get(group,{})
        shape=self.shape_catalog.get(spec.get('profile'))
        scene=self.section_preview.scene();scene.clear()
        if shape is None:return
        cfg={'centroid_dx_mm':self.dx.value(),'centroid_dy_mm':self.dy.value(),
             'rotation_deg':float(self.rotation.currentText()),
             'assembly_type':self.layout_type.currentData()}
        try:polygons,_=make_section_layout(shape,self.count.value(),cfg)
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
        self._orbit_update.start()

    def apply_layout(self):
        if self._app is None:
            QMessageBox.information(self,'Arranjo','Editor somente leitura: abra pelo aplicativo principal.');return
        group=self.group.currentText()
        project=deepcopy(self.session.project)
        sections=project.setdefault('sections',{})
        if group not in sections:
            QMessageBox.warning(self,'Perfil','Não há seção atribuída para este grupo.');return
        sections[group]['count']=self.count.value()
        cfg=project.setdefault('section_arrangements',{})
        cfg[group]={
            'centroid_dx_mm':self.dx.value(), 'centroid_dy_mm':self.dy.value(),
            'rotation_deg':float(self.rotation.currentText()),
            'assembly_type':self.layout_type.currentData(),
            'connection_reference':cfg.get(group,{}).get('connection_reference',''),
        }
        try:
            self._app._apply(project,f'Arranjo do {group} atualizado')
        except Exception as exc:
            QMessageBox.warning(self,'Arranjo não aplicado',str(exc));return

    def set_preset(self,label):
        angles={'Isométrica':(30,25),'Frontal XY':(0,0),
                'Perfil lateral':(90,0),'Superior':(0,80)}
        if label not in angles:return
        self.yaw.blockSignals(True);self.elevation.blockSignals(True)
        self.yaw.setValue(angles[label][0]);self.elevation.setValue(angles[label][1])
        self.yaw.blockSignals(False);self.elevation.blockSignals(False)
        self.redraw();self.fit()

    def refresh_model(self, case_id):
        self.case_id = case_id
        if self._mesh_revision != self.session.revision:
            self.load_group()
        self.reset_keys()

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

    def inspect_member(self,mid):
        self._selected_member=mid
        m=next((m for m in self.session.model.members if m.id==mid),None)
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
        self._ensure_meshes()
        scene=self.view.scene();scene.clear()
        mode=self.mode.currentData();forces=self.axial()
        cam=Camera(float(self.yaw.value()),float(self.elevation.value()))
        all_faces=[];colors={}
        nodes=self.session.model.node_map()
        members = {member.id: member for member in self.session.model.members}
        for mesh in self._meshes:
            member = members.get(mesh.member_id)
            if not member:continue
            key=color_key(member,self.session.catalog,mode,forces)
            base=self.colors.get(key,'#8395A3');colors[key]=base
            a,b=nodes[member.i],nodes[member.j]
            drawn=display_scaled_vertices(mesh,(a.x,a.y),(b.x,b.y),self.section_scale.value())
            projected=[project(v,cam) for v in drawn]
            for index,face in enumerate(mesh.faces):
                pts=[projected[i] for i in face]
                z=fsum(p[2] for p in pts)/len(pts)
                all_faces.append((z,index,mesh,base,pts))
        # Aproximação por painter's algorithm. A interpolação em cruzamentos não
        # dispõe de z-buffer; não utilizar para interferência ou fabricação.
        for z,i,mesh,base,pts in sorted(all_faces,key=lambda x:x[0]):
            poly=QPolygonF([QPointF(p[0],p[1]) for p in pts])
            item=QGraphicsPolygonItem(poly)
            c=QColor(base)
            c=(c.darker(127) if i in (0,1) else c.lighter(115) if i%3==0 else c)
            if self._selected_member==mesh.member_id:c=c.lighter(130)
            item.setBrush(QBrush(c) if self.surface_style.currentText()=='Sólido' else QBrush(Qt.BrushStyle.NoBrush))
            item.setPen(QPen(QColor('#244258') if self.show_edges.isChecked() else c,
                             0.65 if self.show_edges.isChecked() else 0))
            item.setToolTip(f'{mesh.member_id} · componente {mesh.component} · {mesh.profile}')
            item.setData(0,mesh.member_id)
            scene.addItem(item)
        if self.show_axes.isChecked():
            nd=self.session.model.node_map()
            for m in self.session.model.members:
                a,b=nd[m.i],nd[m.j]
                p,q=project((a.x,a.y,0),cam),project((b.x,b.y,0),cam)
                line=scene.addLine(p[0],p[1],q[0],q[1],QPen(QColor('#788E9F'),0.7,Qt.PenStyle.DashLine))
                line.setData(0,m.id)
        if self.show_nodes.isChecked():
            for n in self.session.model.nodes:
                x,y,_=project((n.x,n.y,0),cam)
                node=QGraphicsEllipseItem(-3,-3,6,6);node.setPos(x,y)
                node.setPen(QPen(QColor('#1D4259'),1))
                node.setBrush(QBrush(QColor('#FFFFFF')))
                node.setToolTip(f'Nó {n.id} | X={n.x:.2f} Y={n.y:.2f} mm')
                node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,True)
                node.setZValue(9);scene.addItem(node)
        self.legend.setText('  ·  '.join(colors) if colors else 'Nenhuma seção gerada')
        shown=self._warnings[:5]
        if len(self._warnings)>5:shown.append(f'+ {len(self._warnings)-5} avisos semelhantes')
        self.issue.setText('\n'.join(shown) if shown else 'Contornos ideais gerados; conferir catálogo e condições de ligação.')
        if self._selected_member:self.inspect_member(self._selected_member)
        if scene.items():
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
        if scene.items():self.view.fitInView(scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
