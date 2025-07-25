# JetaDirectaBot

## Descripción

JetaDirectaBot es un bot avanzado para Discord que permite **trackear jugadores profesionales y amateurs de League of Legends**, mostrar partidas en vivo, consultar estadísticas, gestionar inscripciones para torneos y recibir notificaciones automáticas de partidas competitivas (LEC, LCS, LCK, MSI, Worlds, etc).

Incluye integración con APIs de Riot, DPM.lol y LoL Esports, scraping de datos, gestión de cuentas y comandos para torneos personalizados como la Jetacup.

---

## Características principales

- **Trackeo de jugadores y equipos LEC/LEC+**
- **Notificaciones automáticas de partidas en vivo**
- **Historial y ranking de SoloQ europeo**
- **Comandos para ver partidas activas, próximas y estadísticas**
- **Gestión de inscripciones y registro para torneos (Jetacup)**
- **Integración con Google Sheets para inscripciones**
- **Scraping y actualización automática de datos de jugadores**
- **Soporte para imágenes de jugadores y equipos**
- **Comandos para admins y usuarios**

---

## Estructura general del proyecto

```
JetaDirectaBot/
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
├── copa/                  # Lógica de torneos Jetacup
│   ├── registro.py
│   ├── validacion.py
│   ├── datos.py
│   ├── sheets.py
│   └── ...
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
    cd JetaDirectaBot
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

4. **(Opcional) Configura credenciales de Google Sheets para Jetacup:**
    - Coloca tu archivo `credentials.json` en la carpeta `secrets/` y define la variable `CREDENTIALS_PATH` en `.env` si usas Render u otro host.

---

## Uso

1. **Arranca el bot:**
    ```bash
    python main.py
    ```

2. **El bot actualizará los datos y lanzará el bot de Discord automáticamente.**

---

## Comandos disponibles

### **Comandos generales**
- `!help` — Muestra la ayuda y lista de comandos
- `!setchannel` — Configura el canal para notificaciones de partidas SoloQ
- `!unsubscribe` — Elimina el canal de notificaciones SoloQ

### **Trackeo y partidas**
- `!team <equipo>` — Muestra los jugadores de un equipo LEC/LEC+
- `!live` — Muestra los jugadores en partida en ese momento
- `!info <jugador>` — Muestra información detallada de un jugador
- `!match <jugador>` — Muestra la partida activa de un jugador
- `!historial` — Muestra el historial general de partidas
- `!historial <jugador>` — Muestra el historial de un jugador
- `!historial <cuenta>` — Muestra el historial de una cuenta específica
- `!ranking` — Muestra el ranking de jugadores trackeados

### **Comandos Esports (partidas competitivas)**
- `!setlivechannel` — Configura el canal para notificaciones de partidas de esports (LEC, Worlds, etc)
- `!removelivechannel` — Elimina el canal de notificaciones de esports
- `!partida` — Muestra partidas en vivo de esports
- `!next` — Muestra las próximas partidas competitivas

### **Comandos Jetacup (torneo personalizado)**
- `!jetacup` — Muestra información sobre la Jetacup
- `!jetacup registro` — Inicia el registro paso a paso
- `!jetacup cancelarregistro` — Cancela el registro en curso
- `!jetacup cancelarinscripcion` — Elimina tu inscripción
- `!jetacup registrados` — Muestra la lista de inscritos

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
