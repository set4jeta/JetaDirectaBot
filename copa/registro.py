#copa/registro.py
from nextcord.ext import commands
from .validacion import validar_cuenta, obtener_elo
from .datos import guardar_inscripcion
from .datos import obtener_inscripciones  # arriba en tus imports
import re

LINK_HOJA = "https://docs.google.com/spreadsheets/d/1QnYSe8YN76yHlWN-Bxzxe8ooUJu_iT28kxIOn-PUtOI/edit#gid=0"
# Estado global para evitar registros concurrentes del mismo usuario
registro_en_progreso = {}

# Validadores extra
def validar_horario(hora_str):
    # Valida formato HH:MM 24h
    return re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", hora_str)

def validar_nombre_tag(texto):
    # Valida formato nombre#tag simple
    partes = texto.split("#")
    return len(partes) == 2 and all(partes)

def es_respuesta_si_no(texto):
    texto = texto.lower()
    return texto in ["sí", "si", "no"]

def normalizar_si_no(texto):
    return "Sí" if texto.lower() in ["sí", "si"] else "No"


def register_copa_commands(bot):
    
    @bot.group(name="jetacup", invoke_without_command=True)
    async def jetacup(ctx):
        await ctx.send("**JETA CUP 2**")
        await ctx.send("Comandos disponibles: `!jetacup registro`, `!jetacup cancelarregistro`, `!jetacup cancelarinscripcion`, `!jetacup registrados`")
        await ctx.send(f"Puedes revisar las inscripciones aquí:\n{LINK_HOJA}")
        
    @jetacup.command(name="registro")
    async def registro(ctx):
        user_id = ctx.author.id

        if user_id in registro_en_progreso:
            await ctx.send("⚠️ Ya tienes un registro en progreso. Por favor, termina o cancela con `!jetacup cancelarregistro` antes de iniciar uno nuevo.")
            return

        registro_en_progreso[user_id] = {"step": 1}

        async def esperar_respuesta(mensaje_esperado=None, timeout=60):
            try:
                msg = await bot.wait_for(
                    "message",
                    check=lambda m: m.author == ctx.author,
                    timeout=timeout
                )
                if msg.content.lower() == "cancelar":
                    await ctx.send("⏹️ Registro cancelado. Escribe `!jetacup registro` para empezar de nuevo.")
                    registro_en_progreso.pop(user_id, None)
                    return None
                return msg.content.strip()
            except Exception:
                await ctx.send("⏹️ Registro cancelado por inactividad. Escribe `!jetacup registro` para empezar de nuevo.")
                registro_en_progreso.pop(user_id, None)
                return None

        await ctx.send("¡Bienvenido a la inscripción en **Copa JETACUP 2**!. Por favor, ingresa tu cuenta de LoL en formato nombre#tag (ejemplo: GarenTop#EUW):")
        cuenta_usuario = await esperar_respuesta()
        if cuenta_usuario is None:
            return

        if not validar_nombre_tag(cuenta_usuario):
            await ctx.send("Formato incorrecto. Intenta de nuevo con nombre#tag (ej: GarenTop#EUW).")
            registro_en_progreso.pop(user_id, None)
            return

        game_name, tag_line = cuenta_usuario.split("#")

        cuenta = await validar_cuenta(game_name, tag_line)
        if not cuenta:
            await ctx.send("❌ Cuenta no válida o no encontrada.")
            registro_en_progreso.pop(user_id, None)
            return

        if not cuenta.get("platform"):
            await ctx.send("❌ No se pudo determinar la región activa de tu cuenta.")
            registro_en_progreso.pop(user_id, None)
            return

        if cuenta["platform"].upper() != "EUW1":
            await ctx.send("❌ Solo se permiten cuentas de EUW.")
            registro_en_progreso.pop(user_id, None)
            return

        puuid = cuenta["puuid"]
        elo_data = await obtener_elo(puuid)
        if not elo_data:
            await ctx.send("❌ No se pudo obtener tu ELO. API ocupada, intenta más tarde.")
            registro_en_progreso.pop(user_id, None)
            return

        elo_str = f"{elo_data['tier']} {elo_data['rank']} ({elo_data['leaguePoints']} LP)"
        await ctx.send(f"✅ Tu cuenta fue validada: {game_name}#{tag_line} - {elo_str}")

        # Nick personalizado
        await ctx.send("Ahora, elige un nick identificador único (ej: 'SuperGaren').")
        nick = await esperar_respuesta()
        if nick is None:
            return


        # Preguntar roles preferidos
        await ctx.send(
            "¿Qué roles prefieres jugar? (elige hasta 2 separados por coma)\n"
            "Opciones: Top, JG, Mid, ADC, Support"
        )
        while True:
            roles_input = await esperar_respuesta()
            if roles_input is None:
                return

            roles = [r.strip().capitalize() for r in roles_input.split(",")]
            roles_validos = {"Top", "Jg", "Mid", "Adc", "Support"}

            if not all(r in roles_validos for r in roles) or not (1 <= len(roles) <= 2):
                await ctx.send("❌ Roles inválidos. Escribe 1 o 2 roles separados por coma. Ej: `Mid, JG`")
                continue

            roles_preferidos = ", ".join(roles)
            break






        # ¿Acepta jugar con desconocidos?
        while True:
            await ctx.send("¿Aceptas jugar con desconocidos? (Responde Sí o No)")
            acepta_desconocidos = await esperar_respuesta()
            if acepta_desconocidos is None:
                return
            if not es_respuesta_si_no(acepta_desconocidos):
                await ctx.send("Respuesta no válida. Por favor, responde Sí o No o escribe 'cancelar' para salir.")
                continue
            acepta_desconocidos = normalizar_si_no(acepta_desconocidos)
            break

        # Amigo preferido (opcional)
        await ctx.send("Si tienes un amigo con quien prefieres estar en el mismo equipo, escribe su cuenta (nombre#tag). Si no, responde 'ninguno'.")
        amigo = await esperar_respuesta()
        if amigo is None:
            return
        if amigo.lower() != "ninguno" and not validar_nombre_tag(amigo):
            await ctx.send("Formato inválido para amigo. Usa nombre#tag o escribe 'ninguno'.")
            registro_en_progreso.pop(user_id, None)
            return

        # Disponibilidad horaria
        while True:
            await ctx.send("¿Cuál es tu disponibilidad horaria? (ejemplo: 18:00, 22:30, etc.)")
            disponibilidad = await esperar_respuesta()
            if disponibilidad is None:
                return
            if not validar_horario(disponibilidad):
                await ctx.send("Formato de horario inválido. Usa formato 24 horas, ejemplo: 18:00, 22:30.")
                continue
            break

        

        ok, msg_guardar = guardar_inscripcion(
            str(user_id), nick, game_name, tag_line, puuid, elo_str, cuenta.get("platform", "EUW1"), roles_preferidos,
            acepta_desconocidos, amigo, disponibilidad
        )
        if not ok:
            await ctx.send(f"❌ No se pudo guardar tu inscripción: {msg_guardar}")
            registro_en_progreso.pop(user_id, None)
            return

        resumen = (
            "✅ **Registro completo**\n"
            f"**Nick:** {nick}\n"
            f"**Cuenta:** {game_name}#{tag_line}\n"
            f"**ELO:** {elo_str}\n"
            f"**Roles preferidos:** {roles_preferidos}\n"
            f"**Jugar con desconocidos:** {acepta_desconocidos}\n"
            f"**Amigo preferido:** {amigo if amigo.lower() != 'ninguno' else 'Ninguno'}\n"
            f"**Horario:** {disponibilidad}\n\n"
            f"Puedes revisar tu inscripción aquí:\n{LINK_HOJA}"
        )
        await ctx.send(resumen)

        # Eliminar estado de registro
        registro_en_progreso.pop(user_id, None)

    @jetacup.command(name="cancelarregistro")
    async def cancelarregistro(ctx):
        user_id = ctx.author.id
        if user_id in registro_en_progreso:
            registro_en_progreso.pop(user_id, None)
            await ctx.send("⏹️ Registro cancelado. Puedes iniciar uno nuevo con `!jetacup registro` cuando quieras.")
        else:
            await ctx.send("❌ No tienes ningún registro en progreso.")

    @jetacup.command(name="cancelarinscripcion")
    async def cancelar_inscripcion(ctx):
        from .datos import eliminar_inscripcion
        eliminado = eliminar_inscripcion(str(ctx.author.id))
        if eliminado:
            await ctx.send("✅ Tu inscripción fue cancelada y eliminada.")
        else:
            await ctx.send("❌ No se encontró ninguna inscripción con tu Discord ID.")
            
            
    if not bot.get_command("jetacup"):
        bot.add_command(jetacup)         

    

    @jetacup.command(name="registrados")
    async def registrados(ctx):
        inscripciones = obtener_inscripciones()

        if not inscripciones:
            await ctx.send("⚠️ No hay inscripciones registradas aún.")
            return

        mensaje = "**📋 Lista de inscritos en la JETACUP 2:**\n"
        mensaje += "```markdown\n"
        mensaje += f"{'Nick':<16} | {'Cuenta':<20} | {'ELO':<15} | {'Roles':<15} | {'Amigo':<20} | {'Disponibilidad'}\n"
        mensaje += "-" * 110 + "\n"

        for i, ins in enumerate(inscripciones[:20]):  # Muestra hasta 20 para evitar mensajes muy largos
            mensaje += f"{ins['Nick']:<16} | {ins['Cuenta']:<20} | {ins['ELO']:<15} | {ins.get('Roles', ''):<15} | {ins['Amigo']:<20} | {ins['Disponibilidad']}\n"

        mensaje += "```"

        await ctx.send(mensaje)

        # Si hay más de 20 registros, avisa
        if len(inscripciones) > 20:
            await ctx.send(f"⚠️ Se muestran los primeros 20 registros de {len(inscripciones)}. Usa el enlace para ver todos:\n{LINK_HOJA}")



