"""Viewport de engenharia 2D em Canvas nativo: seleção, pan, zoom e edição.

As coordenadas estruturais são sempre mm; o zoom só transforma pixels.
O viewport não calcula resultados: apenas representa o estado Session.
"""
from __future__ import annotations
import math
import tkinter as tk
from tkinter import ttk

NAVY='#11253B'; BLUE='#1871B4'; COMP='#2563B8'; TENS='#C44048'
BG='#F7FAFD'; GRID='#EAF0F5'; TEXT='#20354A'; MUTED='#728497'; CYAN='#0798B6'

class TrussViewport(ttk.Frame):
    def __init__(self,parent,session,selection_changed=lambda kind,key:None,node_moved=lambda *a:None):
        super().__init__(parent)
        self.session=session
        self.selection_changed=selection_changed
        self.node_moved=node_moved
        self.canvas=tk.Canvas(self,bg=BG,highlightthickness=0,cursor='crosshair',bd=0)
        self.canvas.pack(fill='both',expand=True)
        self.zoom=1.0;self.offset_x=0.0;self.offset_y=0.0;self.fitted=False
        self.vertical_factor=tk.DoubleVar(value=2.0)
        self.selected_kind=None;self.selected_id=None
        self.show_nodes=tk.BooleanVar(value=True)
        self.show_labels=tk.BooleanVar(value=False)
        self.show_forces=tk.BooleanVar(value=False)
        self.show_efforts=tk.BooleanVar(value=True)
        self.show_deformed=tk.BooleanVar(value=False)
        self.edit_nodes=tk.BooleanVar(value=False)
        self.case_id=tk.StringVar(value='')
        self.force_unit=tk.StringVar(value='kN')
        self._objects=[];self._drag=None;self._pan=None;self._space=False;self._auto_fit=True
        self._preview_position=None
        cv=self.canvas
        cv.bind('<Configure>',self._on_resize)
        cv.bind('<Button-1>',self._on_left_down)
        cv.bind('<B1-Motion>',self._on_move)
        cv.bind('<ButtonRelease-1>',self._on_release)
        cv.bind('<Button-2>',self._on_pan_down)
        cv.bind('<B2-Motion>',self._on_pan_move)
        cv.bind('<ButtonRelease-2>',lambda e:self._end_pan())
        cv.bind('<Button-3>',self._on_pan_down)
        cv.bind('<B3-Motion>',self._on_pan_move)
        cv.bind('<ButtonRelease-3>',lambda e:self._end_pan())
        cv.bind('<MouseWheel>',self._on_zoom)
        cv.bind('<Button-4>',lambda e:self.zoom_at(e.x,e.y,1.14))
        cv.bind('<Button-5>',lambda e:self.zoom_at(e.x,e.y,1/1.14))
        cv.bind('<Double-Button-1>',lambda e:self.fit())
        self.refresh()

    def _on_resize(self,event):
        if not self.fitted or self._auto_fit:self.fit()
        else:self.refresh()

    def to_screen(self,x,y):return self.offset_x+self.zoom*x,self.offset_y-self.zoom*y*self.vertical_factor.get()
    def to_world(self,x,y):return (x-self.offset_x)/self.zoom,(self.offset_y-y)/(self.zoom*self.vertical_factor.get())

    def fit(self):
        if not self.session.model:return
        ns=self.session.model.nodes
        minx,maxx=min(n.x for n in ns),max(n.x for n in ns)
        miny,maxy=min(n.y for n in ns),max(n.y for n in ns)
        w=max(self.canvas.winfo_width(),500);h=max(self.canvas.winfo_height(),350)
        pad_x=90;pad_y=85
        self.zoom=max(.0001,min((w-2*pad_x)/max(maxx-minx,100),(h-2*pad_y)/max((maxy-miny)*self.vertical_factor.get(),300)))
        self.offset_x=w/2-self.zoom*(minx+maxx)/2
        self.offset_y=h/2+self.zoom*(miny+maxy)*self.vertical_factor.get()/2
        self.fitted=True;self._auto_fit=True
        self.refresh()

    def zoom_at(self,px,py,factor):
        self._auto_fit=False
        ox,oy=self.to_world(px,py)
        self.zoom=max(.001,min(50.,self.zoom*factor))
        self.offset_x=px-ox*self.zoom
        self.offset_y=py+oy*self.zoom
        self.refresh()

    def _on_zoom(self,e):self.zoom_at(e.x,e.y,1.14 if e.delta>0 else 1/1.14)

    def _on_pan_down(self,e):self._auto_fit=False;self._pan=(e.x,e.y,self.offset_x,self.offset_y)
    def _on_pan_move(self,e):
        if self._pan:
            x,y,ox,oy=self._pan;self.offset_x=ox+e.x-x;self.offset_y=oy+e.y-y;self.refresh()
    def _end_pan(self):self._pan=None

    def _hit(self,x,y):
        best=(float('inf'),None,None)
        nd=self.session.model.node_map()
        for n in self.session.model.nodes:
            xx,yy=self.to_screen(n.x,n.y)
            d=math.hypot(x-xx,y-yy)
            if d<=13 and d<best[0]: best=(d,'node',n.id)
        if best[1]:return best[1:]
        for m in self.session.model.members:
            a,b=nd[m.i],nd[m.j]
            x0,y0=self.to_screen(a.x,a.y);x1,y1=self.to_screen(b.x,b.y)
            length2=(x1-x0)**2+(y1-y0)**2
            if not length2:continue
            t=max(0,min(1,((x-x0)*(x1-x0)+(y-y0)*(y1-y0))/length2))
            d=math.hypot(x-(x0+t*(x1-x0)),y-(y0+t*(y1-y0)))
            if d<=9 and d<best[0]:best=(d,'member',m.id)
        return best[1:]

    def _on_left_down(self,e):
        kind,key=self._hit(e.x,e.y)
        self.selected_kind,self.selected_id=kind,key
        self.selection_changed(kind,key)
        if kind=='node' and self.edit_nodes.get():
            n=self.session.model.node_map()[key]
            self._drag=(key,n.x,n.y,e.x,e.y)
        self.refresh()

    def _on_move(self,e):
        if self._drag:
            key,x,y,x0,y0=self._drag
            self._preview_position=(key,x+(e.x-x0)/self.zoom,y-(e.y-y0)/(self.zoom*self.vertical_factor.get()))
            self.refresh()

    def _on_release(self,e):
        if self._drag:
            key,x,y,x0,y0=self._drag
            self._drag=None;self._preview_position=None
            if abs(e.x-x0)+abs(e.y-y0)>4:
                self.node_moved(key,x+(e.x-x0)/self.zoom,y-(e.y-y0)/(self.zoom*self.vertical_factor.get()))
            self.refresh()

    def set_selection(self,kind,key):
        self.selected_kind,self.selected_id=kind,key
        self.refresh()

    def _grid(self,w,h):
        # grade fixa no viewport, não interfere nas coordenadas de engenharia
        cv=self.canvas
        for x in range(0,w,48):cv.create_line(x,0,x,h,fill=GRID)
        for y in range(0,h,48):cv.create_line(0,y,w,y,fill=GRID)

    def _support(self,x,y,ux,uy):
        c=self.canvas
        if ux and uy:
            c.create_polygon(x,y+6,x-10,y+21,x+10,y+21,fill='#BAC9D5',outline='#657B8E',width=1)
            c.create_line(x-15,y+23,x+15,y+23,fill='#657B8E',width=2)
        elif uy:
            c.create_polygon(x,y+5,x-10,y+20,x+10,y+20,fill='#C6D6E0',outline='#657B8E',width=1)
            for dx in (-7,0,7):c.create_oval(x+dx-2,y+22,x+dx+2,y+26,fill='#8FA3B5',outline='')
            c.create_line(x-16,y+28,x+16,y+28,fill='#657B8E',width=1)
        elif ux:
            c.create_line(x-5,y-9,x-5,y+9,fill='#657B8E',width=3)
            c.create_line(x-12,y-11,x-12,y+11,fill='#657B8E',width=2)

    def refresh(self):
        c=self.canvas;c.delete('all')
        w=max(c.winfo_width(),500);h=max(c.winfo_height(),350)
        self._grid(w,h)
        model=self.session.model
        if model is None:return
        nm=model.node_map()
        pos={n.id:self.to_screen(n.x,n.y) for n in model.nodes}
        if self._preview_position:
            node,x,y=self._preview_position
            if node in pos:pos[node]=self.to_screen(x,y)
        res=self.session.result
        analysis=None
        if res and self.case_id.get() in res['analyses']:
            analysis=res['analyses'][self.case_id.get()]
        if not analysis and res:
            first=next(iter(res['analyses']),None)
            if first: analysis=res['analyses'][first]
        c.create_text(22,22,anchor='w',text='MODELO ESTRUTURAL  /  VISTA XY',font=('Segoe UI',10,'bold'),fill=NAVY)
        c.create_text(22,44,anchor='w',text=f"{model.truss_type} · {model.shape} · {len(model.nodes)} nós · {len(model.members)} barras · L={model.span_mm/1000:.3f} m",font=('Segoe UI',9),fill=MUTED)
        if not res:
            c.create_rectangle(w-220,16,w-15,45,fill='#FFF3DD',outline='#ECD6AD')
            c.create_text(w-118,30,text='PRÉVIA · NÃO CALCULADO',font=('Segoe UI',9,'bold'),fill='#8D611E')
        else:
            c.create_rectangle(w-168,16,w-15,45,fill='#E8F5ED',outline='#B5DCC4')
            c.create_text(w-92,30,text='ANÁLISE ATUAL',font=('Segoe UI',9,'bold'),fill='#216A3E')
        # deformada amplificada
        if analysis and self.show_deformed.get():
            u=analysis['nodal_displacements']
            maxu=max([abs(v['ux_mm'])+abs(v['uy_mm']) for v in u.values()] or [1])
            mag=min(1200.,max(1.,30/(maxu*self.zoom)))
            for m in model.members:
                a,b=nm[m.i],nm[m.j]
                p=u[m.i];q=u[m.j]
                x0,y0=self.to_screen(a.x+mag*p['ux_mm'],a.y+mag*p['uy_mm'])
                x1,y1=self.to_screen(b.x+mag*q['ux_mm'],b.y+mag*q['uy_mm'])
                c.create_line(x0,y0,x1,y1,fill='#55B7A0',dash=(5,3),width=2)
            c.create_text(w-20,h-46,anchor='e',text=f'Deformada ampliada ×{mag:.1f}',fill='#3B9283',font=('Segoe UI',9))
        # barras
        maxax=max([abs(v) for v in analysis['axial_n'].values()] or [1]) if analysis else 1.
        for m in model.members:
            x0,y0=pos[m.i];x1,y1=pos[m.j]
            color='#738FA5' if m.group in ('montante','diagonal') else '#167AAB'
            width=2 if m.group in ('montante','diagonal') else 3
            if analysis and self.show_efforts.get():
                force=analysis['axial_n'][m.id]
                color=TENS if force>1e-5 else COMP if force< -1e-5 else '#A1AAB4'
                width=1.7+2.1*math.sqrt(abs(force)/maxax)
            if self.selected_kind=='member' and self.selected_id==m.id:
                c.create_line(x0,y0,x1,y1,fill='#F7B242',width=width+7)
            c.create_line(x0,y0,x1,y1,fill=color,width=width,capstyle=tk.ROUND)
        # rotulagem com anticolisão; forças preferencialmente visíveis em barras mais solicitadas
        if analysis and self.show_efforts.get():
            ranked=sorted(model.members,key=lambda m:abs(analysis['axial_n'][m.id]),reverse=True)
            limit=1000 if self.show_labels.get() else 16
            rectangles=[]
            for m in ranked:
                if limit<=0:break
                val=analysis['axial_n'][m.id]/1000
                if abs(val)<.005: continue
                x0,y0=pos[m.i];x1,y1=pos[m.j]
                dx=x1-x0;dy=y1-y0
                L=math.hypot(dx,dy)
                if L<28:continue
                mx=(x0+x1)/2;my=(y0+y1)/2
                theta=math.degrees(math.atan2(-dy,dx))
                if theta>90:theta-=180
                if theta< -90:theta+=180
                offset=11
                mx-=dy/L*offset;my+=dx/L*offset
                label=f'{val:+.2f}'
                wide=12+len(label)*7.4
                rect=(mx-wide/2,my-10,mx+wide/2,my+10)
                if (not self.show_labels.get()) and any(not (rect[2]<r[0] or rect[0]>r[2] or rect[3]<r[1] or rect[1]>r[3]) for r in rectangles):
                    continue
                rectangles.append(rect)
                c.create_text(mx,my,text=label,font=('Segoe UI',12,'bold'),fill=TENS if val>0 else COMP,angle=theta)
                limit-=1
        # nós em primeiro plano
        for node in model.nodes:
            x,y=pos[node.id]
            active=self.selected_kind=='node' and self.selected_id==node.id
            if active:c.create_oval(x-10,y-10,x+10,y+10,fill='#FFD178',outline='#BA8D27',width=2)
            c.create_oval(x-4,y-4,x+4,y+4,fill='#FFFFFF',outline=NAVY,width=2)
            if self.show_nodes.get() and (active or len(model.nodes)<=18 or (node.id[1:].isdigit() and int(node.id[1:]) % 4 == 0)):
                c.create_text(x+8,y-13,anchor='w',text=node.id,font=('Segoe UI',9,'bold' if active else 'normal'),fill=NAVY if active else MUTED)
        for node,(ux,uy) in model.supports.items():
            x,y=pos[node];self._support(x,y,ux,uy)
        # carregamentos nodais equivalentes
        if self.show_forces.get():
            loads=analysis['loads'] if analysis else self.session.forces_for_case(self.case_id.get())
            nonzero=[(node,v) for node,v in loads.items() if abs(v.get('fx_n',0) if isinstance(v,dict) else v[0])+abs(v.get('fy_n',0) if isinstance(v,dict) else v[1])>1e-5]
            maxf=max([math.hypot(v.get('fx_n',0),v.get('fy_n',0)) if isinstance(v,dict) else math.hypot(*v) for _,v in nonzero] or [1])
            for node,v in nonzero:
                if node not in pos:continue
                x,y=pos[node]
                fx=v.get('fx_n',0) if isinstance(v,dict) else v[0]
                fy=v.get('fy_n',0) if isinstance(v,dict) else v[1]
                length=max(14,min(43,42*math.hypot(fx,fy)/maxf))
                norm=math.hypot(fx,fy)
                ux=fx/norm;uy=-fy/norm
                # seta aponta para o nó, na direção do esforço
                c.create_line(x-ux*length,y-uy*length,x,y,fill='#E69727',width=2.3,arrow=tk.LAST,arrowshape=(10,12,4))
        c.create_line(22,h-27,47,h-27,fill=COMP,width=3)
        c.create_text(52,h-27,text='Compressão',anchor='w',fill=MUTED,font=('Segoe UI',9))
        c.create_line(150,h-27,175,h-27,fill=TENS,width=3)
        c.create_text(180,h-27,text='Tração  ·  N [kN]  |  Coordenadas [mm]',anchor='w',fill=MUTED,font=('Segoe UI',9))
        c.create_text(w-18,h-17,anchor='e',text=f'{self.zoom:.4f} px/mm   ·   Roda: zoom   ·   Botão do meio: pan   ·   Duplo clique: ajustar',fill=MUTED,font=('Segoe UI',8))
