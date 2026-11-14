"""2DTruss v0.1 — aplicativo desktop nativo, sem navegador.

Camada gráfica Tk/ttk; cálculo e dados pertencem exclusivamente ao pacote poe_truss.
Não executa servidor HTTP, não abre portas nem usa webview.
"""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from .bridge import Session, load_project, write_project, ROOT
from .viewport import TrussViewport, NAVY, BLUE, BG, TEXT, MUTED, CYAN
from poe_truss.export import dimperfil_rows, as_csv, report_html, load_audit_rows

TITLE='2DTRUSS  |  v0.1 DESKTOP'
COLORS={'header':'#122D47','accent':'#1074A7','soft':'#EDF3F9','border':'#DCE5ED','white':'#FFFFFF','left':'#EDF3F7','warning':'#925C15'}
SHAPES={'Banzos paralelos':'parallel','Uma água':'single','Duas águas':'gable','Trapezoidal':'trapezoid'}
SHAPE_NAMES={v:k for k,v in SHAPES.items()}

class App(tk.Tk):
    def __init__(self,session=None):
        super().__init__()
        self.title(TITLE)
        self.geometry('1480x900');self.minsize(1080,690)
        self.configure(bg=COLORS['soft'])
        self.session=session or Session()
        self._history=[];self._future=[];self._file=None;self._dirty=False
        self._loading=False;self._geometry_job=None
        self._ribbon_tab='Modelagem'
        self._selected=(None,None)
        self._create_style();self._build()
        self._refresh_all(fit=True)
        self.protocol('WM_DELETE_WINDOW',self._on_close)
        self.bind_all('<Control-s>',lambda e:self.save())
        self.bind_all('<Control-o>',lambda e:self.open_file())
        self.bind_all('<Control-z>',lambda e:self.undo())
        self.bind_all('<Control-y>',lambda e:self.redo())
        self.bind_all('<F5>',lambda e:self.calculate())

    def _create_style(self):
        s=ttk.Style(self)
        s.theme_use('clam')
        s.configure('.',font=('Segoe UI',10))
        s.configure('TFrame',background=COLORS['soft'])
        s.configure('White.TFrame',background='white')
        s.configure('TLabel',background=COLORS['soft'],foreground=TEXT)
        s.configure('White.TLabel',background='white',foreground=TEXT)
        s.configure('Hint.TLabel',background='white',foreground=MUTED,font=('Segoe UI',9))
        s.configure('TLabelframe',background='white',bordercolor=COLORS['border'])
        s.configure('TLabelframe.Label',background='white',foreground=NAVY,font=('Segoe UI',10,'bold'))
        s.configure('TButton',padding=(9,6),background='#EDF2F7',foreground=NAVY,bordercolor='#D4E0E9')
        s.map('TButton',background=[('active','#DCEBF4')])
        s.configure('Primary.TButton',background=BLUE,foreground='white',bordercolor=BLUE)
        s.map('Primary.TButton',background=[('active','#14598F')])
        s.configure('Treeview',rowheight=27,background='white',fieldbackground='white',foreground=NAVY,borderwidth=0)
        s.configure('Treeview.Heading',font=('Segoe UI',9,'bold'),background='#EDF3F7',foreground=NAVY)
        s.map('Treeview',background=[('selected','#D5EBF7')],foreground=[('selected',NAVY)])
        s.configure('TNotebook',background=COLORS['soft'],borderwidth=0)
        s.configure('TNotebook.Tab',font=('Segoe UI',8),padding=(6,7),background='#E7EEF4')
        s.map('TNotebook.Tab',background=[('selected','white')],foreground=[('selected',BLUE)])
        s.configure('TCombobox',padding=5)
        s.configure('TEntry',padding=6)

    def _build(self):
        self._header=tk.Frame(self,bg=COLORS['header'],height=48)
        self._header.pack(fill='x');self._header.pack_propagate(False)
        tk.Label(self._header,text='POE  /  TRELIÇA',font=('Segoe UI',14,'bold'),bg=COLORS['header'],fg='white').pack(side='left',padx=20)
        tk.Label(self._header,text='ENGENHARIA ESTRUTURAL  •  ANÁLISE 2D',font=('Segoe UI',9),bg=COLORS['header'],fg='#A7C3D7').pack(side='left',padx=8)
        self.title_file=tk.Label(self._header,text='PROJETO NÃO SALVO',font=('Segoe UI',9,'bold'),bg=COLORS['header'],fg='#B0D5EA')
        self.title_file.pack(side='right',padx=20)

        # Ribbon em duas linhas — navegação por tarefas, ações agrupadas.
        self.ribbon_host=tk.Frame(self,bg='white',height=124,highlightthickness=1,highlightbackground=COLORS['border'])
        self.ribbon_host.pack(fill='x');self.ribbon_host.pack_propagate(False)
        self.ribbon_tabs=tk.Frame(self.ribbon_host,bg='#E9F1F7',height=31)
        self.ribbon_tabs.pack(fill='x');self.ribbon_tabs.pack_propagate(False)
        self.tab_buttons={}
        for name in ('Arquivo','Modelagem','Ações','Análise','Visualização'):
            b=tk.Button(self.ribbon_tabs,text=name,command=lambda n=name:self._set_ribbon(n),relief='flat',bd=0,padx=20,pady=5,highlightthickness=0,font=('Segoe UI',10,'bold'),cursor='hand2')
            b.pack(side='left');self.tab_buttons[name]=b
        self.ribbon=tk.Frame(self.ribbon_host,bg='white',height=86)
        self.ribbon.pack(fill='both',expand=True)
        self._set_ribbon('Modelagem')

        self.content=tk.PanedWindow(self,orient='horizontal',bg=COLORS['border'],sashwidth=6,showhandle=False,bd=0)
        self.content.pack(fill='both',expand=True)
        self.left=tk.Frame(self.content,bg=COLORS['left'],width=235)
        self.left.pack_propagate(False)
        self.center=tk.Frame(self.content,bg=BG)
        self.right=tk.Frame(self.content,bg='white',width=367)
        self.right.pack_propagate(False)
        self.content.add(self.left,minsize=165,stretch='never')
        self.content.add(self.center,minsize=350,stretch='always')
        self.content.add(self.right,minsize=305,stretch='never')
        self._sash_job=self.after(200,lambda:self._place_sashes())

        self._build_left();self._build_center();self._build_right()
        self.status=tk.Label(self,text='Pronto | Pré-dimensionamento experimental — sem aprovação ELU.',anchor='w',bg='#E5EDF3',fg=NAVY,font=('Segoe UI',9),padx=15,height=2)
        self.status.pack(fill='x')

    def _place_sashes(self):
        try:
            w=self.content.winfo_width()
            if w>950:
                self.content.sash_place(0,228,0)
                self.content.sash_place(1,w-368,0)
        except tk.TclError:pass

    def _ribbon_button(self,parent,text,cmd,primary=False):
        block=tk.Frame(parent,bg='white')
        block.pack(side='left',padx=(4,4),pady=5)
        ttk.Button(block,text=text,command=cmd,style='Primary.TButton' if primary else 'TButton').pack(pady=(8,2))
        return block

    def _set_ribbon(self,name):
        self._ribbon_tab=name
        for n,b in self.tab_buttons.items():
            b.configure(bg='white' if n==name else '#E9F1F7',fg=BLUE if n==name else NAVY)
        for child in self.ribbon.winfo_children():child.destroy()
        groups={
         'Arquivo':[('Novo',self.new_file),('Abrir JSON',self.open_file),('Salvar',self.save),('Salvar como',self.save_as),('Desfazer',self.undo),('Refazer',self.redo)],
         'Modelagem':[('Geometria',lambda:self._show_inspector('Modelo')),('Nós',lambda:self._show_inspector('Propriedades')),('Perfis',lambda:self._show_inspector('Perfis')),('Editar nó',self._toggle_edit),('Ajustar vista',self._fit)],
         'Ações':[('Casos de carga',lambda:self._show_inspector('Cargas')),('Nova carga nodal',self.add_nodal_case),('Carga no nó',self.add_load),('Ver forças',self._toggle_forces)],
         'Análise':[('Calcular  F5',self.calculate),('Resultados',lambda:self._show_inspector('Resultados')),('Exportar DimPerfil',self.export_dimperfil),('Exportar análise',self.export_results),('Memorial A3',self.export_memorial)],
         'Visualização':[('Nós / IDs',self._toggle_ids),('Esforços',self._toggle_efforts),('Deformada',self._toggle_def),('Forças',self._toggle_forces),('Vertical ×1',lambda:self._set_vertical(1)),('Vertical ×2',lambda:self._set_vertical(2)),('Vertical ×3',lambda:self._set_vertical(3)),('Enquadrar',self._fit)]
        }
        for i,(label,action) in enumerate(groups[name]):
            self._ribbon_button(self.ribbon,label,action,primary=(label=='Calcular  F5'))
        tk.Frame(self.ribbon,width=1,bg=COLORS['border']).pack(side='left',fill='y',padx=13,pady=11)
        tk.Label(self.ribbon,text='2DTRUSS  |  v0.1  •  DESKTOP NATIVO\nAnálise linear 2D  •  Resistências ELU não verificadas',fg=MUTED,bg='white',justify='left',font=('Segoe UI',9)).pack(side='left',padx=8)

    def _build_left(self):
        tk.Label(self.left,text='NAVEGADOR DO MODELO',bg=COLORS['left'],fg=NAVY,font=('Segoe UI',10,'bold'),anchor='w').pack(fill='x',padx=15,pady=(20,8))
        tk.Frame(self.left,height=1,bg=COLORS['border']).pack(fill='x',padx=10)
        tree_host=tk.Frame(self.left,bg=COLORS['left'])
        tree_host.pack(fill='both',expand=True,padx=(8,4),pady=(10,5))
        self.tree=ttk.Treeview(tree_host,show='tree',selectmode='browse')
        nav_scroll=ttk.Scrollbar(tree_host,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=nav_scroll.set)
        nav_scroll.pack(side='right',fill='y');self.tree.pack(side='left',fill='both',expand=True)
        self.tree.bind('<<TreeviewSelect>>',self._tree_select)
        self.tree.bind('<Double-1>',lambda e:self._show_inspector('Propriedades'))
        bottom=tk.Frame(self.left,bg=COLORS['left'])
        bottom.pack(fill='x',padx=10,pady=(2,12))
        ttk.Button(bottom,text='Enquadrar',command=self._fit).pack(fill='x',pady=3)
        ttk.Button(bottom,text='Calcular modelo',command=self.calculate,style='Primary.TButton').pack(fill='x',pady=3)

    def _build_center(self):
        top=tk.Frame(self.center,bg='white',height=49)
        top.pack(fill='x');top.pack_propagate(False)
        tk.Label(top,text='VISTA PRINCIPAL',font=('Segoe UI',10,'bold'),bg='white',fg=NAVY).pack(side='left',padx=15)
        tk.Label(top,text='Caso / combinação',font=('Segoe UI',9),bg='white',fg=MUTED).pack(side='left',padx=(25,6))
        self.case_var=tk.StringVar()
        self.case_combo=ttk.Combobox(top,textvariable=self.case_var,state='readonly',width=21)
        self.case_combo.pack(side='left',padx=(0,11))
        self.case_combo.bind('<<ComboboxSelected>>',lambda e:self._on_case())
        self.uncalc=tk.Label(top,text='NÃO CALCULADO',bg='#FFF2DE',fg='#8E621C',font=('Segoe UI',9,'bold'),padx=9,pady=4)
        self.uncalc.pack(side='right',padx=15)
        self.viewport=TrussViewport(self.center,self.session,self._on_select,self._move_node)
        self.viewport.pack(fill='both',expand=True)
        self.viewnote=tk.Frame(self.center,bg='white',height=38)
        self.viewnote.pack(fill='x');self.viewnote.pack_propagate(False)
        tk.Label(self.viewnote,text='ESC: cancelar seleção    |    Botão do meio: mover vista    |    Roda: zoom    |    Editar nó: arrastar e confirmar',bg='white',fg=MUTED,font=('Segoe UI',9)).pack(side='left',padx=16)

    def _build_right(self):
        tk.Label(self.right,text='INSPEÇÃO E PARÂMETROS',bg='white',fg=NAVY,font=('Segoe UI',10,'bold'),anchor='w').pack(fill='x',padx=14,pady=(17,8))
        self.inspector=ttk.Notebook(self.right)
        self.inspector.pack(fill='both',expand=True,padx=8,pady=(0,9))
        self.tabs={}
        for name in ('Propriedades','Modelo','Cargas','Resultados','Perfis'):
            tab=tk.Frame(self.inspector,bg='white')
            self.tabs[name]=tab
            self.inspector.add(tab,text={'Propriedades':'Nó / Barra','Resultados':'Esforços'}.get(name,name))
        self._build_property_panel()
        self._build_model_panel()
        self._build_load_panel()
        self._build_result_panel()
        self._build_profiles_panel()

    def _show_inspector(self,name):self.inspector.select(self.tabs[name])
    @staticmethod
    def _label(parent,text,row,column=0):
        tk.Label(parent,text=text,bg='white',fg=MUTED,font=('Segoe UI',9),anchor='w').grid(row=row,column=column,sticky='ew',padx=10,pady=(8,2))

    def _build_property_panel(self):
        p=self.tabs['Propriedades']
        self.prop_title=tk.Label(p,text='SELECIONE UM NÓ OU UMA BARRA',bg='white',fg=NAVY,font=('Segoe UI',10,'bold'),anchor='w',wraplength=310)
        self.prop_title.pack(fill='x',padx=12,pady=(19,8))
        self.prop_desc=tk.Label(p,text='Selecione diretamente no desenho ou no navegador do modelo.',bg='white',fg=MUTED,justify='left',anchor='nw',wraplength=310,font=('Segoe UI',9))
        self.prop_desc.pack(fill='x',padx=12,pady=(0,11))
        fields=tk.LabelFrame(p,text='Coordenadas do nó [mm]',bg='white',fg=NAVY,font=('Segoe UI',9,'bold'))
        fields.pack(fill='x',padx=10,pady=6)
        self.node_x=tk.StringVar(value='0.00');self.node_y=tk.StringVar(value='0.00')
        for i,(label,v) in enumerate((('X',self.node_x),('Y',self.node_y))):
            tk.Label(fields,text=label,bg='white',fg=MUTED).grid(row=i,column=0,padx=8,pady=5,sticky='w')
            ttk.Entry(fields,textvariable=v,width=18).grid(row=i,column=1,padx=7,pady=5,sticky='ew')
        ttk.Button(fields,text='Aplicar coordenadas',command=self.apply_node).grid(row=2,column=0,columnspan=2,sticky='ew',padx=8,pady=8)
        self.ux=tk.BooleanVar();self.uy=tk.BooleanVar()
        b=tk.LabelFrame(p,text='Apoios e restrições',bg='white',fg=NAVY,font=('Segoe UI',9,'bold'))
        b.pack(fill='x',padx=10,pady=7)
        ttk.Checkbutton(b,text='UX restringido',variable=self.ux).pack(anchor='w',padx=10,pady=3)
        ttk.Checkbutton(b,text='UY restringido',variable=self.uy).pack(anchor='w',padx=10,pady=3)
        ttk.Button(b,text='Aplicar vínculo',command=self.apply_support).pack(fill='x',padx=8,pady=8)
        ttk.Button(p,text='Criar força neste nó',command=self.add_load).pack(fill='x',padx=15,pady=12)
        tk.Label(p,text='Alterações manuais são registradas em node_edits no JSON.\nNó arrastado não cria barra nova.',bg='white',fg=MUTED,font=('Segoe UI',9),justify='left',wraplength=300).pack(fill='x',padx=15,pady=6)

    def _build_model_panel(self):
        p=self.tabs['Modelo']
        tk.Label(p,text='GEOMETRIA PARAMÉTRICA',bg='white',fg=NAVY,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=12,pady=(19,9))
        grid=tk.Frame(p,bg='white');grid.pack(fill='x',padx=10)
        self.geom_vars={}
        items=[('Vão [m]','span_m'),('Entre pórticos [m]','frame_spacing_m'),('Painéis','panels'),('Altura [m]','height_m'),('Elevação [m]','rise_m')]
        for i,(name,key) in enumerate(items):
            self._label(grid,name,i)
            v=tk.StringVar();self.geom_vars[key]=v
            e=ttk.Entry(grid,textvariable=v,width=17)
            e.grid(row=i,column=1,padx=5,pady=6,sticky='ew')
            v.trace_add('write',self._schedule_geometry)
        self.geom_vars['roof_shape']=tk.StringVar()
        self.geom_vars['truss_type']=tk.StringVar()
        self._label(grid,'Cobertura',5)
        self.shape_box=ttk.Combobox(grid,textvariable=self.geom_vars['roof_shape'],values=list(SHAPES),state='readonly',width=17)
        self.shape_box.grid(row=5,column=1,pady=5,sticky='ew');self.shape_box.bind('<<ComboboxSelected>>',lambda e:self._schedule_geometry())
        self._label(grid,'Triangulação',6)
        self.kind_box=ttk.Combobox(grid,textvariable=self.geom_vars['truss_type'],values=('Pratt','Howe','Warren'),state='readonly',width=17)
        self.kind_box.grid(row=6,column=1,pady=5,sticky='ew');self.kind_box.bind('<<ComboboxSelected>>',lambda e:self._schedule_geometry())
        grid.columnconfigure(1,weight=1)
        self.model_error=tk.Label(p,text='',bg='white',fg='#B94938',wraplength=300,justify='left',font=('Segoe UI',9))
        self.model_error.pack(fill='x',padx=14,pady=6)
        ttk.Button(p,text='Atualizar geometria',command=self.apply_geometry,style='Primary.TButton').pack(fill='x',padx=15,pady=9)
        ttk.Button(p,text='Limpar edições locais de nós',command=self.clear_node_edits).pack(fill='x',padx=15,pady=6)
        tk.Label(p,text='Prévia atualizada automaticamente. Ao trocar o número de painéis, confirma-se a limpeza das edições de nós e apoios personalizados.',bg='white',fg=MUTED,font=('Segoe UI',9),wraplength=306,justify='left').pack(fill='x',padx=15,pady=12)

    def _build_load_panel(self):
        p=self.tabs['Cargas']
        tk.Label(p,text='CASOS DE CARREGAMENTO',bg='white',fg=NAVY,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=12,pady=(15,9))
        self.load_cases_list=tk.Listbox(p,height=9,exportselection=False,font=('Segoe UI',9),bd=1,relief='solid',highlightthickness=0,selectbackground='#D8EDF9',selectforeground=NAVY)
        self.load_cases_list.pack(fill='x',padx=12,pady=4)
        self.load_cases_list.bind('<<ListboxSelect>>',lambda e:self._show_case_loads())
        tools=tk.Frame(p,bg='white');tools.pack(fill='x',padx=10,pady=7)
        ttk.Button(tools,text='Novo caso nodal',command=self.add_nodal_case).pack(side='left',padx=3)
        ttk.Button(tools,text='Inserir força',command=self.add_load).pack(side='left',padx=3)
        self.load_header=tk.Label(p,text='DADOS DO CASO SELECIONADO',bg='white',fg=NAVY,font=('Segoe UI',9,'bold'))
        self.load_header.pack(anchor='w',padx=12,pady=(12,6))
        self.surface_editor=tk.Frame(p,bg='white')
        self.surface_vars={}
        self._surface_fields=[
            ('Intensidade','value',None),('Unidade','force_unit',('kgf','tf','kN')),
            ('Direção','direction',('down','up','outward_normal','inward_normal','right','left')),
            ('Aplicação','application',('top','bottom')),
            ('Base','basis',('projected','roof_surface')),
            ('Zona','zone',('all','left','right'))]
        for i,(label,key,options) in enumerate(self._surface_fields):
            tk.Label(self.surface_editor,text=label,bg='white',fg=MUTED).grid(row=i,column=0,sticky='w',padx=10,pady=5)
            var=tk.StringVar();self.surface_vars[key]=var
            widget=(ttk.Combobox(self.surface_editor,textvariable=var,values=options,state='readonly',width=23)
                    if options is not None else ttk.Entry(self.surface_editor,textvariable=var,width=25))
            widget.grid(row=i,column=1,sticky='ew',padx=9,pady=5)
        self.surface_editor.columnconfigure(1,weight=1)
        self.surface_apply=ttk.Button(self.surface_editor,text='Aplicar parâmetros do caso',command=self.apply_load_case,style='Primary.TButton')
        self.surface_apply.grid(row=6,column=0,columnspan=2,sticky='ew',padx=10,pady=9)
        self.load_table=ttk.Treeview(p,columns=('node','fx','fy'),show='headings',height=7,selectmode='browse')
        for name,title,width in [('node','Nó',70),('fx','Fx',92),('fy','Fy',92)]:
            self.load_table.heading(name,text=title);self.load_table.column(name,width=width,stretch=True,anchor='center')
        self.load_table.pack(fill='x',padx=10)
        self.load_table.bind('<Double-1>',lambda e:self.edit_load())
        actions=tk.Frame(p,bg='white');actions.pack(fill='x',padx=10,pady=7)
        self.load_actions=actions
        ttk.Button(actions,text='Editar',command=self.edit_load).pack(side='left',padx=3)
        ttk.Button(actions,text='Excluir',command=self.delete_load).pack(side='left',padx=3)
        self.case_hint=tk.Label(p,text='Clique em um nó no desenho para selecionar o destino.',bg='white',fg=MUTED,wraplength=305,justify='left',font=('Segoe UI',9))
        self.case_hint.pack(fill='x',padx=12,pady=10)

    def _build_result_panel(self):
        p=self.tabs['Resultados']
        tk.Label(p,text='ESFORÇOS NORMAIS  ·  N [kN]',bg='white',fg=NAVY,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=12,pady=(15,9))
        controls=tk.Frame(p,bg='white');controls.pack(fill='x',padx=10,pady=5)
        self.group_filter=tk.StringVar(value='Todos')
        self.critical_filter=tk.StringVar(value='Todos')
        ttk.Combobox(controls,textvariable=self.group_filter,values=('Todos','superior','inferior','montante','diagonal'),state='readonly',width=14).pack(side='left',padx=2)
        ttk.Combobox(controls,textvariable=self.critical_filter,values=('Todos','Tração','Compressão','Críticas 15'),state='readonly',width=14).pack(side='left',padx=2)
        self.group_filter.trace_add('write',lambda *a:self._populate_results())
        self.critical_filter.trace_add('write',lambda *a:self._populate_results())
        self.results_table=ttk.Treeview(p,columns=('member','group','force'),show='headings',height=14)
        for k,t,w in [('member','Barra',75),('group','Grupo',85),('force','N [kN]',110)]:
            self.results_table.heading(k,text=t);self.results_table.column(k,width=w,anchor='center',stretch=True)
        result_host=tk.Frame(p,bg='white')
        result_host.pack(fill='both',expand=True,padx=9,pady=8)
        results_scroll=ttk.Scrollbar(result_host,orient='vertical',command=self.results_table.yview)
        self.results_table.configure(yscrollcommand=results_scroll.set)
        results_scroll.pack(side='right',fill='y')
        self.results_table.pack(side='left',fill='both',expand=True)
        self.results_table.bind('<<TreeviewSelect>>',self._result_select)
        self.result_summary=tk.Label(p,text='Calcule o modelo para visualizar resultados.',bg='white',fg=MUTED,wraplength=330,justify='left',font=('Segoe UI',9))
        self.result_summary.pack(fill='x',padx=11,pady=8)
        ttk.Button(p,text='Calcular agora  F5',style='Primary.TButton',command=self.calculate).pack(fill='x',padx=11,pady=7)

    def _build_profiles_panel(self):
        p=self.tabs['Perfis']
        tk.Label(p,text='PERFIS POR GRUPO',bg='white',fg=NAVY,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=11,pady=(17,9))
        self.profile_vars={};self.count_vars={}
        names=sorted(self.session.catalog)
        for group in ('superior','inferior','montante','diagonal'):
            block=tk.LabelFrame(p,text=group.capitalize(),bg='white',fg=NAVY,font=('Segoe UI',9,'bold'))
            block.pack(fill='x',padx=10,pady=5)
            a=tk.StringVar();n=tk.StringVar()
            self.profile_vars[group]=a;self.count_vars[group]=n
            cb=ttk.Combobox(block,textvariable=a,values=names,state='readonly',width=32)
            cb.pack(fill='x',padx=8,pady=(5,2))
            row=tk.Frame(block,bg='white');row.pack(fill='x',padx=8,pady=(0,7))
            tk.Label(row,text='Quantidade',bg='white',fg=MUTED).pack(side='left')
            ttk.Combobox(row,textvariable=n,values=('1','2'),state='readonly',width=4).pack(side='right')
        ttk.Button(p,text='Aplicar perfis',command=self.apply_profiles,style='Primary.TButton').pack(fill='x',padx=13,pady=12)
        tk.Label(p,text='Perfis duplos: a triagem da v0.1 não comprova a solidarização entre componentes nem a resistência ELU.',bg='white',fg=MUTED,font=('Segoe UI',9),wraplength=313,justify='left').pack(fill='x',padx=13)

    def _set_status(self,msg):self.status.configure(text=msg)

    def _refresh_all(self,fit=False):
        self._loading=True
        try:
            self.title_file.configure(text=(Path(self._file).name if self._file else 'PROJETO NÃO SALVO')+(' *' if self._dirty else ''))
            g=self.session.project.get('geometry',{})
            for k,v in self.geom_vars.items():
                if k=='roof_shape':v.set(SHAPE_NAMES.get(g.get(k,'parallel'),'Banzos paralelos'))
                elif k=='truss_type':v.set(g.get(k,'Pratt'))
                else:
                    val=g.get(k,0)
                    v.set(str(int(val)) if k=='panels' else f'{float(val):.5f}')
            for group in self.profile_vars:
                spec=self.session.project.get('sections',{}).get(group,{})
                self.profile_vars[group].set(spec.get('profile',''))
                self.count_vars[group].set(str(spec.get('count',1)))
            selected_case=self.case_var.get()
            cases=[c['id'] for c in self.session.project.get('load_cases',[])]+[x['id'] for x in self.session.project.get('combinations',[])]
            self.case_combo['values']=cases
            if selected_case not in cases:selected_case=cases[0] if cases else ''
            self.case_var.set(selected_case);self.viewport.case_id.set(selected_case)
            self._populate_tree();self._populate_load_cases();self._populate_results();self._update_property()
            self.uncalc.configure(text='ANÁLISE ATUAL' if self.session.result else 'NÃO CALCULADO',bg='#E8F5EC' if self.session.result else '#FFF2DE',fg='#226B3F' if self.session.result else '#8E621C')
            if fit:self.viewport.fit()
            else:self.viewport.refresh()
        finally:self._loading=False

    def _populate_tree(self):
        tree=self.tree
        tree.delete(*tree.get_children())
        g=tree.insert('', 'end',iid='project',text=self.session.project.get('name','Projeto estrutural'),open=True)
        nroot=tree.insert(g,'end',iid='root_nodes',text=f'Nós  ({len(self.session.model.nodes)})',open=False)
        for node in self.session.model.nodes:tree.insert(nroot,'end',iid='node|'+node.id,text=node.id)
        broot=tree.insert(g,'end',iid='root_members',text=f'Barras  ({len(self.session.model.members)})',open=False)
        for m in self.session.model.members:tree.insert(broot,'end',iid='member|'+m.id,text=f'{m.id} · {m.group}')
        tree.insert(g,'end',iid='root_cases',text=f"Casos  ({len(self.session.project.get('load_cases',[]))})")

    def _populate_load_cases(self):
        old=self._chosen_case_id()
        self.load_cases_list.delete(0,'end')
        self._load_case_ids=[]
        for x in self.session.project.get('load_cases',[]):
            self._load_case_ids.append(x['id'])
            self.load_cases_list.insert('end',f"{x['id']} · {x.get('kind')}")
        if self._load_case_ids:
            try:i=self._load_case_ids.index(old)
            except ValueError:i=0
            self.load_cases_list.selection_set(i)
        self._show_case_loads()

    def _chosen_case_id(self):
        sel=self.load_cases_list.curselection() if hasattr(self,'load_cases_list') else ()
        return self._load_case_ids[sel[0]] if sel and sel[0]<len(getattr(self,'_load_case_ids',[])) else None

    def _show_case_loads(self):
        if not hasattr(self,'load_table'):return
        tree=self.load_table;tree.delete(*tree.get_children())
        cid=self._chosen_case_id()
        case=next((c for c in self.session.project.get('load_cases',[]) if c['id']==cid),None)
        if not case:return
        if not self._loading and cid!=self.case_var.get() and cid in self.case_combo['values']:
            self.case_var.set(cid);self._on_case()
        kind=case['kind']
        if kind in ('surface','line'):
            self.load_table.pack_forget();self.load_actions.pack_forget()
            self.load_header.configure(text='PARÂMETROS DA AÇÃO')
            for label,key,options in self._surface_fields:
                value=case.get(key,{'force_unit':'kgf','direction':'down','application':'top','basis':'projected','zone':'all'}.get(key,''))
                self.surface_vars[key].set(str(value))
            self.surface_editor.pack(fill='x',padx=10,before=self.case_hint)
            self.case_hint.configure(text='As cargas resultantes são redistribuídas automaticamente pelos nós após aplicar. Edite os valores e recalcule (F5).')
            return
        self.surface_editor.pack_forget()
        self.load_actions.pack(fill='x',padx=10,pady=7,before=self.case_hint)
        self.load_table.pack(fill='x',padx=10,before=self.load_actions)
        self.load_header.configure(text='FORÇAS NODAIS' if kind=='nodal' else 'PESO PRÓPRIO AUTOMÁTICO')
        if case['kind']=='nodal':
            for idx,force in enumerate(case.get('loads',[])):
                tree.insert('','end',iid=str(idx),values=(force['node'],f"{force.get('fx',0):+.2f}",f"{force.get('fy',0):+.2f}"))
            self.case_hint.configure(text='Caso nodal: clique em um nó e use Inserir força; unidades individuais são preservadas no JSON.')
        else:self.case_hint.configure(text=f"Caso {cid} do tipo {case['kind']}: as ações são definidas pelos parâmetros originais; sua edição continua disponível no JSON legado.")

    def _populate_results(self):
        if not hasattr(self,'results_table'):return
        tree=self.results_table;tree.delete(*tree.get_children())
        res=self.session.result
        if not res:
            self.result_summary.configure(text='Resultados desatualizados após alteração. Execute F5 para recalcular.');return
        case=self.case_var.get()
        analysis=res['analyses'].get(case)
        if not analysis:return
        group=self.group_filter.get();typ=self.critical_filter.get()
        members=self.session.model.members
        data=[(m,analysis['axial_n'].get(m.id,0)/1000) for m in members]
        if group!='Todos':data=[x for x in data if x[0].group==group]
        if typ=='Tração':data=[x for x in data if x[1]>0]
        if typ=='Compressão':data=[x for x in data if x[1]<0]
        data.sort(key=lambda x:-abs(x[1]))
        if typ=='Críticas 15':data=data[:15]
        for m,value in data:
            tree.insert('','end',iid=m.id,values=(m.id,m.group,f'{value:+.2f}'))
        self.result_summary.configure(text=f"Caso {case}  ·  {len(data)} barras  ·  Flecha máx. {analysis['max_abs_roof_mm']:.2f} mm  ·  Massa {self.session.model.mass_kg():.1f} kg.\nELU resistente NÃO verificado.")

    def _on_case(self):
        cid=self.case_var.get()
        if hasattr(self,'_load_case_ids') and cid in self._load_case_ids:
            idx=self._load_case_ids.index(cid)
            if self.load_cases_list.curselection()!=(idx,):
                self.load_cases_list.selection_clear(0,'end')
                self.load_cases_list.selection_set(idx)
        self.viewport.case_id.set(cid);self.viewport.refresh();self._populate_results()

    def _tree_select(self,e):
        sel=self.tree.selection()
        if not sel:return
        iid=sel[0]
        if '|' in iid:
            kind,key=iid.split('|',1)
            self.viewport.set_selection(kind,key)
            self._selected=(kind,key)
            self._update_property()

    def _result_select(self,e):
        chosen=self.results_table.selection()
        if chosen:self.viewport.set_selection('member',chosen[0]);self._on_select('member',chosen[0])

    def _on_select(self,kind,key):
        self._selected=(kind,key)
        self._update_property()
        if kind and key:
            iid=f'{kind}|{key}'
            if self.tree.exists(iid):
                self.tree.selection_set(iid);self.tree.see(iid)
            if kind=='member' and self.results_table.exists(key):self.results_table.selection_set(key)

    def _update_property(self):
        kind,key=self._selected
        model=self.session.model
        if kind=='node' and key in model.node_map():
            n=model.node_map()[key]
            self.prop_title.configure(text=f'NÓ  {key}')
            description=f'Coordenadas globais. Modelo plano, DOFs UX e UY.\nX={n.x/1000:.5f} m  ·  Y={n.y/1000:.5f} m'
            if self.session.result:
                a=self.session.result['analyses'].get(self.case_var.get())
                if a:
                    disp=a['nodal_displacements'].get(key,{})
                    reaction=a['reactions'].get(key,{})
                    description+=(f"\n\nDeslocamento: UX={disp.get('ux_mm',0):+.3f} mm | UY={disp.get('uy_mm',0):+.3f} mm"
                                  f"\nReações: RX={reaction.get('fx_n',0)/1000:+.3f} kN | RY={reaction.get('fy_n',0)/1000:+.3f} kN")
            self.prop_desc.configure(text=description)
            self.node_x.set(f'{n.x:.2f}');self.node_y.set(f'{n.y:.2f}')
            ux,uy=model.supports.get(key,(False,False));self.ux.set(ux);self.uy.set(uy)
        elif kind=='member':
            m=next((m for m in model.members if m.id==key),None)
            if m:
                self.prop_title.configure(text=f'BARRA  {m.id}  /  {m.group.upper()}')
                val=''
                if self.session.result:
                    ana=self.session.result['analyses'].get(self.case_var.get())
                    if ana:val=f"\nNormal: {ana['axial_n'][m.id]/1000:+.3f} kN"
                self.prop_desc.configure(text=f'Nós {m.i}—{m.j}\nPerfil: {m.profile}\nComprimento: {model.member_length(m)/1000:.3f} m\nÁrea: {m.area:.1f} mm²{val}\nSem verificação ELU.')
        else:
            self.prop_title.configure(text='PROJETO  /  SELEÇÃO')
            self.prop_desc.configure(text='Clique em um nó ou barra no desenho para editar ou inspecionar os dados.')

    def _capture(self):
        self._history.append(deepcopy(self.session.project))
        self._history=self._history[-40:]
        self._future.clear()

    def _mutate(self,callback,label='Modelo atualizado',fit=False):
        previous=deepcopy(self.session.project)
        try:callback()
        except Exception as exc:
            messagebox.showerror('Entrada inválida',str(exc),parent=self)
            self._set_status('Operação não realizada: '+str(exc))
            return False
        self._history.append(previous);self._history=self._history[-40:];self._future.clear()
        self._dirty=True;self._refresh_all(fit=fit);self._set_status(label+'  ·  Execute F5 para recalcular.')
        return True

    def _schedule_geometry(self,*args):
        if self._loading:return
        if self._geometry_job:self.after_cancel(self._geometry_job)
        self._geometry_job=self.after(450,self._auto_geometry)

    def _auto_geometry(self):
        self._geometry_job=None
        self.apply_geometry(silent=True)

    def apply_geometry(self,silent=False):
        try:
            g=deepcopy(self.session.project.get('geometry',{}))
            for k in ('span_m','frame_spacing_m','height_m','rise_m'):
                g[k]=float(self.geom_vars[k].get().strip().replace(',','.'))
            g['panels']=int(self.geom_vars['panels'].get().strip())
            g['roof_shape']=SHAPES[self.geom_vars['roof_shape'].get()]
            g['truss_type']=self.geom_vars['truss_type'].get()
            p=deepcopy(self.session.project)
            panels_changed=g['panels']!=p['geometry']['panels']
            if panels_changed and not silent and (p.get('node_edits') or p.get('supports')):
                if not messagebox.askyesno('Nova topologia','O número de painéis mudou. Descartar coordenadas de nós e apoios personalizados?',parent=self):return
            if panels_changed:
                p.pop('node_edits',None);p.pop('supports',None)
            p['geometry']=g
            if p==self.session.project:
                self.model_error.configure(text='');return
            if silent:
                previous=deepcopy(self.session.project)
                self.session.update_project(p)
                self._history.append(previous);self._history=self._history[-40:];self._future.clear()
                self._dirty=True;self._refresh_all(fit=True)
            else:self._mutate(lambda:self.session.update_project(p),'Geometria paramétrica atualizada',fit=True)
            self.model_error.configure(text='')
        except Exception as exc:
            self.model_error.configure(text=str(exc))
            if not silent:messagebox.showerror('Geometria inválida',str(exc),parent=self)

    def clear_node_edits(self):
        def f():
            p=deepcopy(self.session.project);p.pop('node_edits',None);self.session.update_project(p)
        self._mutate(f,'Edições locais de nós limpas',fit=True)

    def _move_node(self,node,x,y):
        self._mutate(lambda:self.session.set_node(node,round(x,2),round(y,2)),f'Nó {node} deslocado')

    def apply_node(self):
        kind,node=self._selected
        if kind!='node':return self._set_status('Selecione um nó antes de editar coordenadas.')
        try:x=float(self.node_x.get().replace(',','.'));y=float(self.node_y.get().replace(',','.'))
        except ValueError:return messagebox.showerror('Coordenadas','Forneça valores numéricos.',parent=self)
        self._mutate(lambda:self.session.set_node(node,x,y),f'Coordenadas de {node} atualizadas')

    def apply_support(self):
        kind,node=self._selected
        if kind!='node':return self._set_status('Selecione um nó para definir o vínculo.')
        self._mutate(lambda:self.session.set_support(node,self.ux.get(),self.uy.get()),f'Apoio de {node} atualizado')

    def apply_profiles(self):
        def f():
            p=deepcopy(self.session.project)
            for group in self.profile_vars:
                p['sections'][group]={'profile':self.profile_vars[group].get(),'count':int(self.count_vars[group].get())}
            self.session.update_project(p)
        self._mutate(f,'Seções atualizadas')

    def _toggle_edit(self):
        self.viewport.edit_nodes.set(not self.viewport.edit_nodes.get())
        self._set_status('EDIÇÃO DE NÓS ATIVA: arraste um nó para atualizar as coordenadas.' if self.viewport.edit_nodes.get() else 'Edição de nós desativada.')

    def _toggle_forces(self):self.viewport.show_forces.set(not self.viewport.show_forces.get());self.viewport.refresh()
    def _toggle_ids(self):self.viewport.show_nodes.set(not self.viewport.show_nodes.get());self.viewport.refresh()
    def _toggle_efforts(self):self.viewport.show_efforts.set(not self.viewport.show_efforts.get());self.viewport.refresh()
    def _toggle_def(self):self.viewport.show_deformed.set(not self.viewport.show_deformed.get());self.viewport.refresh()
    def _fit(self):self.viewport.fit()

    def _set_vertical(self,value):
        self.viewport.vertical_factor.set(float(value))
        self.viewport.fit()
        self._set_status(f'Exagero vertical ×{value} aplicado apenas à visualização; coordenadas e cálculo preservados.')

    def apply_load_case(self):
        cid=self._chosen_case_id()
        if not cid:return
        def apply():
            p=deepcopy(self.session.project)
            c=next(x for x in p['load_cases'] if x['id']==cid)
            if c['kind'] not in ('surface','line'):raise ValueError('Este tipo de caso não é editável aqui')
            c['value']=float(self.surface_vars['value'].get().replace(',','.'))
            for k in ('force_unit','direction','application','basis','zone'):
                c[k]=self.surface_vars[k].get()
            self.session.update_project(p)
        self._mutate(apply,f'Caso {cid} atualizado')

    def add_nodal_case(self):
        cid=simpledialog.askstring('Novo caso nodal','Identificador do novo caso (ex.: P_NOD):',parent=self)
        if not cid:return
        if self._mutate(lambda:self.session.add_nodal_case(cid),'Caso nodal criado'):
            self._show_inspector('Cargas')
            if cid in self._load_case_ids:
                i=self._load_case_ids.index(cid);self.load_cases_list.selection_clear(0,'end');self.load_cases_list.selection_set(i);self._show_case_loads()

    def _open_load_editor(self,case_id,node_id,index=None):
        dlg=tk.Toplevel(self);dlg.title('Força nodal  /  '+case_id)
        dlg.transient(self);dlg.grab_set();dlg.resizable(False,False);dlg.configure(bg='white')
        dlg.geometry('370x290')
        case=next(c for c in self.session.project['load_cases'] if c['id']==case_id)
        existing=case['loads'][index] if index is not None else {}
        node=tk.StringVar(value=existing.get('node',node_id or ''))
        fx=tk.StringVar(value=str(existing.get('fx',0)))
        fy=tk.StringVar(value=str(existing.get('fy',0)))
        unit=tk.StringVar(value=existing.get('force_unit','kgf'))
        tk.Label(dlg,text=f'Caso: {case_id}',bg='white',fg=NAVY,font=('Segoe UI',11,'bold')).pack(pady=(13,8))
        area=tk.Frame(dlg,bg='white');area.pack(fill='x',padx=20)
        for i,(label,v,choices) in enumerate((('Nó',node,[n.id for n in self.session.model.nodes]),('Fx',fx,None),('Fy',fy,None),('Unidade',unit,['kgf','tf','kN','N']))):
            tk.Label(area,text=label,bg='white',fg=MUTED).grid(row=i,column=0,sticky='w',pady=6)
            if choices:w=ttk.Combobox(area,textvariable=v,values=choices,state='readonly',width=23)
            else:w=ttk.Entry(area,textvariable=v,width=24)
            w.grid(row=i,column=1,padx=8,pady=6)
        def confirm():
            try:
                xv=float(fx.get().replace(',','.'));yv=float(fy.get().replace(',','.'))
                ok=self._mutate(lambda:self.session.set_nodal_load(case_id,node.get(),xv,yv,unit.get(),index),f'Força em {node.get()} registrada')
                if ok:dlg.destroy();self._show_inspector('Cargas')
            except Exception as exc:messagebox.showerror('Erro',str(exc),parent=dlg)
        ttk.Button(dlg,text='Aplicar força nodal',command=confirm,style='Primary.TButton').pack(fill='x',padx=22,pady=11)
        dlg.wait_visibility();dlg.focus_force()

    def add_load(self):
        cid=self._chosen_case_id()
        if not cid or not any(c['id']==cid and c['kind']=='nodal' for c in self.session.project['load_cases']):
            messagebox.showinfo('Cargas nodais','Crie ou selecione um caso do tipo nodal primeiro.',parent=self)
            self._show_inspector('Cargas');return
        node=self._selected[1] if self._selected[0]=='node' else self.session.model.nodes[0].id
        self._open_load_editor(cid,node)

    def edit_load(self):
        cid=self._chosen_case_id();sel=self.load_table.selection()
        if not sel or not cid:return
        index=int(sel[0])
        case=next(c for c in self.session.project['load_cases'] if c['id']==cid)
        if case['kind']=='nodal':self._open_load_editor(cid,case['loads'][index]['node'],index)

    def delete_load(self):
        cid=self._chosen_case_id();sel=self.load_table.selection()
        if not cid or not sel:return
        self._mutate(lambda:self.session.delete_nodal_load(cid,int(sel[0])),'Força nodal excluída')

    def calculate(self):
        try:
            self.session.calculate()
        except Exception as exc:
            self._set_status('Falha na análise: '+str(exc))
            return messagebox.showerror('Análise estrutural interrompida',str(exc),parent=self)
        self._refresh_all()
        ana=self.session.result['analyses'].get(self.case_var.get())
        if ana:
            r=ana['equilibrium'];self._set_status(f"ANÁLISE CONCLUÍDA · ΣFx={r['sum_fx_n']:.3g} N · ΣFy={r['sum_fy_n']:.3g} N · ΣM={r['sum_m_nmm']:.3g} Nmm · SEM VERIFICAÇÃO ELU")
        self._show_inspector('Resultados')

    def undo(self):
        if not self._history:return
        self._future.append(deepcopy(self.session.project))
        item=self._history.pop()
        try:self.session.update_project(item)
        except Exception as exc:return messagebox.showerror('Desfazer',str(exc),parent=self)
        self._dirty=True;self._selected=(None,None);self._refresh_all(fit=True)

    def redo(self):
        if not self._future:return
        self._history.append(deepcopy(self.session.project))
        item=self._future.pop()
        try:self.session.update_project(item)
        except Exception as exc:return messagebox.showerror('Refazer',str(exc),parent=self)
        self._dirty=True;self._selected=(None,None);self._refresh_all(fit=True)

    def _ask_discard(self):
        if self._dirty:return messagebox.askyesnocancel('Alterações não salvas','Deseja salvar o projeto antes de continuar?',parent=self)
        return False

    def new_file(self):
        answer=self._ask_discard()
        if answer is None:return
        if answer and not self.save():return
        self.session=Session(catalog=self.session.catalog)
        self.viewport.session=self.session;self._history=[];self._future=[];self._dirty=False;self._file=None;self._selected=(None,None)
        self._refresh_all(fit=True)

    def open_file(self):
        answer=self._ask_discard()
        if answer is None:return
        if answer and not self.save():return
        name=filedialog.askopenfilename(parent=self,title='Abrir projeto 2DTruss',filetypes=[('Projetos JSON','*.json')])
        if not name:return
        try:self.session=Session(project=load_project(name),catalog=self.session.catalog)
        except Exception as exc:return messagebox.showerror('Projeto inválido',str(exc),parent=self)
        self.viewport.session=self.session;self._file=name;self._dirty=False;self._history=[];self._future=[];self._selected=(None,None)
        self._refresh_all(fit=True);self._set_status('Projeto aberto: '+name)

    def save(self):
        if not self._file:return self.save_as()
        try:write_project(self._file,self.session.project)
        except Exception as exc:
            messagebox.showerror('Falha ao salvar',str(exc),parent=self);return False
        self._dirty=False;self._refresh_all();self._set_status('Projeto salvo: '+self._file)
        return True

    def save_as(self):
        name=filedialog.asksaveasfilename(parent=self,title='Salvar projeto',defaultextension='.json',filetypes=[('Projeto JSON','*.json')],initialfile='2DTruss_Projeto.json')
        if not name:return False
        self._file=name;return self.save()

    def _ensure_result(self):
        if self.session.result is None:
            messagebox.showwarning('Cálculo pendente','Execute F5 para calcular antes de exportar.',parent=self);return False
        return True

    def export_dimperfil(self):
        if not self._ensure_result():return
        name=filedialog.asksaveasfilename(parent=self,defaultextension='.csv',filetypes=[('CSV','*.csv')],initialfile='2DTruss_DimPerfil.csv')
        if name:
            try:Path(name).write_text(as_csv(dimperfil_rows(self.session.result)),encoding='utf-8-sig');self._set_status('DimPerfil CSV exportado')
            except Exception as exc:messagebox.showerror('Exportação',str(exc),parent=self)

    def export_results(self):
        if not self._ensure_result():return
        name=filedialog.asksaveasfilename(parent=self,defaultextension='.json',filetypes=[('JSON','*.json')],initialfile='2DTruss_Analise.json')
        if name:
            try:Path(name).write_text(json.dumps(self.session.result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');self._set_status('Resultados JSON exportados')
            except Exception as exc:messagebox.showerror('Exportação',str(exc),parent=self)

    def export_memorial(self):
        if not self._ensure_result():return
        name=filedialog.asksaveasfilename(parent=self,defaultextension='.html',filetypes=[('HTML A3','*.html')],initialfile='2DTruss_Memorial_A3.html')
        if name:
            try:Path(name).write_text(report_html(self.session.result,self.session.project,self.case_var.get()),encoding='utf-8');self._set_status('Memorial HTML gerado. Não abre navegador automaticamente.')
            except Exception as exc:messagebox.showerror('Memorial',str(exc),parent=self)

    def destroy(self):
        for job in (getattr(self,'_geometry_job',None),getattr(self,'_sash_job',None)):
            if job:
                try:self.after_cancel(job)
                except tk.TclError:pass
        super().destroy()

    def _on_close(self):
        answer=self._ask_discard()
        if answer is None:return
        if answer and not self.save():return
        self.destroy()


def main():
    app=App();app.mainloop()

if __name__=='__main__':main()
