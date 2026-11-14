"""Fachada fina: interface nativa / núcleo Python auditável da v0.1."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import json
from math import isfinite
from poe_truss.catalog import load_catalog
from poe_truss.engine import run_project
from poe_truss.model import make_model
from poe_truss.loads import build_case_loads, merge_forces

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / 'examples' / 'cobertura_duas_aguas.json'
CATALOG = ROOT / 'catalogo_perfis.csv'


def load_project(path: Path|str = DEFAULT) -> dict:
    obj = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(obj, dict): raise ValueError('Projeto JSON deve conter objeto raiz')
    if obj.get('schema') != 'poe-truss-python/v1': raise ValueError('Schema de projeto não suportado')
    return obj


def write_project(path: Path|str, project: dict) -> None:
    p=Path(path)
    temp=p.with_name(p.name+'.tmp')
    temp.write_text(json.dumps(project,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temp.replace(p)


class Session:
    def __init__(self, project=None, catalog=None):
        self.catalog=catalog or load_catalog(CATALOG)
        self.project=deepcopy(project if project is not None else load_project())
        self.model=None
        self.result=None
        self.revision=0
        self.calculated_revision=-1
        self.update_preview()

    def update_preview(self):
        self.model=make_model(self.project,self.catalog)
        self.revision+=1
        self.result=None
        return self.model

    def calculate(self):
        self.result=run_project(self.project,self.catalog)
        self.calculated_revision=self.revision
        return self.result

    def update_project(self, obj):
        before=self.project
        self.project=deepcopy(obj)
        try: self.update_preview()
        except Exception:
            self.project=before
            raise

    def set_node(self, node_id: str, x_mm:float, y_mm:float):
        if not all(isfinite(float(v)) for v in (x_mm,y_mm)):
            raise ValueError('Coordenadas inválidas')
        p=deepcopy(self.project)
        if 'model_override' in p:
            rows=p['model_override']['nodes']
            item=next((n for n in rows if n['id']==node_id),None)
            if item is None:raise ValueError('Nó inexistente no modelo explícito')
            item['x_mm']=float(x_mm);item['y_mm']=float(y_mm)
        else:
            p.setdefault('node_edits',{})[node_id]={'x_mm':float(x_mm),'y_mm':float(y_mm)}
        self.update_project(p)

    def set_support(self, node_id: str, ux:bool, uy:bool):
        if node_id not in {n.id for n in self.model.nodes}:
            raise ValueError('Nó inexistente')
        p=deepcopy(self.project)
        target=p['model_override'] if 'model_override' in p else p
        supports=target.get('supports')
        if supports is None:
            supports=[{'node':id,'ux':ux,'uy':uy} for id,(ux,uy) in self.model.supports.items()]
        supports=[s for s in supports if s['node']!=node_id]
        if ux or uy: supports.append({'node':node_id,'ux':bool(ux),'uy':bool(uy)})
        target['supports']=supports
        self.update_project(p)

    def nodal_cases(self):
        return [x for x in self.project.get('load_cases',[]) if x.get('kind')=='nodal']

    def add_nodal_case(self, case_id:str):
        case_id=case_id.strip()
        if not case_id or len(case_id)>32 or not case_id.replace('_','').isalnum():
            raise ValueError('ID do caso deve ser alfanumérico, até 32 caracteres')
        if case_id in {c['id'] for c in self.project.get('load_cases',[])}:
            raise ValueError('ID já utilizado')
        p=deepcopy(self.project)
        p.setdefault('load_cases',[]).append({'id':case_id,'name':case_id,'kind':'nodal','loads':[]})
        self.update_project(p)

    def set_nodal_load(self, case_id:str, node_id:str, fx:float, fy:float, force_unit='kgf', index=None):
        if node_id not in {n.id for n in self.model.nodes}: raise ValueError('Nó inexistente')
        if force_unit not in ('kgf','tf','kN','N'): raise ValueError('Unidade inválida')
        if not all(isfinite(float(v)) for v in (fx,fy)): raise ValueError('Força inválida')
        p=deepcopy(self.project)
        case=next((x for x in p['load_cases'] if x['id']==case_id),None)
        if case is None or case['kind']!='nodal': raise ValueError('Caso nodal não encontrado')
        row={'node':node_id,'fx':float(fx),'fy':float(fy),'force_unit':force_unit}
        if index is None:case.setdefault('loads',[]).append(row)
        elif 0<=index<len(case['loads']):case['loads'][index]=row
        else: raise IndexError('Índice da força nodal inexistente')
        self.update_project(p)

    def delete_nodal_load(self,case_id,index:int):
        p=deepcopy(self.project)
        case=next((x for x in p['load_cases'] if x['id']==case_id and x['kind']=='nodal'),None)
        if case is None: raise ValueError('Caso nodal inexistente')
        del case['loads'][index]
        self.update_project(p)

    def forces_for_case(self, case_id:str):
        raw={}
        for c in self.project.get('load_cases',[]):
            if c['kind']=='nodal' and not c.get('loads'):
                raw[c['id']]={}
            else:raw[c['id']]=build_case_loads(self.model,c)[0]
        if case_id in raw:return raw[case_id]
        comb=next((c for c in self.project.get('combinations',[]) if c['id']==case_id),None)
        if comb:return merge_forces(comb['factors'],raw)
        return {}
