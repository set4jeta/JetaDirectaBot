#tracking/soloq/infoplayers_eu_dpm.py

import html
import json
import os
import re

import cloudscraper

from utils.logger import get_logger

log = get_logger("tracking.infoplayers")

# Crear carpeta de salida si no existe
OUTPUT_DIR = "Infoplayers"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def extraer_datos_nextjs(pagina: str):
    """Extrae el JSON interno de Next.js con la data estructurada del jugador.

    El parámetro se llamaba `html` y tapaba al módulo `html` importado arriba:
    dentro de esta función, `html.unescape(...)` habría petado con
    `AttributeError: 'str' object has no attribute 'unescape'`.
    """
    patron_json = r'self\.__next_f\.push\(\[1,"5:\[.*?\\"data\\":\s*({.*?})\s*}\]\\n"\]\)'
    match_json = re.search(patron_json, pagina, re.DOTALL)

    if not match_json:
        # Pasa constantemente: dpm.lol no tiene página para muchos jugadores.
        # Era un print por cada uno, 60 por hora.
        log.debug("Sin JSON de Next.js en el HTML (jugador sin página en dpm.lol).")
        return None, None, None, None

    try:
        json_str = match_json.group(1).replace('\\"', '"').replace('\\n', '')
        datos_brutos = json.loads(json_str)
    except json.JSONDecodeError as e:
        log.debug("JSON de dpm.lol no válido: %s", e)
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
    match_imagen = re.search(r'<img alt="[^"]*" [^>]*src="(/esport/players/[^"]+\.webp)"', pagina)
    imagen_jugador = f"https://dpm.lol{match_imagen.group(1)}" if match_imagen else None

    # Logo del equipo
    match_logo = re.search(r'<img alt="Team Icon"[^>]*src="(/esport/teams/[^"]+\.webp)"', pagina)
    logo_equipo = f"https://dpm.lol{match_logo.group(1)}" if match_logo else None

    return datos_brutos, redes, imagen_jugador, logo_equipo





def obtener_datos_jugador(nombre_jugador: str, scraper) -> dict | None:
    """Obtiene y estructura todos los datos del jugador"""
    url = f"https://dpm.lol/pro/{nombre_jugador}"

    try:
        log.debug("Descargando datos de %s", nombre_jugador)
        response = scraper.get(url)
        response.raise_for_status()

        datos_brutos, redes, imagen_jugador, logo_equipo = extraer_datos_nextjs(response.text)
        if not datos_brutos:
            log.debug("Sin datos válidos para %s", nombre_jugador)
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
        log.debug("Error obteniendo datos de %s: %s", nombre_jugador, e)
        return None

def guardar_datos_jugador_en_json(nombre_jugador: str, scraper):
    """Guarda los datos del jugador en un JSON dentro de `Infoplayers/`.

    Aquí había una medición de memoria con `tracemalloc` que **hacía caer el
    proceso entero** con `access violation` (segfault). Motivo:

    * `tracemalloc.start()` / `.stop()` cambian los *allocators* de CPython a
      nivel de **proceso**, no de hilo (comprobado: `is_tracing()` puesto en un
      hilo se ve `True` desde otro).
    * Esta función la llama `actualizar_infoplayers_por_lotes` mediante
      `asyncio.to_thread`, 60 veces por hora, así que esos `start`/`stop`
      ocurrían en hilos de un pool mientras el hilo principal estaba dentro de
      `zlib` descomprimiendo respuestas gzip de `aiohttp`.
    * Cambiar el allocator con una descompresión en vuelo libera con un
      allocator distinto del que reservó: memoria corrupta.

    Reproducido y aislado en un A/B de 3+3 ejecuciones: con las llamadas a
    `tracemalloc` los tres intentos murieron por segfault; sin ellas, los tres
    terminaron bien. En el bot real fallaba 1 de cada 3 arranques, siempre con
    `Current thread` dentro de `aiohttp/compression_utils.py decompress_sync`.

    Si hace falta medir memoria otra vez, hay que hacerlo desde el hilo
    principal y una sola vez (`PYTHONTRACEMALLOC=1` al arrancar), nunca por
    lote y nunca desde un hilo secundario.
    """
    datos = obtener_datos_jugador(nombre_jugador, scraper)

    if datos is None:
        log.debug("No se pudo guardar datos de %s", nombre_jugador)
        return

    archivo_salida = os.path.join(OUTPUT_DIR, f"{nombre_jugador}.json")
    # Escritura atómica: el fichero lo lee `!info` en cualquier momento y un
    # corte a media escritura dejaba un JSON truncado que rompía el comando.
    tmp = archivo_salida + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(tmp, archivo_salida)
    except OSError as exc:
        log.warning("No se pudo escribir %s: %s", archivo_salida, exc)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return

    log.debug("Datos de %s guardados.", nombre_jugador)


# Uso directo si se ejecuta este archivo
if __name__ == "__main__":
    scraper = cloudscraper.create_scraper()
    for jugador in ("Faker", "Caps", "113"):
        guardar_datos_jugador_en_json(jugador, scraper)

