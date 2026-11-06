"""Sube/actualiza SOLO archivos compactos en una carpeta PRIVADA de Drive.

Uso:
 python scripts/publicar_drive.py --credenciales cuenta.json --carpeta ID_CARPETA
 python scripts/publicar_drive.py --credenciales cuenta.json --carpeta ID --ventas-id ID_EXISTENTE --clientes-id ID_EXISTENTE

No subas los datos a GitHub. Nunca publiques cuenta.json.
"""
import argparse,json
from pathlib import Path
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

FILES={'ventas':'ventas_resumen.csv.gz','clientes':'clientes.csv.gz'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--credenciales',required=True);p.add_argument('--carpeta',required=True)
    p.add_argument('--ventas-id',default='');p.add_argument('--clientes-id',default='')
    args=p.parse_args()
    creds=Credentials.from_service_account_file(args.credenciales,scopes=['https://www.googleapis.com/auth/drive'])
    api=build('drive','v3',credentials=creds,cache_discovery=False)
    for key,name in FILES.items():
        path=Path(__file__).parent.parent/'data'/name
        if not path.exists():raise FileNotFoundError(path)
        media=MediaFileUpload(str(path),mimetype='application/gzip',resumable=False)
        existing=getattr(args,key+'_id')
        if existing:
            result=api.files().update(fileId=existing,media_body=media,fields='id,name').execute()
        else:
            result=api.files().create(body={'name':name,'parents':[args.carpeta]},media_body=media,fields='id,name').execute()
        print(key+'_snapshot_id',result['id'],name)
    print('Completado. Copiá los IDs a los Secrets de Streamlit Cloud.')

if __name__=='__main__':main()
