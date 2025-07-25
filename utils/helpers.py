from utils.constants import SPELL_ID_TO_NAME, SPELL_ROLE_PRIORITY
# utils/helpers.py
#Parseo de datos de clasificación para mostrar el rango del jugador desde los datos de ranked obtenidos de la API de Riot.
def parse_ranked_data(ranked_data):
    if ranked_data is not None:
        if isinstance(ranked_data, list) and ranked_data:
            soloq = next((q for q in ranked_data if q["queueType"] == "RANKED_SOLO_5x5"), None)
            if soloq:
                return {
                    "tier": soloq["tier"].capitalize(),
                    "division": soloq["rank"],
                    "lp": soloq["leaguePoints"]
                }
            else:
                return {"tier": "Unranked", "division": "", "lp": 0}
        else:
            return {"tier": "Unranked", "division": "", "lp": 0}
    else:
        return {"tier": "Sin datos", "division": "", "lp": 0}
    
    
    
