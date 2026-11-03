"""Ancho de banda de salida del servicio en Render: total, ritmo y proyección.

Para qué
--------
El plan free de Render da 5 GB de salida al mes y suspende el bot si se pasa
(la última vez, el 29-10-2026, tres días caído). Esta utilidad deja el número
a mano sin tener que pelearse con la API de métricas.

Uso
---
    python scripts/render_bw.py            # 7 días + mes en curso
    python scripts/render_bw.py --dias 14

De dónde sale
-------------
La métrica `bandwidth_usage` viene **en MB por intervalo** (buckets de 1 h
aunque se pida otra resolución), así que el total es la suma de los buckets.
El ciclo de cuota reinicia el día 1 en UTC: lo que manda para la cuota es el
total del mes, no el acumulado de 7 días (que puede cruzar el cambio de mes).

Ojo: `/health` no vale para esto. Mide lo que el bot **cree** que envía, no lo
que Render factura, y desde el 01-11-2026 cuenta también el sondeo; el dpm.lol
ni siquiera se cuenta.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_mcp import call  # noqa: E402

SERVICIO = "srv-d25e71ili9vc73f6sbu0"
WORKSPACE = "tea-d25e35ruibrs73ah90sg"
TOPE_RENDER_MB = 5000.0


def _ts(iso: str) -> datetime:
    return datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def traer(dias: int) -> list[dict]:
    """Buckets de `bandwidth_usage` de los últimos `dias` días."""
    fin = datetime.now(timezone.utc)
    inicio = fin - timedelta(days=dias)
    res = call("get_metrics", {
        "resourceId": SERVICIO,
        "workspaceId": WORKSPACE,
        "metricTypes": ["bandwidth_usage"],
        "resolution": 3600,
        "startTime": inicio.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endTime": fin.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    if not res or not isinstance(res[0], dict):
        return []
    datos = res[0]["metrics"][0]["data"][0]["values"]
    return [{"ts": _ts(p["timestamp"]), "mb": float(p["value"])} for p in datos]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=7)
    args = ap.parse_args()

    puntos = traer(args.dias)
    if not puntos:
        print("Sin datos de bandwidth_usage.")
        return 1

    puntos.sort(key=lambda p: p["ts"])
    total = sum(p["mb"] for p in puntos)
    ahora = datetime.now(timezone.utc)

    print(f"Ventana: {puntos[0]['ts']:%Y-%m-%d %H:%M} -> {puntos[-1]['ts']:%Y-%m-%d %H:%M} UTC")
    print(f"Total {args.dias} días: {total:,.1f} MB ({total/1000:.2f} GB)")

    por_dia: dict = defaultdict(float)
    for p in puntos:
        por_dia[p["ts"].date()] += p["mb"]
    print("\nPor día (UTC):")
    for dia in sorted(por_dia):
        print(f"  {dia}  {por_dia[dia]:8.1f} MB")

    mes = sum(v for d, v in por_dia.items() if d >= ahora.replace(day=1).date())
    print(f"\nMes en curso: {mes:,.1f} MB de {TOPE_RENDER_MB:.0f} ({mes/TOPE_RENDER_MB*100:.1f} %)")

    def suma(desde: datetime, hasta: datetime) -> float:
        return sum(p["mb"] for p in puntos if desde <= p["ts"] < hasta)

    u24 = suma(ahora - timedelta(hours=24), ahora)
    u12 = suma(ahora - timedelta(hours=12), ahora)
    print(f"Últimas 24 h: {u24:,.1f} MB ({u24/24:.2f} MB/h)")
    print(f"Últimas 12 h: {u12:,.1f} MB ({u12/12:.2f} MB/h)")

    for nombre, ritmo in (("24 h", u24), ("12 h", u12)):
        if ritmo <= 0:
            continue
        dias_hasta = (TOPE_RENDER_MB - mes) / ritmo
        print(f"  a {ritmo:.0f} MB/día -> {TOPE_RENDER_MB:.0f} MB el "
              f"{(ahora + timedelta(days=dias_hasta)):%Y-%m-%d %H:%M} UTC")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
