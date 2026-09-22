"""Ejecuta `/seguir`, `/dejarseguir` y `/misavisos` de verdad, sin Discord.

Por qué existe
--------------
Los tres comandos compilan y Discord los acepta (`test_slash_locale.py` lo
comprueba), pero eso no dice **nada** de lo que hacen. Los cuatro fallos que
importan aquí no se ven ni compilando ni registrando:

1. **Un eje mal escrito.** `user_config.agregar` devuelve `("invalido", 0)` con
   un eje que no existe, y el comando contestaría un error genérico habiendo
   guardado nada. Compila igual.
2. **Guardar lo que el reparto no compara.** `dm_notifier.destinatarios` compara
   contra `BootcampPlayer.name` y contra el código de liga. Si `/seguir korea`
   guardara `"korea"` en vez de `"lck"`, la suscripción existiría y **nunca**
   dispararía un aviso. Es el fallo peor de todos: no hay error, solo silencio.
3. **Prometer un aviso que no puede ocurrir.** Una liga sin cuentas descargadas
   o no rastreable (LPL) no va a producir ninguna partida detectada.
4. **Una clave del catálogo suelta.** `t()` no levanta: devuelve la clave, y el
   usuario lee `seguir.ok_liga` en vez de una frase.

Todo se hace sobre ficheros temporales y con un `Respuesta` de pega. La prueba
**no puede** tocar `users_config.json`, `plans_users.json` ni la config real.

    python scripts/test_avisos_usuario.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nextcord  # noqa: E402

from tracking.soloq import accounts_io, plans, user_config as usuarios  # noqa: E402
from utils import i18n  # noqa: E402
from utils.i18n import _CATALOGO, tr_usuario  # noqa: E402

import core.user_alerts_commands as avisos  # noqa: E402

fallos: list[str] = []

USUARIO = 424242424242424242
GUILD = 111222333444555666

def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    marca = "OK   " if condicion else "FALLA"
    print(f"  {marca} {etiqueta}" + (f" ({extra})" if extra else ""))
    if not condicion:
        fallos.append(etiqueta)


CLAVES = sorted(_CATALOGO)


def crudas(texto: str) -> list[str]:
    """Claves del catálogo que han salido literalmente. Ver el docstring."""
    return [k for k in CLAVES if k in texto]


# --------------------------------------------------------------------- #
# Dobles
# --------------------------------------------------------------------- #

class RespuestaFalsa:
    """Lo que usan los tres cuerpos, apuntando en vez de enviar.

    `bot` está aquí porque `/misavisos` prueba el DM de verdad: sin un bot que
    responda, esa rama no se ejecutaría nunca en la prueba, que es justo la que
    convierte un "sin_probar" en un diagnóstico.
    """

    def __init__(self, user_id: int = USUARIO, guild_id: int | None = GUILD, bot=None):
        self.autor_id = user_id
        self.guild_id = guild_id
        self.guild = None
        self.locale = None
        self.es_slash = True
        self.origen = object()
        self.bot = bot
        self.enviados: list[str] = []

    @property
    def es_privado(self) -> bool:
        return self.guild_id is None

    def traductor(self):
        return tr_usuario(self.autor_id, self.guild_id, self.locale)

    async def esperando(self, texto: str = "") -> None:
        pass

    async def send(self, content=None, **kwargs):
        if content:
            self.enviados.append(str(content))
        return None

    send_privado = send

    async def error(self, texto: str):
        self.enviados.append(str(texto))
        return None

    def todo(self) -> str:
        return "\n".join(self.enviados)


class _Cuenta:
    def __init__(self, nombre: str):
        self.puuid = f"puuid-{nombre}"
        self.riot_id = {"game_name": nombre, "tag_line": "EUW"}
        self.platform = "euw1"


class _Jugador:
    """Lo mínimo de `BootcampPlayer` que mira el comando."""

    def __init__(self, nombre: str, equipo: str, liga: str, display: str | None = None):
        self.name = nombre
        self.team = equipo
        self.league = liga
        self.display_name = display
        self.accounts = [_Cuenta(nombre)]


PLANTILLA = [
    _Jugador("Caps", "G2", "lec", display="Caps"),
    _Jugador("Hans Sama", "KC", "lec"),
    _Jugador("Chovy", "GEN", "lck", display="Chovy"),
]


class BotFalso:
    """Un bot que acepta o rechaza el DM según lo que se le diga.

    Reproduce los tres desenlaces reales de `user.send`, y el 50278 se construye
    de verdad (`nextcord.Forbidden` con `code`), porque el clasificador de
    `dm_notifier` mira el código y no el tipo.
    """

    def __init__(self, resultado: str = "ok"):
        self.resultado = resultado
        self.enviados: list[dict] = []

    def get_user(self, user_id):
        return _UsuarioFalso(self)

    async def fetch_user(self, user_id):
        return _UsuarioFalso(self)


class _RespuestaHTTP:
    def __init__(self, status: int):
        self.status = status
        self.reason = "Forbidden" if status == 403 else "Bad Request"


class _UsuarioFalso:
    def __init__(self, bot: BotFalso):
        self._bot = bot

    async def send(self, **kwargs):
        modo = self._bot.resultado
        if modo == "sin_guild":
            raise nextcord.Forbidden(
                _RespuestaHTTP(403),
                {"code": 50278, "message": "Cannot send messages to this user"},
            )
        if modo == "cerrado":
            raise nextcord.Forbidden(
                _RespuestaHTTP(403),
                {"code": 50007, "message": "Cannot send messages to this user"},
            )
        if modo == "rapido":
            raise nextcord.HTTPException(
                _RespuestaHTTP(400),
                {"code": 40003, "message": "Opening direct messages too fast"},
            )
        self._bot.enviados.append(kwargs)
        return None


# --------------------------------------------------------------------- #
# Pruebas
# --------------------------------------------------------------------- #

def prueba_seguir_jugador() -> None:
    print("\n=== /seguir <pro> ===")
    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_seguir(res, "caps"))
    salida = res.todo()

    ok(usuarios.seguidos(USUARIO, "jugadores") == ["Caps"],
       "guarda el nombre canónico de la plantilla, no lo que escribió el usuario",
       str(usuarios.guardados(USUARIO, "jugadores")))
    ok("Caps" in salida and "G2" in salida and "LEC" in salida,
       "confirma con equipo y liga")
    ok(not crudas(salida), "sin claves crudas", ", ".join(crudas(salida)) or "limpio")

    # El nombre guardado tiene que ser exactamente lo que la pasada compara.
    nombres_de_la_pasada = {j.name for j in PLANTILLA}
    ok(set(usuarios.seguidos(USUARIO, "jugadores")) <= nombres_de_la_pasada,
       "lo guardado coincide con lo que compara dm_notifier.destinatarios")

    res2 = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_seguir(res2, "CAPS"))
    ok("Ya seguías" in res2.todo() or "already" in res2.todo(),
       "el mismo pro con otras mayúsculas es repetido, no duplicado")
    ok(len(usuarios.guardados(USUARIO, "jugadores")) == 1, "y no se duplica")


def prueba_seguir_nick_con_espacios() -> None:
    print("\n=== /seguir 'Hans Sama' ===")
    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_seguir(res, "hans sama"))
    ok("Hans Sama" in usuarios.seguidos(USUARIO, "jugadores"),
       "un nick con espacio se resuelve entero",
       str(usuarios.seguidos(USUARIO, "jugadores")))


def prueba_seguir_desconocido() -> None:
    print("\n=== /seguir <nick que no se rastrea> ===")
    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_seguir(res, "JugadorInventado"))
    salida = res.todo()
    ok("JugadorInventado" in usuarios.guardados(USUARIO, "jugadores"),
       "se guarda igual: su liga puede empezar a rastrearse mañana")
    ok("⚠️" in salida, "pero se avisa de que todavía no le va a llegar nada")
    ok("/info" in salida, "y se le da la salida concreta")
    ok(not crudas(salida), "sin claves crudas", ", ".join(crudas(salida)) or "limpio")


def prueba_seguir_liga() -> None:
    print("\n=== /seguir <liga> y sus alias ===")
    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_seguir(res, "korea"))
    ok(usuarios.seguidos(USUARIO, "ligas") == ["lck"],
       "un alias se guarda como el código canónico que compara el reparto",
       str(usuarios.guardados(USUARIO, "ligas")))
    salida = res.todo()
    ok("LCK" in salida, "y se confirma con el nombre de la liga")
    ok(not crudas(salida), "sin claves crudas", ", ".join(crudas(salida)) or "limpio")

    # La LCK sí tiene cuentas en la plantilla de prueba (Chovy), la LEC también.
    ok("no rastreable" not in salida.lower(), "una liga con cuentas no lleva advertencia")


def prueba_seguir_liga_sin_cuentas() -> None:
    print("\n=== /seguir <liga sin cuentas descargadas> ===")
    usuarios.vaciar(USUARIO)
    plans.asignar_plan_usuario(USUARIO, "plus", motivo="prueba")
    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_seguir(res, "lfl"))
    salida = res.todo()
    ok("lfl" in usuarios.guardados(USUARIO, "ligas"), "se guarda")
    ok("ℹ️" in salida or "⚠️" in salida,
       "y se avisa de que sus cuentas aún no están descargadas")
    ok(not crudas(salida), "sin claves crudas", ", ".join(crudas(salida)) or "limpio")


def prueba_seguir_liga_no_rastreable() -> None:
    print("\n=== /seguir lpl (Riot no cubre China) ===")
    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_seguir(res, "lpl"))
    salida = res.todo()
    ok("lpl" in usuarios.guardados(USUARIO, "ligas"), "se guarda: los rangos sí salen")
    ok("⚠️" in salida, "pero se dice que no habrá avisos de partida")
    ok(not crudas(salida), "sin claves crudas", ", ".join(crudas(salida)) or "limpio")


def prueba_cupo() -> None:
    print("\n=== el cupo del plan se aplica al añadir ===")
    usuarios.vaciar(USUARIO)
    plans.asignar_plan_usuario(USUARIO, "gratis", motivo="prueba")

    for nombre in ("Caps", "Chovy", "Hans Sama"):
        asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), nombre))
    ok(len(usuarios.guardados(USUARIO, "jugadores")) == 3,
       "el gratuito llega a 3 jugadores")

    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_seguir(res, "JugadorCuatro"))
    salida = res.todo()
    ok(len(usuarios.guardados(USUARIO, "jugadores")) == 3, "el cuarto no entra")
    ok("❌" in salida, "y se dice por qué")
    ok("/premium" in salida or "premium" in salida.lower(),
       "con la salida: cambiar de plan o quitar algo")
    ok(not crudas(salida), "sin claves crudas", ", ".join(crudas(salida)) or "limpio")

    # Y lo que ya estaba guardado no se pierde al bajar de plan: `resumen()`
    # separa `en_uso` de `guardados` justo para poder decirlo.
    plans.asignar_plan_usuario(USUARIO, "plus", motivo="prueba")
    asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "JugadorCuatro"))
    ok(len(usuarios.guardados(USUARIO, "jugadores")) == 4,
       "con Plus el cuarto ya entra")
    plans.asignar_plan_usuario(USUARIO, "gratis", motivo="baja")
    ok(len(usuarios.seguidos(USUARIO, "jugadores")) == 3,
       "al bajar de plan solo se usan 3")
    ok(len(usuarios.guardados(USUARIO, "jugadores")) == 4,
       "pero los 4 siguen en disco")


def prueba_dejarseguir() -> None:
    print("\n=== /dejarseguir ===")
    usuarios.vaciar(USUARIO)
    plans.asignar_plan_usuario(USUARIO, "plus", motivo="prueba")
    asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "Caps"))
    asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "korea"))

    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_dejarseguir(res, "caps"))
    ok(usuarios.guardados(USUARIO, "jugadores") == [],
       "quita un jugador escrito en minúsculas")
    ok(not crudas(res.todo()), "sin claves crudas")

    # Lo que se guardó fue `lck`; el usuario escribe el alias otra vez.
    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_dejarseguir(res, "korea"))
    ok(usuarios.guardados(USUARIO, "ligas") == [],
       "quita una liga por su alias, aunque esté guardada por código",
       str(usuarios.guardados(USUARIO, "ligas")))

    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_dejarseguir(res, "Nadie"))
    ok("ℹ️" in res.todo(), "algo que no seguías lo dice, no falla")
    ok(not crudas(res.todo()), "sin claves crudas")

    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_dejarseguir(res, ""))
    ok("/dejarseguir" in res.todo(), "sin argumento explica cómo se usa")


def prueba_dejarseguir_todo() -> None:
    print("\n=== /dejarseguir todo ===")
    usuarios.vaciar(USUARIO)
    asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "Caps"))
    asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "lec"))

    for palabra in ("todo", "all", "*"):
        usuarios.vaciar(USUARIO)
        asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "Caps"))
        res = RespuestaFalsa()
        asyncio.run(avisos._cuerpo_dejarseguir(res, palabra))
        ok(not usuarios.existe(USUARIO), f"`{palabra}` borra todo")
        ok(not crudas(res.todo()), f"`{palabra}`: sin claves crudas")

    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_dejarseguir(res, "todo"))
    ok("ℹ️" in res.todo(), "borrar dos veces no revienta")


def prueba_misavisos() -> None:
    print("\n=== /misavisos ===")
    usuarios.vaciar(USUARIO)

    res = RespuestaFalsa(bot=BotFalso("ok"))
    asyncio.run(avisos._cuerpo_misavisos(res))
    ok("/seguir" in res.todo(), "sin nada registrado explica cómo empezar")
    ok(not crudas(res.todo()), "sin claves crudas")

    plans.asignar_plan_usuario(USUARIO, "plus", motivo="prueba")
    asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "Caps"))
    asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "lck"))

    bot = BotFalso("ok")
    res = RespuestaFalsa(bot=bot)
    asyncio.run(avisos._cuerpo_misavisos(res))
    salida = res.todo()
    ok("Caps" in salida, "lista los jugadores")
    ok("lck" in salida or "LCK" in salida, "lista las ligas")
    ok("Plus" in salida, "enseña el plan")
    ok(len(bot.enviados) == 1, "prueba el DM cuando el estado no es 'ok'",
       f"{len(bot.enviados)} envíos")
    ok(usuarios.estado_dm(USUARIO) == usuarios.DM_OK,
       "y guarda que la entrega funciona", usuarios.estado_dm(USUARIO))
    ok(not crudas(salida), "sin claves crudas", ", ".join(crudas(salida)) or "limpio")

    # Segunda vez: ya se sabe que funciona, así que no se manda otro DM.
    bot2 = BotFalso("ok")
    res = RespuestaFalsa(bot=bot2)
    asyncio.run(avisos._cuerpo_misavisos(res))
    ok(not bot2.enviados,
       "con la entrega ya verificada no se vuelve a molestar al usuario")


def prueba_misavisos_dm_roto() -> None:
    print("\n=== /misavisos cuando el DM no llega ===")
    for modo, esperado, pista in (
        ("sin_guild", usuarios.DM_SIN_GUILD, "servidor"),
        ("cerrado", usuarios.DM_CERRADO, "privados"),
    ):
        usuarios.vaciar(USUARIO)
        asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "Caps"))
        res = RespuestaFalsa(bot=BotFalso(modo))
        asyncio.run(avisos._cuerpo_misavisos(res))
        salida = res.todo()
        ok(usuarios.estado_dm(USUARIO) == esperado,
           f"{modo}: se clasifica el fallo", usuarios.estado_dm(USUARIO))
        ok(pista in salida.lower(), f"{modo}: se dice qué hacer")
        ok("Caps" in salida,
           f"{modo}: la suscripción NO se borra por un fallo de entrega")
        ok(not crudas(salida), f"{modo}: sin claves crudas")

    # 40003: es nuestro problema, no del usuario. No se le puede marcar nada.
    usuarios.vaciar(USUARIO)
    asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "Caps"))
    res = RespuestaFalsa(bot=BotFalso("rapido"))
    asyncio.run(avisos._cuerpo_misavisos(res))
    ok(usuarios.estado_dm(USUARIO) == usuarios.DM_SIN_PROBAR,
       "un 40003 no marca al usuario como inalcanzable",
       usuarios.estado_dm(USUARIO))
    ok(not crudas(res.todo()), "40003: sin claves crudas")

    # Sin bot resoluble (prefijo en un contexto raro) se enseña lo último sabido.
    res = RespuestaFalsa(bot=None)
    asyncio.run(avisos._cuerpo_misavisos(res))
    ok("Caps" in res.todo(), "sin bot, el panel sigue saliendo")


def prueba_idioma() -> None:
    print("\n=== el idioma se fija al registrarse ===")
    usuarios.vaciar(USUARIO)
    i18n._guardar({str(GUILD): {"idioma": "en"}})

    res = RespuestaFalsa()
    asyncio.run(avisos._cuerpo_seguir(res, "Caps"))
    ok(usuarios.idioma_guardado(USUARIO) == "en",
       "hereda el idioma del servidor donde se registró",
       str(usuarios.idioma_guardado(USUARIO)))
    ok("I'll" in res.todo() or "language" in res.todo().lower(),
       "y la confirmación ya sale en ese idioma")

    # Un DM (sin servidor) le habla en el idioma que ya eligió.
    res = RespuestaFalsa(guild_id=None)
    asyncio.run(avisos._cuerpo_seguir(res, "Chovy"))
    ok("I'll DM you" in res.todo(),
       "en privado, donde no hay servidor, se respeta el idioma propio")

    # Y no se le cambia por usar el bot en un servidor en español.
    res = RespuestaFalsa(guild_id=999888777)
    asyncio.run(avisos._cuerpo_seguir(res, "Hans Sama"))
    ok(usuarios.idioma_guardado(USUARIO) == "en",
       "usar el bot en otro servidor no le cambia el idioma elegido")


def prueba_reparto_encuentra_al_suscrito() -> None:
    """El eslabón que ninguna otra prueba cubre: lo guardado vs. lo que compara.

    `/seguir` guarda y `dm_notifier.destinatarios` lee. Si los dos no usan la
    misma forma del nombre y del código de liga, todo lo demás funciona y **el
    aviso nunca sale**. Aquí se comprueba de punta a punta con los valores que
    la pasada real pasa (`player_name` y `liga_jugador` de
    `active_game_checker`).
    """
    print("\n=== lo guardado es lo que el reparto encuentra ===")
    from tracking.soloq.dm_notifier import destinatarios

    usuarios.vaciar(USUARIO)
    plans.asignar_plan_usuario(USUARIO, "plus", motivo="prueba")

    asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "caps"))
    ok(USUARIO in destinatarios("Caps", "lec"),
       "quien sigue a un pro recibe su partida")
    ok(USUARIO not in destinatarios("Chovy", "lck"),
       "y no recibe la de otro")

    asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "korea"))
    ok(USUARIO in destinatarios("Chovy", "lck"),
       "quien sigue una liga por su alias recibe a cualquiera de esa liga")
    ok(USUARIO in destinatarios("Peyz", "LCK"),
       "y el código llega en mayúsculas desde la pasada sin romper la comparación")

    # Un usuario suscrito solo por liga no debe recibir otras ligas.
    ok(USUARIO not in destinatarios("JugadorRandom", "lcs"),
       "una liga a la que no está suscrito no le llega")


def prueba_ligas_en_uso_incluye_al_usuario() -> None:
    """La regresión que ya costó una vez: la unión de ligas a descargar.

    El escenario exacto es el que importa: un servidor **con canal de avisos y
    sin ligas elegidas** sigue la LEC de forma implícita, y antes eso se cubría
    de casualidad (la unión salía vacía y se caía a la LEC). En cuanto un solo
    usuario se suscribe a la LCK la unión ya no está vacía, así que la LEC
    dejaba de descargarse y ese servidor se quedaba sin avisos **en silencio**.
    Sin el canal configurado no hay nada que siga la LEC y `{"lck"}` es la
    respuesta correcta, así que la prueba tiene que montar el canal.
    """
    print("\n=== la pasada descarga la liga del usuario ===")
    from tracking.soloq import channel_config, leagues

    usuarios.vaciar(USUARIO)
    channel_config.agregar_canal(GUILD, 987654321)
    ok(channel_config.canales_de(GUILD) == [987654321],
       "hay un servidor con canal de avisos y sin ligas elegidas")
    ok(leagues.ligas_de(GUILD) == [leagues.LIGA_POR_DEFECTO],
       "que por tanto sigue la liga por defecto de forma implícita")

    asyncio.run(avisos._cuerpo_seguir(RespuestaFalsa(), "lck"))
    en_uso = leagues.ligas_en_uso()
    ok("lck" in en_uso, "la liga que sigue un usuario entra en la unión", str(en_uso))
    ok(leagues.LIGA_POR_DEFECTO in en_uso,
       "y no desplaza la que sigue implícitamente un servidor", str(en_uso))



def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        # Todo lo que se escribe va a `tmp`: la prueba no puede tocar la config
        # real, y menos los planes, que es lo que alguien habría pagado.
        usuarios.CONFIG_PATH = os.path.join(tmp, "users.json")
        plans._USUARIOS_PATH = os.path.join(tmp, "plans_users.json")
        plans._CONFIG_PATH = os.path.join(tmp, "plans.json")
        i18n._IDIOMAS_PATH = os.path.join(tmp, "idiomas.json")

        from tracking.soloq import channel_config, leagues
        channel_config.CONFIG_PATH = os.path.join(tmp, "notify.json")
        leagues._CONFIG_PATH = os.path.join(tmp, "leagues.json")

        # La plantilla: se sustituye la lectura de disco, no el fichero, para no
        # tocar los 192 KB reales ni depender de qué ligas tenga hoy.
        accounts_io.load_tracked_accounts = lambda: list(PLANTILLA)

        prueba_seguir_jugador()
        prueba_seguir_nick_con_espacios()
        prueba_seguir_desconocido()
        prueba_seguir_liga()
        prueba_seguir_liga_sin_cuentas()
        prueba_seguir_liga_no_rastreable()
        prueba_cupo()
        prueba_dejarseguir()
        prueba_dejarseguir_todo()
        prueba_misavisos()
        prueba_misavisos_dm_roto()
        prueba_idioma()
        prueba_reparto_encuentra_al_suscrito()
        prueba_ligas_en_uso_incluye_al_usuario()

    print("\n" + "=" * 60)
    if fallos:
        print(f"{len(fallos)} fallo(s):")
        for f in fallos:
            print(f"  - {f}")
        return 1
    print("Los tres comandos hacen lo que dicen: guardan lo que el reparto")
    print("compara, avisan de lo que no va a funcionar y hablan los dos idiomas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())





