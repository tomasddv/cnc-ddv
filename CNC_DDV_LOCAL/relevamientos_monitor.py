"""Monitoreo de respuestas de promotores: cliente único/mes, no suma CZA y UNG.

Separado de BEES Force: relevamientos simples de la campaña, no evidencia
oficial de BEES Force ni visita/gestión de contacto U12M.
"""
from __future__ import annotations
from collections import defaultdict
import pandas as pd


def resumen_relevamientos(rows, supervisor='Todos', promotor='Todos', negocio='Todos'):
    """Filtra registros de campaña y cuenta cada cliente una sola vez.

    Un cliente se considera relevado cuando todos los negocios incluidos en
    el filtro tienen respuesta. Al filtrar CZA/UNG, solo se exige ese negocio.
    El resumen no confunde clientes y casos por negocio.
    """
    negocio={'NABS':'UNG','NABs':'UNG'}.get(negocio,negocio)
    groups={}
    for r in rows:
        if supervisor!='Todos' and r.get('supervisor')!=supervisor: continue
        if promotor!='Todos' and r.get('promotor')!=promotor: continue
        if negocio not in ('Todos',r.get('negocio')): continue
        key=(r['promotor'],str(r['cliente']))
        g=groups.setdefault(key, {'promotor':r['promotor'], 'supervisor':r.get('supervisor',''),
            'cliente':str(r['cliente']), 'fantasia':r.get('fantasia',''),
            'razon_social':r.get('razon_social',''), 'negocios':set(), 'respondidos_negocios':0,
            'motivo':'','comentario':'','fecha':''})
        g['negocios'].add(r['negocio'])
        if str(r.get('motivo') or '').strip():
            g['respondidos_negocios']+=1
            if str(r.get('respondido') or '') >= g['fecha']:
                g['motivo']=r['motivo'];g['comentario']=r.get('comentario') or ''
                g['fecha']=r.get('respondido') or ''
    summary=defaultdict(lambda:{'asignados':0,'respondidos':0,'pendientes':0,'casos_cza':0,'casos_ung':0})
    detail=[]
    for x in groups.values():
        complete=x['respondidos_negocios']==len(x['negocios'])
        pr=x['promotor'];v=summary[pr]
        v['asignados']+=1
        v['respondidos']+=int(complete)
        v['pendientes']+=int(not complete)
        v['casos_cza']+=int('CZA' in x['negocios'])
        v['casos_ung']+=int('UNG' in x['negocios'])
        detail.append({'promotor':pr,'supervisor':x['supervisor'],'cliente':x['cliente'],
            'fantasia':x['fantasia'],'razon_social':x['razon_social'],
            'negocios':' + '.join(sorted(x['negocios'])),
            'estado':'Respondido' if complete else 'Pendiente',
            'motivo':x['motivo'] if complete else '',
            'comentario':x['comentario'] if complete else '',
            'fecha_respuesta':x['fecha'] if complete else ''})
    result=[]
    for pr,v in summary.items():
        x={**v,'promotor':pr}
        matches=[y['supervisor'] for y in detail if y['promotor']==pr]
        x['supervisor']=matches[0] if matches else ''
        x['avance_pct']=round(100*v['respondidos']/v['asignados'],1) if v['asignados'] else 0
        x['alerta']=f'Faltan {v["pendientes"]}' if v['pendientes'] else 'Al día'
        result.append(x)
    return (pd.DataFrame(sorted(result,key=lambda x:(-x['pendientes'],x['promotor']))),
            pd.DataFrame(sorted(detail,key=lambda x:(x['promotor'],x['estado']!='Pendiente',x['fantasia']))))


def validar_sincronizacion(casos, mes):
    """Construye SOLO CNC U3M elegibles, CZA y UNG, evitando otros negocios.
    No toma el selector lateral: quien importa debe pasar un universo completo.
    """
    from store import preparar_csv
    import io
    v=casos.loc[casos['cnc_u3m'] & casos['negocio'].isin(['CZA','NABS'])].copy()
    if v.empty:
        return []
    v['periodo']=mes
    v['negocio']=v['negocio'].replace({'NABS':'UNG'})
    v['licencia_alcohol']=v['licencia_alcohol'].astype(str)
    v['cnc_u3m']='SI'
    v['ultima_compra']=v['ultima_compra'].fillna('').astype(str)
    v['alta']=pd.to_datetime(v['alta'],errors='coerce').dt.strftime('%Y-%m-%d').fillna('')
    cols=['periodo','cliente','negocio','promotor','supervisor_asignado','fantasia',
          'razon_social','ultima_compra','licencia_alcohol','cnc_u3m','alta']
    return preparar_csv(v[cols].to_csv(index=False))
