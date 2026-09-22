"""Qué sigue cada **usuario** y por dónde se le avisa.

Por qué existe este módulo
--------------------------
Todo el estado del bot estaba indexado por servidor: los canales de aviso
(`notify_config.json`), las ligas (`leagues_config.json`), el idioma
(`idiomas_config.json`) y el plan (`plans_config.json`). Eso cubre el caso "un
servidor de comunidad con un canal de avisos", que sigue siendo válido y **no se
toca**, pero deja fuera al que instala el bot en su propia cuenta y quiere que le
avisen a él: seguir solo a Elyoya, o a Chovy, o a cuatro jugadores, o a una liga
entera, y recibirlo en su chat privado.

Este fichero es el eje que faltaba: `{user_id: qué sigue}`. Es **aditivo**. La
pasada del tracker sigue siendo una y global; lo único que cambia es que al final,
además de repartir a los canales de los servidores, reparte a los DM de los
usuarios suscritos.

Lo que se guarda de cada usuario
--------------------------------
    {
      "331111111111111111": {
        "idioma": "es",
        "jugadores": ["Elyoya", "Chovy"],   # SoloQ, por nombre de pro
        "ligas": ["lec"],                   # SoloQ, liga entera
        "partidos_ligas": ["lck"],          # partidos oficiales, por liga
        "partidos_equipos": ["T1"],         # partidos oficiales, por equipo
        "dm": {"estado": "ok", "visto": 1756800000, "motivo": ""},
        "creado": 1756800000
      }
    }

Los cuatro ejes de suscripción son independientes a propósito: seguir la SoloQ de
la LEC no implica que te interesen sus partidos oficiales, y seguir los partidos
de T1 no implica querer las 80 cuentas de SoloQ de la LCK a las tres de la
mañana. Mezclarlos habría hecho el producto más simple de programar y peor de
usar.

Vive en `tracking/soloq/` aunque también guarde suscripciones de esports, por lo
mismo que `idiomas_config.json`, que es de todo el bot y está aquí: es donde
están los módulos de configuración. Moverlo todo a un paquete propio es
refactor, no función, y se hará cuando toque.

Sobre el estado del DM (el campo `dm`)
--------------------------------------
Esto no es telemetría: es la diferencia entre que el producto funcione o no, y
está aquí por una limitación de Discord que se comprobó antes de escribir una
línea. **Un bot no puede abrir un DM a un usuario con el que no comparte ningún
servidor.** La instalación por usuario ("Add to My Apps") concede solo
`applications.commands` con `permissions: 0`, así que un usuario que únicamente
haya hecho eso no es alcanzable: `POST /users/@me/channels` puede incluso
devolver el canal, y el envío falla después con **50278 — "Cannot send messages
to this user due to having no mutual guilds"**. También aplica el clásico
**50007** cuando el usuario tiene los DM cerrados o ha bloqueado la app, y
**40003** si se abren demasiados DM demasiado rápido.

Lo que sí funciona sin excepción es responder a una interacción, pero ese camino
caduca a los 15 minutos y no sirve para un aviso que llega cuando llega. Por eso
el aviso por DM **no se promete: se comprueba**. `estado` tiene cuatro valores y
cada uno tiene una consecuencia distinta en la interfaz:

* `"ok"`         — se ha enviado al menos un DM con éxito.
* `"sin_probar"` — se acaba de registrar y todavía no se ha intentado.
* `"cerrado"`    — 50007: el usuario tiene los DM cerrados. Lo arregla él.
* `"sin_guild"`  — 50278: no compartimos servidor. Lo arregla entrando en uno.

La suscripción **no se borra** cuando falla el DM. Si un usuario cierra los DM
una semana y los reabre, sus jugadores siguen ahí. Borrar en el fallo convertiría
un problema de entrega temporal en pérdida de datos, que es el mismo criterio por
el que `channel_config` recorta al leer en vez de borrar al bajar de plan.

Sobre los cupos
---------------
Se aplican **al leer**, igual que en `channel_config` y en `leagues`: un usuario
que baje de plan conserva en disco los 20 jugadores que tenía y solo se le usan
los que su plan permite. La tabla de planes por usuario está en `plans.py`
(`PLANES_USUARIO`), separada de la de servidor porque lo que se vende no es lo
mismo: a un servidor se le venden canales, a una persona no.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from utils.logger import get_logger

log = get_logger("tracking.user_config")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "users_config.json")

#: Estados de entrega por DM. Ver el docstring del módulo: no son etiquetas
#: informativas, cada uno lleva a un mensaje distinto y a una solución distinta.
DM_OK = "ok"
DM_SIN_PROBAR = "sin_probar"
DM_CERRADO = "cerrado"       # Discord 50007
DM_SIN_GUILD = "sin_guild"   # Discord 50278

#: Las cuatro listas que puede tener un usuario. Están declaradas en un solo
#: sitio porque el lector, el escritor, el borrado y `resumen()` tienen que
#: coincidir; cuando cada uno llevaba su propia lista de claves, añadir un eje
#: nuevo significaba tocar cuatro funciones y olvidarse de una.
#:
#: El valor es el recurso del plan que las acota (`plans.limite`). `None` = sin
#: cupo propio: los partidos oficiales no cuestan peticiones a Riot (salen del
#: calendario de lolesports, que se pide una vez para todos), así que limitarlos
#: sería un cupo inventado.
EJES: dict[str, str | None] = {
    "jugadores": "jugadores_seguidos",
    "ligas": "ligas",
    "partidos_ligas": None,
    "partidos_equipos": None,
}


# ---------------------------------------------------------------------- #
# Disco
# ---------------------------------------------------------------------- #

def _cargar_bruto() -> dict[str, dict[str, Any]]:
    """Lo que hay en disco, normalizado. **Nunca levanta.**

    Un JSON roto deja al bot sin suscripciones personales, que es visible y se
    arregla; levantar aquí tumbaría la pasada del tracker y con ella los avisos
    de los servidores, que no tienen nada que ver con esto.

    Se toleran dos deformaciones que van a ocurrir de verdad: una cadena suelta
    donde debería haber lista (`"jugadores": "Elyoya"`, que es lo que escribiría
    cualquiera editando el fichero a mano) y un bloque que no es dict.
    """
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            datos = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("users_config.json ilegible (%s): sin suscripciones personales", exc)
        return {}

    if not isinstance(datos, dict):
        return {}

    salida: dict[str, dict[str, Any]] = {}
    for clave, bloque in datos.items():
        if not isinstance(bloque, dict):
            continue
        limpio: dict[str, Any] = {}
        for eje in EJES:
            valor = bloque.get(eje)
            if isinstance(valor, str):
                valor = [valor]
            if isinstance(valor, list):
                # Se conserva el orden de suscripción y se quitan duplicados:
                # el orden importa porque el recorte por cupo se queda con los
                # primeros, así que quien se suscribió antes no pierde su sitio.
                vistos: list[str] = []
                for v in valor:
                    txt = str(v).strip()
                    if txt and txt not in vistos:
                        vistos.append(txt)
                limpio[eje] = vistos
        if isinstance(bloque.get("idioma"), str):
            limpio["idioma"] = bloque["idioma"]
        if isinstance(bloque.get("dm"), dict):
            limpio["dm"] = dict(bloque["dm"])
        for extra in ("creado", "plan", "motivo"):
            if extra in bloque:
                limpio[extra] = bloque[extra]
        salida[str(clave)] = limpio
    return salida


def _guardar(datos: dict[str, dict[str, Any]]) -> None:
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


# ---------------------------------------------------------------------- #
# Lectura
# ---------------------------------------------------------------------- #

def existe(user_id: int | str) -> bool:
    """¿Este usuario tiene algo registrado?

    Se usa para saber si hay que preguntarle el idioma: el usuario que nunca ha
    usado el bot recibe la pregunta una vez, y el que ya está registrado no la
    ve nunca más.
    """
    return str(user_id) in _cargar_bruto()


def datos_de(user_id: int | str) -> dict[str, Any]:
    """Bloque crudo de un usuario, sin cupos. `{}` si no está registrado."""
    return dict(_cargar_bruto().get(str(user_id), {}))


def seguidos(user_id: int | str, eje: str) -> list[str]:
    """Lo que un usuario sigue en un eje, **recortado a su cupo**.

    Un eje que no existe devuelve lista vacía en vez de levantar, por el mismo
    motivo que `plans.limite` devuelve 0: esto se llama desde el camino que
    decide si sale un aviso, y ahí una excepción por una cadena mal escrita
    apaga la notificación en silencio.
    """
    guardados = list(_cargar_bruto().get(str(user_id), {}).get(eje) or [])
    recurso = EJES.get(eje)
    if recurso is None:
        return guardados
    from tracking.soloq.plans import recortar_usuario

    return recortar_usuario(user_id, recurso, guardados)


def guardados(user_id: int | str, eje: str) -> list[str]:
    """Todo lo que tiene guardado en un eje, ignorando el cupo.

    Hace falta para poder decirle "tienes 12 jugadores y tu plan usa 3": si el
    comando solo viera la lista recortada, los otros nueve parecerían borrados y
    el usuario los volvería a añadir para nada.
    """
    return list(_cargar_bruto().get(str(user_id), {}).get(eje) or [])


def usuarios_con(eje: str) -> dict[int, list[str]]:
    """`{user_id: [valores]}` de todos los que siguen algo en un eje, con cupo.

    Es lo que consume el reparto de avisos. El cupo se aplica aquí y no en el
    envío para que el bucle de notificación no tenga que saber nada de planes,
    igual que hace `channel_config.todos_los_canales`.
    """
    from tracking.soloq.plans import recortar_usuario

    recurso = EJES.get(eje)
    salida: dict[int, list[str]] = {}
    for clave, bloque in _cargar_bruto().items():
        try:
            user_id = int(clave)
        except (TypeError, ValueError):
            continue
        valores = list(bloque.get(eje) or [])
        if recurso is not None:
            valores = recortar_usuario(user_id, recurso, valores)
        if valores:
            salida[user_id] = valores
    return salida


def ligas_de_usuarios() -> set[str]:
    """Ligas que algún usuario sigue por su cuenta, para la SoloQ.

    La pasada del tracker descarga la **unión** de las ligas de todos los
    servidores (`leagues.ligas_en_uso`). Con suscripciones personales esa unión
    se ensancha: un usuario suscrito a la LCK obliga a descargarla aunque
    ningún servidor la siga. Esto es lo que hay que sumar allí, y por eso está
    aquí y no dentro de `leagues`: `leagues` no debe importar este módulo, que
    ya lo importa a él.

    Ojo con el coste: el techo de 4 ligas es por servidor y por usuario, pero la
    unión no tiene techo. Es la misma vigilancia que ya existe en la pasada.
    """
    from tracking.soloq.leagues import LIGAS

    codigos: set[str] = set()
    for valores in usuarios_con("ligas").values():
        codigos.update(c for c in valores if c in LIGAS)
    return codigos


# ---------------------------------------------------------------------- #
# Escritura
# ---------------------------------------------------------------------- #

def agregar(user_id: int | str, eje: str, valor: str) -> tuple[str, int]:
    """Añade algo a un eje. Devuelve `(resultado, cupo)`.

    Misma forma que `channel_config.agregar_canal`, a propósito: los comandos
    que lo llaman tienen que decidir el texto, no la capa de datos, y tener dos
    contratos distintos para lo mismo garantiza que un día uno de los dos se
    quede sin traducir. `resultado` es una de cuatro cadenas:

    * `"añadido"`  — se guardó;
    * `"repetido"` — ya estaba (comparando sin distinguir mayúsculas, porque
      "elyoya" y "Elyoya" son el mismo pro y nadie escribe el nick igual dos
      veces);
    * `"cupo"`     — el plan no da para más;
    * `"invalido"` — valor vacío o eje que no existe.

    `"invalido"` está separado de `"repetido"` porque si no, un eje mal escrito
    en el código de un comando produciría el mensaje "ya sigues a Elyoya" sin
    haber guardado nada, y el fallo tardaría semanas en aparecer.

    El cupo se devuelve junto al resultado para no leer el plan dos veces.
    """
    limpio = (valor or "").strip()
    if not limpio or eje not in EJES:
        if eje not in EJES:
            log.warning("Eje de suscripción desconocido: %r", eje)
        return "invalido", 0

    recurso = EJES[eje]
    tope = 0
    if recurso is not None:
        from tracking.soloq.plans import limite_usuario

        tope = limite_usuario(user_id, recurso)

    datos = _cargar_bruto()
    bloque = datos.setdefault(str(user_id), {})
    actuales = list(bloque.get(eje) or [])

    if limpio.casefold() in {a.casefold() for a in actuales}:
        return "repetido", tope
    if recurso is not None and len(actuales) >= tope:
        return "cupo", tope

    bloque[eje] = actuales + [limpio]
    bloque.setdefault("creado", int(time.time()))
    bloque.setdefault("dm", {"estado": DM_SIN_PROBAR, "visto": 0, "motivo": ""})
    _guardar(datos)
    log.info("Usuario %s: %s += %s (%d%s)", user_id, eje, limpio,
             len(actuales) + 1, f"/{tope}" if tope else "")
    return "añadido", tope


def quitar(user_id: int | str, eje: str, valor: str) -> bool:
    """Quita algo de un eje. `False` si no estaba.

    La comparación ignora mayúsculas por el mismo motivo que en `agregar`: quien
    escribió `/seguir Elyoya` va a escribir `/dejarseguir elyoya`.
    """
    limpio = (valor or "").strip().casefold()
    if not limpio or eje not in EJES:
        return False

    datos = _cargar_bruto()
    bloque = datos.get(str(user_id))
    if not bloque:
        return False
    actuales = list(bloque.get(eje) or [])
    restantes = [a for a in actuales if a.casefold() != limpio]
    if len(restantes) == len(actuales):
        return False

    bloque[eje] = restantes
    _guardar(datos)
    log.info("Usuario %s: %s -= %s (quedan %d)", user_id, eje, valor, len(restantes))
    return True


def vaciar(user_id: int | str) -> int:
    """Borra **todo** lo de un usuario. Devuelve cuántas suscripciones había.

    Existe porque el RGPD y la política de privacidad publicada en la web
    prometen una vía de borrado, y porque `/dejarseguir` uno a uno no es una vía
    de borrado cuando alguien sigue una liga de 80 jugadores. El idioma se va
    con lo demás: si el usuario se borra, no queda nada suyo.
    """
    datos = _cargar_bruto()
    bloque = datos.pop(str(user_id), None)
    if bloque is None:
        return 0
    cuantas = sum(len(bloque.get(eje) or []) for eje in EJES)
    _guardar(datos)
    log.info("Usuario %s: borrado completo (%d suscripciones)", user_id, cuantas)
    return cuantas


# ---------------------------------------------------------------------- #
# Idioma
# ---------------------------------------------------------------------- #

def idioma_guardado(user_id: int | str) -> str | None:
    """Idioma que el usuario eligió, o `None` si nunca eligió.

    Devuelve `None` y no el idioma por defecto **a propósito**: quien decide es
    `i18n.idioma_efectivo`, que tiene que poder distinguir "eligió español" de
    "no ha elegido y hay que mirar el locale de su cliente de Discord". Si aquí
    se devolviera "es" por defecto, un usuario inglés recién llegado recibiría
    todo en español para siempre sin haber elegido nada.
    """
    valor = _cargar_bruto().get(str(user_id), {}).get("idioma")
    return valor if isinstance(valor, str) and valor else None


def establecer_idioma(user_id: int | str, idioma: str) -> str:
    """Guarda el idioma de un usuario. Devuelve el código guardado."""
    datos = _cargar_bruto()
    bloque = datos.setdefault(str(user_id), {})
    bloque["idioma"] = idioma
    bloque.setdefault("creado", int(time.time()))
    _guardar(datos)
    log.info("Idioma del usuario %s -> %s", user_id, idioma)
    return idioma


# ---------------------------------------------------------------------- #
# Estado del DM
# ---------------------------------------------------------------------- #

def estado_dm(user_id: int | str) -> str:
    """Estado de entrega por DM. Ver el docstring del módulo."""
    dm = _cargar_bruto().get(str(user_id), {}).get("dm") or {}
    estado = dm.get("estado")
    return estado if estado in (DM_OK, DM_CERRADO, DM_SIN_GUILD) else DM_SIN_PROBAR


def marcar_dm(user_id: int | str, estado: str, motivo: str = "") -> None:
    """Apunta cómo fue el último intento de DM.

    No crea el usuario si no existe: si alguien ya no está registrado, un envío
    tardío que falle no debe resucitar su entrada.
    """
    datos = _cargar_bruto()
    bloque = datos.get(str(user_id))
    if bloque is None:
        return
    anterior = (bloque.get("dm") or {}).get("estado")
    bloque["dm"] = {"estado": estado, "visto": int(time.time()), "motivo": motivo[:200]}
    _guardar(datos)
    # Solo se registra el cambio: un usuario con los DM cerrados aparece en cada
    # pasada, y a 30 s por pasada eso son 2.880 líneas de log al día por persona.
    if anterior != estado:
        log.info("DM del usuario %s: %s -> %s (%s)", user_id, anterior or "?", estado,
                 motivo or "sin motivo")


def resumen(user_id: int | str) -> dict[str, Any]:
    """Todo lo que un comando necesita para pintar el estado de un usuario.

    Devuelve por cada eje lo que está **en uso** y lo que hay **guardado**, que
    no son lo mismo cuando el plan recorta. Sin esa distinción, un usuario que
    baja de plan vería desaparecer jugadores sin explicación y los volvería a
    añadir para nada.

    Los cupos salen de `limite_usuario` y no de leer el campo del plan a mano,
    porque el de ligas pasa además por el techo físico: un plan que dijera 8
    ligas sigue estando limitado a 4 por la duración de la pasada, y el comando
    tiene que enseñar el número que se aplica de verdad.
    """
    from tracking.soloq.plans import limite_usuario, plan_de_usuario, recortar_usuario

    bruto = _cargar_bruto().get(str(user_id), {})
    ejes: dict[str, dict[str, Any]] = {}
    for eje, recurso in EJES.items():
        todo = list(bruto.get(eje) or [])
        if recurso is None:
            ejes[eje] = {"en_uso": todo, "guardados": todo, "tope": 0}
            continue
        ejes[eje] = {
            "en_uso": recortar_usuario(user_id, recurso, todo),
            "guardados": todo,
            "tope": limite_usuario(user_id, recurso),
        }
    return {
        "registrado": bool(bruto),
        "idioma": bruto.get("idioma"),
        "plan": plan_de_usuario(user_id),
        "dm": estado_dm(user_id),
        "ejes": ejes,
    }
