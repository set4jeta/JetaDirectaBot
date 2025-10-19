import re
import json
from pprint import pprint
import cloudscraper

def extraer_datos_nextjs(html):
    """Extrae el JSON específico de Next.js"""
    # Patrón optimizado para la estructura exacta que compartiste
    patron = (
        r'self\.__next_f\.push\(\[1,"5:\[.*?\\"data\\":\s*'
        r'({.*?})'
        r'\s*}\]\\n"\]\)'
    )
    match = re.search(patron, html, re.DOTALL)
    
    if not match:
        print("❌ No se encontró el patrón principal")
        return None
    
    try:
        # Limpieza especial del JSON
        json_str = match.group(1)
        json_str = json_str.replace('\\"', '"')  # Elimina escapes de comillas
        json_str = json_str.replace('\\n', '')   # Elimina saltos de línea
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"❌ Error decodificando JSON: {e}")
        return None

def descargar_y_procesar(player_id="113"):
    """Descarga y procesa los datos del jugador"""
    url = f"https://dpm.lol/pro/{player_id}"
    scraper = cloudscraper.create_scraper()
    
    try:
        print(f"⬇️ Descargando datos de {player_id}...")
        response = scraper.get(url)
        response.raise_for_status()
        
        print("🔍 Extrayendo datos...")
        datos_brutos = extraer_datos_nextjs(response.text)
        
        if not datos_brutos:
            print("⚠️ No se encontraron datos en el HTML")
            return None
        
        # Procesamiento de datos
        resultado = {
            "info_jugador": {
                "nombre": datos_brutos.get("esportPlayer", {}).get("name"),
                "edad": datos_brutos.get("esportPlayer", {}).get("age"),
                "equipo": datos_brutos.get("esportPlayer", {}).get("team"),
                "pais": datos_brutos.get("esportPlayer", {}).get("country"),
                "contrato_hasta": datos_brutos.get("esportPlayer", {}).get("contract")
            },
            "cuentas": [
                {
                    "nombre": f"{acc.get('gameName')}#{acc.get('tagLine')}",
                    "nivel": acc.get("summonerLevel"),
                    "liga": f"{acc.get('ranks', [{}])[0].get('tier')} {acc.get('ranks', [{}])[0].get('rank')}",
                    "lp": acc.get("ranks", [{}])[0].get("leaguePoints"),
                    "victorias": acc.get("ranks", [{}])[0].get("wins"),
                    "derrotas": acc.get("ranks", [{}])[0].get("losses"),
                    "ultima_partida": acc.get("lastMatchTimestamp")
                } for acc in datos_brutos.get("players", [])
            ],
            "campeones_recientes": [
                {
                    "nombre": champ.get("championName"),
                    "partidas": champ.get("games"),
                    "victorias": champ.get("wins"),
                    "winrate": f"{(champ.get('wins', 0)/champ.get('games', 1))*100:.1f}%",
                    "kda_promedio": champ.get("avgKda")
                } for champ in datos_brutos.get("lastChampions", [])
            ],
            "estadisticas_2_semanas": datos_brutos.get("last2Weeks", {})
        }
        
        return resultado
    
    except Exception as e:
        print(f"🚨 Error durante el proceso: {str(e)}")
        return None

if __name__ == "__main__":
    datos = descargar_y_procesar()
    
    if datos:
        print("\n🎉 ¡Datos extraídos con éxito!")
        pprint(datos, indent=2, width=120)
        
        # Guardar en JSON
        with open("datos_113.json", "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        print("\n💾 Datos guardados en 'datos_113.json'")
    else:
        print("\n❌ No se pudieron obtener los datos. Soluciones posibles:")
        print("1. Verifica que el jugador exista en DPM.LOL")
        print("2. Actualiza cloudscraper: pip install --upgrade cloudscraper")
        print("3. Prueba con otro jugador (ej: 'faker')")