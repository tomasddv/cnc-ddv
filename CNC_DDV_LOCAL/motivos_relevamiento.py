"""Filtrar el plan de acción por el motivo reportado por los promotores.

No mezclar con BEES Force ni con el motivo escrito manualmente en el plan.
"""
from __future__ import annotations
import pandas as pd

MOTIVOS_PROMOTOR = (
    'Sin dinero',
    'Cerrado',
    'Compra en súper/mayorista',
    'Otro',
)


def filtrar_motivo_promotor(casos: pd.DataFrame, motivo: str) -> pd.DataFrame:
    """Devuelve sólo casos del motivo; vacío => sin respuesta en campaña.

    Mantiene el índice para que el dataframe de Streamlit coincida con los
    registros que se envían al guardado masivo. No cambia el dataframe origen.
    """
    if motivo == 'Todos':
        return casos.copy()
    if motivo not in (*MOTIVOS_PROMOTOR, 'Sin relevar'):
        raise ValueError('Motivo de promotor no reconocido: '+str(motivo))
    if 'motivo_relevamiento' not in casos:
        razones=pd.Series('',index=casos.index,dtype='string')
    else:
        razones=casos['motivo_relevamiento'].fillna('').astype(str).str.strip()
    mask=razones.eq('') if motivo == 'Sin relevar' else razones.eq(motivo)
    return casos.loc[mask].copy()
