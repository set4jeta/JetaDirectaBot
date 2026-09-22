"""Avisos personales: `/seguir`, `/dejarseguir`, `/misavisos`.

Qué añade esto
--------------
Hasta ahora todo el estado del bot era de servidor: un admin ponía un canal con
`/setchannel` y ahí caían los avisos de SoloQ. Eso sigue funcionando igual y no
se toca. Lo que faltaba era el otro caso, que es el que se pidió:

    "puedas pedirle trackear a Elyoya, o Chovy o quien sea que te avise cuando
     está jugando solo él, o que te puedas registrar a varios, o a una liga, y
     que te tire todas las soloq de esa liga"

El almacén (`tracking/soloq/user_config.py`), el envío (`dm_notifier.py`) y el
enganche en la pasada (`active_game_checker._notificar_por_dm`) ya existían.
Esto es lo único que faltaba: la puerta de entrada.

Por qué `/seguir` es un solo comando y no dos
---------------------------------------------
`dual_texto` da **un** argumento de texto, así que `/seguir <valor>` decide él
mismo qué le han dado: si `leagues.resolver(valor)` acierta es una liga, y si no
es el nick de un pro. No es un atajo por pereza, es lo que hace que el comando se
pueda explicar en una línea; `/seguir` y `/seguirliga` serían dos comandos que la
gente confundiría para hacer lo mismo.

`resolver` pasa por `ALIAS`, así que `korea`, `superliga` y `LEC ` caen en su
liga. El único choque posible sería un pro cuyo nick fuera igual que un código de
liga o que uno de sus alias, y no hay ninguno.

Lo que este módulo **no** hace: validar el nick contra dpm.lol
--------------------------------------------------------------
Se puede saber si un pro existe pidiendo `/v1/pros/<nombre>`, pero esa llamada
va por cloudscraper (aiohttp recibe un 403 de Cloudflare) con 20 s de timeout, y
aun así **no dice en qué liga juega**: `BootcampPlayer.from_pro_api` recibe
`league` como parámetro del llamante, no del API. Es decir, la petición costaría
segundos y no resolvería la pregunta que importa.

Así que la comprobación se hace contra `accounts_from_teams.json`, que es lo que
el bot está rastreando de verdad: gratis, en disco y sin red. Un nick que no esté
ahí **se guarda igual** —el usuario puede estar suscribiéndose a alguien de una
liga que aún no se descarga— pero se le dice claramente que todavía no le va a
llegar nada, con el porqué y con la salida (`/info <nick>` para comprobar el nick,
`/seguir <liga>` para que se empiece a rastrear). Guardarlo en silencio sería
prometer un aviso que no existe.

Sobre el idioma
---------------
"se le pregunta el idioma o algo al principio y de ahí todo se le da en ese
idioma". Aquí eso no es un adorno: `dm_notifier.repartir` resuelve el idioma con
`idioma_efectivo(user_id)` **sin servidor y sin locale**, porque un DM no tiene
ninguno de los dos. Sin idioma propio guardado eso cae al español siempre, así
que un inglés que se suscribiera desde un servidor inglés recibiría sus avisos en
español para siempre.

Se arregla en el único momento en el que existe la señal: al registrarse se
guarda su idioma a partir del locale de su cliente de Discord (y si no, del
idioma del servidor donde lo pidió), y se le dice en qué idioma le va a hablar y
cómo cambiarlo con `/lang`. Una pregunta con botones habría sido más vistosa,
pero el resultado que hace falta es que su idioma quede guardado, y esto lo deja
guardado sin añadir una vista que caduca.

Por qué las respuestas son privadas
-----------------------------------
`res.send_privado`: a quién sigue una persona y si tiene los DM cerrados no le
importa al canal, y en un servidor sería ruido y además expondría su
configuración. En la forma `!` no hay mensajes efímeros, así que ahí se manda
normal (ver `core/responder.py`).
"""

from __future__ import annotations

import asyncio
import time

from nextcord.ext import commands

from core.dual_command import dual, dual_texto
from core.responder import Respuesta
from tracking.soloq import user_config as usuarios
from tracking.soloq.leagues import LIGAS, Liga, resolver
from tracking.soloq.plans import plan_de_usuario
from utils.branding import SOPORTE_URL
from utils.i18n import (
    IDIOMA_POR_DEFECTO,
    IDIOMAS,
    establecer_idioma_usuario,
    idioma_de,
    idioma_de_locale,
    idioma_de_usuario,
)
from utils.logger import get_logger

log = get_logger("core.user_alerts")

#: Palabras que borran todas las suscripciones de golpe. Van en los dos idiomas
#: y no pasan por el catálogo a propósito: es una entrada del usuario, y quien
#: escriba `all` teniendo el bot en español espera que funcione igual.
_TODO = {"todo", "todos", "todas", "all", "everything", "*"}

#: Ejes que guardan códigos de liga. Se usa para que `/dejarseguir korea` quite
#: `lck`, que es lo que hay guardado.
_EJES_DE_LIGA = ("ligas", "partidos_ligas")

#: Ejes que guardan nombres propios: nicks de pro, tricodes de equipo y tricodes
#: de partido. Un valor que no es una liga puede estar en cualquiera de los tres,
#: así que `/untrack` los mira todos en vez de exigirle al usuario que recuerde
#: por qué comando se suscribió.
_EJES_DE_NOMBRE = ("jugadores", "equipos", "partidos_equipos")


# ---------------------------------------------------------------------- #
# Ayudas
# ---------------------------------------------------------------------- #

def _pro_rastreado(nombre: str):
    """El jugador rastreado que coincide con este nombre, o `None`.

    Se busca en `accounts_from_teams.json` —lo que el bot está barriendo ahora
    mismo— y no contra dpm.lol. Los motivos, medidos:

    * `/v1/pros/<nombre>` va por cloudscraper con 20 s de timeout y hasta 3
      reintentos con `sleep(2)`; bloquea o tarda, y un comando no puede hacer eso.
    * y aunque respondiera, **no trae la liga**: `BootcampPlayer.from_pro_api`
      recibe `league` del llamante. Así que no contestaría la pregunta que
      importa, que es si a esta persona le va a llegar un aviso.

    Lo que hay en disco sí la contesta: si el nick está ahí, sus cuentas se
    consultan en cada pasada.

    Se compara con `name` y con `display_name` porque el usuario puede escribir
    cualquiera de los dos, pero lo que se guarda es siempre `name`: es el valor
    con el que `dm_notifier.destinatarios` compara (viene de la pasada, línea 404
    de `active_game_checker`), y guardar el otro dejaría una suscripción que
    nunca coincide.
    """
    from tracking.soloq.accounts_io import load_tracked_accounts

    objetivo = (nombre or "").strip().casefold()
    if not objetivo:
        return None
    try:
        for jugador in load_tracked_accounts():
            nombres = {
                (getattr(jugador, "name", "") or "").casefold(),
                (getattr(jugador, "display_name", "") or "").casefold(),
            }
            if objetivo in nombres - {""}:
                return jugador
    except Exception:
        # Un JSON a medio escribir no puede impedir que alguien se suscriba: se
        # guarda igual y se le avisa de que no se ha podido comprobar.
        log.exception("No se pudo leer accounts_from_teams.json para validar %r", nombre)
    return None


def _equipo_rastreado(nombre: str) -> tuple[str, str, str] | None:
    """El equipo que coincide con lo escrito: `(tricode, nombre, liga)`.

    Se busca en el roster ya descargado —lo que el bot está barriendo de verdad—
    y se compara **el tricode y el nombre completo** (`T1` y `T1`, `FNC` y
    `Fnatic`): la gente escribe las dos cosas y ninguna es más correcta.

    Lo que se guarda es el tricode, porque es lo que trae la pasada en
    `player.team` y con lo que compara `dm_notifier.destinatarios`. Guardar el
    nombre completo dejaría una suscripción que no coincide nunca.

    Devuelve `None` si no hay ningún equipo así, y entonces quien llama trata el
    valor como un nick.
    """
    from tracking.soloq.accounts_io import load_tracked_accounts

    objetivo = (nombre or "").strip().casefold()
    if not objetivo:
        return None
    try:
        for jugador in load_tracked_accounts():
            tricode = (getattr(jugador, "team", "") or "").strip()
            completo = (getattr(jugador, "team_name", "") or "").strip()
            if objetivo in {tricode.casefold(), completo.casefold()} - {""}:
                return (
                    tricode,
                    completo or tricode,
                    (getattr(jugador, "league", "") or "").strip(),
                )
    except Exception:
        log.exception("No se pudo leer el roster para validar el equipo %r", nombre)
    return None


def _asegurar_idioma(res: Respuesta) -> str | None:
    """Guarda el idioma de esta persona la primera vez. Devuelve el código nuevo.

    `None` si ya tenía uno elegido, que es la señal de "no hace falta decirle
    nada". Se llama al registrarse y no en cada comando porque quien ya eligió con
    `/lang` no debe verse cambiado por haber usado el bot desde otro servidor.

    Por qué es necesario y no cosmético: el reparto de avisos llama a
    `idioma_efectivo(user_id)` **sin servidor y sin locale** —en un DM no existe
    ninguno de los dos—, así que sin idioma propio guardado todos los avisos
    salen en español. La única señal disponible es el locale del cliente, y solo
    llega en las interacciones; en la forma `!` se cae al idioma del servidor
    donde escribió, que es la mejor conjetura que hay ahí.
    """
    if res.autor_id is None or idioma_de_usuario(res.autor_id):
        return None

    codigo = (
        idioma_de_locale(res.locale)
        or (idioma_de(res.guild_id) if res.guild_id else None)
        or IDIOMA_POR_DEFECTO
    )
    establecer_idioma_usuario(res.autor_id, codigo)
    return codigo


def _lista_ligas(codigos: list[str]) -> str:
    """`["lec"]` -> `` `lec` LEC ``. Igual que en `/ligas`: interesa el código.

    Con 20 ligas la forma larga («**Nombre** (Región)») se come el mensaje y
    encima no enseña lo único que hay que teclear.
    """
    partes = [f"`{c}` {LIGAS[c].nombre}" for c in codigos if c in LIGAS]
    return " · ".join(partes) or "—"


def _ligas_con_cuentas() -> set[str]:
    """Ligas de las que el bot tiene cuentas descargadas ahora mismo.

    No es lo mismo que `ligas_en_uso()`, y la diferencia es justo lo que hay que
    contarle al usuario. `ligas_en_uso()` es lo que **habría que** descargar;
    esto es lo que está descargado. Entre las dos hay hasta 24 h, porque los
    rosters los refresca `background_tasks.actualizar_accounts_diario`, que es un
    `@tasks.loop(hours=24)`.

    Además evita un error de orden: si esto se preguntara con `ligas_en_uso()`
    después de guardar la suscripción, la liga recién añadida ya estaría en la
    unión y el aviso de "todavía no" no saldría nunca.
    """
    from tracking.soloq.accounts_io import load_tracked_accounts

    try:
        return {
            (getattr(j, "league", "") or "").strip().lower()
            for j in load_tracked_accounts()
        } - {""}
    except Exception:
        log.exception("No se pudo leer accounts_from_teams.json")
        return set()


def _aviso_liga(liga: Liga, _) -> str:
    """Lo que hay que advertir de una liga concreta, o cadena vacía.

    Tres cosas distintas, y ninguna es un detalle:

    * `rastreable=False` (LPL): la API de Riot no cubre los servidores chinos, así
      que de esa liga **nunca** va a salir un aviso de partida. Suscribirse sin
      saberlo es esperar para siempre.
    * el bot todavía no tiene cuentas de esa liga: la suscripción la mete en la
      unión que hay que descargar, pero los rosters se refrescan en un loop de
      24 h, así que hasta esa pasada no hay nada que vigilar.
    * `plataforma_mixta`: sus jugadores están repartidos por varios servidores y
      la cobertura depende de cada cuenta.
    """
    if not liga.rastreable:
        return _("seguir.liga_no_rastreable", liga=liga.nombre)
    if liga.codigo not in _ligas_con_cuentas():
        return _("seguir.liga_pendiente", liga=liga.nombre)
    if liga.plataforma_mixta:
        return _("seguir.liga_mixta", liga=liga.nombre)
    return ""


# ---------------------------------------------------------------------- #
# /seguir
# ---------------------------------------------------------------------- #

async def _seguir_cuenta_suelta(res: Respuesta, texto: str) -> None:
    """`/track Nombre#TAG [region]`: sigue una cuenta concreta, no un roster.

    Es el caso de la cuenta de un streamer, de un smurf o de alguien que no está
    en ningún equipo. La cuenta se guarda en su propio fichero
    (`cuentas_sueltas.json`) y se le añade a la pasada **siempre**, sin depender
    de ninguna liga: por eso no gasta cupo de ligas, solo el de jugadores.

    La región es opcional y va como segundo trozo (`eu`, `na`, `kr`…). Se admite
    porque la plataforma **no la da ningún endpoint de Riot**: hay que probarla, y
    con el atajo se prueban una o dos en vez de siete. Sin atajo, el bot le
    pregunta el clúster a Riot para acotar; el resultado queda guardado, así que
    esto se paga una sola vez.
    """
    _ = res.traductor()

    if res.autor_id is None:
        await res.error(_("avisos.sin_usuario"))
        return

    trozos = texto.split()
    riot_id = trozos[0]
    atajo = trozos[1] if len(trozos) > 1 else ""

    from tracking.soloq import cuentas_sueltas
    from tracking.soloq.accounts_io import guardar_cuenta_suelta

    try:
        jugador, error = await cuentas_sueltas.resolver(riot_id, atajo)
    except Exception:
        # `resolver` ya se protege, pero esto corre dentro de una interacción:
        # una traza aquí dejaría al usuario sin respuesta.
        log.exception("Fallo resolviendo la cuenta suelta %r", riot_id)
        jugador, error = None, "avisos.cuenta_sin_respuesta"

    if jugador is None:
        await res.send_privado(_(error or "error.generico"))
        return

    if not guardar_cuenta_suelta(jugador):
        await res.error(_("error.generico"))
        return

    resultado, tope = usuarios.agregar(res.autor_id, "jugadores", jugador.name)
    if resultado == "cupo":
        await res.send_privado(
            _("seguir.cupo_jugadores", n=tope)
            + "\n"
            + _("seguir.cupo_salida", plan=plan_de_usuario(res.autor_id).nombre)
        )
        return
    if resultado == "invalido":
        await res.error(_("error.generico"))
        return

    plataforma = jugador.accounts[0].platform if jugador.accounts else "?"
    lineas = [
        _("seguir.ok_cuenta_suelta", jugador=jugador.name, plataforma=plataforma)
    ]
    lineas.extend(_cola_registro(res, _))
    await res.send_privado("\n".join(lineas))


#: Marca de tiempo del último alta de roster lanzada desde un comando.
#: `time.monotonic` y no `time.time` porque lo único que se mide es un intervalo.
_ultimo_alta = 0.0

#: Segundos mínimos entre dos altas. Sin esto, quien escriba `/track lck` varias
#: veces (o lo pruebe en bucle) dispara un scraping de la liga entera cada vez.
ESPERA_ENTRE_ALTAS = 600.0


def _descargar_roster_en_fondo(codigo: str) -> bool:
    """Trae el roster de esta liga ya, sin bloquear el comando. True si lo lanzó.

    Por qué hace falta
    ------------------
    Seguir una liga solo la mete en `ligas_en_uso()`, y quien descarga los
    rosters con esa lista es la tarea diaria: hasta 24 h de silencio para alguien
    que acaba de escribir `/track lck` y está esperando su primer aviso. Con esto
    las cuentas entran en el fichero en minutos, y la pasada siguiente (30 s) ya
    las consulta.

    Se hace con `asyncio.to_thread` porque `refrescar_ligas` va por `cloudscraper`
    (bloquea) y con `create_task` para no meter minutos de scraping dentro de la
    respuesta a una interacción, que caduca a los 15 s. Si no hay bucle de
    eventos no se pierde nada: la tarea diaria lo hará igual.
    """
    global _ultimo_alta
    ahora = time.monotonic()
    if ahora - _ultimo_alta < ESPERA_ENTRE_ALTAS:
        return False
    _ultimo_alta = ahora

    from tracking.soloq.accounts_from_teams import refrescar_ligas

    async def _tarea() -> None:
        try:
            await asyncio.to_thread(refrescar_ligas, [codigo])
        except Exception:
            # Un fallo aquí no puede tumbar el comando ni la pasada: la tarea
            # diaria lo reintenta con todas las ligas en uso.
            log.exception("No se pudo añadir el roster de %s", codigo)

    try:
        asyncio.create_task(_tarea())
    except RuntimeError:
        log.warning(
            "Sin bucle de eventos: el roster de %s se añadirá en la tarea diaria.",
            codigo,
        )
        return False
    return True


async def _cuerpo_seguir(res: Respuesta, valor: str) -> None:
    """`/seguir <pro o liga>`: suscribe a esta persona a avisos por DM.

    Sin argumento no da error: enseña qué sigue, que es lo que hace `/ligas` y lo
    que espera quien escribe el comando para ver qué opciones tiene. Un comando
    que solo sabe contestar "te falta un argumento" obliga a leer la ayuda para
    averiguar qué se le puede pedir.
    """
    _ = res.traductor()

    if res.autor_id is None:
        await res.error(_("avisos.sin_usuario"))
        return

    texto = (valor or "").strip()
    if not texto:
        await _mostrar_estado(res, _)
        return

    # Una cuenta suelta (`Nombre#TAG`, con la región opcional detrás). Se mira
    # antes que nada porque un Riot ID no puede ser una liga, ni un pro del
    # roster, ni un equipo: lleva `#` y eso no lo tiene ninguno de los tres.
    if "#" in texto:
        await _seguir_cuenta_suelta(res, texto)
        return

    liga = resolver(texto)
    # Tres cosas se pueden escribir aquí, y el orden de comprobación importa:
    # liga (por nombre, alias o código) → jugador del roster → equipo del roster.
    # De lo que se guarda: de una liga su código canónico (`korea` -> `lck`),
    # porque es con lo que compara el reparto; de un pro su nombre tal cual lo
    # trae la pasada; de un equipo su tricode (`T1`), que es lo que trae la
    # pasada en `player.team`.
    jugador = None if liga else _pro_rastreado(texto)
    equipo = None if (liga or jugador is not None) else _equipo_rastreado(texto)

    if liga:
        eje, guardar = "ligas", liga.codigo
    elif jugador is not None:
        eje, guardar = "jugadores", (getattr(jugador, "name", None) or texto)
    elif equipo is not None:
        eje, guardar = "equipos", equipo[0]
    else:
        # Ni liga, ni pro ni equipo del roster: se guarda como nick igual que
        # antes —puede ser alguien de una liga que aún no se ha descargado— y se
        # le dice claramente que todavía no le va a llegar nada.
        eje, guardar = "jugadores", texto

    resultado, tope = usuarios.agregar(res.autor_id, eje, guardar)

    if resultado == "repetido":
        await res.send_privado(_("seguir.repetido", valor=guardar))
        return
    if resultado == "cupo":
        clave = "seguir.cupo_ligas" if liga else "seguir.cupo_jugadores"
        await res.send_privado(
            _(clave, n=tope) + "\n" + _("seguir.cupo_salida", plan=plan_de_usuario(res.autor_id).nombre)
        )
        return
    if resultado != "añadido":
        await res.error(_("error.generico"))
        return

    # ---- Guardado. Ahora hay que decir qué va a pasar de verdad ---------- #
    lineas: list[str] = []
    if liga:
        lineas.append(_("seguir.ok_liga", liga=liga.nombre, codigo=liga.codigo))
        aviso = _aviso_liga(liga, _)
        if aviso:
            lineas.append(aviso)
        # Si la liga no se estaba rastreando, sus cuentas no están en disco y no
        # habrá avisos hasta que lo estén: se lanza la descarga aquí mismo. Solo
        # para ligas rastreables — de la LPL no hay servidor de Riot que cubra
        # sus partidas, así que bajar sus cuentas sería gastar por nada.
        if getattr(liga, "rastreable", True) and _descargar_roster_en_fondo(liga.codigo):
            lineas.append(_("seguir.liga_descargando"))
    elif jugador is not None:
        lineas.append(_(
            "seguir.ok_jugador",
            jugador=guardar,
            equipo=getattr(jugador, "team", "") or "—",
            liga=(getattr(jugador, "league", "") or "").upper() or "—",
        ))
    elif equipo is not None:
        lineas.append(_(
            "seguir.ok_equipo",
            equipo=equipo[0],
            nombre=equipo[1],
            liga=(equipo[2] or "").upper() or "—",
        ))

    # Y los **partidos oficiales**, en los ejes aparte. Se añaden aquí y no en un
    # comando nuevo porque para el usuario "seguir la LEC" o "seguir a T1" es una
    # sola idea: quiere enterarse de lo que pasa con eso, juegue SoloQ o juegue
    # liga. Los ejes siguen separados por dentro (no tienen cupo, no cuestan
    # peticiones a Riot y se quitan igual con `/untrack`), así que quien solo
    # quiera una de las dos cosas puede quitarla y la otra se queda.
    if liga or equipo is not None:
        eje_partidos = "partidos_ligas" if liga else "partidos_equipos"
        valor_partidos = liga.codigo if liga else equipo[0]  # type: ignore[index]
        if usuarios.agregar(res.autor_id, eje_partidos, valor_partidos)[0] == "añadido":
            lineas.append(_("seguir.ok_partidos", valor=valor_partidos))
    else:
        # El caso importante: se ha guardado, pero no hay nada rastreando a esta
        # persona, así que no le va a llegar ningún aviso y hay que decirlo con
        # las dos salidas posibles.
        lineas.append(_("seguir.ok_jugador_sin_datos", jugador=guardar))
        lineas.append(_("seguir.sin_datos_salida", jugador=guardar))

    lineas.extend(_cola_registro(res, _))
    await res.send_privado("\n".join(lineas))


def _cola_registro(res: Respuesta, _) -> list[str]:
    """Lo que hay que decir la primera vez que alguien se suscribe.

    Dos cosas, y las dos son consecuencia de cómo funciona Discord de verdad:

    1. **En qué idioma le van a llegar los avisos.** Se acaba de decidir por él a
       partir del locale de su cliente, así que se le dice y se le da `/lang`. Si
       no, un usuario cuyo cliente esté en un idioma que el bot no habla recibiría
       español sin entender por qué.
    2. **Que el DM puede no llegar.** Un bot no puede escribir a alguien con quien
       no comparte servidor (50278), y quien solo se ha instalado la app en su
       cuenta está exactamente en ese caso. Se avisa **al suscribirse**, no cuando
       el aviso falla, porque cuando falla el usuario no está mirando: lo único
       que nota es que el bot no funciona.

    El estado nuevo es siempre `sin_probar` (lo siembra `user_config.agregar`), así
    que aquí no se puede afirmar que el DM llegue; lo que se dice es cómo
    comprobarlo, y `/misavisos` es quien lo prueba de verdad.
    """
    cola: list[str] = []

    nuevo = _asegurar_idioma(res)
    if nuevo:
        cola.append(_("avisos.idioma_fijado", idioma=IDIOMAS.get(nuevo, nuevo)))

    estado = usuarios.estado_dm(res.autor_id)
    if estado in (usuarios.DM_SIN_GUILD, usuarios.DM_CERRADO):
        cola.append(_pista_dm(estado, _))
    elif estado == usuarios.DM_SIN_PROBAR:
        cola.append(_("avisos.dm_sin_probar"))
    return cola


def _pista_dm(estado: str, _) -> str:
    """Qué tiene que hacer el usuario para que el DM le llegue.

    Los dos fallos tienen solución, pero **no la misma**, y por eso no se
    colapsan en un "no se pudo enviar":

    * `cerrado` (50007) lo arregla él en los ajustes de privacidad del servidor
      donde estemos los dos;
    * `sin_guild` (50278) solo se arregla compartiendo un servidor con el bot, así
      que el mensaje lleva el enlace de soporte si está configurado. Es la misma
      solución que usa Dorans-bot para sus DM de pago.
    """
    if estado == usuarios.DM_CERRADO:
        return _("avisos.dm_cerrado")
    if SOPORTE_URL:
        return _("avisos.dm_sin_guild_enlace", url=SOPORTE_URL)
    return _("avisos.dm_sin_guild")


# ---------------------------------------------------------------------- #
# /dejarseguir
# ---------------------------------------------------------------------- #

async def _cuerpo_dejarseguir(res: Respuesta, valor: str) -> None:
    """`/dejarseguir <pro | liga | todo>`.

    Busca el valor en los cuatro ejes en vez de pedirle al usuario que diga en
    cuál estaba. Quien escribió `/seguir t1` no tiene por qué recordar si eso
    quedó en "equipos de partidos" o en "jugadores", y un comando que responde "no
    seguías a t1" cuando sí lo sigue es peor que uno que lo busca.

    `todo` borra la suscripción entera. No es solo comodidad: alguien suscrito a
    una liga de 80 jugadores no tiene forma práctica de darse de baja uno a uno, y
    la política de privacidad publicada promete una vía de borrado.
    """
    _ = res.traductor()

    if res.autor_id is None:
        await res.error(_("avisos.sin_usuario"))
        return

    texto = (valor or "").strip()
    if not texto:
        await res.send_privado(_("dejarseguir.falta_valor"))
        return

    if texto.casefold() in _TODO:
        cuantas = usuarios.vaciar(res.autor_id)
        if not cuantas:
            await res.send_privado(_("dejarseguir.nada_que_borrar"))
        else:
            await res.send_privado(_("dejarseguir.todo", n=cuantas))
        return

    liga = resolver(texto)
    # De una liga se quita su código canónico —es lo que está guardado— y de un
    # nombre lo que escribió el usuario, que `user_config.quitar` compara sin
    # distinguir mayúsculas. Si escribió el Riot ID completo (`Nombre#TAG`), lo
    # que hay guardado es solo el nombre: sin esto, `/untrack MIDKING#7273`
    # diría "no lo seguías" con la suscripción delante.
    if "#" in texto:
        texto = texto.split("#", 1)[0].strip()
    objetivo = liga.codigo if liga else texto
    ejes = _EJES_DE_LIGA if liga else _EJES_DE_NOMBRE

    quitados = [eje for eje in ejes if usuarios.quitar(res.autor_id, eje, objetivo)]

    # Y si era una cuenta suelta, se va también del fichero de cuentas: si no,
    # la pasada la seguiría consultando en cada vuelta para nadie. Va aquí y no
    # antes porque el texto sin `#` es lo que se guardó como nombre del jugador.
    suelta_quitada = False
    if not liga:
        from tracking.soloq.accounts_io import quitar_cuenta_suelta

        try:
            suelta_quitada = quitar_cuenta_suelta(texto)
        except Exception:
            log.exception("No se pudo quitar la cuenta suelta %r", texto)

    if not quitados and not suelta_quitada:
        await res.send_privado(_("dejarseguir.no_estaba", valor=texto))
        return

    etiqueta = f"{liga.nombre} (`{liga.codigo}`)" if liga else objetivo
    await res.send_privado(_("dejarseguir.ok", valor=etiqueta))


# ---------------------------------------------------------------------- #
# /misavisos
# ---------------------------------------------------------------------- #

def _bloque_ejes(datos: dict, _) -> list[str]:
    """Las cuatro listas de un usuario, con lo guardado que no se está usando.

    `resumen()` da `en_uso` y `guardados` aparte, y aquí se enseñan los dos
    cuando no coinciden. Es el mismo criterio que en `/canales` y `/ligas`: quien
    baja de plan conserva su configuración y solo deja de aplicarse la parte que
    excede el cupo, así que si solo se enseñara `en_uso` los demás parecerían
    borrados y los volvería a añadir para nada.
    """
    lineas: list[str] = []
    for eje, clave in (
        ("jugadores", "misavisos.eje_jugadores"),
        ("equipos", "misavisos.eje_equipos"),
        ("ligas", "misavisos.eje_ligas"),
        ("partidos_ligas", "misavisos.eje_partidos_ligas"),
        ("partidos_equipos", "misavisos.eje_partidos_equipos"),
    ):
        bloque = datos.get(eje) or {}
        en_uso = list(bloque.get("en_uso") or [])
        guardados = list(bloque.get("guardados") or [])
        tope = int(bloque.get("tope") or 0)

        if eje in _EJES_DE_LIGA:
            texto = _lista_ligas(en_uso)
        else:
            texto = ", ".join(f"**{v}**" for v in en_uso) or "—"

        cuenta = f" ({len(en_uso)}/{tope})" if tope else ""
        lineas.append(f"{_(clave)}{cuenta}: {texto}")

        fuera = [v for v in guardados if v not in en_uso]
        if fuera:
            fuera_txt = (
                _lista_ligas(fuera) if eje in _EJES_DE_LIGA else ", ".join(fuera)
            )
            lineas.append(_("misavisos.fuera_de_cupo", valores=fuera_txt))
    return lineas


async def _mostrar_estado(res: Respuesta, _) -> None:
    """Lo que `/seguir` sin argumento contesta: qué sigues y cómo añadir más.

    Sin argumento no se da un error. Quien escribe `/seguir` a secas está
    preguntando qué puede pedir, y contestarle "falta el argumento" le obliga a ir
    a `/help` para averiguar lo mismo.
    """
    datos = usuarios.resumen(res.autor_id)

    if not datos["registrado"]:
        await res.send_privado("\n".join([
            f"**{_('misavisos.titulo')}**",
            _("misavisos.vacio"),
            "",
            _("seguir.como_usar"),
        ]))
        return

    lineas = [f"**{_('misavisos.titulo')}**"]
    lineas.extend(_bloque_ejes(datos["ejes"], _))
    lineas.append("")
    lineas.append(_("seguir.como_usar"))
    await res.send_privado("\n".join(lineas))


async def _cuerpo_misavisos(res: Respuesta) -> None:
    """`/misavisos`: qué sigues, en qué idioma, y **si el DM te llega de verdad**.

    La comprobación del DM es la razón de ser del comando. La entrega no está
    garantizada: un bot no puede escribir a alguien con quien no comparte ningún
    servidor (50278) y quien solo se instaló la app en su cuenta está en ese caso,
    así que un panel que dijera "suscrito a Elyoya ✅" sin más sería mentira la
    mitad de las veces.

    Se prueba solo cuando el estado **no** es `ok`, por dos motivos: a quien ya le
    llega no hace falta molestarle con un DM de prueba cada vez que mira su
    configuración, y cada apertura de DM acerca el 40003 que bloquearía los avisos
    de todos. Y sí se reintenta cuando falló, porque eso es exactamente lo que
    hace alguien que acaba de abrir sus DM o de entrar en el servidor de soporte.
    """
    _ = res.traductor()

    if res.autor_id is None:
        await res.error(_("avisos.sin_usuario"))
        return

    datos = usuarios.resumen(res.autor_id)

    if not datos["registrado"]:
        await res.send_privado("\n".join([
            f"**{_('misavisos.titulo')}**",
            _("misavisos.vacio"),
            "",
            _("seguir.como_usar"),
        ]))
        return

    lineas = [f"**{_('misavisos.titulo')}**"]
    lineas.extend(_bloque_ejes(datos["ejes"], _))

    plan = datos["plan"]
    lineas.append("")
    lineas.append(_("misavisos.plan", plan=plan.nombre))
    idioma = datos["idioma"]
    lineas.append(_(
        "misavisos.idioma",
        idioma=IDIOMAS.get(idioma, idioma) if idioma else _("misavisos.idioma_sin_elegir"),
    ))

    estado = await _comprobar_dm(res, datos["dm"])
    lineas.append(_estado_dm_texto(estado, _))
    if estado != usuarios.DM_OK:
        lineas.append(_pista_dm(estado, _))

    lineas.append("")
    lineas.append(_("misavisos.como_usar"))
    await res.send_privado("\n".join(lineas))


async def _comprobar_dm(res: Respuesta, estado: str) -> str:
    """Intenta un DM de prueba si hace falta. Devuelve el estado que queda.

    `enviar_dm` es quien clasifica y guarda el resultado en `user_config`, así que
    aquí solo hay que provocarlo y volver a leer. Si no se puede resolver el bot
    —`Respuesta` lo saca de `client` o de `bot` según el origen— se devuelve el
    estado que había: enseñar lo último que se sabe es mejor que no decir nada.
    """
    if estado == usuarios.DM_OK:
        return estado

    bot = res.bot
    if bot is None:
        log.warning("No se pudo obtener el bot desde %s", type(res.origen).__name__)
        return estado

    from tracking.soloq.dm_notifier import DemasiadosDM, enviar_dm

    _ = res.traductor()
    try:
        await enviar_dm(bot, res.autor_id, content=_("misavisos.dm_prueba"))
    except DemasiadosDM:
        # Discord está frenando la apertura de DM. No dice nada del usuario, así
        # que no se toca su estado.
        log.warning("40003 al probar el DM de %s", res.autor_id)
        return estado
    except Exception:
        log.exception("Fallo probando el DM de %s", res.autor_id)
        return estado

    return usuarios.estado_dm(res.autor_id)


def _estado_dm_texto(estado: str, _) -> str:
    return _({
        usuarios.DM_OK: "misavisos.dm_ok",
        usuarios.DM_CERRADO: "misavisos.dm_cerrado",
        usuarios.DM_SIN_GUILD: "misavisos.dm_sin_guild",
    }.get(estado, "misavisos.dm_sin_probar"))


# ---------------------------------------------------------------------- #
# Registro
# ---------------------------------------------------------------------- #

def register_user_alerts_commands(bot: commands.Bot) -> None:
    """Los comandos personales, en alcance global.

    Global es el punto: `dual_texto` y `dual` sin `permiso` derivan
    `integration_types` con `user_install` y `contexts` con `bot_dm` y
    `private_channel`, que es lo que hace que estos comandos existan para alguien
    que se ha instalado la app en su cuenta y no solo dentro de un servidor donde
    el bot esté. Sin eso, unos comandos de suscripción personal solo se podrían
    usar desde un servidor, que es justo lo contrario de lo que son.

    `/track` y `/untrack` son alias de `/seguir` y `/dejarseguir`: **el mismo
    cuerpo**, registrado con otro nombre. No se duplica nada —ni el guardado, ni
    los cupos, ni el reparto de avisos—, así que quien use `/track` y quien use
    `/seguir` acaban en la misma lista. Se añaden porque "track" es la palabra
    que la gente escribe por defecto y la que se busca en inglés; `seguir` se
    mantiene porque ya hay gente suscrita con ella y renombrar un comando rompe
    a quien lo tenía guardado en sus atajos.
    """
    dual_texto(
        bot,
        "seguir",
        "cmd.seguir.desc",
        _cuerpo_seguir,
        arg_nombre="cmd.seguir.arg",
        arg_desc="cmd.seguir.arg_desc",
        requerido=False,
    )
    dual_texto(
        bot,
        "dejarseguir",
        "cmd.dejarseguir.desc",
        _cuerpo_dejarseguir,
        arg_nombre="cmd.dejarseguir.arg",
        arg_desc="cmd.dejarseguir.arg_desc",
        requerido=False,
    )
    dual_texto(
        bot,
        "track",
        "cmd.track.desc",
        _cuerpo_seguir,
        arg_nombre="cmd.track.arg",
        arg_desc="cmd.track.arg_desc",
        requerido=False,
    )
    dual_texto(
        bot,
        "untrack",
        "cmd.untrack.desc",
        _cuerpo_dejarseguir,
        arg_nombre="cmd.untrack.arg",
        arg_desc="cmd.untrack.arg_desc",
        requerido=False,
    )
    dual(bot, "misavisos", "cmd.misavisos.desc", _cuerpo_misavisos)







