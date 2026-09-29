# LoLProTrackr

## Descripción

LoLProTrackr es un bot avanzado para Discord que permite **trackear jugadores profesionales y amateurs de League of Legends**, mostrar partidas en vivo, consultar estadísticas y recibir notificaciones automáticas de partidas competitivas (LEC, LCS, LCK, MSI, Worlds, etc).

Incluye integración con APIs de Riot, DPM.lol y LoL Esports, scraping de datos y gestión de cuentas.

---

## Características principales

- **Trackeo de jugadores y equipos LEC/LEC+**
- **Notificaciones automáticas de partidas en vivo**
- **Historial y ranking de SoloQ europeo**
- **Comandos para ver partidas activas, próximas y estadísticas**
- **Scraping y actualización automática de datos de jugadores**
- **Soporte para imágenes de jugadores y equipos**
- **Comandos para admins y usuarios**

---

## Estructura general del proyecto

```
LoLProTrackr/
│
├── core/                  # Lógica principal del bot y comandos
│   ├── bot_launcher.py
│   ├── commands.py
│   ├── background_tasks.py
│   ├── info_command.py
│   ├── live_command.py
│   ├── ranking_command.py
│   ├── register_team_commands.py
│   ├── register_player_commands.py
│   ├── notification_config_commands.py
│   ├── help_commands.py
│   └── rank_data.py
│
├── tracking/soloq/        # Gestión de cuentas, scraping y cache
│   ├── accounts.json
│   ├── accounts_from_teams.json
│   ├── active_game_checker.py
│   ├── active_game_cache.py
│   ├── notifier.py
│   ├── infoplayers_search.py
│   ├── infoplayers_eu_dpm.py
│   ├── update_puuids.py
│   ├── update_tracked_puuids.py
│   ├── force_update_all_tracked_puuids.py
│   ├── channel_config.py
│   └── ...
│
├── esports_extension/     # Extensión para partidas competitivas (LEC, Worlds, etc)
│   ├── bot/
│   │   └── commands.py
│   ├── models/
│   │   ├── match.py
│   │   ├── tracker.py
│   │   ├── live.py
│   ├── services/
│   │   ├── api.py
│   │   ├── tracker_service.py
│   │   ├── storage.py
│   │   ├── embed_service.py
│   │   └── chat_winner_detector.py
│   └── utils/
│       └── time_utils.py
│
├── ui/                    # Embeds y utilidades visuales
│   ├── player_info_embed.py
│   ├── active_match_embed.py
│   ├── team_image_utils.py
│   ├── player_image_utils.py
│   └── utils_embed.py
│
├── cache/                 # Cache de campeones y datos
│   └── champion_cache.py
│
├── utils/                 # Utilidades generales
│   ├── constants.py
│   ├── helpers.py
│   ├── cache_utils.py
│   ├── player_filters.py
│   ├── load_accounts.py
│   ├── spectate_bat.py
│   └── ...
│
├── models/                # Modelos de datos
│   ├── bootcamp_player.py
│   └── soloq_match.py
│
├── .env                   # Variables de entorno (API keys, tokens)
├── config.py              # Carga de variables de entorno
├── requirements.txt
├── README.md
└── main.py                # Script de arranque y actualización de datos
```

---

## Instalación

1. **Clona el repositorio:**
    ```bash
    git clone https://github.com/tuusuario/JetaDirectaBot.git
    cd LoLProTrackr
    ```

2. **Instala las dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

3. **Configura el archivo `.env`:**
    ```
    RIOT_API_KEY=tu_api_key_de_riot
    DISCORD_TOKEN=tu_token_de_discord
    LOL_API_KEY=tu_api_key_de_lol_esports
    ```

4. **(Opcional) Ajusta los intervalos de las tareas:** todas las variables de
   funcionamiento (`CHECK_GAMES_INTERVAL`, `TRACKER_CONCURRENCY`,
   `DPM_PATCH`...) se leen de `.env` y tienen valor por defecto en `config.py`.

---

## Uso

**Arrancar el bot:**
```bash
python main.py
```

Eso es todo: un solo proceso. `main.py` comprueba la configuración, abre el
puerto de salud, arranca las tareas automáticas y conecta con Discord.

En Windows, si `python` no apunta al intérprete correcto, usa la ruta completa:
```bash
"C:/Users/Chino/AppData/Local/Programs/Python/Python312/python.exe" main.py
```

Al arrancar, la consola imprime un resumen: comandos registrados, jugadores
seguidos, tareas activas con su intervalo, y servidores con avisos si les falta
canal o permisos. Para pararlo, `Ctrl+C` (hace un cierre ordenado: vuelca los
rangos pendientes y cierra las sesiones HTTP).

**Variables útiles:**

| Variable | Para qué |
|---|---|
| `LOG_LEVEL=DEBUG` | Ver el detalle interno del tracker. Por defecto `INFO`. |
| `STARTUP_REFRESH=1` | Forzar la descarga de cuentas antes de conectar. Retrasa el arranque; solo para depurar los scrapers. |

---

## Comandos disponibles

Son **slash commands** (`/comando`): Discord los autocompleta, enseña qué hace
cada uno y valida los argumentos. Los antiguos `!comando` ya no existen.

Los nombres están **en inglés y son de una palabra** (`/info`, `/history`,
`/esports`), que es lo que se entiende en cualquier servidor. Lo que cambia con
`/language` es lo que contesta el bot, no los nombres de sus comandos.

### Partidas de SoloQ
- `/live [liga]` — Pros que están jugando SoloQ ahora mismo (`/live lck` para una liga)
- `/match <jugador>` — La partida en vivo de un pro, con los diez participantes
- `/info <jugador>` — Ficha: equipo, elo y partida actual
- `/team <equipo>` — Plantilla de un equipo, con la mejor cuenta de cada jugador

### Datos y clasificación
- `/ranking <liga> [rol] [limite]` — Tabla de SoloQ de una liga (20 ligas en el desplegable).
  Con rol y límite: `/ranking lck mid limit:10`
- `/history [liga|jugador|cuenta]` — Últimas partidas de SoloQ: sin argumento, de todos;
  `/history lec` de una liga; `/history Elyoya` de un pro; `/history Caps#EUW` de una cuenta
- `/leagues` — Ver o elegir qué ligas sigue el servidor

### Esports (partidos profesionales)
- `/esports [liga]` — Partidos profesionales en vivo o a punto de empezar
- `/schedule` — Calendario de los próximos partidos

### Avisos personales por DM
- `/track <pro|liga>` — Que te avise por privado cuando juegue
- `/untrack <pro|liga|all>` — Dejar de recibir esos avisos
- `/following` — A quién sigues y si el bot puede escribirte

### Configuración · requiere *Gestionar servidor*
- `/subscribe [type] [objetivo]` — Añadir este canal a los avisos. Sin objetivo, todas las ligas
  del servidor; con objetivo, **solo** eso: `/subscribe soloq lck`, `/subscribe esports lck`,
  `/subscribe soloq T1`, `/subscribe soloq Elyoya`
- `/channels` — Ver los canales con avisos y cuántos caben
- `/unsubscribe [type]` — Quitar este canal de los avisos
- `/mute [type]` — Apagar los avisos en todo el servidor
- `/language [código]` — Ver o cambiar el idioma del bot

### Estado
- `/health` — Si las fuentes de datos van bien y cuándo se actualizaron
- `/premium` — Los dos planes (Gratis y Pro) y los cupos de este servidor
- `/help` — La lista de comandos

---

## Notas técnicas

- **El bot usa caché para acelerar consultas y evitar rate limit.**
- **Las imágenes de jugadores y equipos se descargan y almacenan localmente.**
- **El bot puede funcionar en Windows, Linux y servicios cloud (Render, Replit, Discloud, etc).**
- **La estructura modular permite agregar nuevas ligas, comandos y extensiones fácilmente.**
- **El bot soporta scraping y actualización automática de datos de jugadores y equipos.**

---

## Contribuir

1. Haz un fork del repositorio.
2. Crea una rama nueva para tu feature o fix.
3. Haz tus cambios y abre un Pull Request.

---

## Licencia

Copyright (c) 2025 set4jeta. Todos los derechos reservados.

Este software y su código fuente están protegidos por las leyes de derechos de autor y son propiedad exclusiva del autor. 

Queda prohibida cualquier forma de reproducción, distribución, modificación, uso o explotación del código, total o parcial, sin el consentimiento previo, expreso y por escrito del autor.

Puedes usarlo de manera personal para trackear partidas o agregarlo a algun servidor para tus amigos

Este software se proporciona únicamente con fines de demostración o revisión privada, y no está destinado a su uso comercial, distribución pública, ni a su modificación por terceros.

Para consultas de licencia o autorización de uso, contactar a: [scre4m.for.me@gmail.com].

---

## Créditos

- Basado en APIs públicas de Riot Games, DPM.lol y LoL Esports.
- Imágenes y datos de equipos/jugadores son propiedad de sus respectivos dueños.

---

## Contacto

Para dudas, sugerencias o soporte, abre un issue en GitHub o contacta al autor.
