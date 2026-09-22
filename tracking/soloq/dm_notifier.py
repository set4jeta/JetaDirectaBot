"""Envío de avisos al chat privado de cada persona.

Por qué este módulo es tan defensivo
------------------------------------
Porque la entrega por DM **no está garantizada por Discord**, y eso se comprobó
antes de escribir el resto. Un bot solo puede mandar un DM a alguien con quien
comparte un servidor. La instalación por usuario ("Add to My Apps") concede
únicamente `applications.commands` con `permissions: 0`, así que quien solo haya
hecho eso **no es alcanzable**: `POST /users/@me/channels` puede incluso
devolver el canal, y el envío falla después. Los tres errores que salen en la
práctica:

* **50278** — "Cannot send messages to this user due to having no mutual guilds".
  No compartimos servidor. Lo arregla el usuario entrando en uno.
* **50007** — "Cannot send messages to this user". Tiene los DM cerrados o ha
  bloqueado la app. Lo arregla en sus ajustes de privacidad.
* **40003** — se están abriendo DM demasiado rápido. Es nuestro problema, no
  suyo, y se trata distinto: no se marca nada al usuario, se para la tanda.

Lo que sí funciona siempre es responder a una interacción, pero ese camino
caduca a los 15 minutos y no sirve para un aviso que llega cuando el pro entra
en partida. Así que aquí no se asume nada: se intenta, se clasifica el fallo y se
guarda el estado en `user_config` para que los comandos puedan decirle a la
persona **qué** tiene que hacer en vez de dejarla esperando un aviso que no va a
llegar nunca.

Lo que este módulo no hace
--------------------------
No decide a quién avisar por liga ni por jugador: eso es `destinatarios()`, que
sí está aquí, pero la fuente de la verdad es `user_config`. Y no construye
embeds: llegan hechos desde `active_game_checker`, que ya los cachea por idioma.

Sobre la tanda
--------------
El reparto va **en serie con una pausa**, no con `asyncio.gather`. Es al revés de
lo que hace el tracker con las peticiones a Riot, y a propósito: abrir muchos DM
a la vez es justo lo que provoca el 40003, y la documentación de Discord lo dice
explícitamente ("If you open a significant amount of DMs too quickly, your bot
may be rate limited or blocked from opening new ones"). Un aviso que tarda dos
segundos más en llegar no se nota; que Discord bloquee al bot la apertura de DM,
sí.
"""

from __future__ import annotations

import asyncio

import nextcord

from tracking.soloq import user_config as usuarios
from utils.logger import get_logger

log = get_logger("tracking.dm_notifier")

#: Pausa entre DM de una misma tanda. 0,25 s son 4 envíos por segundo, muy por
#: debajo de cualquier límite conocido, y con 50 suscriptores la tanda entera
#: tarda 12 s: cabe de sobra en el intervalo de 30 s de la pasada.
PAUSA = 0.25

#: Tope de DM por tanda. Es un freno de mano, no un cupo: si un día una liga
#: entera de suscriptores hace que una sola partida genere cientos de envíos,
#: mejor perder los últimos avisos de esa partida que quedarse bloqueado para
#: todas las siguientes. Se registra cuando pasa, para que se vea y se arregle.
MAX_POR_TANDA = 200

#: Códigos de Discord que significan "este usuario no es alcanzable". Ver arriba.
_SIN_GUILD = 50278
_CERRADO = 50007
_DEMASIADO_RAPIDO = 40003


class DemasiadosDM(Exception):
    """Discord está frenando la apertura de DM (40003). Hay que parar la tanda.

    Es una excepción y no un valor de retorno porque quien la recibe no es quien
    puede decidir: el envío individual no sabe cuántos quedan por mandar, y el
    bucle de la tanda no debe tener que comprobar un código en cada vuelta para
    saber si sigue. Si esto sale, se corta y se reintenta en la pasada siguiente.
    """


def _codigo(exc: Exception) -> int:
    """Código de error de Discord, o 0 si el fallo es de otra cosa."""
    return int(getattr(exc, "code", 0) or 0)


async def enviar_dm(bot, user_id: int, **kwargs) -> bool:
    """Manda un mensaje al chat privado de una persona. True si llegó.

    `kwargs` va tal cual a `send`, así que sirve para texto, embed y adjuntos.

    Además de enviar, **clasifica el resultado** en `user_config`: es lo que
    permite que `/misavisos` diga "no puedo escribirte porque no compartimos
    servidor" en vez de dejar a alguien esperando avisos que no van a llegar. Un
    fallo no borra la suscripción; ver el docstring de `user_config`.

    Levanta `DemasiadosDM` con un 40003 para que la tanda pare: seguir
    insistiendo con el resto es lo que convierte un freno temporal en un bloqueo.
    """
    try:
        # `fetch_user` en vez de `get_user` porque la caché solo tiene a los
        # usuarios de servidores donde el bot está, y el caso que importa —quien
        # se instaló el bot en su cuenta— no está ahí por definición.
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
    except (nextcord.NotFound, nextcord.HTTPException) as exc:
        log.warning("No se pudo resolver al usuario %s: %s", user_id, exc)
        return False

    try:
        await user.send(**kwargs)
    except nextcord.Forbidden as exc:
        codigo = _codigo(exc)
        if codigo == _SIN_GUILD:
            usuarios.marcar_dm(user_id, usuarios.DM_SIN_GUILD, "50278 sin servidor común")
        else:
            # 50007 y cualquier otro 403 se tratan igual: el usuario no nos deja
            # escribirle. Distinguir más no cambia lo que él tiene que hacer.
            usuarios.marcar_dm(user_id, usuarios.DM_CERRADO, f"{codigo or 403} DM cerrados")
        return False
    except nextcord.HTTPException as exc:
        if _codigo(exc) == _DEMASIADO_RAPIDO:
            log.warning("Discord está frenando la apertura de DM (40003): se corta la tanda.")
            raise DemasiadosDM from exc
        # Un 500 de Discord o un corte de red no dicen nada del usuario: no se
        # le marca nada, porque marcarlo "cerrado" por un fallo nuestro le
        # enseñaría un error que no puede arreglar.
        log.warning("Fallo enviando DM a %s: %s", user_id, exc)
        return False

    usuarios.marcar_dm(user_id, usuarios.DM_OK)
    return True


# ---------------------------------------------------------------------- #
# A quién le interesa una partida
# ---------------------------------------------------------------------- #

def destinatarios(nombre_pro: str, liga: str, equipo: str = "") -> list[int]:
    """Ids de quien quiere saber que este jugador ha entrado en partida.

    Tres motivos independientes para recibir el aviso, y basta uno:

    * sigue a **este jugador** por su nombre (`/track Elyoya`);
    * sigue a **este equipo** (`/track t1`), y entonces recibe a cualquiera de sus
      jugadores — el equipo lo trae la propia pasada, del roster;
    * sigue **su liga** entera (`/track lec`), y entonces recibe cualquier partida
      de cualquier jugador de ahí, que es lo que hace el bot en un canal.

    Quien cumpla varios aparece **una vez**. Sin eso, alguien suscrito a Chovy, a
    Gen.G y a la LCK recibiría tres DM idénticos de la misma partida, que es la
    forma más rápida de que desactive los avisos.

    La comparación de nombres ignora mayúsculas: el nick que guarda el usuario lo
    escribió él a mano y el que trae el leaderboard viene de dpm.lol. En los
    equipos pasa lo mismo, y por eso `equipo` se compara también en minúsculas:
    el roster guarda el tricode en mayúsculas (`T1`, `FNC`).
    """
    objetivo = (nombre_pro or "").strip().casefold()
    codigo = (liga or "").strip().casefold()
    tricode = (equipo or "").strip().casefold()

    ids: list[int] = []
    if objetivo:
        for user_id, nicks in usuarios.usuarios_con("jugadores").items():
            if objetivo in {n.casefold() for n in nicks}:
                ids.append(user_id)

    if tricode:
        ya = set(ids)
        for user_id, equipos in usuarios.usuarios_con("equipos").items():
            if user_id not in ya and tricode in {e.casefold() for e in equipos}:
                ids.append(user_id)

    if codigo:
        ya = set(ids)
        for user_id, ligas in usuarios.usuarios_con("ligas").items():
            if user_id not in ya and codigo in {c.casefold() for c in ligas}:
                ids.append(user_id)

    return ids


def alcanzable(user_id: int) -> bool:
    """¿Merece la pena intentar el DM?

    Se saltan los que ya fallaron por no compartir servidor o por tener los DM
    cerrados. No es una optimización: cada intento condenado consume una petición
    de apertura de DM y acerca el 40003 que bloquearía a los que sí funcionan.

    `sin_probar` **sí** se intenta: es el estado de quien acaba de registrarse, y
    su primer aviso es justo el que decide si el producto le sirve.
    """
    return usuarios.estado_dm(user_id) not in (
        usuarios.DM_SIN_GUILD,
        usuarios.DM_CERRADO,
    )


# ---------------------------------------------------------------------- #
# Reparto
# ---------------------------------------------------------------------- #

def clave_dedupe(user_id: int) -> str:
    """Clave de este usuario en el registro de "ya avisado".

    El registro (`notifier.announced_games`) está indexado por canal, y aquí no
    hay canal: el DM se abre solo. Se usa el id del usuario con un prefijo `u`
    para que las dos cosas convivan en el mismo fichero sin poder pisarse. Un id
    de usuario y uno de canal no van a coincidir nunca, pero el prefijo hace que
    al abrir el JSON se vea de un vistazo qué es cada línea, y sin él el día que
    haya que depurar por qué alguien recibió dos avisos no habría forma de saber
    si la entrada era de un canal o de una persona.
    """
    return f"u{user_id}"


async def repartir(bot, ids: list[int], construir) -> list[int]:
    """Manda el mismo aviso a varias personas. Devuelve a quiénes llegó.

    `construir(idioma)` devuelve los `kwargs` del envío para ese idioma. Se pide
    una función y no un mensaje ya hecho porque el embed depende del idioma de
    cada destinatario y los adjuntos **no se pueden reutilizar**: nextcord cierra
    el descriptor del fichero después de enviarlo, así que el segundo envío con
    los mismos `File` muere con `ValueError: seek of closed file`. Quien construye
    ya sabe cachear por idioma y reabrir los adjuntos; aquí solo se pide.

    Los que no reciben el aviso **no se devuelven**, así que el llamante no los
    marca como avisados y se reintentan en la pasada siguiente. Eso importa en el
    caso del 40003: la tanda se corta y a quien se quedó fuera le llega tarde,
    que es mucho mejor que no llegarle nunca.
    """
    entregados: list[int] = []
    if not ids:
        return entregados

    from utils.i18n import idioma_efectivo

    if len(ids) > MAX_POR_TANDA:
        log.warning(
            "Tanda de %d DM por encima del tope (%d): se manda el resto en la "
            "pasada siguiente.", len(ids), MAX_POR_TANDA,
        )
        ids = ids[:MAX_POR_TANDA]

    for user_id in ids:
        if not alcanzable(user_id):
            continue
        try:
            kwargs = construir(idioma_efectivo(user_id))
        except Exception:
            # Un fallo construyendo el mensaje de una persona no puede cortar el
            # reparto a las demás. Se registra con traza porque esto sí es un
            # error nuestro, no una limitación de Discord.
            log.exception("No se pudo construir el aviso para %s", user_id)
            continue

        try:
            if await enviar_dm(bot, user_id, **kwargs):
                entregados.append(user_id)
        except DemasiadosDM:
            break

        await asyncio.sleep(PAUSA)

    return entregados
