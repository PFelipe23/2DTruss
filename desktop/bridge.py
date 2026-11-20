"""Fachada fina: interface nativa / núcleo Python auditável da v0.1."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import json
from math import isfinite
from poe_truss.catalog import load_catalog
from poe_truss.engine import run_project
from poe_truss.model import make_model
from poe_truss.loads import load_patterns, merge_forces, resolve_case_loads
from .editing import review_nodal_restraints
from .workflow import add_load_case, update_nodal_loads

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
        original = self.model.node_map().get(node_id)
        if original is not None and (original.x, original.y) != (float(x_mm), float(y_mm)):
            review_nodal_restraints(p)
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
        return [pattern for pattern in load_patterns(self.project) if pattern['kind'] == 'nodal']

    def add_nodal_case(self, case_id:str):
        self.update_project(add_load_case(self.project, case_id, 'nodal'))

    def set_nodal_load(self, case_id:str, node_id:str, fx:float, fy:float, force_unit='kgf', index=None):
        self.update_project(update_nodal_loads(
            self.project, self.model, case_id, [node_id], float(fx), float(fy), force_unit, index,
        ))

    def delete_nodal_load(self,case_id,index:int):
        p=deepcopy(self.project)
        case=next((x for x in load_patterns(p) if x['id']==case_id and x['kind']=='nodal'),None)
        if case is None: raise ValueError('Caso nodal inexistente')
        del case['loads'][index]
        self.update_project(p)

    def forces_for_case(self, case_id:str):
        cases = {case['id']: case for case in self.project.get('load_cases', [])}
        patterns = {pattern['id']: pattern for pattern in load_patterns(self.project)}
        cache = {}

        def nodal_forces(case):
            return resolve_case_loads(self.model, case, patterns, preview=True, cache=cache)[0]

        source = cases.get(case_id) or patterns.get(case_id)
        if source is not None:
            if source['kind'] == 'nodal' and not source.get('loads'):
                return {}
            return nodal_forces(source)
        combination = next((entry for entry in self.project.get('combinations', [])
                            if entry['id'] == case_id), None)
        if combination and combination['factors']:
            factors = combination['factors']
            raw = {key: nodal_forces(cases[key]) for key in factors if key in cases}
            return merge_forces(factors, raw)
        return {}
