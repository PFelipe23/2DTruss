"""Elementos axiais de treliça plana por rigidez direta (sem numpy).

Convenção: N > 0 tração; N < 0 compressão.
Restrições por nó e grau de liberdade, sem assumir localização dos apoios.
"""
from __future__ import annotations
from dataclasses import replace
from itertools import combinations
from math import hypot, isfinite
from .model import Model

class StabilityError(ValueError):
    pass


class LU:
    """Fatoração LU de matriz real com pivoteamento parcial; sem dependências."""
    def __init__(self, matrix:list[list[float]]):
        n=len(matrix)
        self.a=[row[:] for row in matrix]
        self.n=n
        self.piv=list(range(n))
        scale=max([max((abs(x) for x in row), default=0) for row in matrix],default=0)
        if scale<=0:raise StabilityError('Matriz de rigidez nula; apoios/membros insuficientes')
        self.threshold=scale*1e-12
        self.pivot_sizes=[]
        for k in range(n):
            pivot=max(range(k,n),key=lambda r:abs(self.a[r][k]))
            if abs(self.a[pivot][k])<self.threshold:
                raise StabilityError('Matriz de rigidez singular ou quase singular: verifique apoios, mecanismos e barras')
            if pivot!=k:
                self.a[k],self.a[pivot]=self.a[pivot],self.a[k]
                self.piv[k],self.piv[pivot]=self.piv[pivot],self.piv[k]
            self.pivot_sizes.append(abs(self.a[k][k]))
            for r in range(k+1,n):
                self.a[r][k]/=self.a[k][k]
                val=self.a[r][k]
                for c in range(k+1,n):self.a[r][c]-=val*self.a[k][c]

    def solve(self,b:list[float])->list[float]:
        if len(b)!=self.n:raise ValueError('Dimensão do vetor de carregamento incompatível')
        y=[b[self.piv[i]] for i in range(self.n)]
        for i in range(self.n):
            for j in range(i):y[i]-=self.a[i][j]*y[j]
        x=y[:]
        for i in range(self.n-1,-1,-1):
            for j in range(i+1,self.n):x[i]-=self.a[i][j]*x[j]
            x[i]/=self.a[i][i]
        return x


class LinearTruss:
    def __init__(self,model:Model, E_mpa:float):
        self.model=model
        self.ties = tuple(m.id for m in model.members if m.tension_only)
        if len(self.ties) > 12:
            raise ValueError('A análise unilateral aceita até 12 barras somente à tração por plano.')
        self.E=float(E_mpa)
        if not isfinite(self.E) or self.E<=0:raise ValueError('Módulo de elasticidade inválido')
        self.ids=[n.id for n in model.nodes]
        self.index={name:i for i,name in enumerate(self.ids)}
        self.node_map=model.node_map()
        size=len(self.ids)*2
        self.K=[[0.]*size for _ in range(size)]
        self.member_data=[]
        for m in model.members:
            a,b=self.node_map[m.i],self.node_map[m.j]
            L=hypot(b.x-a.x,b.y-a.y)
            c=(b.x-a.x)/L;s=(b.y-a.y)/L
            dofs=[2*self.index[m.i],2*self.index[m.i]+1,2*self.index[m.j],2*self.index[m.j]+1]
            v=[-c,-s,c,s]
            k=self.E*m.area/L
            for i in range(4):
                for j in range(4):self.K[dofs[i]][dofs[j]]+=k*v[i]*v[j]
            self.member_data.append((L,c,s,dofs))
        self.restrained=[]
        for node,(ux,uy) in model.supports.items():
            ix=self.index[node]
            if ux:self.restrained.append(2*ix)
            if uy:self.restrained.append(2*ix+1)
        self.restrained=sorted(self.restrained)
        fixed=set(self.restrained)
        self.free=[i for i in range(size) if i not in fixed]
        if not self.restrained:raise StabilityError('Modelo sem apoios')
        if not self.free:raise ValueError('Todos os graus de liberdade estão restringidos')
        kr=[[self.K[i][j] for j in self.free] for i in self.free]
        self.lu=LU(kr)
        self.pivot_ratio=max(self.lu.pivot_sizes)/min(self.lu.pivot_sizes)

    def analyze(self, loadmap: dict[str, tuple[float, float]]) -> dict:
        result = self._analyze(loadmap)
        if not self.ties:
            return result
        tolerance = 1e-6
        negative = frozenset(key for key in self.ties if result['axial_n'][key] < -tolerance)
        if not negative:
            for key in self.ties:
                result['axial_n'][key] = max(0., result['axial_n'][key])
            return result

        lookup = {member.id: member for member in self.model.members}
        active_sets = (frozenset(inactive) for count in range(1, len(self.ties) + 1)
                       for inactive in combinations(self.ties, count))

        def attempt(inactive):
            members = [replace(m, tension_only=False) for m in self.model.members if m.id not in inactive]
            try:
                trial = LinearTruss(replace(self.model, members=members), self.E)._analyze(loadmap)
            except StabilityError:
                return None
            axial = trial['axial_n']
            active = set(self.ties) - inactive
            if any(axial[key] < -tolerance for key in active):
                return None
            displacements = trial['nodal_displacements']
            for key in inactive:
                member = lookup[key]
                i, j = self.node_map[member.i], self.node_map[member.j]
                ui, uj = displacements[i.id], displacements[j.id]
                dx, dy = j.x - i.x, j.y - i.y
                extension = dx * (uj['ux_mm'] - ui['ux_mm']) + dy * (uj['uy_mm'] - ui['uy_mm'])
                elastic_force = self.E * member.area * extension / (dx * dx + dy * dy)
                if elastic_force > tolerance:
                    return None
            axial.update({key: max(0., axial[key]) for key in active})
            axial.update(dict.fromkeys(inactive, 0.))
            return trial

        result = attempt(negative)
        if result is not None:
            return result
        for inactive in active_sets:
            if inactive != negative and (result := attempt(inactive)) is not None:
                return result
        raise StabilityError('O plano com barras somente à tração não tem solução estável para esta ação.')

    def _analyze(self,loadmap:dict[str,tuple[float,float]])->dict:
        n=len(self.ids)
        F=[0.]*(2*n)
        for name,(fx,fy) in loadmap.items():
            ix=self.index[name];F[2*ix]+=fx;F[2*ix+1]+=fy
        uf=self.lu.solve([F[i] for i in self.free])
        U=[0.]*(2*n)
        for i,v in zip(self.free,uf):U[i]=v
        axial={}
        for m,(L,c,s,dofs) in zip(self.model.members,self.member_data):
            elongation=-c*U[dofs[0]]-s*U[dofs[1]]+c*U[dofs[2]]+s*U[dofs[3]]
            axial[m.id]=self.E*m.area/L*elongation
        reactions={name:{'fx_n':0.,'fy_n':0.} for name in self.ids if name in self.model.supports}
        for i in self.restrained:
            value=sum(self.K[i][j]*U[j] for j in range(len(F)))-F[i]
            key=self.ids[i//2]
            reactions[key]['fx_n' if i%2==0 else 'fy_n']=value
        nd={name:{'ux_mm':U[2*i],'uy_mm':U[2*i+1]} for i,name in enumerate(self.ids)}
        # Resíduos de equilíbrio do sistema global e máximo resíduo nos GDL livres.
        residual=[sum(self.K[i][j]*U[j] for j in range(len(F)))-F[i] for i in range(len(F))]
        max_resid=max((abs(residual[i]) for i in self.free),default=0.)
        rx=sum(v['fx_n'] for v in reactions.values())
        ry=sum(v['fy_n'] for v in reactions.values())
        px=sum(F[0::2]); py=sum(F[1::2])
        # Contribuições de forças e reações para momento em torno da origem global.
        mf=sum(self.node_map[name].x*F[2*i+1]-self.node_map[name].y*F[2*i]
               for i,name in enumerate(self.ids))
        mr=sum(self.node_map[name].x*v['fy_n']-self.node_map[name].y*v['fx_n']
               for name,v in reactions.items())
        roof_nodes=[k for k in self.ids if k.startswith('T')]
        candidates=roof_nodes if roof_nodes else self.ids
        roof_uy=[nd[k]['uy_mm'] for k in candidates]
        max_down=min(0.,min(roof_uy))
        max_up=max(0.,max(roof_uy))
        max_abs_roof=max(roof_uy,key=abs)
        max_abs=max(abs(v['uy_mm']) for v in nd.values())
        return {'nodal_displacements':nd,'axial_n':axial,'reactions':reactions,
                'max_down_roof_mm':max_down,'max_up_roof_mm':max_up,
                'max_abs_roof_mm':max_abs_roof,'max_abs_vertical_mm':max_abs,
                'equilibrium':{'sum_fx_n':px+rx,'sum_fy_n':py+ry,
                               'sum_m_nmm':mf+mr,'max_free_residual_n':max_resid},
                'loads':{node:{'fx_n':v[0],'fy_n':v[1]} for node,v in loadmap.items()},
                'stiffness_pivot_ratio':self.pivot_ratio}
