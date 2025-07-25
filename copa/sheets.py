#copa/sheets.py
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Registro JETACUP 2"  # Cambia por el nombre real

EXPECTED_HEADERS = [
    "Discord ID", "Nick", "Nombre", "Tag", "PUUID", "ELO", "Región", "Roles preferidos" ,
    "¿Juega con desconocidos?", "Amigo preferido", "Disponibilidad"
]

def get_sheet():
    cred_path = os.getenv("CREDENTIALS_PATH", os.path.join("secrets", "credentials.json"))
    creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, SCOPE)  # type: ignore
    client = gspread.authorize(creds)  # type: ignore
    sheet = client.open(SHEET_NAME).sheet1

    current_headers = sheet.row_values(1)

    # Si la fila 1 está vacía o no coincide con los encabezados esperados, los reemplaza
    if current_headers != EXPECTED_HEADERS:
        # Borra la fila 1 para limpiar (opcional)
        sheet.delete_rows(1)
        # Inserta la fila con encabezados
        sheet.insert_row(EXPECTED_HEADERS, 1)

    return sheet


#CREDENTIALS_PATH=/etc/secrets/credentials.json EN RENDER!!!!!!!