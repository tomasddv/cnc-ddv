"""Lectura mínima autenticada de CSV.gz privados de Google Drive."""
from __future__ import annotations
from io import BytesIO
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

SCOPES=['https://www.googleapis.com/auth/drive.readonly','https://www.googleapis.com/auth/spreadsheets']

def credenciales(info):
    return service_account.Credentials.from_service_account_info(dict(info),scopes=SCOPES)

def descargar_bytes(creds,file_id):
    ses=AuthorizedSession(creds)
    resp=ses.get('https://www.googleapis.com/drive/v3/files/'+file_id,params={'alt':'media'},timeout=90)
    resp.raise_for_status();return BytesIO(resp.content)
