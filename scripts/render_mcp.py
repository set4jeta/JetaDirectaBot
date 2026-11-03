"""Cliente MCP de Render por JSON-RPC, para lo que las tools no dejan pasar.

Por qué existe
--------------
Las tools `mcp__render__*` llegan con los arrays de argumentos deformados: al
llamar a `get_metrics` con `metricTypes: ["bandwidth_usage"]` el array se
convierte en objeto y la validación falla ("received object; expected array of
strings"). Como `get_metrics` es la única forma de pedir la métrica de ancho de
banda, y es la que vigila la cuota de 5 GB, hace falta una vía que no pase por
esa conversión.

Este módulo habla JSON-RPC a pelo con `https://mcp.render.com/mcp`: hace el
handshake (`initialize` → `notifications/initialized`) y llama a la tool que se
le pida con los argumentos en JSON literal.

Uso
---
    from scripts.render_mcp import call
    logs = call("list_logs", {"resource": ["srv-..."], "text": ["Pasada:"]})

El token sale de `~/.workbuddy-ai/mcp.json` (el conector `render`). No se
escribe en ningún fichero del repo.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

BASE = "https://mcp.render.com/mcp"
TIMEOUT = 180


def _token() -> str:
    """El token del conector `render`, leído de la configuración del usuario."""
    ruta = Path.home() / ".workbuddy-ai" / "mcp.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return datos["mcpServers"]["render"]["headers"]["Authorization"].split(" ", 1)[1]
    except Exception as exc:  # noqa: BLE001 - el mensaje dice qué revisar
        raise RuntimeError(
            f"No se encontró el token de Render en {ruta}: {exc}"
        ) from exc


def _post(payload: dict, sid: str | None = None, headers_out: dict | None = None) -> dict:
    cabeceras = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if sid:
        cabeceras["mcp-session-id"] = sid
    peticion = urllib.request.Request(
        BASE, data=json.dumps(payload).encode(), headers=cabeceras, method="POST"
    )
    with urllib.request.urlopen(peticion, timeout=TIMEOUT) as r:
        if headers_out is not None:
            headers_out.update({k.lower(): v for k, v in r.headers.items()})
        cuerpo = r.read().decode("utf-8", "replace")
    # El servidor responde como SSE: "event: message\ndata: {...}"
    for linea in cuerpo.splitlines():
        if linea.startswith("data:"):
            return json.loads(linea[5:].strip())
    return json.loads(cuerpo) if cuerpo.strip() else {}


def call(tool: str, argumentos: dict) -> list:
    """Llama a una tool del MCP de Render y devuelve su contenido ya parseado."""
    cabeceras: dict = {}
    _post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "loLProTrackr-scripts", "version": "1.0"},
            },
        },
        headers_out=cabeceras,
    )
    sid = cabeceras.get("mcp-session-id")
    try:
        _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid=sid)
    except Exception:  # noqa: BLE001 - la notificación puede no devolver cuerpo
        pass

    respuesta = _post(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": argumentos},
        },
        sid=sid,
    )
    if isinstance(respuesta, dict) and "result" in respuesta:
        salida = []
        for bloque in respuesta["result"].get("content", []):
            texto = bloque.get("text", "")
            try:
                salida.append(json.loads(texto))
            except (TypeError, ValueError):
                salida.append(texto)
        return salida
    return [respuesta]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    print(json.dumps(call(sys.argv[1], json.loads(sys.argv[2])), ensure_ascii=False, indent=1))
