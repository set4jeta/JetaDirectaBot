"""Planes del bot: qué cupos tiene cada servidor y quién puede subirlos.

Por qué existe este módulo
--------------------------
El usuario quiere cobrar por el bot. Las políticas generales de Riot
(https://developer.riotgames.com/policies/general, revisión del 29-05-2025) lo
permiten, pero con condiciones que **son de diseño, no de marketing**:

    "You must have a free tier of access for players, which may include
     advertising"
    "Your content must be transformative if you are charging players for it"
    "Acceptable ways to charge players are: Subscriptions, donations, or
     crowdfunding; Entry fees for tournaments; Currencies that cannot be
     exchanged back into fiat"
    "Your product cannot feature betting or gambling functionality"

De ahí sale la regla que gobierna este archivo: **lo que se cobra son cupos,
nunca el aviso de partida**. Un servidor en plan gratuito recibe la
notificación de que un pro está jugando, con su embed completo, para siempre.
Lo que compra el plan de pago es *volumen*: más ligas a la vez, más canales,
más jugadores propios, más historial.

Eso no es un truco para cumplir la letra de la política: es lo que hacen los
bots comparables que sí cobran. Dorans-bot (2.191 servidores, el análogo más
cercano) cobra 3,99 $/mes y deja gratis los avisos de partida y 10 invocadores
enlazados; lo que vende son más enlaces, rutado por canal y quitar la marca.
Carl-bot y Arcane hacen lo mismo con sus propias cuotas. Ninguno cobra por la
función principal, porque un bot cuya función principal está detrás de un muro
no llega a los 2.000 servidores desde los que se puede cobrar algo.

Por qué los límites son estos números
-------------------------------------
No son redondeos de marketing, salen del coste real de una pasada:

* `ligas`: el techo duro es `MAX_LIGAS_POR_SERVIDOR` (4) y está en
  `leagues.py`, calculado sobre el cupo de Riot de 500 peticiones/10 s. Ningún
  plan puede saltárselo, porque no es una decisión comercial sino física. El
  plan gratuito lleva 1 —que es lo que el bot hacía siempre, la LEC— y los de
  pago llegan al techo.
* `jugadores_propios`: cada jugador que un servidor añade a mano es una cuenta
  más que consultar en cada pasada, y a diferencia de las ligas no se comparte
  entre servidores. Por eso el gratuito lleva 3 (suficiente para seguir a un
  amigo o a un streamer) y es el cupo que más sentido tiene vender.
* `canales`: rutar el mismo aviso a varios canales no cuesta datos, solo
  mensajes. Es el cupo más barato de regalar y el que más se pide en servidores
  grandes con canal por región.
* `historial`: cuántas partidas enseña `/historial`. **Se bajó de 20/100/500 a
  10/30/50 el 2026-09-02**, porque los números viejos eran imposibles de
  entregar: una línea de historial ocupa unos 100 caracteres, Discord corta el
  mensaje en 2000 y `/historial` manda como mucho 3, así que el techo real son
  ~55 líneas. Un plan Elite que prometía 500 iba a entregar 55 y a tirar el
  resto en un `log.warning` que el cliente no ve. 50 se puede cumplir; 500 no
  sin paginación con botones, y hasta que exista no se vende.

Sobre el cobro en sí
--------------------
Este módulo **no cobra nada**: no hay pasarela de pago, ni tokens, ni webhooks.
Solo dice qué cupo tiene un servidor y guarda el plan que se le haya asignado.
El cobro real, cuando exista, tiene dos vías y las dos escriben aquí:

1. **Discord Premium Apps** (`entitlements`). Es la vía natural: el pago ocurre
   dentro de Discord y no hay que tocar dinero. Requisitos medidos en la
   documentación de monetización de Discord: app verificada y propiedad de un
   *team*, dueño mayor de edad con 2FA, ToS y política de privacidad públicas, y
   estar en US/EU/UK. La comisión es ~20 % (6 % de proceso de pago más 15 %
   sobre el resto en el Growth Tier, hasta 1 M$ de por vida), no el 10 % que se
   suele repetir.
2. **Donaciones** (Ko-fi, Patreon, GitHub Sponsors). Riot las nombra
   explícitamente como forma aceptable, no exigen app verificada ni team, y se
   pueden tener funcionando hoy. Es la vía con menos fricción para empezar.

Mientras no haya ninguna de las dos, `asignar_plan` existe para poder conceder
un plan a mano: es lo que se usa para dar las gracias a quien done y para
probar los límites sin montar la pasarela.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from utils.logger import get_logger

log = get_logger("tracking.plans")

#: Dónde se guarda el plan de cada servidor. Fichero aparte de
#: `leagues_config.json` a propósito: las ligas las cambia el admin del
#: servidor y el plan no, así que un borrado accidental de la config de ligas no
#: debe poder quitarle a nadie lo que ha pagado.
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "plans_config.json")


@dataclass(frozen=True)
class Plan:
    """Un nivel de acceso con sus cupos."""

    codigo: str
    nombre: str
    #: Ligas simultáneas. Nunca por encima de `MAX_LIGAS_POR_SERVIDOR`.
    ligas: int
    #: Canales a los que se puede mandar el mismo aviso.
    canales: int
    #: Jugadores que el servidor añade a mano, fuera de las ligas del catálogo.
    jugadores_propios: int
    #: Partidas que guarda `/historial`.
    historial: int
    #: Precio orientativo en euros al mes. 0 = gratis. Es solo para el texto:
    #: el precio real lo fija Discord o la plataforma de donaciones.
    precio: float = 0.0

    @property
    def gratis(self) -> bool:
        return self.precio <= 0


#: El plan gratuito **no es una demo**. Lleva la función principal completa:
#: aviso de partida con embed, `/live`, `/match`, `/info`, `/ranking`,
#: `/historial`, `/team` y esports. Lo único que lleva recortado son los cupos.
#: Esto es lo que exige la política de Riot ("You must have a free tier of
#: access for players") y además es lo que hace que el bot se pueda instalar sin
#: pensarlo, que es la condición para que alguien llegue a pagar.
GRATIS = Plan(
    codigo="gratis",
    nombre="Gratis",
    ligas=1,
    canales=1,
    jugadores_propios=3,
    historial=10,
)

#: Para servidores de comunidad: varias ligas y varios canales. El precio sale
#: de mirar lo que cobran los bots comparables (Dorans-bot 3,99 $/mes): por
#: encima de eso no hay volumen en este nicho.
PRO = Plan(
    codigo="pro",
    nombre="Pro",
    ligas=3,
    canales=3,
    jugadores_propios=25,
    historial=30,
    precio=3.99,
)

#: El techo. `ligas=4` es `MAX_LIGAS_POR_SERVIDOR`, así que este plan no puede
#: mejorarse en ese eje sin subir el límite físico.
ELITE = Plan(
    codigo="elite",
    nombre="Elite",
    ligas=4,
    canales=10,
    jugadores_propios=100,
    historial=50,
    precio=8.99,
)

PLANES: dict[str, Plan] = {p.codigo: p for p in (GRATIS, PRO, ELITE)}

#: Orden de menor a mayor, para pintar la tabla de `/premium` sin depender del
#: orden de inserción de un dict.
ORDEN = ("gratis", "pro", "elite")


# ---------------------------------------------------------------------- #
# Planes por usuario
# ---------------------------------------------------------------------- #
#
# Por qué hay una segunda tabla en vez de reutilizar la de arriba
# --------------------------------------------------------------
# A un servidor se le venden **canales**: rutar el mismo aviso al canal de EUW y
# al de KR es lo que pide un servidor grande y no cuesta datos. A una persona no
# se le puede vender eso: tiene un DM y ya está. Lo que una persona quiere
# comprar es a cuánta gente puede seguir.
#
# Reutilizar `Plan` con `canales=1` habría dejado un campo que no significa nada
# en la mitad de los casos y una tabla de `/premium` que promete algo que en el
# lado usuario no existe. Son dos productos, así que son dos tablas.
#
# Sobre los números
# -----------------
# `jugadores_seguidos=3` en el gratuito no es un número redondo: es la cifra que
# el mercado ya valida. ReadyCheck deja gratis 3 equipos + 1 liga por servidor, y
# Dorans-bot —el análogo más cercano en LoL, 2.191 servidores a 3,99 $/mes— deja
# gratis 10 invocadores enlazados y los avisos de partida completos. Con 3 pros
# el producto ya sirve (los tres jugadores que a alguien le importan de verdad
# son dos o tres), y a la vez es visiblemente poco si lo que quieres es una liga.
#
# `ligas` está acotado además por `MAX_LIGAS_POR_SERVIDOR` (4), que es físico y
# aplica igual a los usuarios: la pasada del tracker descarga la unión de las
# ligas de todos los servidores **y** de todos los usuarios, así que un cupo
# generoso por persona sale del mismo presupuesto de 30 s.
#
# Lo que **nunca** entra en esta tabla es el aviso en sí. Un usuario gratuito
# recibe el DM completo, con su embed, para siempre. Es lo que exige la política
# de Riot ("You must have a free tier of access for players") y además es lo que
# hace que alguien llegue a pagar: un aviso que no ves no lo echas de menos.
#
# Y no se vende latencia. Varios bots comparables sí lo hacen (Raider.IO vende
# "Express refresh", EasyFortniteStats vende 45 minutos de ventaja), pero aquí el
# aviso de partida caduca: llega 3 minutos tarde y el pro ya está en la fase de
# juego que te ibas a perder. Vender el retraso sería vender un producto roto en
# el tramo gratuito, que es justo el que tiene que enganchar.

@dataclass(frozen=True)
class PlanUsuario:
    """Un nivel de acceso **personal** con sus cupos."""

    codigo: str
    nombre: str
    #: Pros que puede seguir uno a uno, por nombre.
    jugadores_seguidos: int
    #: Ligas cuya SoloQ entera recibe. Acotado por `MAX_LIGAS_POR_SERVIDOR`.
    ligas: int
    #: Partidas que enseña `/historial`. Mismo techo real que en el lado
    #: servidor (~55 líneas por los 2000 caracteres de Discord).
    historial: int
    precio: float = 0.0

    @property
    def gratis(self) -> bool:
        return self.precio <= 0


#: El gratuito de verdad: avisos completos por DM de 3 pros y de 1 liga entera.
#: Una liga entera son ~80 jugadores, así que esto **no** es una demo: es más
#: volumen de avisos del que la mayoría va a querer.
USUARIO_GRATIS = PlanUsuario(
    codigo="gratis",
    nombre="Gratis",
    jugadores_seguidos=3,
    ligas=1,
    historial=10,
)

#: El precio sale del mismo sitio que el de servidor: por encima de ~4 € no hay
#: volumen en este nicho. Va por debajo del Pro de servidor porque una persona
#: no es una comunidad; EasyFortniteStats cobra 1 $/mes por usuario y 4,50 $ por
#: servidor, y esa proporción es la que tiene sentido aquí.
USUARIO_PLUS = PlanUsuario(
    codigo="plus",
    nombre="Plus",
    jugadores_seguidos=25,
    ligas=4,
    historial=30,
    precio=2.49,
)

PLANES_USUARIO: dict[str, PlanUsuario] = {
    p.codigo: p for p in (USUARIO_GRATIS, USUARIO_PLUS)
}

ORDEN_USUARIO = ("gratis", "plus")

#: Dónde se guarda el plan de cada usuario. Fichero aparte de
#: `users_config.json` por el mismo motivo que el de servidor está aparte de las
#: ligas: un borrado de suscripciones no puede quitarle a nadie lo que ha pagado.
_USUARIOS_PATH = os.path.join(os.path.dirname(__file__), "plans_users.json")


def _cargar() -> dict[str, Any]:
    if not os.path.exists(_CONFIG_PATH):
        return {}
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as fh:
            datos = json.load(fh)
        return datos if isinstance(datos, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        # Si el fichero está corrupto se sigue con el plan gratuito. La
        # alternativa —reventar— dejaría el bot sin arrancar por un JSON roto,
        # y el plan es lo menos crítico que hay aquí.
        log.warning("plans_config.json ilegible (%s): todos en plan gratuito", exc)
        return {}


def _guardar(datos: dict[str, Any]) -> None:
    tmp = _CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _CONFIG_PATH)


def plan_de(guild_id: int | str | None) -> Plan:
    """El plan de un servidor. Sin registro, el gratuito.

    Nunca devuelve `None` ni levanta: el resto del bot llama a esto en caliente
    (cada pasada del tracker mira cupos) y un fallo aquí no puede cortar un
    aviso de partida.
    """
    if guild_id is None:
        return GRATIS
    codigo = _cargar().get(str(guild_id), {}).get("plan")
    return PLANES.get(codigo or "", GRATIS)


def asignar_plan(guild_id: int | str, codigo: str, *, motivo: str = "") -> Plan:
    """Cambia el plan de un servidor. Devuelve el que queda.

    `motivo` se guarda tal cual para poder saber de dónde vino ("donación
    Ko-fi", "entitlement 12345", "prueba"). Sin él, en seis meses no habría
    forma de distinguir un plan pagado de uno regalado.
    """
    plan = PLANES.get((codigo or "").lower().strip())
    if plan is None:
        log.warning("Plan desconocido '%s' para %s: se deja como está", codigo, guild_id)
        return plan_de(guild_id)

    datos = _cargar()
    entrada = datos.setdefault(str(guild_id), {})
    entrada["plan"] = plan.codigo
    if motivo:
        entrada["motivo"] = motivo
    _guardar(datos)
    log.info("Plan de %s -> %s (%s)", guild_id, plan.codigo, motivo or "sin motivo")
    return plan


def limite(guild_id: int | str | None, recurso: str) -> int:
    """Cupo de un recurso concreto: `"ligas"`, `"canales"`, `"jugadores_propios"`,
    `"historial"`.

    Un recurso que no exista devuelve 0 en vez de levantar. Es a propósito: la
    llamada típica está en un camino que decide si se manda un aviso, y ahí un
    `AttributeError` por una cadena mal escrita apagaría la notificación. 0 hace
    que el cupo se agote, que es visible y se arregla; una excepción se come el
    aviso en silencio.
    """
    return int(getattr(plan_de(guild_id), recurso, 0) or 0)


def cabe(guild_id: int | str | None, recurso: str, usados: int) -> bool:
    """¿Queda hueco para uno más?"""
    return usados < limite(guild_id, recurso)


def recortar(guild_id: int | str | None, recurso: str, valores: list) -> list:
    """Corta una lista al cupo del servidor.

    Se usa donde el dato ya está guardado y hay que respetar el plan al leerlo
    (por ejemplo, un servidor que baja de plan y tiene 4 ligas configuradas):
    recortar al leer es reversible, borrarle la configuración no lo es. Si
    vuelve a subir de plan, sus 4 ligas siguen ahí.
    """
    tope = limite(guild_id, recurso)
    if tope <= 0 or len(valores) <= tope:
        return list(valores)
    return list(valores)[:tope]


# ---------------------------------------------------------------------- #
# Cupos por usuario
# ---------------------------------------------------------------------- #
#
# Son las mismas cuatro funciones del lado servidor con la otra tabla. Se
# duplican en vez de parametrizar `plan_de(clave, tabla)` porque las dos
# versiones se llaman desde sitios distintos y con tipos distintos de id, y un
# solo punto de entrada con un flag `es_usuario` es exactamente el sitio donde un
# día se pasa el flag mal y un usuario cobra los cupos de un servidor.

def _cargar_usuarios() -> dict[str, Any]:
    if not os.path.exists(_USUARIOS_PATH):
        return {}
    try:
        with open(_USUARIOS_PATH, encoding="utf-8") as fh:
            datos = json.load(fh)
        return datos if isinstance(datos, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("plans_users.json ilegible (%s): todos en plan gratuito", exc)
        return {}


def _guardar_usuarios(datos: dict[str, Any]) -> None:
    tmp = _USUARIOS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _USUARIOS_PATH)


def plan_de_usuario(user_id: int | str | None) -> PlanUsuario:
    """El plan de una persona. Sin registro, el gratuito. Nunca levanta."""
    if user_id is None:
        return USUARIO_GRATIS
    codigo = _cargar_usuarios().get(str(user_id), {}).get("plan")
    return PLANES_USUARIO.get(codigo or "", USUARIO_GRATIS)


def asignar_plan_usuario(user_id: int | str, codigo: str, *, motivo: str = "") -> PlanUsuario:
    """Cambia el plan de una persona. Devuelve el que queda.

    `motivo` se guarda tal cual ("entitlement 12345", "donación Ko-fi",
    "prueba"): sin él, en seis meses no habría forma de distinguir un plan
    pagado de uno regalado, que es justo lo que hay que auditar si Discord o
    Riot preguntan.
    """
    plan = PLANES_USUARIO.get((codigo or "").lower().strip())
    if plan is None:
        log.warning("Plan de usuario desconocido '%s' para %s: se deja como está",
                    codigo, user_id)
        return plan_de_usuario(user_id)

    datos = _cargar_usuarios()
    entrada = datos.setdefault(str(user_id), {})
    entrada["plan"] = plan.codigo
    if motivo:
        entrada["motivo"] = motivo
    _guardar_usuarios(datos)
    log.info("Plan del usuario %s -> %s (%s)", user_id, plan.codigo, motivo or "sin motivo")
    return plan


def limite_usuario(user_id: int | str | None, recurso: str) -> int:
    """Cupo personal de un recurso. 0 si el recurso no existe, no excepción.

    Mismo criterio que `limite`: esto se llama desde el camino que decide si sale
    un aviso por DM, y ahí una excepción por una cadena mal escrita apaga la
    notificación en silencio. 0 agota el cupo, que se ve y se arregla.

    `ligas` pasa además por el techo físico: ningún plan personal puede hacer que
    el bot descargue más ligas de las que caben en una pasada.
    """
    tope = int(getattr(plan_de_usuario(user_id), recurso, 0) or 0)
    if recurso == "ligas" and tope > 0:
        from tracking.soloq.leagues import MAX_LIGAS_POR_SERVIDOR

        return min(tope, MAX_LIGAS_POR_SERVIDOR)
    return tope


def cabe_usuario(user_id: int | str | None, recurso: str, usados: int) -> bool:
    """¿Le queda hueco a esta persona para uno más?"""
    return usados < limite_usuario(user_id, recurso)


def recortar_usuario(user_id: int | str | None, recurso: str, valores: list) -> list:
    """Corta una lista al cupo personal, al leer y no al guardar.

    Igual que `recortar`: quien deja de pagar no pierde su configuración, solo
    deja de usarse la parte que excede su cupo. Si vuelve, sigue ahí.

    Con `tope <= 0` —un recurso mal escrito— devuelve la lista **entera**, no
    vacía. Es la misma decisión que en `recortar` y merece explicarse porque
    parece la contraria de `limite`: un recurso desconocido hace que `cabe` diga
    que no (no se puede añadir nada nuevo, el fallo se ve al primer intento) pero
    no borra lo que ya había. Devolver `[]` aquí apagaría todos los avisos de
    todos los usuarios por una cadena mal escrita, y sin ningún error visible.
    """
    tope = limite_usuario(user_id, recurso)
    if tope <= 0 or len(valores) <= tope:
        return list(valores)
    return list(valores)[:tope]
