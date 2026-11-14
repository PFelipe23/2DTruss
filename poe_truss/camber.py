"""v0.1 — geometria de contraflecha preliminar a partir de deformação ELS.

Este módulo NÃO reanalisa uma geometria pré-deformada e NÃO determina
comprimentos de fabricação ou esforços de montagem. Devolve apenas posições
nominais ajustadas em Y e um prognóstico linear de deslocamento residual.
"""
from __future__ import annotations
from math import isfinite


def suggested_camber(project:dict, model:dict, analyses:dict)->dict:
    opts=project.get('camber',{}) or {}
    if not isinstance(opts,dict):raise ValueError('camber deve ser objeto')
    case=str(opts.get('reference_case','G1'))
    factor=float(opts.get('compensation_fraction',1.0))
    if not isfinite(factor) or factor<0 or factor>1.5:
        raise ValueError('camber.compensation_fraction deve estar entre 0 e 1,5')
    if case not in analyses:
        return {'state':'PENDENTE_CASO_REFERENCIA','reference_case':case,
                'warning':'Sem caso de referência; nenhuma geometria de contraflecha foi gerada.', 'nodes':[]}
    nodes=model['nodes']; u=analyses[case]['nodal_displacements']
    roof=sorted((n for n in nodes if n['id'].startswith('T')),key=lambda n:n['x_mm'])
    if len(roof)<2:
        return {'state':'NAO_SUPORTADO_GEOMETRIA_EXPLICITA','reference_case':case,'nodes':[],
                'warning':'Apenas treliças paramétricas com nós de banzo superior Txx são aceitas.'}
    xs=[n['x_mm'] for n in roof]
    if any(b<=a for a,b in zip(xs,xs[1:])):
        raise ValueError('Banzo superior com abscissas inválidas')
    ys=[u[n['id']]['uy_mm'] for n in roof]
    # Remove reta de deslocamentos dos nós extremos (referência entre extremos).
    ys_rel=[y-(ys[0]+(ys[-1]-ys[0])*(x-xs[0])/(xs[-1]-xs[0])) for x,y in zip(xs,ys)]
    def offset(x):
        for i in range(len(xs)-1):
            if xs[i]<=x<=xs[i+1]:
                r=(x-xs[i])/(xs[i+1]-xs[i]);return -factor*(ys_rel[i]*(1-r)+ys_rel[i+1]*r)
        return 0.0
    out=[{'node_id':n['id'],'x_mm':n['x_mm'],'y_original_mm':n['y_mm'],
          'camber_y_mm':offset(n['x_mm']),'y_fabrication_illustrative_mm':n['y_mm']+offset(n['x_mm'])}
         for n in nodes]
    return {'state':'GEOMETRIA_PRELIMINAR_NAO_CONSTRUTIVA','reference_case':case,
            'compensation_fraction':factor,'max_abs_camber_mm':max(abs(x['camber_y_mm']) for x in out),
            'nodes':out,'warning':'Previsão linear de contraflecha. Não recalcula geometria resistente, comprimentos de fabricação, forças de montagem ou ELS residual sob outros casos.'}
