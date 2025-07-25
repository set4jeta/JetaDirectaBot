# copa/datos.py
from .sheets import get_sheet

def guardar_inscripcion(discord_id, nick, game_name, tag_line, puuid, elo, region, roles, acepta_desconocidos, amigo, disponibilidad):
    sheet = get_sheet()
    registros = sheet.get_all_records()
    for row in registros:
        if str(row.get("Discord ID", "")).strip() == str(discord_id).strip():
            return False, "Ya estás inscrito con esta cuenta de Discord."
        if str(row.get("Nick", "")).strip().lower() == nick.strip().lower():
            return False, "Ese nick ya está en uso."
    sheet.append_row([
        discord_id, nick, game_name, tag_line, puuid, elo, region, roles,
        acepta_desconocidos, amigo, disponibilidad
    ])
    return True, "✅ Registro exitoso. ¡Estás inscrito en la copa!"

def eliminar_inscripcion(discord_id):
    sheet = get_sheet()
    registros = sheet.get_all_records()
    # Busca la fila con ese Discord ID
    for i, row in enumerate(registros, start=2):  # Las filas empiezan en 2 por encabezado
        if str(row.get("Discord ID", "")).strip() == str(discord_id).strip():
            sheet.delete_rows(i)
            return True
    return False

def modificar_inscripcion(discord_id, **kwargs):
    """
    kwargs puede incluir: nick, acepta_desconocidos, amigo, disponibilidad, etc.
    Modifica la fila que corresponda al discord_id con los datos nuevos que se pasen.
    """
    sheet = get_sheet()
    registros = sheet.get_all_records()
    for i, row in enumerate(registros, start=2):
        if str(row.get("Discord ID", "")).strip() == str(discord_id).strip():
            # Actualiza las columnas que se pasan en kwargs
            headers = sheet.row_values(1)
            for key, val in kwargs.items():
                if key in headers:
                    col_idx = headers.index(key) + 1
                    sheet.update_cell(i, col_idx, val)
            return True
    return False





def obtener_inscripciones():
    sheet = get_sheet()
    registros = sheet.get_all_records()
    resultados = []

    for row in registros:
        nick = str(row.get("Nick", "")).strip()
        nombre = str(row.get("Nombre", "")).strip()
        tag = str(row.get("Tag", "")).strip()
        elo = str(row.get("ELO", "")).strip()
        roles = str(row.get("Roles preferidos", "")).strip()
        amigo = str(row.get("Amigo preferido", "")).strip()
        disponibilidad = str(row.get("Disponibilidad", "")).strip()

        cuenta = f"{nombre}#{tag}"
        resultados.append({
            "Nick": nick,
            "Cuenta": cuenta,
            "ELO": elo,
            "Roles": roles,
            "Amigo": amigo if amigo.lower() != "ninguno" else "—",
            "Disponibilidad": disponibilidad
        })
    return resultados