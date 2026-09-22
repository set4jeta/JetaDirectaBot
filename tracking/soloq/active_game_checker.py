"""Tracker de partidas en curso de los jugadores seguidos.

Qué estaba roto antes
---------------------
`run()` era un `while True` que nunca terminaba. Como `core/background_tasks.py`
lo llamaba desde un `@tasks.loop(seconds=60)`, ocurría esto:

* la primera llamada entraba en `run()` y ya no salía nunca;
* el loop de 60 s no volvía a dispararse jamás (nextcord espera a que el cuerpo
  termine para programar la siguiente vuelta);
* en la práctica el intervalo real quedaba fijado por el `sleep(5)` del final
  del `while`, no por el decorador.

Además:
* `self.index = 0` al principio de cada vuelta anulaba el índice persistido en
  `last_index.json`, así que ese mecanismo de reanudación era código muerto.
* Cada pasada era secuencial con `sleep(0.5)` por jugador: con 55 jugadores,
  más de 30 s por vuelta.
* Ante un 429 hacía `sleep(8)` y reintentaba en un bucle interior.
* Los jugadores se cargaban una sola vez en `__init__`, así que cualquier
  cambio en los ficheros de cuentas exigía reiniciar el bot.

Cómo queda ahora
----------------
`run()` hace **una pasada** y devuelve: el `tasks.loop` es quien manda.
Las peticiones van con concurrencia acotada y el rate limiting vive en
`apis/riot_client.py`, no aquí. Los PUUIDs inválidos se marcan como `stale`
para no volver a gastar una petición en ellos.

Cuando la pasada no cabe en su intervalo
----------------------------------------
El tope de ligas por servidor (`MAX_LIGAS_POR_SERVIDOR`) **no acota** el coste
real: la pasada recorre la unión de las ligas de todos los servidores, así que
20 servidores con 4 ligas distintas cada uno cuestan las 20 ligas. Medido en
`scripts/_coste_ligas.py`: las 20 son ~3154 cuentas, unos 63 s al cupo de Riot,
contra un `CHECK_GAMES_INTERVAL` de 30.

Lo que pasaba entonces era degradación en silencio: la vuelta siguiente
encontraba `self._running` en True, escribía una línea de log y se saltaba. Sin
contarlas, la única forma de enterarse de que los avisos llegan tarde era leer
el log. Ahora la pasada se mide contra su intervalo, las vueltas perdidas se
cuentan y el resultado se registra en `core.health`, que es donde `/health`
puede decirlo.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

import config
from apis.riot_client import RiotApiError, get_riot_client, normalizar_plataforma
from core import health as salud
from core import rank_store
from core.rank_data import get_cached_rank, save_rank_data
from core.ranked_cache import get_rank_data_or_cache
from models.soloq_match import SoloQMatch
from tracking.soloq.accounts_io import load_cuentas_sueltas, load_tracked_accounts
from tracking.soloq.active_game_cache import (
    get_active_game_cache,
    olvidar,
    set_active_game_with_ranked,
)
from tracking.soloq.avisos_log import registrar as registrar_aviso
from tracking.soloq.channel_config import todos_los_canales
from tracking.soloq.notifier import (
    already_announced,
    clean_old_announcements,
    load_announced_games,
    mark_announced,
    olvidar_anuncio,
    save_announced_games,
)
from tracking.soloq.tracker_utils import is_valid_game
from ui.active_match_embed import create_match_embed
from utils.cache_utils import limpiar_cache_partidas_viejas
from utils.game_clock import desde_partida
from utils.logger import get_logger
from utils.player_filters import get_tracked_players

log = get_logger("tracking.active_game_checker")

# Cuántas cuentas se consultan a la vez. El límite real lo impone el rate
# limiter del cliente; esto solo evita abrir cientos de conexiones a la vez.
MAX_CONCURRENCY = int(os.getenv("TRACKER_CONCURRENCY", "12"))


@dataclass
class SweepStats:
    """Resultado de una pasada: sirve para el log y para diagnosticar."""

    revisadas: int = 0
    en_partida: int = 0
    notificadas: int = 0
    omitidas_stale: int = 0
    marcadas_stale: int = 0
    errores: int = 0
    duracion: float = 0.0
    #: Segundos que tiene la pasada antes de que toque la siguiente vuelta.
    #: Se copia de `CHECK_GAMES_INTERVAL` al terminar, no se lee al mirarlo, para
    #: que la cifra guardada sea la que estaba en vigor en esa pasada.
    presupuesto: float = 0.0
    #: True si esta "pasada" no llegó a correr porque la anterior seguía viva.
    solapada: bool = False
    #: Vueltas perdidas por solapamiento desde que arrancó el proceso.
    vueltas_perdidas: int = 0
    detalle: list[str] = field(default_factory=list)

    @property
    def cabe(self) -> bool:
        """¿Terminó dentro de su intervalo?

        Sin presupuesto conocido se responde que sí: es una pasada suelta
        (un script, un test) y no hay nada contra lo que compararla.
        """
        return self.presupuesto <= 0 or self.duracion <= self.presupuesto

    @property
    def uso(self) -> float:
        """Fracción del intervalo consumida. 1.0 = justo en el límite."""
        if self.presupuesto <= 0:
            return 0.0
        return self.duracion / self.presupuesto


#: A partir de qué fracción del intervalo se avisa de que la pasada raspa. No
#: es un número redondo por gusto: con 6 ligas la medición daba ~24 s sobre un
#: intervalo de 30 (0,8), y ese es justo el caso que hay que ver venir antes de
#: que empiecen a perderse vueltas.
UMBRAL_AVISO = 0.8

#: Última pasada terminada, para que `/health` pueda decir "tarda 41 s y el
#: intervalo es 30". Antes esto solo existía en una línea de log: el bot se
#: degradaba (avisos con un minuto de retraso) sin que ninguna superficie lo
#: dijera. Es de módulo y no del tracker porque `/health` no tiene la instancia.
ultima_pasada: SweepStats | None = None

#: Acumulado del proceso. Una vuelta perdida suelta puede ser un pico de la API;
#: que el contador suba sin parar es que la pasada ya no cabe.
_vueltas_perdidas = 0


def _presupuesto() -> float:
    """Segundos entre vueltas. Se lee en caliente para respetar el `.env`."""
    return float(getattr(config, "CHECK_GAMES_INTERVAL", 0) or 0)


def _rutas_de(files) -> list[tuple[str, str]]:
    """`(ruta_en_disco, nombre_en_discord)` de cada adjunto del embed.

    Hace falta para poder mandar el mismo embed a varios servidores: un
    `nextcord.File` solo sirve para un envío.
    """
    rutas: list[tuple[str, str]] = []
    for f in files or []:
        ruta = getattr(getattr(f, "fp", None), "name", None)
        if isinstance(ruta, str) and os.path.exists(ruta):
            rutas.append((ruta, f.filename))
    return rutas


def _reabrir(rutas: list[tuple[str, str]]):
    """Adjuntos nuevos a partir de las rutas, para el siguiente envío."""
    import nextcord

    nuevos = []
    for ruta, nombre in rutas:
        try:
            nuevos.append(nextcord.File(ruta, filename=nombre))
        except OSError as exc:
            log.debug("No se pudo reabrir el adjunto %s: %s", ruta, exc)
    return nuevos


class ActiveGameTracker:
    """Comprueba quién está en partida y avisa en los canales configurados."""

    def __init__(self, bot, concurrency: int = MAX_CONCURRENCY):
        self.bot = bot
        self.concurrency = concurrency
        self.announced_games = load_announced_games()
        self._puuid_to_player: dict[str, object] = {}
        self._players: list = []
        self._running = False

        self.refresh_players()

    # ------------------------------------------------------------------ #
    # Carga de jugadores
    # ------------------------------------------------------------------ #

    def refresh_players(self) -> None:
        """Recarga las cuentas para recoger cambios sin reiniciar el bot.

        **Se barre solo lo que alguien sigue**, no todo el catálogo.

        Esto no era evidente y se rompió el 22-09-2026: hasta entonces
        `accounts_from_teams.json` contenía únicamente las ligas en uso (la LEC),
        así que "barrer el fichero" y "barrer lo que se sigue" eran lo mismo por
        casualidad. Al descargar las 20 ligas para que `/track` pueda resolver a
        cualquiera, el fichero pasó a 908 jugadores y **1948 cuentas**: barrer eso
        cada 30 s son ~43 s medidos, o sea vueltas perdidas y avisos tarde, en
        silencio. De ahí el filtro explícito.

        El filtro es `ligas_en_uso()`, que ya es la unión de lo que siguen los
        servidores, lo que siguen los usuarios por liga **y la liga de cada
        jugador o equipo seguido** (`leagues.ligas_de_seguidos`). O sea: lo que se
        barre es exactamente lo que alguien puede llegar a recibir.

        Las **cuentas sueltas** (`/track Nombre#TAG`) se añaden siempre y sin
        filtro: si están ahí es porque alguien las pidió una a una, y no
        pertenecen a ninguna liga.
        """
        from tracking.soloq.leagues import ligas_en_uso
        from utils.player_filters import _liga_de

        catalogo = get_tracked_players(load_tracked_accounts())
        permitidas = set(ligas_en_uso())
        seguidas = [p for p in catalogo if _liga_de(p) in permitidas]
        sueltas = load_cuentas_sueltas()

        self._players = seguidas + sueltas
        self._puuid_to_player = {
            acc.puuid: player
            for player in self._players
            for acc in player.accounts
            if acc.puuid
        }

        log.debug(
            "A barrer: %d cuentas (%d jugadores) de las %d del catálogo, +%d "
            "sueltas · ligas en uso: %s",
            sum(len(p.accounts) for p in self._players),
            len(self._players),
            sum(len(p.accounts) for p in catalogo),
            sum(len(p.accounts) for p in sueltas),
            ", ".join(sorted(permitidas)) or "ninguna",
        )

    # ------------------------------------------------------------------ #
    # Una pasada
    # ------------------------------------------------------------------ #

    async def run(self) -> SweepStats:
        """Hace UNA pasada sobre todas las cuentas y devuelve estadísticas.

        Devuelve siempre: quien la llame (`check_games_loop`) es responsable de
        la cadencia. Un `while True` aquí rompería el `tasks.loop`.
        """
        global ultima_pasada, _vueltas_perdidas

        started = time.perf_counter()
        stats = SweepStats(presupuesto=_presupuesto())

        # Si una pasada anterior sigue viva, no solapamos trabajo.
        if self._running:
            _vueltas_perdidas += 1
            stats.solapada = True
            stats.vueltas_perdidas = _vueltas_perdidas
            log.warning(
                "Pasada anterior aún en curso: se pierde esta vuelta (%d en total). "
                "La pasada no cabe en los %.0fs de intervalo.",
                _vueltas_perdidas, stats.presupuesto,
            )
            salud.registrar(
                "pasada", False,
                f"{_vueltas_perdidas} vuelta(s) perdidas por solapamiento",
            )
            return stats

        self._running = True
        try:
            self.refresh_players()

            all_accounts = [acc for p in self._players for acc in p.accounts]
            stats.omitidas_stale = sum(
                1 for acc in all_accounts if getattr(acc, "stale", False)
            )

            targets = [
                (player, account)
                for player in self._players
                for account in player.accounts
                if account.puuid and not getattr(account, "stale", False)
            ]
            stats.revisadas = len(targets)

            if not targets:
                log.warning("No hay cuentas que revisar. Revisa accounts_from_teams.json")
                return stats

            semaphore = asyncio.Semaphore(self.concurrency)

            async def guarded(player, account):
                async with semaphore:
                    return await self._check_account(player, account, stats)

            await asyncio.gather(*(guarded(p, a) for p, a in targets))

            self.cleanup()
            # Marca de continuidad: es lo que permite detectar después un apagón
            # (ver `rank_store._calcular_hueco`). Va al final y no al principio:
            # solo cuenta como "pasada hecha" si terminó.
            rank_store.marcar_pasada()
        finally:
            self._running = False
            stats.duracion = time.perf_counter() - started
            stats.vueltas_perdidas = _vueltas_perdidas
            ultima_pasada = stats

        log.info(
            "Pasada: %.1fs | %d cuentas | %d en partida | %d notificadas | "
            "%d stale omitidas | %d errores",
            stats.duracion, stats.revisadas, stats.en_partida,
            stats.notificadas, stats.omitidas_stale, stats.errores,
        )
        for line in stats.detalle:
            log.info("   %s", line)

        self._avisar_si_no_cabe(stats)
        return stats

    def _avisar_si_no_cabe(self, stats: SweepStats) -> None:
        """Compara la pasada con su intervalo y lo registra en `core.health`.

        Se separa de `run()` porque son dos preguntas distintas: `run()` dice qué
        encontró, esto dice si va a tiempo. Y hace falta porque el tope de ligas
        por servidor no acota el coste global (ver la cabecera del módulo): el
        bot puede acabar con 20 ligas en la unión y degradarse sin quejarse.

        No se toca la cadencia automáticamente. Bajar la frecuencia de sondeo o
        recortar ligas por decisión propia cambiaría el producto que el servidor
        contrató sin decírselo; lo que hace falta es que se **vea**, y de eso ya
        se encarga `/health`.
        """
        if stats.presupuesto <= 0:
            return

        if not stats.cabe:
            log.warning(
                "La pasada tardó %.1fs y el intervalo es %.0fs (%.0f %%): los avisos "
                "van a llegar tarde. Reduce ligas seguidas o sube CHECK_GAMES_INTERVAL.",
                stats.duracion, stats.presupuesto, stats.uso * 100,
            )
            salud.registrar(
                "pasada", False,
                f"{stats.duracion:.0f}s sobre {stats.presupuesto:.0f}s de intervalo",
            )
            return

        if stats.uso >= UMBRAL_AVISO:
            # Todavía cabe, así que no es una avería: es el aviso previo. Se
            # registra como "ok" con detalle para no encender `/health` en rojo
            # por algo que aún funciona.
            log.warning(
                "La pasada ocupa el %.0f %% de su intervalo (%.1fs de %.0fs). "
                "Con una liga más deja de caber.",
                stats.uso * 100, stats.duracion, stats.presupuesto,
            )
            salud.registrar(
                "pasada", True,
                f"al {stats.uso * 100:.0f} % del intervalo ({stats.duracion:.0f}s)",
            )
            return

        salud.registrar("pasada", True, f"{stats.duracion:.1f}s de {stats.presupuesto:.0f}s")

    # ------------------------------------------------------------------ #
    # Comprobación de una cuenta
    # ------------------------------------------------------------------ #

    async def _refrescar_rango(self, account) -> None:
        """Pide el rango de una cuenta que acaba de terminar partida y lo anota.

        Reutiliza `rank_warm.refrescar`, que ya sabe consultar **en el servidor de
        la cuenta** (las de KR/NA/BR daban 404 contra euw1) y convertir la
        respuesta al formato del almacén. Duplicar esa conversión aquí sería la
        forma más fácil de que las dos se separaran.

        Un fallo no puede romper la pasada: si esto va mal, el rango se vuelve a
        pedir por el camino normal (`rank_warm`) y nadie se entera.
        """
        from tracking.soloq.rank_warm import refrescar as refrescar_rangos

        plataforma = normalizar_plataforma(getattr(account, "platform", None))
        try:
            await refrescar_rangos([(account.puuid, plataforma)])
        except Exception:
            log.debug(
                "No se pudo refrescar el rango tras la partida de %s",
                (account.puuid or "")[:12],
            )

    async def _check_account(self, player, account, stats: SweepStats) -> None:
        """Mira si una cuenta está en partida y avisa si corresponde."""
        client = await get_riot_client()
        rid = account.riot_id or {}
        label = f"{rid.get('game_name', '?')}#{rid.get('tag_line', '?')}"

        # Cada cuenta se consulta en SU servidor. Antes todas iban contra
        # `DEFAULT_PLATFORM` (euw1): con la LEC no se notaba, pero las cuentas
        # de KR/NA/BR daban 404 aunque el jugador estuviera en partida.
        plataforma = normalizar_plataforma(getattr(account, "platform", None))

        try:
            game_data = await client.get_active_game(account.puuid, platform=plataforma)
        except RiotApiError as exc:
            # 400 = PUUID que Riot no puede descifrar. Es permanente: marcamos
            # la cuenta para no volver a gastar una petición en cada pasada.
            if exc.status == 400:
                account.stale = True
                stats.marcadas_stale += 1
                log.warning("PUUID inválido en %s -> marcada stale: %s", label, exc.message[:90])
            else:
                stats.errores += 1
                log.debug("Error consultando %s: %s", label, exc)
            return

        # 404 = no está en partida. Es el caso normal, no ensuciamos el log.
        if not game_data:
            # Pero si estaba en la caché de partidas activas, **acaba de
            # terminar una**, y ese es el instante exacto en el que cambian sus
            # LP. Se pide el rango aquí: una petición por partida, y a cambio el
            # dato queda exacto hasta que vuelva a jugar, así que no habrá que
            # preguntar por él en días (ver la cabecera de `core/rank_store`).
            if get_active_game_cache(account.puuid):
                await self._refrescar_rango(account)
            # `olvidar` limpia también el índice por nombre: con `pop` a secas
            # la entrada por nombre sobrevivía y `!match` podía servir una
            # partida ya terminada al caer a ese respaldo.
            olvidar(account.puuid, getattr(player, "name", None))
            return

        if not is_valid_game(game_data):
            return

        # Marca de actividad: el tracker es el único que sabe de primera mano que
        # esta cuenta está jugando, y es lo que después permite decidir si el
        # rango guardado sigue valiendo **sin gastar una petición**. No escribe
        # en disco por cada pasada: ver `rank_store.marcar_en_partida`.
        rank_store.marcar_en_partida(account.puuid)

        match = SoloQMatch.from_riot_game_data(game_data)
        stats.en_partida += 1
        if await self.notificar_partida(account, match):
            stats.notificadas += 1
        # El log llevaba `gameLength` en crudo, que es el reloj del espectador y
        # sale negativo al principio de la partida: en el log aparecía
        # "CLASSIC -134s". Ahora va el mismo texto que ve el usuario.
        stats.detalle.append(
            f"{getattr(player, 'name', '?')} · {label} · {game_data.get('gameMode')} "
            f"{desde_partida(game_data).texto_corto()}"
        )

    # ------------------------------------------------------------------ #
    # Notificación
    # ------------------------------------------------------------------ #

    async def notificar_partida(self, account, match: SoloQMatch) -> bool:
        """Envía el embed a cada canal suscrito. True si se envió al menos uno."""
        game_id = match.game_id
        ranked_map: dict[str, dict] = {}

        # Los 10 participantes están en el servidor de la partida. Se pasa
        # `platformId` en vez de dejar que el cliente caiga a euw1: en una
        # partida de KR eso devolvía 404 diez veces y el embed salía sin Elo.
        plataforma = match.platform or getattr(account, "platform", None)

        for participant in match.participants:
            if not participant.puuid:
                continue
            cached = get_cached_rank(participant)
            if cached:
                ranked_map[participant.puuid] = cached
                continue

            rank_data = await get_rank_data_or_cache(
                participant.puuid, platform=plataforma
            )
            ranked_map[participant.puuid] = rank_data
            if rank_data.get("tier") not in (None, "Desconocido"):
                participant.rank = rank_data
                save_rank_data(participant)

        player = self._puuid_to_player.get(account.puuid)
        player_name = getattr(player, "name", None) or account.riot_id["game_name"]
        set_active_game_with_ranked(account.puuid, match.datos_extra, ranked_map, player_name)

        # La pasada es global (abarca las ligas de todos los servidores), pero
        # cada servidor solo recibe las que eligió. Sin este filtro, quien
        # siguiera solo la LEC recibiría también las partidas de la LCK.
        from tracking.soloq.leagues import ligas_de
        from utils.i18n import idioma_de
        from utils.player_filters import _liga_de

        liga_jugador = _liga_de(player)
        # El equipo sale del roster (tricode: `T1`, `FNC`). Hace falta para que
        # quien sigue un equipo reciba a sus jugadores: ver `dm_notifier`.
        equipo_jugador = (getattr(player, "team", "") or "").strip()

        # Antes aquí había un `return False` cuando no había ningún canal
        # configurado. Ya no puede estar: con suscripciones personales, el caso
        # "cero canales y un usuario que se instaló el bot en su cuenta" es
        # exactamente el que hay que atender, y ese atajo lo dejaba sin avisos.
        canales_por_servidor = todos_los_canales()
        if not canales_por_servidor:
            log.debug("Partida detectada y ningún canal suscrito: solo DM.")

        sent = False
        # Un embed **por idioma**, no por servidor: dos servidores en inglés
        # comparten el mismo. Montarlo cuesta lectura de ficheros de cuentas y
        # de imágenes, así que se cachea aquí. Los adjuntos sí van aparte
        # (`nextcord.File` solo sirve para un envío).
        por_idioma: dict[str, tuple[object, list[tuple[str, str]]]] = {}

        for guild_id, canales in canales_por_servidor.items():
            if liga_jugador not in ligas_de(guild_id):
                log.debug(
                    "Servidor %s: %s es de la liga '%s', que no sigue.",
                    guild_id, player_name, liga_jugador,
                )
                continue

            idioma = idioma_de(guild_id)

            # Un servidor puede tener varios canales de avisos (cupo del plan),
            # así que el filtro por liga y el idioma se resuelven una vez por
            # servidor y el envío se repite por canal.
            for channel_id in canales:
                if already_announced(self.announced_games, game_id, channel_id):
                    continue

                channel = self.bot.get_channel(channel_id)
                if not channel:
                    log.debug("Canal %s no accesible.", channel_id)
                    continue

                # El embed se construye una vez por idioma, pero los adjuntos NO
                # se pueden reutilizar: nextcord cierra el descriptor tras
                # enviarlo, así que el segundo `channel.send` con los mismos
                # `File` moría con `ValueError: seek of closed file` (comprobado
                # reproduciendo el ciclo reset/close de nextcord). Con un solo
                # canal nunca se vio; con dos, el segundo se quedaba sin aviso.
                # Se RESERVA antes de enviar, sin ningún `await` entre la
                # comprobación de arriba y esto. Antes se marcaba después de
                # enviar, y en medio hay dos `await` (montar el embed y el envío):
                # como la pasada procesa las cuentas en paralelo, dos jugadores
                # del MISMO partido pasaban los dos la comprobación y el canal
                # recibía el mismo embed dos veces. Si el envío falla, se suelta
                # la reserva para poder reintentarlo.
                mark_announced(self.announced_games, game_id, channel_id)
                try:
                    if idioma not in por_idioma:
                        embed, files = await create_match_embed(
                            match, self._puuid_to_player, ranked_map, idioma=idioma
                        )
                        por_idioma[idioma] = (embed, _rutas_de(files))
                    else:
                        embed, rutas = por_idioma[idioma]
                        files = _reabrir(rutas)

                    await channel.send(embed=embed, files=files)
                    sent = True
                except Exception as exc:
                    olvidar_anuncio(self.announced_games, game_id, channel_id)
                    log.error("No se pudo enviar al canal %s: %s", channel_id, exc)

        # El mismo aviso, a quien lo haya pedido en su chat privado. Va después
        # de los canales a propósito: los canales son el producto que ya
        # funciona, y si el reparto por DM se atasca (Discord frena la apertura
        # de DM con un 40003) no puede retrasar lo que ya iba bien.
        if await self._notificar_por_dm(
            match, ranked_map, player_name, liga_jugador, equipo_jugador
        ):
            sent = True

        # El registro va al final y solo si algo se envió: es un histórico de
        # avisos publicados, no de partidas detectadas. Una partida que nadie
        # sigue se detecta pero no se anuncia, y anotarla haría que la web
        # publicara avisos que nunca existieron.
        #
        # No guarda ningún canal, servidor ni usuario: este fichero se publica
        # en la web. Ver la cabecera de `avisos_log.py`.
        if sent:
            registrar_aviso(match, account, player, liga_jugador, ranked_map)

        return sent

    async def _notificar_por_dm(
        self,
        match: SoloQMatch,
        ranked_map: dict,
        player_name: str,
        liga: str,
        equipo: str = "",
    ) -> bool:
        """Manda la partida a los usuarios suscritos. True si llegó a alguno.

        Esto es el eje por usuario: alguien puede seguir a un jugador suelto o
        una liga entera y recibirlo en su DM sin que haya ningún servidor de por
        medio. Ver `tracking/soloq/dm_notifier.py`, y en particular por qué la
        entrega **no está garantizada** por Discord.

        El embed se cachea por idioma igual que en los canales, y por el mismo
        motivo: montarlo lee ficheros de cuentas e imágenes. Los adjuntos no se
        pueden reutilizar entre envíos, así que se guardan las rutas y se
        reabren; es literalmente el fallo que ya se arregló para el segundo canal
        de un servidor (`ValueError: seek of closed file`).
        """
        from tracking.soloq.dm_notifier import clave_dedupe, destinatarios, repartir

        ids = [
            uid for uid in destinatarios(player_name, liga, equipo)
            if not already_announced(self.announced_games, match.game_id, clave_dedupe(uid))
        ]
        if not ids:
            return False

        # Se RESERVA antes de enviar, sin `await` entre la comprobación y esto.
        # Antes se marcaba al final, y en medio están el montaje del embed y el
        # reparto: con dos jugadores del mismo partido en paralelo, los dos veían
        # la partida como no avisada y al usuario le llegaba el mismo embed dos
        # veces (reportado por el dueño el 22-09-2026). Lo que falle se suelta.
        for uid in ids:
            mark_announced(self.announced_games, match.game_id, clave_dedupe(uid))

        cache: dict[str, tuple[object, list[tuple[str, str]]]] = {}

        def construir(idioma: str) -> dict:
            # Síncrona porque `repartir` la llama por destinatario y no debe
            # esperar E/S: el embed ya está hecho tras el primer idioma.
            embed, rutas = cache[idioma]
            return {"embed": embed, "files": _reabrir(rutas)}

        # Se precalienta la caché aquí, donde sí se puede esperar, con un embed
        # por idioma distinto que haya entre los destinatarios y no uno por
        # persona.
        from utils.i18n import idioma_efectivo

        for idioma in {idioma_efectivo(uid) for uid in ids}:
            embed, files = await create_match_embed(
                match, self._puuid_to_player, ranked_map, idioma=idioma
            )
            cache[idioma] = (embed, _rutas_de(files))

        entregados = await repartir(self.bot, ids, construir)
        for uid in ids:
            if uid not in entregados:
                olvidar_anuncio(self.announced_games, match.game_id, clave_dedupe(uid))
        if entregados:
            log.info("Partida %s enviada por DM a %d usuario(s)",
                     match.game_id, len(entregados))
        return bool(entregados)

    # ------------------------------------------------------------------ #
    # Cierre de pasada
    # ------------------------------------------------------------------ #

    def cleanup(self) -> None:
        """Persiste estado y limpia caches. Se llama al final de cada pasada."""
        clean_old_announcements(self.announced_games)
        save_announced_games(self.announced_games)
        limpiar_cache_partidas_viejas()
