"""Comprueba que el embed de partida en vivo se construye en los dos idiomas.

Por qué existe
--------------
`ui/active_match_embed.py` era lo último que quedaba en español a pelo, y es lo
que más se ve: se publica solo en el canal cada vez que un pro entra en partida.
Al traducirlo hay dos formas fáciles de romperlo y ninguna se nota hasta que
ocurre en producción:

1. Una clave mal escrita: `t()` no lanza, devuelve la clave, así que el embed
   diría literalmente `partida.lado_azul` y nadie se enteraría hasta verlo.
2. Un campo que pase de los 1024 caracteres que admite Discord, o un título de
   más de 256: eso sí lanza, pero solo al enviar.

Esta prueba monta el embed con una partida sintética en es/en/fr y verifica las
dos cosas. Se ejecuta sin Discord y sin red.

    python scripts/test_i18n_embed.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time  # noqa: E402

from models.soloq_match import SoloQMatch  # noqa: E402
from ui.active_match_embed import create_match_embed  # noqa: E402
from utils.i18n import _CATALOGO, t  # noqa: E402

fallos: list[str] = []


def check(etiqueta: str, ok: bool, detalle: str = "") -> None:
    marca = "OK  " if ok else "FALLO"
    print(f"  [{marca}] {etiqueta}" + (f" — {detalle}" if detalle else ""))
    if not ok:
        fallos.append(etiqueta)


# --------------------------------------------------------------------- #
# Partida sintética
# --------------------------------------------------------------------- #

def partida(*, en_carga: bool = False, arena: bool = False, jugadores: int = 1) -> dict:
    """Respuesta de `spectator-v5` falsa pero con la forma real."""
    ahora_ms = int(time.time() * 1000)
    participantes = []
    for i in range(10):
        participantes.append({
            "puuid": f"puuid-{i:02d}",
            "teamId": 100 if (arena or i < 5) else 200,
            "championId": 103 + i,
            "riotId": f"Jugador{i}#EUW",
            "spell1Id": 4,
            "spell2Id": 14,
            "bot": False,
        })
    return {
        "gameId": 7654321,
        "platformId": "EUW1",
        "gameMode": "CHERRY" if arena else "CLASSIC",
        "gameQueueConfigId": 1750 if arena else 420,
        # En carga: `gameStartTime` es 0 y `gameLength` negativo. Es el caso en
        # que salen la cuenta atrás y el aviso del delay, que son los textos
        # más largos del embed.
        "gameStartTime": 0 if en_carga else ahora_ms - 20 * 60 * 1000,
        "gameLength": -95 if en_carga else 1180,
        "observers": {"encryptionKey": "clave-falsa=="},
        "participants": participantes,
    }


class _Cuenta:
    def __init__(self, puuid: str, nombre: str):
        self.puuid = puuid
        self.riot_id = {"game_name": nombre, "tag_line": "EUW"}
        self.platform = "euw1"
        self.stale = False


class _Jugador:
    def __init__(self, nombre: str, cuentas):
        self.name = nombre
        self.team = "G2"
        self.team_name = "G2 Esports"
        self.role = "MIDDLE"
        self.accounts = cuentas
        self.league = "lec"


def mapa(n: int) -> dict:
    """`{puuid: jugador}` con `n` jugadores seguidos dentro de la partida."""
    salida = {}
    for i in range(n):
        cuenta = _Cuenta(f"puuid-{i:02d}", f"Jugador{i}")
        salida[cuenta.puuid] = _Jugador(f"Pro{i}", [cuenta])
    return salida


RANGOS = {
    f"puuid-{i:02d}": {"tier": "CHALLENGER", "division": "I", "lp": 1200 - i}
    for i in range(10)
}


# --------------------------------------------------------------------- #
# 1. Todas las claves que usa el embed existen en los dos idiomas
# --------------------------------------------------------------------- #

print("\n1) Cobertura del catálogo")

CLAVES_EMBED = [k for k in _CATALOGO if k.startswith(("partida.", "reloj."))]
sin_ingles = [k for k in CLAVES_EMBED if not _CATALOGO[k].get("en")]
check(f"{len(CLAVES_EMBED)} claves de partida/reloj tienen inglés",
      not sin_ingles, ", ".join(sin_ingles) or "todas")

# Una clave inexistente se devuelve tal cual: eso es lo que hace que un typo
# sea invisible, así que la prueba de abajo busca ese patrón en el embed.
check("una clave inexistente se devuelve tal cual",
      t("no.existe.esta.clave", "en") == "no.existe.esta.clave")

sospechosas = [k for k in _CATALOGO if _CATALOGO[k].get("es") == k]
check("ninguna traducción es igual a su clave", not sospechosas,
      ", ".join(sospechosas) or "ok")


# --------------------------------------------------------------------- #
# 2. El embed se monta en es/en/fr sin dejar claves crudas
# --------------------------------------------------------------------- #

print("\n2) Construcción del embed")


async def construir(idioma, **kw):
    match = SoloQMatch.from_riot_game_data(partida(**kw))
    n = kw.pop("jugadores", 1)
    return await create_match_embed(match, mapa(n), RANGOS, idioma=idioma)


def texto_completo(embed) -> str:
    partes = [embed.title or "", embed.description or ""]
    for campo in embed.fields:
        partes.append(campo.name or "")
        partes.append(str(campo.value or ""))
    return "\n".join(partes)


async def main() -> None:
    for idioma, etiqueta in (("es", "español"), ("en", "inglés"), ("fr", "francés")):
        for escenario, kw in (
            ("normal", {}),
            ("en carga", {"en_carga": True}),
            ("arena", {"arena": True}),
            ("3 jugadores", {"jugadores": 3}),
        ):
            embed, files = await construir(idioma, **kw)
            texto = texto_completo(embed)

            # Una clave sin traducir sale como `partida.algo` o `reloj.algo`.
            crudas = [
                k for k in CLAVES_EMBED
                if k in texto
            ]
            check(f"{etiqueta}/{escenario}: sin claves crudas", not crudas,
                  ", ".join(crudas) or "limpio")

            check(f"{etiqueta}/{escenario}: título <= 256",
                  len(embed.title or "") <= 256, f"{len(embed.title or '')}")

            largos = [
                (c.name, len(str(c.value)))
                for c in embed.fields if len(str(c.value or "")) > 1024
            ]
            check(f"{etiqueta}/{escenario}: campos <= 1024", not largos, str(largos))

            # El descargo de Riot es obligatorio y esta es la superficie que más
            # se ve, así que se comprueba en el embed real, no solo en el módulo
            # que lo genera: `utils/branding.py` ya existía sin que nadie lo
            # llamara, y así no vuelve a pasar sin que salte un fallo.
            pie = getattr(getattr(embed, "footer", None), "text", "") or ""
            check(f"{etiqueta}/{escenario}: pie con descargo de Riot",
                  "Riot Games" in pie, pie or "(sin pie)")

            for f in files:
                try:
                    f.close()
                except Exception:
                    pass

    # --- Comparación es/en del mismo escenario, para leerlo a ojo ---
    print("\n3) Lo que ve el usuario (partida en carga, 2 jugadores)")
    for idioma in ("es", "en"):
        embed, files = await construir(idioma, en_carga=True, jugadores=2)
        print(f"\n  --- {idioma} ---")
        print(f"  título: {embed.title}")
        for linea in (embed.description or "").split("\n"):
            print(f"  desc:   {linea}")
        for campo in embed.fields:
            valor = str(campo.value or "").replace("\n", " ⏎ ")
            print(f"  campo:  {campo.name!r} = {valor[:110]}")
        for f in files:
            try:
                f.close()
            except Exception:
                pass

    # --- El singular/plural del título, que es lo que más canta en inglés ---
    print("\n4) Concordancia del título")
    for n, esperado_en in ((1, " is in game"), (2, " are in game"), (3, " are in game")):
        embed, files = await construir("en", jugadores=n)
        check(f"inglés con {n} jugador(es) dice '{esperado_en.strip()}'",
              esperado_en in (embed.title or ""), embed.title or "")
        embed_es, files_es = await construir("es", jugadores=n)
        esperado_es = " está jugando" if n == 1 else " están jugando"
        check(f"español con {n} jugador(es) dice '{esperado_es.strip()}'",
              esperado_es in (embed_es.title or ""), embed_es.title or "")
        for f in list(files) + list(files_es):
            try:
                f.close()
            except Exception:
                pass


asyncio.run(main())

print("\n" + "=" * 60)
if fallos:
    print(f"FALLOS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("Todo correcto: el embed de partida funciona en es y en en.")
