#tracking/soloq/infoplayers_eu_dpm.py

import re
import json
import os
import cloudscraper
import html

# Crear carpeta de salida si no existe
OUTPUT_DIR = "Infoplayers"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def extraer_datos_nextjs(html):
    """Extrae el JSON interno de Next.js con la data estructurada del jugador"""
    patron_json = r'self\.__next_f\.push\(\[1,"5:\[.*?\\"data\\":\s*({.*?})\s*}\]\\n"\]\)'
    match_json = re.search(patron_json, html, re.DOTALL)
    
    if not match_json:
        print("❌ No se encontró el JSON en el HTML")
        return None, None, None, None

    try:
        json_str = match_json.group(1).replace('\\"', '"').replace('\\n', '')
        datos_brutos = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"❌ Error al decodificar JSON: {e}")
        return None, None, None, None

    # Redes sociales
    redes = {}
    if "players" in datos_brutos and len(datos_brutos["players"]) > 0:
        links = datos_brutos["players"][0].get("links", [])
        if isinstance(links, list):
            for link in links:
                if "twitter.com" in link:
                    redes["twitter"] = link
                elif "twitch.tv" in link:
                    redes["twitch"] = link

    # Imagen del jugador
    match_imagen = re.search(r'<img alt="[^"]*" [^>]*src="(/esport/players/[^"]+\.webp)"', html)
    imagen_jugador = f"https://dpm.lol{match_imagen.group(1)}" if match_imagen else None

    # Logo del equipo
    match_logo = re.search(r'<img alt="Team Icon"[^>]*src="(/esport/teams/[^"]+\.webp)"', html)
    logo_equipo = f"https://dpm.lol{match_logo.group(1)}" if match_logo else None

    return datos_brutos, redes, imagen_jugador, logo_equipo

def obtener_datos_jugador(nombre_jugador: str) -> dict | None:
    """Obtiene y estructura todos los datos del jugador"""
    url = f"https://dpm.lol/pro/{nombre_jugador}"
    scraper = cloudscraper.create_scraper()

    try:
        print(f"⬇️ Descargando datos de {nombre_jugador}...")
        response = scraper.get(url)
        response.raise_for_status()

        datos_brutos, redes, imagen_jugador, logo_equipo = extraer_datos_nextjs(response.text)
        if not datos_brutos:
            print("⚠️ No se encontraron datos válidos para", nombre_jugador)
            return None

        esport_player = datos_brutos.get("esportPlayer")
        if esport_player is None:
            esport_player = {}

        cuentas = []
        for acc in datos_brutos.get("players", []):
            ranks = acc.get("ranks") or []
            if ranks and len(ranks) > 0:
                rank_info = ranks[0]
            else:
                rank_info = {}

            # Aquí la lógica correcta para liga y lp
            if rank_info and rank_info.get("tier") and rank_info.get("rank"):
                liga = f"{rank_info.get('tier')} {rank_info.get('rank')}".strip()
                lp = rank_info.get("leaguePoints") or 0
            else:
                liga = "Unranked"
                lp = None

            cuenta = {
                "nombre": f"{acc.get('gameName', '')}#{acc.get('tagLine', '')}",
                "nivel": acc.get("summonerLevel"),
                "region": acc.get("platform")  ,# <- AQUI SE AÑADE
                "liga": liga,
                "lp": lp,
                "victorias": rank_info.get("wins"),
                "derrotas": rank_info.get("losses"),
                "ultima_partida": acc.get("lastMatchTimestamp")
            }
            cuentas.append(cuenta)

        campeones_recientes = []
        for champ in datos_brutos.get("lastChampions", []):
            juegos = champ.get("games", 1) or 1
            victorias = champ.get("wins", 0) or 0
            winrate = f"{(victorias/juegos)*100:.1f}%" if juegos else "0%"
            campeones_recientes.append({
                "nombre": champ.get("championName"),
                "partidas": juegos,
                "victorias": victorias,
                "winrate": winrate,
                "kda_promedio": champ.get("avgKda")
            })

        return {
            "info_jugador": {
                "nombre": nombre_jugador,
                "nombre_real": html.unescape(esport_player.get("name", "")),
                "edad": esport_player.get("age"),
                "equipo": esport_player.get("team"),
                "pais": esport_player.get("country"),
                "contrato_hasta": esport_player.get("contract"),
                "redes_sociales": redes,
                "imagen_jugador": imagen_jugador,
                "logo_equipo": logo_equipo
            },
            "cuentas": cuentas,
            "campeones_recientes": campeones_recientes,
            "estadisticas_2_semanas": datos_brutos.get("last2Weeks", {})
        }

    except Exception as e:
        print(f"🚨 Error al obtener datos de {nombre_jugador}: {e}")
        return None

def guardar_datos_jugador_en_json(nombre_jugador: str):
    """Guarda los datos del jugador en un archivo JSON en la carpeta Infoplayers"""
    datos = obtener_datos_jugador(nombre_jugador)
    if datos is None:
        print(f"❌ No se pudo guardar datos para {nombre_jugador}")
        return

    archivo_salida = os.path.join(OUTPUT_DIR, f"{nombre_jugador}.json")
    with open(archivo_salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print(f"✅ Datos de {nombre_jugador} guardados en {archivo_salida}")

# Uso directo si se ejecuta este archivo
if __name__ == "__main__":
    jugadores = ["Faker", "Caps", "113"]  # Puedes modificar esta lista
    for jugador in jugadores:
        guardar_datos_jugador_en_json(jugador)
