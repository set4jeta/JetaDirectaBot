#tracking/soloq/index_tracker.py
import os
import json

LAST_INDEX_PATH = os.path.join(os.path.dirname(__file__), "last_index.json")

def load_last_index(path=LAST_INDEX_PATH) -> int:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("last_checked_index", 0)
    except Exception as e:
        print(f"[WARN] No se pudo cargar el índice: {e}")
    return 0

def save_last_index(index: int, path=LAST_INDEX_PATH):
    # Atómico como el resto del proyecto: son 25 bytes, pero es el puntero de la
    # rotación por lotes de Infoplayers. Truncado a 0 vuelve a empezar por el
    # jugador 0 y los del final de la lista no se refrescan nunca.
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"last_checked_index": index}, f)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[ERROR] No se pudo guardar el índice: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass