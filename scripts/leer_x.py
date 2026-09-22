"""Lee publicaciones de X (Twitter) con la sesión que el dueño ya tiene abierta.

Por qué existe
--------------
X no da su contenido a un `fetch` normal: la búsqueda es una SPA que monta el
timeline con JavaScript y exige sesión. `WebFetch` sobre `x.com/search?q=SEO`
devuelve solo "See what's happening", y Nitter (el espejo que servía para esto)
está muerto desde el 24-08-2026 por un cease and desist de X Corp.

La vía que sí funciona: hablar por CDP con un Opera GX arrancado sobre una
**copia** del perfil del dueño (`Local State` + `Cookies`), así la sesión ya
iniciada viaja con nosotros y no se toca el navegador que él tiene abierto.

Uso
---
    python leer_x.py "SEO" 60 salida.json

Argumentos: consulta, segundos de scroll, fichero de salida.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

import websocket

CDP = "http://127.0.0.1:9333"


def _pestaña_nueva(url: str) -> str:
    """Abre una pestaña y devuelve su URL de websocket."""
    pet = urllib.request.Request(
        f"{CDP}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT"
    )
    with urllib.request.urlopen(pet, timeout=15) as r:
        return json.load(r)["webSocketDebuggerUrl"]


class Sesion:
    """Envoltura mínima de CDP: `enviar` con id incremental y espera de respuesta."""

    def __init__(self, ws_url: str) -> None:
        self.ws = websocket.create_connection(ws_url, timeout=40)
        self.n = 0

    def enviar(self, metodo: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": metodo, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                return msg.get("result", {})

    def js(self, expr: str):
        r = self.enviar(
            "Runtime.evaluate",
            expression=expr,
            returnByValue=True,
            awaitPromise=True,
        )
        return r.get("result", {}).get("value")

    def cerrar(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


# JS que saca los tuits del DOM. `article` es el contenedor de cada publicación;
# `data-testid=tweetText` el cuerpo. Se recogen métricas del aria-label porque X
# no las expone en atributos limpios.
EXTRAER = r"""
(() => {
  const salida = [];
  document.querySelectorAll('article[data-testid="tweet"]').forEach(a => {
    const cuerpo = a.querySelector('[data-testid="tweetText"]');
    if (!cuerpo) return;
    const texto = cuerpo.innerText.trim();
    if (!texto) return;
    let autor = '';
    const enlaces = a.querySelectorAll('a[role="link"]');
    for (const e of enlaces) {
      const m = e.getAttribute('href').match(/^\/([A-Za-z0-9_]{2,15})$/);
      if (m) { autor = '@' + m[1]; break; }
    }
    const hora = a.querySelector('time');
    const grupo = a.querySelector('[role="group"]');
    salida.push({
      autor,
      texto,
      fecha: hora ? hora.getAttribute('datetime') : '',
      metricas: grupo ? (grupo.getAttribute('aria-label') || '') : '',
    });
  });
  return JSON.stringify(salida);
})()
"""


def leer(consulta: str, segundos: int) -> list[dict]:
    url = (
        "https://x.com/search?q="
        + urllib.parse.quote(consulta)
        + "&src=typed_query&f=top"
    )
    ses = Sesion(_pestaña_nueva(url))
    try:
        ses.enviar("Page.enable")
        ses.enviar("Runtime.enable")
        time.sleep(9)  # la SPA tarda en montar el timeline

        titulo = ses.js("document.title") or ""
        cuerpo = ses.js("document.body ? document.body.innerText.slice(0,400) : ''")
        if "Log in" in (cuerpo or "") or "Sign in" in (cuerpo or ""):
            print(f"  AVISO: parece pedir login. titulo={titulo!r}", file=sys.stderr)

        vistos: dict[str, dict] = {}
        fin = time.time() + segundos
        sin_nuevos = 0
        while time.time() < fin:
            crudo = ses.js(EXTRAER)
            if crudo:
                antes = len(vistos)
                for t in json.loads(crudo):
                    clave = t["texto"][:120]
                    if clave not in vistos:
                        vistos[clave] = t
                sin_nuevos = 0 if len(vistos) > antes else sin_nuevos + 1
            if sin_nuevos >= 6:  # el timeline dejó de dar contenido nuevo
                break
            ses.js("window.scrollBy(0, window.innerHeight * 2.2)")
            time.sleep(2.2)
        return list(vistos.values())
    finally:
        ses.cerrar()


if __name__ == "__main__":
    consulta = sys.argv[1]
    segundos = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    destino = sys.argv[3] if len(sys.argv) > 3 else "x_salida.json"
    tuits = leer(consulta, segundos)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"consulta": consulta, "tuits": tuits}, f, ensure_ascii=False, indent=1)
    print(f"{consulta!r}: {len(tuits)} publicaciones -> {destino}")
