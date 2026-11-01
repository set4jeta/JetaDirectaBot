"""Despliega (o actualiza) el relay de dpm.lol en Cloudflare, sin npm.

Por qué existe
--------------
El camino normal es `npx wrangler deploy`, pero eso pide Node, `npm install` y un
`wrangler login` que abre el navegador. Este script hace lo mismo con la API REST
de Cloudflare y las dependencias que el proyecto ya tiene (`requests`), que es lo
que permite redesplegar el Worker desde cualquier sitio y comprobarlo acto
seguido.

La trampa que resuelve
----------------------
La API de scripts **no** acepta el fichero a pelo con `Content-Type:
application/javascript`: lo interpreta como script clásico y rechaza el
`export default` con `Unexpected token 'export'`. Un módulo ES hay que mandarlo
en `multipart/form-data` con una parte `metadata` que declare `main_module`. Eso
es lo que hace `_subir()`.

Uso
---
    CF_API_TOKEN=... python scripts/desplegar_relay.py
    CF_API_TOKEN=... python scripts/desplegar_relay.py --clave NUEVA_CLAVE

Variables de entorno:
    CF_API_TOKEN     obligatorio; token con permiso «Edit Cloudflare Workers»
    CF_ACCOUNT_ID    opcional; si falta se coge la única cuenta del token
    CF_WORKER        opcional; nombre del Worker (por defecto `jeta-dpm-relay`)

Con `--clave` se fija (o se cambia) el secreto `RELAY_KEY` del Worker. Sin ella
se respeta el que ya tenga. La clave **no** se imprime nunca: si se genera, se
escribe en `~/relay_key.txt`.

Devuelve 0 si el Worker quedó desplegado y responde 200 contra dpm.lol, 1 si no.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import secrets
import sys

import requests

AQUI = pathlib.Path(__file__).resolve().parent.parent
WORKER = AQUI / "infra" / "relay-dpm" / "worker.js"
API = "https://api.cloudflare.com/client/v4"

#: Compatibilidad del runtime. Fijarla evita que un cambio de comportamiento por
#: defecto de Cloudflare rompa el Worker sin que hayamos tocado nada.
COMPAT = "2024-11-01"

#: URL con la que se comprueba que el relay entra de verdad en dpm.lol. Es la
#: ficha de un jugador cualquiera: barata (2,8 KB) y siempre existe.
PRUEBA = "https://dpm.lol/v1/pros/Faker"


def _cabeceras(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _cuenta(token: str) -> str:
    """El id de la cuenta. Si el token ve varias, se para: elegir a ciegas
    desplegaría el Worker en el sitio equivocado."""
    fija = (os.getenv("CF_ACCOUNT_ID") or "").strip()
    if fija:
        return fija
    r = requests.get(f"{API}/accounts", headers=_cabeceras(token), timeout=20)
    r.raise_for_status()
    cuentas = r.json().get("result") or []
    if not cuentas:
        raise SystemExit("El token no ve ninguna cuenta de Cloudflare.")
    if len(cuentas) > 1:
        nombres = ", ".join(f"{c['name']} ({c['id']})" for c in cuentas)
        raise SystemExit(f"Hay varias cuentas ({nombres}); pasa CF_ACCOUNT_ID.")
    return cuentas[0]["id"]


def _subir(token: str, cuenta: str, nombre: str) -> None:
    codigo = WORKER.read_bytes()
    meta = json.dumps(
        {
            "main_module": "worker.js",
            "compatibility_date": COMPAT,
            "observability": {"enabled": True},
        }
    )
    r = requests.put(
        f"{API}/accounts/{cuenta}/workers/scripts/{nombre}",
        headers=_cabeceras(token),
        files={
            "metadata": (None, meta, "application/json"),
            "worker.js": ("worker.js", codigo, "application/javascript+module"),
        },
        timeout=90,
    )
    if r.status_code != 200:
        raise SystemExit(f"La subida falló ({r.status_code}): {r.text[:300]}")
    print(f"Worker '{nombre}' subido ({len(codigo)} B de código).")


def _clave(token: str, cuenta: str, nombre: str, clave: str | None) -> str:
    """Fija el secreto y devuelve la clave efectiva.

    El PUT de secretos contesta **201** al crearlo y 200 al actualizarlo; mirar
    solo el 200 hace creer que falló justo la primera vez, que es cuando más
    importa.

    Sin `--clave` no se toca el secreto: se intenta leer la clave de
    `~/relay_key.txt` **solo para poder probar** el despliegue. Es lo que hace
    que actualizar el código no obligue a rotar la clave —rotarla dejaría a
    Render con una que ya no vale.
    """
    if clave is None:
        guardada = pathlib.Path(os.path.expanduser("~/relay_key.txt"))
        if guardada.exists():
            return guardada.read_text(encoding="utf-8").strip()
        print("Sin --clave y sin ~/relay_key.txt: no se puede probar el relay.")
        return ""
    r = requests.put(
        f"{API}/accounts/{cuenta}/workers/scripts/{nombre}/secrets",
        headers={**_cabeceras(token), "Content-Type": "application/json"},
        json={"name": "RELAY_KEY", "text": clave, "type": "secret_text"},
        timeout=30,
    )
    if r.status_code not in (200, 201):
        raise SystemExit(f"No se pudo fijar RELAY_KEY ({r.status_code}): {r.text[:300]}")
    print("Secreto RELAY_KEY fijado.")
    return clave


def _activar_ruta(token: str, cuenta: str, nombre: str) -> None:
    r = requests.post(
        f"{API}/accounts/{cuenta}/workers/scripts/{nombre}/subdomain",
        headers={**_cabeceras(token), "Content-Type": "application/json"},
        json={"enabled": True, "previews_enabled": False},
        timeout=30,
    )
    if r.status_code != 200:
        raise SystemExit(f"No se pudo activar la ruta workers.dev ({r.status_code}): {r.text[:300]}")
    print("Ruta workers.dev activada.")


def _probar(url: str, clave: str) -> bool:
    """Una petición real a dpm.lol **a través del Worker**.

    Lo que importa es `x-relay-upstream`: dice qué contestó dpm.lol al Worker, y
    eso es independiente de quién llame. Un 200 de la fachada con upstream 403
    sería un falso positivo.
    """
    from urllib.parse import quote

    cabeceras = {"x-relay-key": clave} if clave else {}
    try:
        r = requests.get(f"{url}/?u={quote(PRUEBA, safe='')}", headers=cabeceras, timeout=40)
    except Exception as exc:
        print(f"Prueba: no se pudo ni llamar al relay ({type(exc).__name__}: {exc}).")
        return False
    arriba = r.headers.get("x-relay-upstream")
    print(f"Prueba: HTTP {r.status_code} | upstream={arriba} | {len(r.content)} B")
    if r.status_code == 403 and r.text.strip() == "forbidden":
        print("  La clave no coincide: el Worker está vivo pero no nos deja pasar.")
        return False
    return r.status_code == 200 and arriba == "200"


def main() -> int:
    token = (os.getenv("CF_API_TOKEN") or "").strip()
    if not token:
        print("Falta CF_API_TOKEN (token con permiso «Edit Cloudflare Workers»).")
        return 1

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--clave", nargs="?", const="", default=None,
        help="fija RELAY_KEY; sin valor genera una y la guarda en ~/relay_key.txt",
    )
    parser.add_argument("--worker", default=os.getenv("CF_WORKER", "jeta-dpm-relay"))
    args = parser.parse_args()

    clave = args.clave
    if clave == "":
        clave = "jk_" + secrets.token_urlsafe(32)
        destino = pathlib.Path(os.path.expanduser("~/relay_key.txt"))
        destino.write_text(clave, encoding="utf-8")
        print(f"Clave generada y guardada en {destino}.")

    cuenta = _cuenta(token)
    _subir(token, cuenta, args.worker)
    clave = _clave(token, cuenta, args.worker, clave)
    _activar_ruta(token, cuenta, args.worker)

    subdominio = requests.get(
        f"{API}/accounts/{cuenta}/workers/subdomain", headers=_cabeceras(token), timeout=20
    ).json().get("result") or {}
    nombre_sub = subdominio.get("subdomain") or ""
    if not nombre_sub:
        print("La cuenta no tiene subdominio workers.dev; créalo en el panel.")
        return 1

    url = f"https://{args.worker}.{nombre_sub}.workers.dev"
    print(f"URL: {url}")
    # El certificado del subdominio tarda un poco en emitirse la primera vez.
    for intento in range(6):
        if _probar(url, clave):
            print("\nRelay operativo. En Render: DPM_RELAY_URL=" + url)
            return 0
        if intento < 5:
            import time

            time.sleep(20)
    print("\nEl relay no entró en dpm.lol. Ver README.md antes de seguir.")
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(AQUI))
    raise SystemExit(main())
