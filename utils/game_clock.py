"""Reloj de una partida en curso y cuenta atrás del delay del espectador.

El problema
-----------

`spectator-v5` devuelve **dos relojes distintos** y el bot los mezclaba:

* `gameStartTime`: milisegundos epoch del inicio de la partida. Es un reloj
  real, pero vale `0` mientras la partida está en pantalla de carga.
* `gameLength`: segundos **según el servidor de espectadores**, que va con
  retraso respecto a la partida real y además **no avanza segundo a segundo**:
  sube a saltos de unos 62 s, la longitud de chunk del espectador.

Medición real (`scripts/probe_spectator_timing.py` sobre partidas en curso):
`gameLength` va entre ~150 s y ~192 s por detrás de `ahora - gameStartTime`, y
su pendiente aparente frente al reloj de pared sale 1,4 en vez de 1,0 por esos
saltos de 62 s.

Consecuencia en pantalla: `!live` calculaba `gameLength + (ahora - guardado)` y
podía dar un número negativo. El código lo sabía —tenía un `sign = "-"`— pero lo
rotulaba igual: `⏱ -02:14 en partida`, que no significa nada para quien lo lee.

Qué hace este módulo
--------------------

Modela los dos relojes por separado, que es lo que son:

* `transcurrido`: cuánto lleva la partida de verdad. Sale de `gameStartTime`.
* `visible`: el reloj del espectador. Sale de `gameLength` y **puede ser
  negativo**: eso es exactamente la cuenta atrás del delay.

Lo importante es que **casi nunca hay que estimar el delay**: la respuesta trae
los dos campos a la vez, así que `visible` es un dato medido, no `transcurrido`
menos una constante. `SPECTATOR_DELAY` solo se usa de respaldo cuando falta uno
de los dos. Esto importa porque la constante no da: el desfase medido llegó a
192 s con `SPECTATOR_DELAY = 180`, así que restar 180 decía «ya se puede ver»
doce segundos antes de que fuera verdad.

Con eso, `espectable` y `falta_para_espectar` dan lo que pedía el backlog:
«Comienza dentro de 3 min» / `-03:00` en vez de un tiempo negativo a secas.
`!live`, el embed de `!match` y la notificación automática usan este módulo, así
que los tres dicen lo mismo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import config

# Colas y modo de Arena. Va con bastante menos retraso que el resto.
#
# El id que devuelve `spectator-v5` de verdad es **1750** (verificado con la
# sonda: `[CHERRY / cola 1750]`), aunque la tabla de colas de Riot documenta
# 1700/1710 para Arena. Se aceptan los tres, y además el modo `CHERRY`, porque
# en pantalla de carga `gameQueueConfigId` puede no venir.
COLAS_ARENA = frozenset({1700, 1710, 1750})
MODO_ARENA = "CHERRY"


def delay_de(modo: str | None = None, cola: int | None = None) -> int:
    """Delay del espectador en segundos según el modo de juego.

    Solo se usa como respaldo: si la respuesta trae `gameLength`, el delay real
    se mide en vez de estimarse.
    """
    if cola in COLAS_ARENA or (modo or "").upper() == MODO_ARENA:
        return config.SPECTATOR_DELAY_ARENA
    return config.SPECTATOR_DELAY


def mmss(segundos: float, con_signo: bool = False) -> str:
    """`754` -> `12:34`. Con `con_signo`, los negativos salen como `-01:05`."""
    total = int(round(segundos))
    signo = "-" if total < 0 and con_signo else ""
    mins, secs = divmod(abs(total), 60)
    return f"{signo}{mins:02d}:{secs:02d}"


def humano(segundos: float, idioma: str | None = None) -> str:
    """Redondeo hacia arriba en lenguaje natural: `3 min`, `40 s`.

    `idioma` va al final y por defecto en `None` para no romper a quien ya la
    llamaba con un solo argumento (el embed, `!live` y las pruebas).
    """
    from utils.i18n import t

    total = max(0, int(round(segundos)))
    if total < 60:
        return t("reloj.segundos", idioma, n=total)
    minutos = -(-total // 60)  # techo
    return t("reloj.minutos", idioma, n=minutos)


@dataclass
class Reloj:
    """Los dos relojes de una partida en curso.

    `transcurrido`: tiempo real de juego, siempre >= 0.
    `visible`: reloj del espectador, negativo mientras no se pueda ver la
    partida. **No** se deriva restando una constante: cuando la respuesta trae
    `gameLength` (que es casi siempre) ese es el valor medido, y el delay sale
    de la diferencia entre los dos.
    """

    transcurrido: int
    visible: int
    fuente: str  # "medido" | "inicio" | "longitud" | "desconocido"

    @property
    def delay(self) -> int:
        """Cuánto va el espectador por detrás. Medido si `fuente == 'medido'`."""
        return self.transcurrido - self.visible

    @property
    def espectable(self) -> bool:
        """True si ya pasó el delay y la partida se puede ver en el cliente."""
        return self.visible >= 0

    @property
    def falta_para_espectar(self) -> int:
        """Segundos que quedan para poder espectar. 0 si ya se puede."""
        return max(0, -self.visible)

    @property
    def fiable(self) -> bool:
        return self.fuente != "desconocido"

    @property
    def aproximado(self) -> bool:
        """True si `transcurrido` es una estimación, no una medida.

        Solo pasa cuando falta `gameStartTime` (pantalla de carga): entonces el
        tiempo real es `gameLength + delay`, y ahí se acumulan dos errores —el
        delay estimado es fijo pero varía entre ~150 y ~192 s, y `gameLength`
        sube a saltos de 62 s—. Se marca con `~` en vez de fingir precisión.
        """
        return self.fuente == "longitud"

    # ---------------------------------------------------------------- #
    # Textos
    # ---------------------------------------------------------------- #
    #
    # Los tres aceptan `idioma` opcional. Se deja opcional a propósito: los
    # scripts de prueba y los sitios que aún no tienen a mano el `guild_id`
    # siguen llamándolos sin argumentos y salen en español, que es el idioma
    # de referencia.

    def texto_corto(self, idioma: str | None = None) -> str:
        """Para listados como `!live`.

        Antes esto era `⏱ -02:10 en partida`: un tiempo negativo rotulado como
        tiempo de juego, que es justo lo que no se entendía.
        """
        from utils.i18n import t

        if not self.fiable:
            return t("reloj.desconocido", idioma)
        if self.espectable:
            aprox = "~" if self.aproximado else ""
            return t("reloj.en_partida", idioma,
                     tiempo=f"{aprox}{mmss(self.transcurrido)}")
        return t(
            "reloj.cuenta_atras", idioma,
            reloj=mmss(-self.falta_para_espectar, con_signo=True),
            falta=humano(self.falta_para_espectar, idioma),
        )

    def texto_embed(self, idioma: str | None = None) -> str:
        """Para el campo «Tiempo transcurrido» del embed de `!match`."""
        from utils.i18n import t

        if not self.fiable:
            return t("reloj.embed_desconocido", idioma)
        mins, secs = divmod(max(0, self.transcurrido), 60)
        base = f"{'~' if self.aproximado else ''}{mins}m {secs}s"
        if self.espectable:
            return base
        return t("reloj.embed_espectable", idioma, base=base,
                 falta=humano(self.falta_para_espectar, idioma))

    def aviso_delay(self, idioma: str | None = None) -> str | None:
        """Aviso para cuando la partida aún no se puede ver. `None` si ya se ve."""
        from utils.i18n import t

        if self.espectable or not self.fiable:
            return None
        return t(
            "reloj.aviso", idioma,
            falta=humano(self.falta_para_espectar, idioma),
            delay=humano(self.delay, idioma),
        )


# ---------------------------------------------------------------------- #
# Constructores
# ---------------------------------------------------------------------- #

# Rango en el que un delay medido es creíble. La sonda dio 60..192 s (Arena por
# abajo, SoloQ por arriba). Fuera de esto el dato es basura —típicamente porque
# el `gameLength` que se está usando se capturó hace rato— y se prefiere la
# constante antes que enseñar «espectable en 20 min».
DELAY_MIN_CREIBLE = 0
DELAY_MAX_CREIBLE = 300


def _visible_creible(transcurrido: int, visible: int, delay_estimado: int) -> tuple[int, str]:
    """Valida el `visible` medido; si no cuela, lo estima. -> (visible, fuente)."""
    if DELAY_MIN_CREIBLE <= transcurrido - visible <= DELAY_MAX_CREIBLE:
        return visible, "medido"
    return transcurrido - delay_estimado, "inicio"


def desde_partida(game: dict | None, ahora: float | None = None) -> Reloj:
    """Reloj a partir de la respuesta cruda de `spectator-v5`.

    Con los dos campos presentes no hay nada que estimar: `gameStartTime` da el
    tiempo real y `gameLength` da el del espectador. Si falta `gameStartTime`
    (pantalla de carga, vale 0) se estima el real a partir del visible, y al
    revés si falta `gameLength`.
    """
    ahora = time.time() if ahora is None else ahora
    if not isinstance(game, dict):
        return Reloj(0, -config.SPECTATOR_DELAY, "desconocido")

    delay = delay_de(game.get("gameMode"), game.get("gameQueueConfigId"))

    inicio = game.get("gameStartTime")
    longitud = game.get("gameLength")
    hay_inicio = isinstance(inicio, (int, float)) and inicio > 0
    hay_longitud = isinstance(longitud, (int, float))

    if hay_inicio:
        transcurrido = max(0, int(ahora - inicio / 1000))
        if hay_longitud:
            visible, fuente = _visible_creible(transcurrido, int(longitud), delay)
            return Reloj(transcurrido, visible, fuente)
        return Reloj(transcurrido, transcurrido - delay, "inicio")

    if hay_longitud:
        # `gameLength` ES el reloj del espectador, así que el tiempo real de la
        # partida es ese valor más el delay. Si es negativo, ese negativo es
        # literalmente la cuenta atrás y se conserva con su signo.
        return Reloj(int(longitud) + delay, int(longitud), "longitud")

    return Reloj(0, -delay, "desconocido")


def desde_cache(entrada: dict | None, ahora: float | None = None) -> Reloj:
    """Reloj a partir de una entrada de `ACTIVE_GAME_CACHE`.

    La caché guarda la partida completa y el instante en que se recibió, así que
    se puede reconstruir todo: `gameStartTime` no envejece, y el `gameLength`
    guardado solo hay que adelantarlo lo que lleve la entrada en memoria.
    `!live` no hacía ni una cosa ni la otra: extrapolaba siempre desde
    `game_length` teniendo el `gameStartTime` exacto a mano.
    """
    ahora = time.time() if ahora is None else ahora
    if not isinstance(entrada, dict):
        return Reloj(0, -config.SPECTATOR_DELAY, "desconocido")

    partida = entrada.get("active_game")
    partida = partida if isinstance(partida, dict) else {}
    delay = delay_de(partida.get("gameMode"), partida.get("gameQueueConfigId"))

    inicio = partida.get("gameStartTime")
    guardado = entrada.get("timestamp")
    longitud = entrada.get("game_length")
    if longitud is None:
        longitud = partida.get("gameLength")

    hay_inicio = isinstance(inicio, (int, float)) and inicio > 0
    # El `gameLength` guardado es de cuando se recibió: hay que adelantarlo.
    hay_visible = isinstance(longitud, (int, float)) and isinstance(guardado, (int, float))
    visible_ahora = int(longitud) + int(ahora - guardado) if hay_visible else None

    if hay_inicio:
        transcurrido = max(0, int(ahora - inicio / 1000))
        if visible_ahora is not None:
            visible, fuente = _visible_creible(transcurrido, visible_ahora, delay)
            return Reloj(transcurrido, visible, fuente)
        return Reloj(transcurrido, transcurrido - delay, "inicio")

    if visible_ahora is not None:
        return Reloj(visible_ahora + delay, visible_ahora, "longitud")

    return Reloj(0, -delay, "desconocido")
