"""Superficie de respuesta común para comandos de prefijo y slash.

Por qué existe
--------------
El bot tenía 13 comandos escritos contra `commands.Context`: `ctx.send`,
`ctx.author`, `ctx.guild`. Los slash commands de Discord no dan un `Context`,
dan un `nextcord.Interaction`, cuya forma es distinta en tres cosas que
importan:

1. **Hay que responder en 3 segundos** o Discord da la interacción por perdida.
   Lo normal es `defer()` primero y mandar el resultado después. Un comando de
   prefijo no tiene ese límite.
2. **La primera respuesta es especial.** Tras `defer()`, los envíos van por el
   webhook de seguimiento (`followup`), no por la respuesta inicial.
3. **No hay indicador de "escribiendo"**: el equivalente es el "pensando..." que
   produce `defer()`.

La alternativa era duplicar cada comando: un cuerpo para prefijo y otro para
slash. Con 13 comandos eso son 13 parejas que hay que mantener sincronizadas, y
en cuanto una se olvida, `/live` y `!live` empiezan a decir cosas distintas.

Así que el cuerpo de cada comando se escribe **una vez** contra `Respuesta`, y
hay dos registros finos que lo envuelven. Lo que el usuario ve es idéntico.

Detalle de UX que se conserva
-----------------------------
`!live` mandaba "⏳ Buscando..." y luego **editaba ese mismo mensaje** con el
resultado. `esperando()` reproduce eso: en prefijo manda el mensaje y lo guarda;
el primer `send()` posterior lo edita en vez de mandar uno nuevo. En slash hace
`defer()`, que es exactamente el mismo gesto ("pensando..." → resultado).
"""

from __future__ import annotations

from typing import Any

import nextcord
from nextcord.ext import commands

from utils.logger import get_logger

log = get_logger("core.responder")

# Discord corta los mensajes en 2000 caracteres. Se deja margen para el cierre
# del bloque de código cuando se manda tabla.
LIMITE_DISCORD = 1900


class Respuesta:
    """Envoltorio uniforme sobre `Context` (prefijo) e `Interaction` (slash).

    Un solo cuerpo de comando sirve para las dos formas. No intenta imitar toda
    la API de nextcord: solo lo que los comandos del bot usan de verdad.
    """

    def __init__(self, origen: commands.Context | nextcord.Interaction):
        self.origen = origen
        self.es_slash = isinstance(origen, nextcord.Interaction)
        # Mensaje de "cargando" pendiente de editar (solo en prefijo).
        self._pendiente: nextcord.Message | None = None

    # ---------------------------------------------------------------- #
    # Datos del contexto
    # ---------------------------------------------------------------- #

    @property
    def autor(self):
        """Quien invocó el comando."""
        return self.origen.user if self.es_slash else self.origen.author

    @property
    def autor_id(self) -> int | None:
        """Id de quien invocó. Es la clave de las suscripciones personales.

        Existe aparte de `autor` porque casi todo lo que se hace con el autor es
        indexar por su id, y `getattr(res.autor, "id", None)` repetido en veinte
        comandos es donde un día aparece un `None.id`.
        """
        return getattr(self.autor, "id", None)

    @property
    def guild(self):
        return self.origen.guild

    @property
    def guild_id(self) -> int | None:
        g = self.origen.guild
        return g.id if g else None

    @property
    def es_privado(self) -> bool:
        """True si esto no ocurre dentro de un servidor.

        Cubre los dos casos que la instalación por usuario añade: el DM con el
        bot y un grupo o un servidor donde el bot no está como miembro y el
        comando llega solo porque el usuario lo tiene instalado en su cuenta. En
        los dos, todo lo que dependa del servidor —el idioma del servidor, los
        permisos de administrador, los canales de aviso— no aplica.
        """
        return self.guild_id is None

    @property
    def locale(self):
        """Idioma del cliente de Discord de quien invoca, si se sabe.

        Solo lo dan las interacciones: un comando de prefijo es un mensaje
        normal y Discord no adjunta ahí el idioma del cliente. Se usa como
        última conjetura antes del español, para que la primera respuesta que
        alguien ve del bot esté en su idioma sin haber configurado nada.
        """
        return getattr(self.origen, "locale", None) if self.es_slash else None

    def traductor(self):
        """La función de traducción ya atada a quien pregunta.

        Es lo que deben usar los comandos nuevos en vez de `tr(res.guild_id)`:
        respeta el idioma que la persona eligió, cae al del servidor cuando la
        respuesta es pública y al locale de su cliente cuando no hay nada
        elegido. En DM `guild_id` es `None`, así que el idioma del servidor
        —que no existe— no se cuela.
        """
        from utils.i18n import tr_usuario

        return tr_usuario(self.autor_id, self.guild_id, self.locale)

    @property
    def bot(self):
        """El bot, venga el comando de donde venga. `None` si no se puede.

        Las dos orígenes lo exponen con **nombres distintos**: `commands.Context`
        tiene `bot` y no tiene `client`, y `nextcord.Interaction` tiene `client` y
        no tiene `bot` (comprobado en nextcord 3.1.0). Así que un comando que
        necesite el bot no puede sacarlo de un sitio común, y de ahí esta
        propiedad.

        Hace falta para una cosa concreta: `/misavisos` **prueba** si el DM
        llega, y eso es un `bot.fetch_user` + `send` que ningún comando podía
        hacer hasta ahora. Sin la prueba, alguien que solo se ha instalado la app
        en su cuenta se queda con un "sin_probar" que no le dice nada y esperando
        avisos que Discord no nos deja entregarle.
        """
        return getattr(self.origen, "client" if self.es_slash else "bot", None)

    @property
    def canal(self):
        return self.origen.channel

    @property
    def canal_id(self) -> int | None:
        c = self.origen.channel
        return c.id if c else None

    def es_admin(self) -> bool:
        """True si quien invoca puede administrar el servidor.

        Hace falta en las dos formas por motivos distintos: en slash es un
        segundo cerrojo (Discord ya oculta el comando con
        `default_member_permissions`, pero eso es interfaz, no seguridad), y en
        prefijo es el **único** control, porque ahí Discord no filtra nada.

        En DM no hay `guild_permissions`, así que devuelve False; los comandos
        que lo usan ya rechazan los DM antes por otro motivo.
        """
        permisos = getattr(self.autor, "guild_permissions", None)
        if permisos is None:
            return False
        return bool(permisos.manage_guild or permisos.administrator)

    # ---------------------------------------------------------------- #
    # Envío
    # ---------------------------------------------------------------- #

    async def esperando(self, texto: str = "⏳ Un momento...") -> None:
        """Avisa de que el comando está trabajando.

        En slash hace `defer()` (el "pensando..." nativo, que además compra los
        15 minutos de plazo para responder). En prefijo manda `texto` y lo deja
        apuntado para que el primer `send()` lo edite, que es como se comportaba
        `!live` antes de esto.
        """
        if self.es_slash:
            try:
                if not self.origen.response.is_done():
                    await self.origen.response.defer()
            except nextcord.HTTPException as exc:
                log.debug("No se pudo diferir la interacción: %s", exc)
            return

        try:
            self._pendiente = await self.origen.send(texto)
        except nextcord.HTTPException as exc:
            log.debug("No se pudo mandar el mensaje de espera: %s", exc)

    async def send(self, content: str | None = None, **kwargs: Any):
        """Manda un mensaje. Misma firma útil que `ctx.send`.

        Si hay un mensaje de espera pendiente, el primer envío lo **edita** en
        vez de añadir otro mensaje al canal.
        """
        if self._pendiente is not None:
            mensaje, self._pendiente = self._pendiente, None
            # `edit` no acepta `file`/`files`: si el envío lleva adjuntos hay
            # que mandarlo aparte y borrar el aviso.
            if "file" in kwargs or "files" in kwargs:
                try:
                    await mensaje.delete()
                except nextcord.HTTPException:
                    pass
            else:
                try:
                    return await mensaje.edit(content=content, **kwargs)
                except nextcord.HTTPException as exc:
                    log.debug("No se pudo editar el mensaje de espera: %s", exc)

        return await self.origen.send(content, **kwargs)

    async def error(self, texto: str):
        """Un fallo esperado (no encontrado, sin datos...)."""
        return await self.send(texto)

    async def send_privado(self, content: str | None = None, **kwargs: Any):
        """Como `send`, pero que solo lo vea quien lo pidió, si se puede.

        Los comandos personales (`/seguir`, `/misavisos`) contestan cosas que no
        le interesan al canal: a quién sigue alguien, en qué estado tiene los DM.
        En un servidor eso es ruido, y encima expone la configuración de una
        persona a los demás.

        `ephemeral` **solo existe en las interacciones**: la firma de
        `Interaction.send` lo acepta y la de `commands.Context.send` no
        (comprobado en nextcord 3.1.0), y como `send` reenvía los `kwargs` tal
        cual a `self.origen.send`, pasarlo en la forma `!` sería un `TypeError`.
        Por eso se decide aquí y no en cada comando: el que lo decidiera en el
        cuerpo tendría que acordarse de `es_slash` cada vez.

        En prefijo se manda normal, que es lo que el usuario ya espera de un `!`
        escrito en un canal.
        """
        if self.es_slash:
            kwargs.setdefault("ephemeral", True)
        return await self.send(content, **kwargs)

    async def enviar_partido(self, texto: str, limite: int = LIMITE_DISCORD) -> None:
        """Manda un texto largo partido por líneas, no a mitad de palabra."""
        for trozo in partir(texto, limite):
            await self.send(trozo)

    async def enviar_bloque(self, texto: str, lenguaje: str = "markdown") -> None:
        """Manda un texto dentro de bloques de código, partiéndolo si hace falta.

        Se usa para las tablas de `!ranking`, que se alinean con espacios y
        necesitan fuente monoespaciada.
        """
        apertura = f"```{lenguaje}\n"
        actual = apertura
        for linea in texto.split("\n"):
            if len(actual) + len(linea) + 4 > 1990:
                await self.send(actual + "```")
                actual = apertura
            actual += linea + "\n"
        if actual != apertura:
            await self.send(actual + "```")


def partir(texto: str, limite: int = LIMITE_DISCORD) -> list[str]:
    """Parte un texto en trozos que quepan en un mensaje, cortando por líneas."""
    if len(texto) <= limite:
        return [texto]

    trozos: list[str] = []
    actual = ""
    for linea in texto.split("\n"):
        if len(actual) + len(linea) + 1 > limite:
            if actual:
                trozos.append(actual)
            # Una sola línea más larga que el límite se trocea a lo bruto.
            while len(linea) > limite:
                trozos.append(linea[:limite])
                linea = linea[limite:]
            actual = linea
        else:
            actual = f"{actual}\n{linea}" if actual else linea
    if actual:
        trozos.append(actual)
    return trozos
