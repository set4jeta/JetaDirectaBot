# esports_extension/bot/commands.py
from nextcord.ext import commands
from nextcord import Embed
from soupsieve import match
from esports_extension.services.embed_service import EmbedService
from esports_extension.services.storage import save_notification_channel, remove_notification_channel
from esports_extension.utils.time_utils import get_network_time
from esports_extension.models.match import ScheduleEvent, EventDetails
from esports_extension.models.tracker import TrackedMatch, TrackedStatus
from esports_extension.services.api import firestore_query_matches 
from esports_extension.services.storage import load_notification_channel
from esports_extension.utils.buttons import ScoreButtonView
import copy
from nextcord.ext import tasks


class EsportsCommands(commands.Cog):
    def __init__(self, bot, tracker_service):
        self.bot = bot
        self.tracker = tracker_service  

        if not self.bg_task.is_running():
            self.bg_task.start()
        
        
        
    @tasks.loop(seconds=30)
    async def bg_task(self):
        try:
            # 1. Detecta partidos solo una vez por ciclo
            await self.tracker.detect_live_matches()

            # 2. Notifica en todos los canales configurados en este ciclo
            for guild in self.bot.guilds:
                channel_id = load_notification_channel(guild.id)
                if not channel_id:
                    print(f"[⚠️] Canal de notificaciones no configurado para guild {guild.id}. Usa !setlivechannel")
                    continue
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    print(f"[❌] Canal no encontrado en guild {guild.id}. ¿Se borró el canal?")
                    continue
                print(f"[INFO] Notificando en guild {guild.id} canal {channel_id} ({channel.name})")
                await self.tracker.notify_new_games(channel)
        except Exception as e:
            print(f"[🔥] Error crítico en bg_task: {str(e)}")
            import traceback
            traceback.print_exc()
        
        
        
        
        
        
        
        
        

    @commands.command(name="partida", help="Muestra partidas en vivo actualmente")
    async def partida(self, ctx):
        matches_snapshot = copy.deepcopy(list(self.tracker.tracked_matches.values()))

        # DEBUG: imprime el estado de todos los partidos y juegos
        for match in matches_snapshot:
            print(f"[DEBUG] match_id={match.match_id} status={match.status} ({type(match.status)}) state={match.state}")
            for g in match.trackedGames:
                print(f"  [DEBUG] game_id={g.game_id} state={g.state} has_participants={g.has_participants}")

        live_matches = [
            match for match in matches_snapshot
            if (match.status == TrackedStatus.DETECTED or match.status == "detected") and match.state == "inProgress"
        ]
        if not live_matches:
            await ctx.send("❌ No hay partidas en vivo en este momento.")
            return

        prioritized = await self.tracker._prioritize_matches(live_matches)
        any_embed_sent = False

        for match in prioritized[:4]:  # Limitar a los primeros 4 partidos
            sent_for_this_match = False

            # 1. ¿Hay juego en progreso con participantes? (partida en vivo)
            for g in reversed(match.trackedGames):
                if g.state == "inProgress" and g.has_participants:
                    embed = await EmbedService.create_live_match_embed(match, is_notification=False)
                    tracked_game = next(
                        (g for g in reversed(match.trackedGames)
                        if g.state == "inProgress"
                        and g.live_blue_metadata
                        and g.live_red_metadata
                        and g.live_blue_metadata.participants
                        and g.live_red_metadata.participants),
                        None
                    )
                    if tracked_game and match.teamsEventDetails:
                        blue_team = next((t for t in match.teamsEventDetails if tracked_game.live_blue_metadata and t.id == tracked_game.live_blue_metadata.team_id), None)
                        red_team = next((t for t in match.teamsEventDetails if tracked_game.live_red_metadata and t.id == tracked_game.live_red_metadata.team_id), None)
                        blue_wins = blue_team.game_wins if blue_team else 0
                        red_wins = red_team.game_wins if red_team else 0
                        if blue_wins == 0 and red_wins == 0:
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send(embed=embed, view=ScoreButtonView(blue_wins, red_wins))
                    else:
                        await ctx.send(embed=embed)
                    sent_for_this_match = True
                    any_embed_sent = True
                    break
            if sent_for_this_match:
                continue

            # 2. ¿Hay draft en progreso? (solo draft, sin jugadores)
            for g in match.trackedGames:
                if g.state in ("inProgress", "unstarted") and not g.has_participants and g.draft_in_progress:
                    embed = await EmbedService.create_draft_embed(match)
                    await ctx.send(embed=embed)
                    sent_for_this_match = True
                    any_embed_sent = True
                    break
            if sent_for_this_match:
                continue

            # 3. ¿Esperando siguiente partida? (el anterior terminó, el siguiente aún no empieza)
            for idx, g in enumerate(match.trackedGames[:-1]):
                next_game = match.trackedGames[idx + 1]
                if (
                    g.state == "completed"
                    and next_game.state in ("unstarted", "inProgress")
                    and not next_game.has_participants
                    and not next_game.draft_in_progress
                ):
                    embed = await EmbedService.create_waiting_embed(match, next_game.number)
                    blue_wins = match.teamsEventDetails[0].game_wins
                    red_wins = match.teamsEventDetails[1].game_wins

                    if blue_wins == 0 and red_wins == 0:
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send(embed=embed, view=ScoreButtonView(blue_wins, red_wins))
                    sent_for_this_match = True
                    any_embed_sent = True
                    break
            if sent_for_this_match:
                continue

        
        
            # 4. Si ningún juego anterior, pero el primer juego está esperando (sin participantes ni draft)
            first_game = match.trackedGames[0]
            if (
                first_game.state in ("inProgress")
                and not first_game.has_participants
                and not first_game.draft_in_progress
            ):
                embed = await EmbedService.create_waiting_embed(match, first_game.number)
                blue_wins = match.teamsEventDetails[0].game_wins
                red_wins = match.teamsEventDetails[1].game_wins

                if blue_wins == 0 and red_wins == 0:
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(embed=embed, view=ScoreButtonView(blue_wins, red_wins))
                sent_for_this_match = True
                any_embed_sent = True
                    
        
        
        
        if not any_embed_sent:
            await ctx.send("❌ No hay partidas en vivo en este momento.")

    @commands.command(name="next", help="Muestra los próximos partidos (series no iniciadas)")
    async def next(self, ctx):
        try: 
            ahora = await get_network_time()
            data = await self.tracker.api_client.get_schedule()
        except Exception:
            await ctx.send("❌ Error al conectarse a la API de LoL Esports.")
            return

        raw_events = data.get("data", {}).get("schedule", {}).get("events", [])
        partidos_proximos = []

        for raw_event in raw_events:
            if not raw_event or not isinstance(raw_event, dict):
                continue  # Salta eventos nulos o mal formateados

            # Salta eventos sin match o con match=None
            if "match" not in raw_event or raw_event.get("match") is None:
                print("[DEBUG] Evento sin match o match=None:", raw_event)
                continue
            elif not isinstance(raw_event.get("match"), dict):
                print("[DEBUG] Evento con match no dict:", raw_event)
                continue

            evento = ScheduleEvent(raw_event)

             # --- NUEVO: Verifica en el tracker si este match ya está en progreso o completado ---
            tracked = self.tracker.tracked_matches.get(evento.match_id)
            if tracked:
                # Si el partido está en progreso o completado, NO lo muestres como próximo
                if tracked.state in ("inProgress", "completed") or tracked.status == TrackedStatus.COMPLETED:
                    continue
                           
            
            
            
            if (
                evento.type == "match"
                and evento.state == "unstarted"
                and evento.start_time is not None
            ):
                diferencia_horas = (evento.start_time - ahora).total_seconds() / 3600 # type: ignore
                if -4 <= diferencia_horas <= 12:
                    partidos_proximos.append(evento)

        partidos_proximos.sort(key=lambda x: x.start_time)

        if not partidos_proximos:
            await ctx.send("🎮 No hay partidos próximos en las próximas 12 horas.")
            return

        for evento in partidos_proximos[:3]:
            try:
                event_details_data = await self.tracker.api_client.get_event_details(evento.match_id)
                detalles = EventDetails(event_details_data.get("data", {}).get("event", {}))

                if ahora is None:
                    raise ValueError("No se pudo obtener la hora de red correctamente.")
                tracked_match = TrackedMatch(
                    detection_time=ahora,
                    scheduleEvent_obj=evento
                )
                await tracked_match.enrich_from_event_details(detalles)

                embed = await EmbedService.create_upcoming_embed(tracked_match)
                await ctx.send(embed=embed)

            except Exception as e:
                print(f"[❌] Error procesando partido {evento.match_id}: {str(e)}")
                continue

    @commands.command(name="setlivechannel", help="Establece el canal para las notificaciones en vivo")
    async def setchannellive(self, ctx):
        try:
            guild_id = ctx.guild.id
            channel_id = ctx.channel.id
            print(f"Intentando guardar channel_id: {channel_id} para guild_id: {guild_id}")
            save_notification_channel(guild_id, channel_id)
            await ctx.send(
                f"✅ Canal de notificaciones configurado en: <#{channel_id}>"
            )
            print("Guardado exitoso y mensaje enviado")
        except Exception as e:
            print(f"Error en setchannel: {e}")
            await ctx.send("❌ Ocurrió un error al guardar el canal.")
            
            
    @commands.command(name="removelivechannel", help="Desactiva las notificaciones en vivo para este canal")
    async def removelivechannel(self, ctx):
        try:
            guild_id = ctx.guild.id
            remove_notification_channel(guild_id)
            await ctx.send("✅ Las notificaciones en vivo han sido desactivadas para este servidor.")
        except Exception as e:
            print(f"Error en removelivechannel: {e}")
            await ctx.send("❌ Ocurrió un error al desactivar las notificaciones.")



    @commands.command(name="testapi", help="Testea la conexión con lolesports-ink")
    async def testapi(self, ctx):
        try:
            data = firestore_query_matches()
            print("Respuesta Firestore:", data)  # <--- Agrega esto para ver la respuesta real en consola
            if data and "documents" in data:
                await ctx.send(f"✅ Conexión exitosa. Documentos recibidos: {len(data['documents'])}")
            else:
                await ctx.send("⚠️ Conectado, pero no se encontraron documentos o respuesta inesperada.")
        except Exception as e:
            await ctx.send(f"❌ Error al conectar con lolesports-ink:\n`{str(e)}`")
            


async def setup(bot):
    from esports_extension.services.tracker_service import TrackerService
    from esports_extension.services.api import APIClient
    tracker_service = TrackerService(APIClient())
    bot.add_cog(EsportsCommands(bot, tracker_service)) 