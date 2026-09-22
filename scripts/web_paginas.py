"""Las páginas de contenido: hub de ligas, una por liga, avisos, comparativa y 404.

Qué es esto en términos de SEO
------------------------------
Es la parte "template + variable" del material que pidió el usuario: **una
plantilla y 20 ligas** producen 20 páginas que responden a búsquedas que hoy no
tienen una página propia en ninguna parte ("elo de los jugadores de la LFL",
"quién es el mejor de la LEC en SoloQ", "equipos de la NLC"). No es contenido
duplicado porque cada una lleva datos distintos y medidos; lo que se repite es la
estructura, que es exactamente lo que tiene que repetirse.

Y es también la parte de "intención Do que un LLM no te puede robar": el aviso de
que un pro ha entrado en partida **ocurre en Discord**, no en una respuesta de
chat. Un modelo puede resumir la tabla de Elo; no puede notificarte a las 3 de la
mañana de que Caps está en cola.

Las tres reglas que gobiernan cada página
-----------------------------------------
1. **Si el dato no está, la sección no se pinta.** Y cuando hay dos calidades del
   mismo dato, se pinta la que hay con la tabla que le corresponde: la LEC está
   barrida jugador por jugador (50, con Riot ID y con historial de campeones) y
   las otras 19 están medidas contra el leaderboard de su liga (869 jugadores más,
   con Elo, victorias y KDA pero sin Riot ID). Son dos tablas distintas y no una
   con celdas vacías. Una página que diga "0 jugadores" es peor que una página sin
   esa sección; una que prometa una columna que no puede rellenar, también.
2. **Un `<h1>` y nada más.** Los `<h2>` van formulados como preguntas, que es la
   forma en la que se busca y la que un modelo puede citar como bloque.
3. **El schema sale de la misma variable que el HTML.** Las FAQ se escriben una
   vez y se usan para pintar y para el JSON-LD, así que no pueden divergir. El
   `ItemList` describe la tabla que de verdad está pintada, no la mejor de las dos.
"""

from __future__ import annotations

from tracking.soloq.leagues import LIGAS, MAX_LIGAS_POR_SERVIDOR
from utils import branding

from scripts import web_datos as datos
from scripts import web_layout as maq
from scripts import web_seo as seo
from scripts.web_seo import Pagina
from scripts.web_layout import e

#: Cuántos jugadores salen en la tabla de una liga. 15 cubre las tres primeras
#: plantillas completas de la LEC; con los 50 la página se convierte en una lista
#: infinita que nadie baja a leer, y el resto se ve igual en `/ranking`.
TOPE_TABLA = 15

#: Cuántos campeones salen en el agregado. 8 caben en pantalla sin scroll en
#: móvil, que es donde se lee esto.
TOPE_CAMPEONES = 8

#: Cuántos avisos publicados se enseñan en `avisos.html`. Con 12 se ve que el
#: bot avisa de verdad y que no es siempre el mismo jugador, sin convertir la
#: página en un volcado de log. El registro en disco guarda 500.
TOPE_AVISOS = 12


# ---------------------------------------------------------------------- #
# Componentes
# ---------------------------------------------------------------------- #

def tldr(lineas: list[str]) -> str:
    """El bloque de resumen del principio de la página.

    Está por dos motivos que apuntan al mismo sitio. Para una persona, es lo que
    permite saber en tres líneas si la página tiene lo que buscaba. Para un
    modelo que extrae contenido, es un bloque delimitado con la respuesta
    completa y sin adorno, que es el formato que acaba citado; una respuesta
    repartida en cuatro párrafos hay que reconstruirla y casi nunca se cita.
    """
    filas = "\n".join(f"      <li>{linea}</li>" for linea in lineas)
    return (
        '    <div class="resumen">\n'
        "      <p><strong>In short</strong></p>\n"
        f"      <ul>\n{filas}\n      </ul>\n"
        "    </div>\n"
    )


def faq_html(preguntas: list[tuple[str, str]]) -> str:
    """Las preguntas frecuentes, en HTML.

    Recibe **la misma lista** que se le pasa a `seo.faq()`, y ese es el punto:
    el marcado de datos estructurados no puede declarar una pregunta que no esté
    en la página, y con una sola variable no hay forma de que se separen.

    Van como `<h3>` dentro de una sección con su `<h2>`, no como `<h2>` cada
    una: son subapartados de "preguntas frecuentes" y ponerlas al nivel de las
    secciones grandes rompe el esquema de encabezados.
    """
    bloques = []
    for pregunta, respuesta in preguntas:
        bloques.append(
            f"      <h3>{e(pregunta)}</h3>\n"
            f"      <p>{e(respuesta)}</p>"
        )
    return "\n".join(bloques)


def img_html(imagen, alt: str, *, clase: str, tope: int) -> str:
    """Un `<img>` con `width`, `height`, `loading` y `decoding`, o nada.

    Las cuatro cosas son de la lista del usuario y cada una arregla un problema
    distinto:

    * `width`/`height` reales (medidos con `web_datos.medir_imagen`) para que el
      navegador reserve el hueco y la página no salte al cargar: eso es CLS.
    * `loading="lazy"` porque una página de liga puede llevar 15 fotos y solo se
      ven dos sin bajar.
    * `decoding="async"` para que decodificar el WebP no bloquee el hilo de
      pintado.

    Si no hay imagen devuelve cadena vacía y el llamante pinta la tarjeta sin
    foto. Es el caso normal: hay foto de 38 de los 50 jugadores.

    `tope` es el ancho al que se enseña. Se reescala la altura para no deformar
    la imagen, porque los logos vienen en tamaños distintos y forzar un cuadrado
    aplastaría los que son anchos.
    """
    if imagen is None:
        return ""
    ancho = min(tope, imagen.ancho)
    alto = max(1, round(imagen.alto * ancho / imagen.ancho))
    return (
        f'<img class="{clase}" src="{e(imagen.src)}" alt="{e(alt)}" '
        f'width="{ancho}" height="{alto}" loading="lazy" decoding="async">'
    )


def tabla_jugadores(jugadores: list[datos.Jugador], *, tope: int = TOPE_TABLA) -> str:
    """La tabla de Elo de una liga.

    Es una `<table>` de verdad y no divs con CSS: son datos tabulares, un lector
    de pantalla los anuncia por fila y columna, y es lo que un extractor
    reconoce como tabla sin tener que adivinar.

    La columna de la cuenta lleva el Riot ID completo porque es el dato que
    convierte esta tabla en algo que no está en ninguna otra parte: los rankings
    públicos dan el nombre del pro, no con qué cuenta juega.
    """
    filas = []
    for i, j in enumerate(jugadores[:tope], start=1):
        foto = img_html(
            datos.imagen_de_jugador(j.nombre), j.nombre, clase="mini", tope=28
        )
        filas.append(
            "        <tr>\n"
            f'          <td class="pos">{i}</td>\n'
            f"          <td>{foto}<b>{e(j.nombre)}</b></td>\n"
            f"          <td>{e(j.equipo)}</td>\n"
            f"          <td>{e(j.rol)}</td>\n"
            f'          <td class="rango">{e(j.rango_texto) or "—"}</td>\n'
            f'          <td class="cuenta">{e(j.riot_id) or "—"}</td>\n'
            "        </tr>"
        )
    return (
        '    <table class="tabla">\n'
        "      <thead>\n"
        "        <tr><th>#</th><th>Player</th><th>Team</th><th>Role</th>"
        "<th>Rank</th><th>SoloQ account</th></tr>\n"
        "      </thead>\n"
        "      <tbody>\n" + "\n".join(filas) + "\n      </tbody>\n"
        "    </table>\n"
    )


def tabla_clasificacion(
    clasificados: list[datos.Clasificado], *, tope: int = TOPE_TABLA
) -> str:
    """La tabla de Elo de una liga que solo está medida por el leaderboard.

    Es una tabla **distinta** a `tabla_jugadores` y no la misma con celdas
    vacías. Lo que cambia:

    * No hay columna "Cuenta de SoloQ": el leaderboard identifica por `puuid` y
      `displayName`, no por Riot ID. Pintar la columna vacía sería prometer un
      dato que no está.
    * Hay victorias y KDA, que en la tabla de la LEC no salen porque allí el dato
      equivalente está en el agregado de campeones con su DPM.

    El guion en las partidas no es decorativo: cuatro filas de las 919 vienen sin
    tier y con 0-0, y escribir "0 %" en esas sería publicar un dato falso.
    """
    filas = []
    for i, c in enumerate(clasificados[:tope], start=1):
        foto = img_html(
            datos.imagen_de_jugador(c.nombre), c.nombre, clase="mini", tope=28
        )
        partidas = f"{c.winrate} % of {c.partidas}" if c.partidas else "—"
        filas.append(
            "        <tr>\n"
            f'          <td class="pos">{i}</td>\n'
            f"          <td>{foto}<b>{e(c.nombre)}</b></td>\n"
            f"          <td>{e(c.equipo)}</td>\n"
            f"          <td>{e(c.rol) or '—'}</td>\n"
            f'          <td class="rango">{e(c.rango_texto) or "—"}</td>\n'
            f"          <td>{e(partidas)}</td>\n"
            f"          <td>{c.kda:.2f}</td>\n"
            "        </tr>"
        )
    return (
        '    <table class="tabla">\n'
        "      <thead>\n"
        "        <tr><th>#</th><th>Player</th><th>Team</th><th>Role</th>"
        "<th>Rank</th><th>Wins</th><th>KDA</th></tr>\n"
        "      </thead>\n"
        "      <tbody>\n" + "\n".join(filas) + "\n      </tbody>\n"
        "    </table>\n"
    )


def tabla_presencia(usos: list[datos.UsoCampeon]) -> str:
    """Los campeones del ranking, contados por presencia y no por partidas.

    Dos columnas y no seis. `mostChamps` dice qué campeones juega más cada uno,
    pero no cuántas veces ni con qué resultado, así que lo único que se puede
    afirmar es en cuántos rankings aparece cada campeón. La tabla de la LEC —con
    partidas, winrate y DPM— sale de otra fuente y no se mezcla con esta.
    """
    filas = []
    for u in usos:
        filas.append(
            "        <tr>\n"
            f"          <td><b>{e(u.nombre)}</b></td>\n"
            f"          <td>{u.jugadores}</td>\n"
            f"          <td>{e(u.top)}</td>\n"
            "        </tr>"
        )
    return (
        '    <table class="tabla">\n'
        "      <thead>\n"
        "        <tr><th>Champion</th><th>Players who run it</th>"
        "<th>Highest-ranked player on it</th></tr>\n"
        "      </thead>\n"
        "      <tbody>\n" + "\n".join(filas) + "\n      </tbody>\n"
        "    </table>\n"
    )


def tabla_campeones(usos: list[datos.UsoCampeon]) -> str:
    """El agregado de campeones más jugados.

    El DPM va en la tabla porque es el dato propio: sale de ponderar por partidas
    el DPM de cada jugador con ese campeón, y no existe agregado así en ninguna
    web pública de la liga.
    """
    filas = []
    for u in usos:
        filas.append(
            "        <tr>\n"
            f"          <td><b>{e(u.nombre)}</b></td>\n"
            f"          <td>{u.partidas}</td>\n"
            f"          <td>{u.winrate} %</td>\n"
            f"          <td>{u.dpm}</td>\n"
            f"          <td>{u.jugadores}</td>\n"
            f"          <td>{e(u.top)}</td>\n"
            "        </tr>"
        )
    return (
        '    <table class="tabla">\n'
        "      <thead>\n"
        "        <tr><th>Champion</th><th>Games</th><th>Wins</th>"
        "<th>Average DPM</th><th>Players</th><th>Plays it most</th></tr>\n"
        "      </thead>\n"
        "      <tbody>\n" + "\n".join(filas) + "\n      </tbody>\n"
        "    </table>\n"
    )


def tarjetas_equipos(tricodes: list[str]) -> str:
    """Los equipos de una liga como tarjetas con su logo si lo hay."""
    tarjetas = []
    for t in tricodes:
        nombre = datos.nombre_de_equipo(t)
        logo = img_html(datos.imagen_de_equipo(t), nombre, clase="logo", tope=48)
        plantilla = datos.plantilla_de(t)
        detalle = (
            f"<span>{len(plantilla)} players</span>" if plantilla else ""
        )
        tarjetas.append(
            '      <li class="equipo">'
            f"{logo}<b>{e(t)}</b> {e(nombre)}{detalle}</li>"
        )
    return '    <ul class="equipos">\n' + "\n".join(tarjetas) + "\n    </ul>\n"


# ---------------------------------------------------------------------- #
# Próximos partidos
# ---------------------------------------------------------------------- #

#: Días y meses en palabras. Están aquí y no con `strftime("%A")` porque el
#: nombre del día que devuelve `strftime` depende del `locale` de la máquina que
#: genera la web: en un runner de GitHub Actions saldría "Thursday" en una página
#: en español, y no habría ningún error visible.
_DIAS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
         "Sunday")
_MESES = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def dia_en_palabras(iso: str) -> str:
    """`"2026-09-03"` -> `"Thursday 3 September"`. La cadena tal cual si falla."""
    from datetime import date

    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return f"{_DIAS[d.weekday()]} {d.day} {_MESES[d.month - 1]}"


def tarjeta_partido(partido, *, con_liga: bool) -> str:
    """Un partido como tarjeta: hora, liga, fase, y los dos equipos con su récord.

    El logo se pinta **solo si está descargado**, igual que en las tarjetas de
    equipo: hay 12 logos locales de los 75 equipos que aparecen en el calendario,
    y los otros 63 están en `static.lolesports.com`. No se enlazan desde ahí a
    propósito —serían 63 peticiones a un tercero desde una web que declara no
    hacer ninguna— y descargarlos son ~4 MB de PNG de 1000×1000 que habría que
    reescalar. Sin logo la tarjeta se lee igual: el tricode es lo que identifica
    al equipo en cualquier marcador.

    `con_liga` va a False en las páginas de liga, donde repetir "LEC" en los ocho
    partidos de la LEC no informa de nada.
    """
    a, b = partido.equipos
    etiquetas = []
    if con_liga:
        etiquetas.append(e(partido.liga_nombre))
    if partido.fase:
        etiquetas.append(e(partido.fase))
    if partido.bo:
        etiquetas.append(f"Bo{partido.bo}")
    marca = ' <b class="vivo">live</b>' if partido.en_juego else ""

    lados = []
    for equipo in (a, b):
        logo = img_html(
            datos.imagen_de_equipo(equipo.codigo), equipo.nombre,
            clase="mini", tope=22,
        )
        record = f' <span>{e(equipo.record)}</span>' if equipo.record else ""
        lados.append(
            f'        <span class="lado">{logo}<b>{e(equipo.codigo)}</b>'
            f"{record}</span>"
        )

    # La línea de etiquetas solo se pinta si hay alguna. Hoy las 93 traen fase y
    # Bo, pero un `<p>` vacío con su borde superior sería una raya suelta al pie
    # de la tarjeta, y eso es lo que se ve cuando la fuente deja de dar un campo.
    pie = (
        f'\n        <p class="etiquetas">{" · ".join(etiquetas)}</p>'
        if etiquetas else ""
    )
    return (
        '      <li class="partido">\n'
        f'        <p class="cuando"><time datetime="{e(partido.inicio)}">'
        f'{e(partido.hora)} UTC</time>{marca}</p>\n'
        + "\n".join(lados)
        + f"{pie}\n"
        "      </li>"
    )


def partidos_html(lista: list, *, con_liga: bool = True) -> str:
    """Los partidos agrupados por día, cada día con su rejilla de tarjetas.

    Agrupados y no en una lista plana porque la pregunta que trae a alguien aquí
    es "¿juega hoy?", y 93 partidos seguidos sin cortes no la responden. El
    encabezado de cada día lleva la fecha en palabras y el `<time>` la lleva en
    ISO, que es lo que puede leer una máquina.
    """
    if not lista:
        return ""
    por_dia: dict[str, list] = {}
    for partido in lista:
        por_dia.setdefault(partido.dia, []).append(partido)

    bloques = []
    for dia, delo in por_dia.items():
        tarjetas = "\n".join(tarjeta_partido(p, con_liga=con_liga) for p in delo)
        bloques.append(
            f'    <h3 class="dia"><time datetime="{e(dia)}">'
            f"{e(dia_en_palabras(dia))}</time></h3>\n"
            f'    <ul class="partidos">\n{tarjetas}\n    </ul>\n'
        )
    return "".join(bloques)


def _intro_partidos(liga, lista: list) -> str:
    """El párrafo del calendario de una liga, **distinto en cada una**.

    Mismo motivo que `_intro_tabla`: esta sección se va a repetir en 16 páginas y
    un párrafo idéntico en 16 páginas es la forma exacta del `scaled content
    abuse`. Lo que lo diferencia son datos de esta liga y de este calendario:
    cuántos partidos hay, cuándo es el primero, qué equipos lo juegan, cuántos
    días distintos cubre y si hay alguno en juego ahora.
    """
    dias = len({p.dia for p in lista})
    primero = lista[0]
    a, b = primero.equipos
    vivos = sum(1 for p in lista if p.en_juego)
    cuantos = (
        f"The next {e(liga.nombre)} match"
        if len(lista) == 1 else
        f"The next {len(lista)} {e(liga.nombre)} matches"
    )
    reparto = "" if dias <= 1 else f", spread over {dias} days"
    if vivos:
        cierre = (
            f" {vivos} of them are being played right now."
            if vivos > 1 else " One of them is being played right now."
        )
    else:
        cierre = (
            f" The first one is {e(a.codigo)} vs {e(b.codigo)}, on "
            f"{e(dia_en_palabras(primero.dia))} at {e(primero.hora)} UTC."
        )
    return (
        f'      <p class="intro">{cuantos}{reparto}, with kick-off times in '
        f"UTC.{cierre}</p>\n"
    )


def seccion_partidos(liga, lista: list, *, medido: str = "") -> str:
    """El calendario de una liga como sección completa, o cadena vacía.

    Va en la página de la liga y no en una página aparte porque la pregunta
    "¿cuándo juega mi equipo?" se hace sobre una liga concreta, y porque es lo
    único de esa página que cambia todos los días: el resto (Elo, campeones,
    equipos) se mueve despacio. Es la frescura que el material de SEO pone como
    señal cuando un sistema de IA elige de dónde responder.

    La nota final lleva el nombre de la liga dentro **a propósito**. La primera
    versión era la misma frase en las 16 páginas con calendario y
    `medir_duplicidad.py` la sacó a la primera, en x16. Con el nombre y la
    plataforma dentro, cada una dice algo que solo vale para su liga.
    """
    if not lista:
        return ""
    nota = ""
    if medido:
        donde = (
            f" The bot watches those same players on {e(liga.plataforma)} and "
            "alerts when they queue up for SoloQ."
            if liga.seguible and liga.plataforma and not liga.plataforma_mixta
            else ""
        )
        nota = (
            f'      <p class="nota">Official {e(liga.nombre)} schedule on '
            f"lolesports, read on {e(medido[:10])}. The {e(liga.nombre)} times "
            "here are UTC, not local time: this page is served identically "
            f"everywhere.{donde}</p>\n"
        )
    return (
        "  <section>\n"
        '    <div class="envoltura">\n'
        f"      <h2>When does the {e(liga.nombre)} play?</h2>\n"
        f"{_intro_partidos(liga, lista)}"
        f"{partidos_html(lista, con_liga=False)}"
        f"{nota}"
        "    </div>\n"
        "  </section>\n"
    )


# ---------------------------------------------------------------------- #
# Una página por liga
# ---------------------------------------------------------------------- #

def ruta_de_liga(codigo: str) -> str:
    """`"lec"` -> `"liga-lec.html"`.

    Con prefijo y en la raíz, no en una carpeta `/ligas/lec.html`: la web se
    publica en GitHub Pages sin servidor propio, así que no hay reescritura de
    URL, y una URL plana no puede romperse por una barra de más o de menos.
    """
    return f"liga-{codigo}.html"


#: Grupos de ligas que alguien compararía entre sí. Existen para los enlaces
#: laterales entre páginas de liga, y el criterio es "quién mira esto también
#: mira aquello": las cinco grandes entre ellas, las regionales europeas entre
#: ellas, y Brasil con su segunda división.
_FAMILIAS: tuple[tuple[str, ...], ...] = (
    ("lec", "lck", "lcs", "lpl", "lcp", "msi"),
    ("lfl", "nlc", "prm", "les", "lit", "rl", "rol", "hm", "ebl", "hll", "tcl", "al"),
    ("cblol", "cd"),
)

#: Las que se ofrecen como salida a cualquier página, cuando su familia no da
#: para cuatro. Son las que más se buscan, así que son el mejor destino posible
#: para alguien que ha llegado a una liga pequeña.
_GRANDES: tuple[str, ...] = ("lec", "lck", "lcs")


def _familia_de(codigo: str) -> tuple[str, ...]:
    for familia in _FAMILIAS:
        if codigo in familia:
            return familia
    return ()


def ligas_vecinas(codigo: str, cuantas: int = 4) -> list[str]:
    """Las ligas a las que enlaza la página de `codigo`, en orden de afinidad.

    Los enlaces laterales entre páginas hermanas existen por la parte de ranking
    que sí se controla desde dentro del sitio: los documentos del juicio
    antimonopolio ponen los **anchors** —los enlaces y su texto— como una de las
    tres señales del cubo de relevancia, junto al cuerpo y a los clics.

    Sin esto, las 20 páginas de liga solo se enlazan hacia arriba (al hub) y no
    entre ellas, así que un rastreador que entra por la LFL tiene que volver al
    hub para llegar a la LEC, y el visitante que quiere comparar dos ligas
    también. Primero la familia (misma clase de liga), después las grandes.
    """
    familia = [c for c in _familia_de(codigo) if c != codigo and c in LIGAS]
    resto = [c for c in _GRANDES if c != codigo and c not in familia and c in LIGAS]
    return (familia + resto)[:cuantas]


def enlaces_vecinas_html(codigo: str) -> str:
    """Los enlaces laterales, con texto descriptivo en vez de "ver más".

    El texto del enlace es señal de relevancia para la página destino, así que
    dice qué hay allí ("Elo de la LCK") y no una fórmula vacía. Y cada uno lleva
    la región, que es lo que distingue una liga de otra para quien no las conoce
    todas.
    """
    vecinas = ligas_vecinas(codigo)
    if not vecinas:
        return ""
    items = []
    for otra in vecinas:
        liga = LIGAS[otra]
        items.append(
            f'      <li><a href="{ruta_de_liga(otra)}">{e(liga.nombre)} SoloQ '
            f"ranks</a> <span>{e(liga.region)}</span></li>"
        )
    return (
        "  <section>\n"
        '    <div class="envoltura">\n'
        "      <h2>Compare with other leagues</h2>\n"
        '      <ul class="vecinas">\n' + "\n".join(items) + "\n      </ul>\n"
        "    </div>\n"
        "  </section>\n"
    )


def _preguntas_de_liga(liga, censo, jugadores, clasificados, equipos,
                       proximos=()) -> list[tuple[str, str]]:
    """Las FAQ de una página de liga, **solo las que se pueden responder**.

    Si no hay ni jugadores barridos ni ranking no se pregunta "quién tiene más
    Elo", porque la respuesta sería un hueco. Esto es lo que impide que el
    `FAQPage` declare una pregunta cuya respuesta no está en la página.

    El primero se saca de la fuente que se esté pintando, no de la mejor de las
    dos: si la tabla visible es la del ranking y la respuesta viniera del barrido,
    la FAQ podría nombrar a alguien que no sale en la tabla de arriba.
    """
    preguntas: list[tuple[str, str]] = []
    primero = (jugadores or clasificados or [None])[0]
    if primero is not None:
        cuantos = len(jugadores or clasificados)
        preguntas.append((
            f"Who has the highest SoloQ rank in the {liga.nombre}?",
            f"{primero.nombre} ({primero.equipo}, {primero.rol}), at "
            f"{primero.rango_texto or 'rank not on record'}. It is the highest "
            f"of the {cuantos} {liga.nombre} players that "
            f"{branding.BOT_NOMBRE} has indexed.",
        ))
    if censo.hay:
        # La cifra de cuentas por jugador va calculada y no como frase fija: es
        # un dato distinto en cada liga (los coreanos tienen más cuentas que los
        # de una regional) y sustituye a la coletilla que salía en 20 páginas.
        por_jugador = censo.cuentas / censo.personas if censo.personas else 0
        preguntas.append((
            f"How many professional players does the {liga.nombre} have?",
            f"{censo.personas} players across {censo.equipos} teams, with about "
            f"{censo.cuentas} SoloQ accounts between them: an average of "
            f"{por_jugador:.1f} accounts per player. It comes from counting the "
            f"{liga.nombre} leaderboard, not from an estimate.",
        ))
    preguntas.append((
        f"Can you tell when a {liga.nombre} player queues up for SoloQ?",
        (
            f"Yes. {branding.BOT_NOMBRE} posts to your Discord channel with the "
            f"champion, the role, the rank and the team of the {liga.nombre} "
            "player as soon as the game starts, without you having to ask for "
            "anything."
            if liga.seguible else
            f"Not live. The {liga.nombre} plays on servers that Riot's API does "
            "not expose, so ranks and standings can be read, but the game in "
            "progress cannot be detected."
        ),
    ))
    if equipos:
        preguntas.append((
            f"Which teams are in the {liga.nombre}?",
            ", ".join(f"{datos.nombre_de_equipo(t)} ({t})" for t in equipos) + ".",
        ))
    if proximos:
        # Pregunta con fecha dentro, que es la que hace que la respuesta se pueda
        # citar tal cual: "¿cuándo juega la LEC?" se busca todos los días y la
        # respuesta cambia todos los días. Es la única FAQ del sitio que caduca, y
        # caduca a la vez que el fichero del calendario.
        siguiente = proximos[0]
        uno, otro = siguiente.equipos
        cuando = (
            f"{uno.nombre} vs {otro.nombre}, on "
            f"{dia_en_palabras(siguiente.dia)} at {siguiente.hora} UTC"
        )
        if siguiente.en_juego:
            respuesta = (
                f"{uno.nombre} vs {otro.nombre} is being played right now. The "
                f"official schedule still lists {len(proximos)} {liga.nombre} "
                "matches."
            )
        elif len(proximos) > 1:
            dias = len({p.dia for p in proximos})
            fase = f" ({siguiente.fase})" if siguiente.fase else ""
            respuesta = (
                f"{cuando}{fase}. After that there are {len(proximos) - 1} more "
                f"spread over {dias} days of the schedule."
            )
        else:
            respuesta = (
                f"{cuando}. It is the only one left on the official lolesports "
                "schedule."
            )
        preguntas.append((
            f"When is the next {liga.nombre} match?", respuesta,
        ))
    preguntas.append(_pregunta_propia(liga, censo, jugadores, clasificados))
    return preguntas


def _pregunta_propia(liga, censo, jugadores, clasificados) -> tuple[str, str]:
    """Una pregunta que **solo tiene sentido en esta liga**.

    Es la defensa contra `scaled content abuse`, la política con la que Google
    tumbó sitios en la actualización de spam de agosto de 2026. Veinte páginas
    generadas con la misma plantilla y la misma FAQ son el patrón exacto que
    persigue; medido con `scripts/medir_duplicidad.py`, las FAQ genéricas eran las
    frases que aparecían en 19 y 20 páginas.

    La respuesta se construye con datos que ya tenemos y que son distintos en cada
    liga —región, plataforma, si es rastreable, cuántas cuentas hay medidas—, no
    con relleno. Una pregunta inventada para rellenar sería el mismo problema con
    otra cara.
    """
    if not liga.seguible:
        return (
            f"Why are {liga.nombre} games not detected live?",
            f"Because the {liga.nombre} is played on servers that Riot's public "
            "API does not expose. Rank and standings can be read, but the "
            "current-game query returns nothing for those accounts, so alerting "
            "on a live game is not possible without making the data up.",
        )
    if liga.plataforma_mixta:
        return (
            f"Which server do {liga.nombre} players play on?",
            f"Several: the {liga.nombre} ({liga.region}) brings together players "
            "from different regions, so the server is resolved account by account "
            "instead of assuming one for the whole league. That is why a player "
            "in this league can show the rank of one server and play on another.",
        )
    if jugadores:
        return (
            f"Where do the {liga.nombre} SoloQ accounts come from?",
            "From each player's known accounts, checked one by one against Riot's "
            f"API on {liga.plataforma or 'their server'}. For every player the "
            "highest-ranked account is published, not all of them: someone with "
            "four accounts has a single relevant rank, the one they compete on.",
        )
    if clasificados:
        return (
            f"Is the {liga.nombre} rank from the season or from right now?",
            "From right now. It is each player's current SoloQ rank, read from "
            f"the {liga.nombre} leaderboard and refreshed with the bot's data; it "
            "is not a season history nor the result of official matches, which "
            "are two different things.",
        )
    if censo.hay:
        return (
            f"Why does the {liga.nombre} not have a rank table yet?",
            f"Because the {liga.nombre} ({liga.region}) has its census measured "
            f"—{censo.personas} players across {censo.equipos} teams— but not yet "
            "the rank of each account. Accounts get resolved when a Discord "
            "server starts following the league, which is what triggers the "
            "sweep.",
        )
    return (
        f"What can you follow in the {liga.nombre}?",
        f"The game alerts of its players on Discord. The {liga.nombre} "
        f"({liga.region}) has no published rank table yet, because accounts are "
        "indexed when a server follows the league.",
    )


def _intro_tabla(liga, filas: list, medido: str, *, con_cuentas: bool) -> str:
    """El párrafo que precede a la tabla de Elo, **distinto en cada liga**.

    Existe por lo mismo que `_pregunta_propia`: medido con
    `scripts/medir_duplicidad.py`, este párrafo era una de las frases que salía
    idéntica en 19 de las 20 páginas de liga, y eso es la forma de la plantilla
    que persigue la política de `scaled content abuse`.

    Lo que lo diferencia son datos que ya están calculados: cuántos jugadores hay
    medidos, el servidor donde se mide, el rango del primero y el del último de la
    tabla visible. Nada inventado; solo dicho con las cifras de esta liga.
    """
    total = len(filas)
    visibles = min(total, TOPE_TABLA)
    primero, ultimo = filas[0], filas[min(visibles, total) - 1]
    donde = (
        "account by account, because its players are not all on the same server"
        if liga.plataforma_mixta
        else f"on {liga.plataforma}" if liga.plataforma
        else "on their server"
    )
    horquilla = ""
    if primero.rango_texto and ultimo.rango_texto and visibles > 1:
        horquilla = (
            f" The table runs from {e(primero.rango_texto)} to "
            f"{e(ultimo.rango_texto)}."
        )
    if con_cuentas:
        return (
            f'      <p class="intro">The top {visibles} of the {total} '
            f"{e(liga.nombre)} players that are indexed with an account, measured "
            f"{donde}. For each one the best account is published, not all of "
            "them: a professional with several has a single rank that counts."
            f"{horquilla}</p>\n"
        )
    cuando = f" Measured on {e(medido)}." if medido else ""
    return (
        f'      <p class="intro">The top {visibles} of the {total} players that '
        f"the {e(liga.nombre)} ({e(liga.region)}) has on the leaderboard, ordered "
        f"by the rank of their best account and measured {donde}."
        f"{horquilla}{cuando}</p>\n"
    )


def pagina_liga(codigo: str, sitio: str, fecha: str, pub: str) -> Pagina:
    """La página de una liga. Es la plantilla que se repite 20 veces.

    Cada sección se pinta **solo si hay dato**, y hay dos niveles de dato:

    * La LEC está barrida jugador por jugador: sale la tabla con el Riot ID de la
      mejor cuenta de cada uno y el agregado de campeones con partidas, winrate y
      DPM. Es el material que no está en ninguna otra web.
    * Las otras 19 están medidas con una petición al leaderboard de su liga: sale
      la tabla de Elo con victorias y KDA, y los campeones contados por presencia.
      Sin Riot ID, porque el leaderboard no lo da.

    La alternativa —una sola tabla con las celdas que falten vacías— daría 19
    páginas prometiendo una columna que no puede rellenar. Y la anterior —no
    pintar nada donde no hubiera barrido— dejaba 19 páginas de censo, que es
    contenido de relleno.

    El título lleva el año porque estas páginas se rehacen al regenerar la web y
    la recencia es lo que más pesa cuando un sistema de IA elige de dónde
    responder. El año sale de la fecha de generación, no escrito a mano.
    """
    liga = LIGAS[codigo]
    censo = datos.censo_de(codigo)
    jugadores = datos.jugadores_de(codigo)
    equipos = datos.equipos_de(codigo)
    campeones = datos.campeones_de(codigo, tope=TOPE_CAMPEONES)
    proximos = datos.partidos(codigo)
    anio = fecha[:4]

    # El ranking solo se pinta donde no hay barrido. Donde lo hay, la tabla de
    # `jugadores` es estrictamente mejor (trae el Riot ID) y dos tablas de Elo en
    # la misma página serían el mismo contenido dos veces con números que no
    # cuadrarían: el barrido mira todas las cuentas conocidas del jugador y el
    # leaderboard solo las que están en la lista de su liga.
    clasificados = [] if jugadores else datos.clasificacion_de(codigo)
    presencia = (
        datos.campeones_del_ranking(codigo, tope=TOPE_CAMPEONES)
        if clasificados and not campeones else []
    )
    medido = datos.fecha_de_tablas()

    # El titular tiene que ser único entre las 20 páginas y llevar delante la
    # palabra por la que se busca. "Elo" y "SoloQ" son los dos términos que usa
    # quien busca esto; "ranking" solo lo usa quien ya conoce la web.
    #
    # Las páginas sin barrido no dicen "cuentas" en el título, porque no publican
    # cuentas: prometer en el `<title>` algo que la página no tiene es lo que hace
    # que alguien entre, no lo encuentre y se vaya, y eso se mide.
    if jugadores:
        titulo = f"{liga.nombre} SoloQ ranks and accounts ({anio})"
        descripcion = (
            f"The {len(jugadores)} {liga.nombre} players with their SoloQ rank, "
            "their account and the champions they are playing. Data from "
            f"{branding.BOT_NOMBRE}, last updated {fecha}."
        )
    elif clasificados:
        titulo = f"{liga.nombre} SoloQ rank ladder ({anio})"
        primero = clasificados[0]
        descripcion = (
            f"The {len(clasificados)} {liga.nombre} players ordered by SoloQ "
            f"rank. {primero.nombre} ({primero.equipo}) leads with "
            f"{primero.rango_texto or 'rank not on record'}. Measured on "
            f"{medido or fecha}."
        )
    elif censo.hay:
        titulo = f"{liga.nombre} players and teams on SoloQ ({anio})"
        descripcion = (
            f"The {liga.nombre} ({liga.region}): {censo.personas} professional "
            f"players across {censo.equipos} teams and about {censo.cuentas} "
            "SoloQ accounts. Discord alerts when they queue up for a game."
        )
    else:
        titulo = f"The {liga.nombre} on SoloQ: Discord alerts ({anio})"
        descripcion = (
            f"The {liga.nombre} ({liga.region}) on {branding.BOT_NOMBRE}: Discord "
            "alerts when its players queue up for SoloQ."
        )

    resumen = []
    if censo.hay:
        resumen.append(
            f"The <b>{e(liga.nombre)}</b> ({e(liga.region)}) has "
            f"<b>{censo.personas} players</b> across {censo.equipos} teams and "
            f"about {censo.cuentas} SoloQ accounts measured."
        )
    if jugadores or clasificados:
        primero = (jugadores or clasificados)[0]
        resumen.append(
            f"The highest rank right now belongs to <b>{e(primero.nombre)}</b> "
            f"({e(primero.equipo)}): {e(primero.rango_texto)}."
        )
    if campeones:
        resumen.append(
            f"The most played champion is <b>{e(campeones[0].nombre)}</b>: "
            f"{campeones[0].partidas} games and {campeones[0].winrate} % wins."
        )
    elif presencia:
        resumen.append(
            f"The champion played by most players is "
            f"<b>{e(presencia[0].nombre)}</b>: {presencia[0].jugadores} players "
            "in the league have it among their most played."
        )
    # El calendario va en el resumen porque es la única línea que cambia todos
    # los días, y "¿juega hoy?" es la pregunta que trae gente nueva a una página
    # de liga. Con el partido concreto dentro, no solo el número: una línea que
    # dice "hay 8 partidos" no responde nada.
    if proximos:
        siguiente = proximos[0]
        uno, otro = siguiente.equipos
        resumen.append(
            f"Live now: <b>{e(uno.codigo)} - {e(otro.codigo)}</b>."
            if siguiente.en_juego else
            f"The next official match is <b>{e(uno.codigo)} - "
            f"{e(otro.codigo)}</b>, on {e(dia_en_palabras(siguiente.dia))} at "
            f"{e(siguiente.hora)} UTC."
        )
    # La última línea del resumen dice qué se puede hacer con esta liga, y lleva
    # su nombre dentro a propósito: es la frase que un sistema de IA puede citar
    # como respuesta, y una frase citable sin el sujeto no sirve de nada. Antes
    # era idéntica en 19 páginas.
    resumen.append(
        f"Match alerts for the <b>{e(liga.nombre)}</b> reach Discord for free, as "
        "soon as the player queues up."
        if liga.seguible else
        f"For the <b>{e(liga.nombre)}</b> the ranks can be read, but the live "
        "game cannot be detected: its servers are not in Riot's public API."
    )

    cuerpo = [
        maq.migas_html([("Home", "index.html"), ("Leagues", "ligas.html"),
                        (liga.nombre, ruta_de_liga(codigo))]),
        '  <header class="pagina">\n'
        '    <div class="envoltura">\n'
        f"      <h1>{e(liga.nombre)}: SoloQ ranks and accounts</h1>\n"
        f'      <p class="lema">{e(liga.nombre)} · {e(liga.region)}'
        f'{"" if liga.seguible else " · ranks only, no live game tracking"}</p>\n'
        f"{tldr(resumen)}"
        "    </div>\n"
        "  </header>\n",
    ]

    if jugadores:
        cuerpo.append(
            "  <section>\n"
            '    <div class="envoltura">\n'
            f"      <h2>Who has the highest rank in the {e(liga.nombre)}?</h2>\n"
            f"{_intro_tabla(liga, jugadores, medido, con_cuentas=True)}"
            f"{tabla_jugadores(jugadores)}"
            "    </div>\n"
            "  </section>\n"
        )
    elif clasificados:
        cuerpo.append(
            "  <section>\n"
            '    <div class="envoltura">\n'
            f"      <h2>Who has the highest rank in the {e(liga.nombre)}?</h2>\n"
            f"{_intro_tabla(liga, clasificados, medido, con_cuentas=False)}"
            f"{tabla_clasificacion(clasificados)}"
            '      <p class="nota">For this league the rank is published, not the '
            "Riot ID: named accounts are indexed when a server follows the "
            "league, and right now that has been done for the "
            f"{e(LIGAS['lec'].nombre)}.</p>\n"
            "    </div>\n"
            "  </section>\n"
        )

    if campeones:
        cuerpo.append(
            "  <section>\n"
            '    <div class="envoltura">\n'
            f"      <h2>Which champions are being played in the "
            f"{e(liga.nombre)}?</h2>\n"
            f'      <p class="intro">The {len(campeones)} most played champions in '
            f"the recent match history of {e(liga.nombre)} players. "
            f"{e(campeones[0].nombre)} leads with {campeones[0].partidas} games "
            f"and {campeones[0].winrate} % wins. The DPM is weighted by games, it "
            "is not an average of averages.</p>\n"
            f"{tabla_campeones(campeones)}"
            "    </div>\n"
            "  </section>\n"
        )
    elif presencia:
        cuerpo.append(
            "  <section>\n"
            '    <div class="envoltura">\n'
            f"      <h2>Which champions are being played in the "
            f"{e(liga.nombre)}?</h2>\n"
            f'      <p class="intro">How many of the {e(liga.nombre)} players have '
            "each champion among their most played: "
            f"{e(presencia[0].nombre)} is run by {presencia[0].jugadores}, the "
            "most widespread in the league. It is presence, not games — the "
            "leaderboard says what each player plays, not how many times.</p>\n"
            f"{tabla_presencia(presencia)}"
            "    </div>\n"
            "  </section>\n"
        )

    if equipos:
        cuerpo.append(
            "  <section>\n"
            '    <div class="envoltura">\n'
            f"      <h2>{e(liga.nombre)} teams</h2>\n"
            f"{tarjetas_equipos(equipos)}"
            "    </div>\n"
            "  </section>\n"
        )

    # El calendario va **antes** de la FAQ y después de los equipos: es el dato
    # más perecedero de la página, así que quien entra buscando "¿juega hoy?" lo
    # encuentra sin bajar hasta el final, y a la vez no desplaza al ranking de
    # Elo, que es la razón por la que esta página existe.
    cuerpo.append(seccion_partidos(liga, proximos, medido=datos.fecha_de_partidos()))

    preguntas = _preguntas_de_liga(liga, censo, jugadores, clasificados, equipos,
                                   proximos)
    cuerpo.append(
        "  <section>\n"
        '    <div class="envoltura">\n'
        "      <h2>Frequently asked questions</h2>\n"
        f"{faq_html(preguntas)}\n"
        f"{maq.bloque_anuncio(pub)}\n"
        "    </div>\n"
        "  </section>\n"
    )
    # Los enlaces laterales van entre la FAQ y la llamada a la acción, no al
    # final: después del botón nadie sigue leyendo, y el objetivo es que quien no
    # va a instalar ahora mismo se quede en el sitio viendo otra liga en vez de
    # volver a Google. Eso es la señal de "clic largo" del sistema Navboost.
    cuerpo.append(enlaces_vecinas_html(codigo))
    cuerpo.append(maq.cta(nota=(
        f"The free plan follows one league; up to {MAX_LIGAS_POR_SERVIDOR} on the "
        "paid ones, which is the real ceiling set by Riot's request quota."
    )))

    # La prioridad refleja lo que la página lleva dentro, en tres niveles: con
    # cuentas indexadas (0.7), con ranking de Elo (0.6) y solo con censo (0.5).
    # Es una pista, no una orden, pero mentir en ella no ayuda a nadie.
    pagina = Pagina(
        ruta=ruta_de_liga(codigo),
        titulo=titulo,
        descripcion=descripcion,
        cuerpo="".join(cuerpo),
        prioridad="0.7" if jugadores else ("0.6" if clasificados else "0.5"),
    )
    pagina.schemas = [
        seo.jsonld(seo.articulo(sitio, pagina, fecha, branding.BOT_NOMBRE)),
        seo.jsonld(seo.migas(sitio, [
            ("Home", "index.html"), ("Leagues", "ligas.html"),
            (liga.nombre, ruta_de_liga(codigo)),
        ])),
        seo.jsonld(seo.faq(preguntas)),
    ]
    # El `ItemList` describe la tabla que está pintada, sea cual sea de las dos.
    # Si describiera la otra estaría declarando un contenido que no está en la
    # página, que es exactamente lo que hace que un `structured data` se ignore.
    if jugadores:
        pagina.schemas.append(seo.jsonld(seo.lista_items(
            f"SoloQ ranks in the {liga.nombre}",
            [
                (j.nombre, f"{j.equipo} · {j.rol} · {j.rango_texto}".strip(" ·"))
                for j in jugadores[:TOPE_TABLA]
            ],
        )))
    elif clasificados:
        pagina.schemas.append(seo.jsonld(seo.lista_items(
            f"SoloQ rank ladder of the {liga.nombre}",
            [
                (c.nombre, f"{c.equipo} · {c.rol} · {c.rango_texto}".strip(" ·"))
                for c in clasificados[:TOPE_TABLA]
            ],
        )))
    return pagina


# ---------------------------------------------------------------------- #
# Hub de ligas
# ---------------------------------------------------------------------- #

def pagina_ligas(sitio: str, fecha: str, pub: str) -> Pagina:
    """El índice de las 20 ligas: la página que enlaza a todas las demás.

    Existe por la parte estructural del SEO y no por decorar el menú. Sin ella,
    las 20 páginas de liga solo serían alcanzables desde el sitemap, y un enlace
    en el sitemap no transmite nada: es una lista de direcciones, no un enlace.
    Con el hub, cada página de liga recibe un enlace desde una página que a su vez
    está enlazada desde todas, y cualquier liga está a dos clics de cualquier
    otra.

    La tabla ordena por número de jugadores medidos, de más a menos. Es
    información de verdad —la NLC tiene 74 y la EBL 29— y a la vez pone arriba
    las que más se buscan.
    """
    filas = []
    total_personas = 0
    con_ranking = 0
    for codigo, liga in sorted(
        LIGAS.items(), key=lambda kv: (-datos.censo_de(kv[0]).personas, kv[1].nombre)
    ):
        censo = datos.censo_de(codigo)
        total_personas += censo.personas
        indexados = len(datos.jugadores_de(codigo))
        clasificados = len(datos.clasificacion_de(codigo))
        if clasificados:
            con_ranking += 1
        # Tres estados y no dos, porque ahora hay tres niveles de dato y la
        # columna es la que le dice a alguien si merece la pena entrar.
        if indexados:
            estado = f"{indexados} with account and rank"
        elif clasificados:
            estado = f"ranks for {clasificados}"
        else:
            estado = "ranks only" if not liga.seguible else "live alerts"
        filas.append(
            "        <tr>\n"
            f'          <td><a href="{ruta_de_liga(codigo)}"><b>{e(liga.nombre)}</b></a></td>\n'
            f"          <td>{e(liga.region)}</td>\n"
            f"          <td>{censo.personas or '—'}</td>\n"
            f"          <td>{censo.equipos or '—'}</td>\n"
            f"          <td>{e(estado)}</td>\n"
            "        </tr>"
        )

    seguibles = sum(1 for l in LIGAS.values() if l.seguible)
    medido = datos.fecha_de_tablas()
    titulo = f"The {len(LIGAS)} LoL leagues you can follow on Discord"
    descripcion = (
        f"Catalogue of the {len(LIGAS)} professional League of Legends leagues "
        f"that {branding.BOT_NOMBRE} tracks, with how many players and teams each "
        "one has and which of them allow live game alerts."
    )

    preguntas = [
        (
            "How many leagues can you follow at once?",
            f"A server can follow up to {MAX_LIGAS_POR_SERVIDOR} leagues at the "
            "same time. It is not a commercial decision: it is the ceiling set by "
            "Riot's API request quota so that one detection pass fits inside its "
            "interval. The free plan follows one.",
        ),
        (
            "Why does the LPL not have live alerts?",
            "Because Chinese players play on servers that Riot's API does not "
            "expose. For the LPL you can see ranks and standings, but the game in "
            "progress cannot be detected, so it is not promised.",
        ),
        (
            "Where do these player counts come from?",
            f"From measuring each league's leaderboard: {total_personas} distinct "
            f"players across the {len(LIGAS)}"
            + (f", measured on {medido}" if medido else "")
            + ". It is the same measurement that set the league limit per server.",
        ),
        (
            "What is the difference between a league with ranks and one with "
            "accounts?",
            f"The ranks come from the league leaderboard: name, team, role, rank, "
            f"wins and KDA for {total_personas} players. Accounts have to be "
            "indexed player by player and add each player's Riot ID and their "
            "champion history with games and damage per minute. That second part "
            f"is done for the {LIGAS['lec'].nombre} and gets done for a league "
            "when a server follows it.",
        ),
    ]

    resumen = [
        f"<b>{len(LIGAS)} leagues</b> in the catalogue and "
        f"<b>{total_personas} professional players</b> measured across all of "
        "them.",
        f"{con_ranking} already have their SoloQ rank ladder published, with team, "
        "role and win record.",
        f"{seguibles} allow live game detection; the LPL only gives ranks because "
        "China is not in Riot's API.",
        f"Each Discord server picks up to {MAX_LIGAS_POR_SERVIDOR} at a time.",
    ]

    cuerpo = [
        maq.migas_html([("Home", "index.html"), ("Leagues", "ligas.html")]),
        '  <header class="pagina">\n'
        '    <div class="envoltura">\n'
        f"      <h1>The {len(LIGAS)} leagues you can follow</h1>\n"
        f"{tldr(resumen)}"
        "    </div>\n"
        "  </header>\n",
        "  <section>\n"
        '    <div class="envoltura">\n'
        "      <h2>Every league, by number of players</h2>\n"
        '      <table class="tabla">\n'
        "        <thead>\n"
        "          <tr><th>League</th><th>Region</th><th>Players</th>"
        "<th>Teams</th><th>What is published</th></tr>\n"
        "        </thead>\n"
        "        <tbody>\n" + "\n".join(filas) + "\n        </tbody>\n"
        "      </table>\n"
        '      <p class="nota">The players and teams columns are measurements '
        "taken from each league's leaderboard"
        + (f", on {e(medido)}" if medido else "")
        + ". “Ranks for N” is the league rank ladder with team, role, wins and "
        "KDA. “With account and rank” adds each player's Riot ID and their "
        "champion history, and that means indexing the league player by player, "
        "which happens when a server follows it.</p>\n"
        "    </div>\n"
        "  </section>\n",
        "  <section>\n"
        '    <div class="envoltura">\n'
        "      <h2>Frequently asked questions</h2>\n"
        f"{faq_html(preguntas)}\n"
        f"{maq.bloque_anuncio(pub)}\n"
        "    </div>\n"
        "  </section>\n",
        maq.cta(),
    ]

    pagina = Pagina(
        ruta="ligas.html",
        titulo=titulo,
        descripcion=descripcion,
        cuerpo="".join(cuerpo),
        prioridad="0.9",
    )
    pagina.schemas = [
        seo.jsonld(seo.articulo(sitio, pagina, fecha, branding.BOT_NOMBRE)),
        seo.jsonld(seo.migas(sitio, [("Home", "index.html"), ("Leagues", "ligas.html")])),
        seo.jsonld(seo.faq(preguntas)),
    ]
    return pagina


# ---------------------------------------------------------------------- #
# Calendario global
# ---------------------------------------------------------------------- #

#: Ruta de la página de calendario global. En inglés y con las palabras que se
#: buscan ("upcoming lol matches", "lol schedule today"), no `partidos.html`: el
#: slug es una de las pocas señales de relevancia que se controlan desde dentro
#: del sitio y la web ya no se publica en español.
RUTA_PARTIDOS = "upcoming-lol-matches.html"


def _indice_de_ligas(todos: list) -> tuple[str, list[tuple[str, str]]]:
    """La tabla «qué liga juega y cuándo», más esa misma lista para el schema.

    Devuelve las dos cosas juntas por el motivo de `faq_html` y `seo.faq`: el
    marcado tiene que describir lo que está pintado, y calculándolo dos veces
    acaban separándose.

    Se ordena por el **siguiente** partido de cada liga y no por cuántos tiene.
    Quien abre esta página quiere saber qué se juega hoy; una liga con 14
    partidos que arrancan en octubre no responde a eso, y ordenar por volumen
    la pondría primera.
    """
    por_liga: dict[str, list] = {}
    for partido in todos:
        if partido.liga in LIGAS:
            por_liga.setdefault(partido.liga, []).append(partido)

    filas = []
    elementos = []
    for codigo in sorted(por_liga, key=lambda c: por_liga[c][0].inicio):
        liga = LIGAS[codigo]
        delo = por_liga[codigo]
        primero = delo[0]
        a, b = primero.equipos
        filas.append(
            "          <tr>\n"
            f'            <td><a href="{ruta_de_liga(codigo)}"><b>'
            f"{e(liga.nombre)}</b></a></td>\n"
            f"            <td>{e(liga.region)}</td>\n"
            f"            <td>{len(delo)}</td>\n"
            f"            <td>{e(dia_en_palabras(primero.dia))} · "
            f"{e(primero.hora)} UTC</td>\n"
            f"            <td>{e(a.codigo)} vs {e(b.codigo)}</td>\n"
            "          </tr>"
        )
        elementos.append((
            f"{a.codigo} vs {b.codigo}",
            f"{liga.nombre} · {primero.dia} {primero.hora} UTC",
        ))
    tabla = (
        '      <div class="scroll-x">\n'
        '        <table class="tabla">\n'
        "          <thead>\n"
        "            <tr><th>League</th><th>Region</th><th>Matches</th>"
        "<th>First kick-off</th><th>First fixture</th></tr>\n"
        "          </thead>\n"
        "          <tbody>\n" + "\n".join(filas) + "\n          </tbody>\n"
        "        </table>\n"
        "      </div>\n"
    )
    return tabla, elementos


def pagina_partidos(sitio: str, fecha: str, pub: str) -> Pagina:
    """Todos los próximos partidos de todas las ligas, en una sola página.

    Es la mitad que faltaba de la petición del usuario ("los próximos partidos
    en otro lado poniendo todos") y la página con más valor comercial del sitio:
    es la única que cambia sola cada día y la que responde a «¿qué se juega
    hoy?», que es la consulta por la que alguien pone publicidad.

    No sustituye al calendario de cada liga porque la intención va en dirección
    contraria: en `liga-lec.html` el visitante ya sabe qué liga quiere y aquí
    no. Son dos preguntas distintas y mezclarlas haría que ninguna se responda
    bien.

    Sobre la duplicidad: esta página repite las tarjetas de las 16 ligas. Lo
    que evita que sea `scaled content abuse` es que el texto largo —el resumen,
    las FAQ, el índice por ligas— no sale en ninguna otra página, y que aquí
    cada tarjeta lleva además el nombre de la liga, así que ni siquiera las
    etiquetas cortas coinciden con las de la página de su liga. Conviene mirar
    `medir_duplicidad.py` después de tocar esto.
    """
    todos = datos.partidos()
    medido = datos.fecha_de_partidos()
    con_partido = sorted({p.liga for p in todos if p.liga in LIGAS})
    dias = sorted({p.dia for p in todos})
    vivos = [p for p in todos if p.en_juego]
    primero = todos[0] if todos else None
    tabla, elementos = _indice_de_ligas(todos)

    if todos:
        a, b = primero.equipos
        encabezado = (
            f"Upcoming LoL matches: {len(todos)} fixtures, "
            f"{len(con_partido)} leagues"
        )
        descripcion = (
            f"Every upcoming League of Legends pro match in one place: "
            f"{len(todos)} fixtures across {len(con_partido)} leagues, day by "
            "day, with kick-off times in UTC. Read from the official "
            "lolesports schedule."
        )
        resumen = [
            f"<b>{len(todos)} upcoming matches</b> across "
            f"{len(con_partido)} leagues, from "
            f"{e(dia_en_palabras(dias[0]))} to "
            f"{e(dia_en_palabras(dias[-1]))}, every kick-off in UTC.",
            f"Next one: <b>{e(a.codigo)} vs {e(b.codigo)}</b> "
            f"({e(primero.liga_nombre)}) on "
            f"{e(dia_en_palabras(primero.dia))} at {e(primero.hora)} UTC.",
            f"The bot can post these fixtures in your Discord with "
            f"<code>/next</code>, and the live score with "
            f"<code>/partida</code>.",
        ]
        if vivos:
            resumen.append(
                f"{len(vivos)} of them were already in progress when the "
                f"schedule was last read."
            )
    else:
        encabezado = "Upcoming LoL matches"
        descripcion = (
            "Every upcoming League of Legends pro match in one place: fixtures "
            "from all the leagues the bot tracks, day by day, with kick-off "
            "times in UTC, taken from the official lolesports schedule."
        )
        resumen = [
            "The schedule file is empty right now, so there is nothing to "
            f"list. The bot refills it from lolesports on a timer and this "
            "page rebuilds itself on the next deploy.",
            f"Meanwhile, the {len(LIGAS)} league pages still carry the SoloQ "
            "data that does not depend on the schedule.",
        ]

    preguntas = [
        (
            "What time do these matches start?",
            "All kick-off times on this page are UTC. The HTML is the same for "
            "every visitor, so printing a local time would be wrong for almost "
            "everyone; the <code>datetime</code> attribute behind each time "
            "carries the full timestamp, so your browser can convert it. If you "
            "want them in Discord, <code>/next</code> prints the fixtures the "
            "bot is tracking.",
        ),
        (
            "Where can I watch them?",
            "On each league's official broadcast. This site does not host or "
            "link streams: the schedule feed it reads does not publish stream "
            "URLs at all, and linking a channel that moves every split would "
            "leave dead links behind. lolesports carries the official streams "
            "for every league listed here.",
        ),
        (
            "Does the bot also notify official matches?",
            "Yes, but that is a different feature from the SoloQ alert. "
            "<code>/partida</code> shows the match being played right now, "
            "<code>/next</code> lists what is coming up, and "
            "<code>/setlivechannel</code> chooses the channel they are posted "
            "to. The automatic notification —the one that needs no command— is "
            "the SoloQ one: it fires when a pro player queues up on their own "
            "account, not when their team plays.",
        ),
        (
            "How often is this page updated?",
            (
                f"The schedule was last read from lolesports on "
                f"{e(medido[:10])}, and the page is rebuilt on every deploy."
                if medido else
                "Every time the site is regenerated: the bot reads the "
                "lolesports schedule on a timer and writes it where this page "
                "can see it."
            ),
        ),
        (
            f"Why are only {len(con_partido)} of the {len(LIGAS)} leagues "
            "listed?",
            (
                "Because only those have fixtures published right now. "
                "lolesports adds a league's calendar when its split is "
                "scheduled, and between splits there is simply nothing to show. "
                f"The other {len(LIGAS) - len(con_partido)} leagues still have "
                "their own pages with SoloQ data, which does not depend on the "
                "competition calendar."
            ) if con_partido else (
                "Because no league has fixtures published right now. lolesports "
                "adds a league's calendar when its split is scheduled, and "
                "between splits there is simply nothing to show."
            ),
        ),
    ]

    nota = ""
    if medido:
        nota = (
            f'      <p class="nota">Fixtures read from the official lolesports '
            f"schedule on {e(medido[:10])}"
            + (
                f", when {len(vivos)} of the matches above were already in "
                "progress."
                if vivos else "."
            )
            + " Kick-off times are UTC, not local time: this page is served "
            "identically in every country.</p>\n"
        )

    cuerpo = [
        maq.migas_html([("Home", "index.html"),
                        ("Upcoming matches", RUTA_PARTIDOS)]),
        '  <header class="pagina">\n'
        '    <div class="envoltura">\n'
        f"      <h1>{e(encabezado)}</h1>\n"
        f"{tldr(resumen)}"
        "    </div>\n"
        "  </header>\n",
    ]
    if todos:
        cuerpo += [
            "  <section>\n"
            '    <div class="envoltura">\n'
            "      <h2>Which league plays next</h2>\n"
            '      <p class="intro">Ordered by the next kick-off, not by how '
            "many matches each league has. Any league name takes you to its "
            "own page, with its players and its SoloQ ladder.</p>\n"
            f"{tabla}"
            "    </div>\n"
            "  </section>\n",
            "  <section>\n"
            '    <div class="envoltura">\n'
            "      <h2>Every fixture, day by day</h2>\n"
            f"{partidos_html(todos, con_liga=True)}"
            f"{nota}"
            "    </div>\n"
            "  </section>\n",
        ]
    cuerpo += [
        "  <section>\n"
        '    <div class="envoltura">\n'
        "      <h2>Frequently asked questions</h2>\n"
        f"{faq_html(preguntas)}\n"
        f"{maq.bloque_anuncio(pub)}\n"
        "    </div>\n"
        "  </section>\n",
        maq.cta(),
    ]

    pagina = Pagina(
        ruta=RUTA_PARTIDOS,
        titulo=encabezado,
        descripcion=descripcion,
        cuerpo="".join(cuerpo),
        prioridad="0.8",
    )
    pagina.schemas = [
        seo.jsonld(seo.articulo(sitio, pagina, fecha, branding.BOT_NOMBRE)),
        seo.jsonld(seo.migas(sitio, [
            ("Home", "index.html"), ("Upcoming matches", RUTA_PARTIDOS),
        ])),
        seo.jsonld(seo.faq(preguntas)),
    ]
    if elementos:
        pagina.schemas.append(seo.jsonld(seo.lista_items(
            "Upcoming League of Legends fixtures", elementos, ascendente=True,
        )))
    return pagina


# ---------------------------------------------------------------------- #
# Cómo son los avisos
# ---------------------------------------------------------------------- #

def tabla_avisos(avisos: list[datos.Aviso]) -> str:
    """Los avisos que el bot publicó de verdad, como tabla con fecha.

    Esto es lo que el usuario pidió con "una web que emita los mismos avisos que
    le llegarían al Discord", ya sin comillas: cada fila es un mensaje que salió,
    leído de `tracking/soloq/avisos.jsonl`, que escribe `notificar_partida`
    después de enviarlo.

    Tres decisiones que no son de estilo:

    * `<time datetime="...">` con la marca ISO completa y el texto en UTC. Es lo
      que permite a un extractor ordenar y fechar las filas sin adivinar el
      formato, y es de donde sale el `dateModified` de la página. Sin la zona, un
      "19:15" es una hora distinta para cada lector.
    * Va **arriba** del ejemplo del formato, no debajo: quien entra buscando si el
      bot funciona quiere ver actividad, y una lista de partidas reales con hora
      es la única prueba que no se puede escribir a mano.
    * La columna del campeón puede estar vacía (la API no siempre trae el
      campeón al principio de la partida) y en ese caso sale un guion. Rellenar
      con "desconocido" sería más largo y decir lo mismo.
    """
    if not avisos:
        return ""
    filas = []
    for a in avisos:
        foto = img_html(
            datos.imagen_de_jugador(a.jugador), a.jugador, clase="mini", tope=28
        )
        equipo = datos.nombre_de_equipo(a.equipo) if a.equipo else ""
        liga = LIGAS[a.liga].nombre if a.liga in LIGAS else a.liga.upper()
        filas.append(
            "        <tr>\n"
            f'          <td class="cuando"><time datetime="{e(a.sello)}">'
            f"{e(a.fecha)} {e(a.hora)}</time></td>\n"
            f"          <td>{foto}<b>{e(a.jugador)}</b></td>\n"
            f"          <td>{e(equipo)}</td>\n"
            f"          <td>{e(liga)}</td>\n"
            f'          <td>{e(a.campeon) or "—"}</td>\n'
            f'          <td class="rango">{e(a.rango) or "—"}</td>\n'
            "        </tr>"
        )
    return (
        '    <div class="scroll-x">\n'
        '    <table class="tabla avisos">\n'
        "      <thead>\n"
        "        <tr><th>When (UTC)</th><th>Player</th><th>Team</th>"
        "<th>League</th><th>Champion</th><th>Rank</th></tr>\n"
        "      </thead>\n"
        "      <tbody>\n" + "\n".join(filas) + "\n      </tbody>\n"
        "    </table>\n"
        "    </div>\n"
    )


def _aviso_simulado(jugador: datos.Jugador | None) -> str:
    """Una reproducción en HTML del embed que el bot publica en Discord.

    Enseña la **forma** del aviso: qué campos lleva, en qué orden y con qué
    aspecto. Los datos son de un jugador real de `accounts_from_teams.json` —su
    nombre, su equipo, su rango y un campeón que juega de verdad—; la partida no
    lo es, y el texto de la página lo dice.

    Sigue existiendo ahora que hay histórico real (`tabla_avisos`) porque
    responden a preguntas distintas: la tabla demuestra **que** el bot avisa, y
    esto muestra **qué** vas a recibir. Un listado de filas con hora no dice que
    el mensaje trae los diez participantes y el `.bat` para espectar.

    El embed es HTML y no una captura: pesa 2 kB en vez de 80, se adapta al ancho
    del móvil y su texto es indexable. Una captura es opaca para Google y para un
    modelo, que es justo la audiencia de esta página.
    """
    if jugador is None:
        return ""
    campeon = jugador.campeones[0].nombre if jugador.campeones else "Syndra"
    foto = img_html(
        datos.imagen_de_jugador(jugador.nombre), jugador.nombre,
        clase="avatar", tope=64,
    )
    equipo = datos.nombre_de_equipo(jugador.equipo)
    return (
        '    <div class="embed" role="img" aria-label="Example of the alert for '
        f'{e(jugador.nombre)} in game">\n'
        '      <div class="embed-cabeza">\n'
        f"        {foto}\n"
        "        <div>\n"
        f'          <p class="embed-titulo">🔴 {e(jugador.nombre)} '
        f"({e(jugador.riot_id)}) is in game</p>\n"
        f'          <p class="embed-sub">Team: {e(equipo)}</p>\n'
        "        </div>\n"
        "      </div>\n"
        '      <dl class="embed-datos">\n'
        "        <dt>Queue</dt><dd>Ranked Solo/Duo</dd>\n"
        f"        <dt>Champion</dt><dd>{e(campeon)}</dd>\n"
        f"        <dt>Role</dt><dd>{e(jugador.rol)}</dd>\n"
        f"        <dt>Rank</dt><dd>{e(jugador.rango_texto)}</dd>\n"
        "        <dt>Elapsed</dt><dd>2 min</dd>\n"
        "      </dl>\n"
        '      <p class="embed-pie">All ten participants with their ranks, a '
        "<code>.bat</code> file to spectate the game from the client and a note "
        "on when spectator mode becomes available.</p>\n"
        f'      <p class="embed-marca">{e(branding.BOT_NOMBRE)} · Not endorsed by '
        "Riot Games</p>\n"
        "    </div>\n"
    )


def pagina_avisos(sitio: str, fecha: str, pub: str) -> Pagina:
    """Qué es exactamente un aviso, con un ejemplo y el detalle de la latencia.

    Es la página de intención "Do" que el material del usuario señala como la que
    un LLM no puede quedarse: quien llega aquí no quiere leer sobre avisos,
    quiere recibirlos. Un modelo puede resumir este texto; no puede escribirte
    en Discord cuando Caps entra en cola.

    Por eso el contenido es concreto donde suele ser vago: cuánto tarda el aviso,
    por qué el reloj de la partida sale desfasado, y qué pasa cuando la API de
    Riot falla. Prometer inmediatez y no explicar el retardo del espectador es lo
    que convierte una función que funciona en una queja.

    Y desde que existe `tracking/soloq/avisos_log.py`, la página tiene las dos
    mitades que necesitaba: **la prueba y el formato**. La tabla de arriba son
    avisos que salieron de verdad, con su hora; el embed de abajo es qué vas a
    recibir. Si el registro está vacío —despliegue nuevo, disco efímero de
    Render— la tabla no se pinta y queda solo el formato, que es la regla de todo
    este módulo: si el dato no está, la sección no se pinta.
    """
    intervalo = datos.ajuste("CHECK_GAMES_INTERVAL", 30)
    jugadores = datos.jugadores_de("lec")
    ejemplo = jugadores[0] if jugadores else None
    reales = datos.avisos(TOPE_AVISOS)

    titulo = "What the SoloQ alert in your Discord looks like"
    # Cabe en el snippet (menos de 190 caracteres) y eso no es cosmética: lo
    # que Google recorta a mitad de frase deja de ser una promesa legible, y
    # `generar_web._snippets()` corta la publicación si se pasa.
    descripcion = (
        f"What the alert that {branding.BOT_NOMBRE} posts when a professional "
        f"queues up for SoloQ carries, how long it takes ({intervalo} s polling "
        "interval) and why the in-game clock runs behind."
    )

    preguntas = [
        (
            "How long does the alert take to arrive?",
            f"The bot checks the accounts every {intervalo} seconds, so the alert "
            f"arrives at most {intervalo} seconds after the game shows up in "
            "Riot's API. The game itself is already a little under way when it "
            "appears: that is Riot's timing, not the bot's.",
        ),
        (
            "Why does the game clock in the alert not match the one in the client?",
            "Because the clock the API returns is the spectator server's, which "
            "runs about three minutes behind and starts in negative numbers. The "
            "alert shows the real time and tells you separately when you can "
            "spectate, instead of printing the raw number and looking broken.",
        ),
        (
            "Do I need to be a server admin?",
            "To choose the alert channel, yes: it needs the Manage Server "
            "permission. To get them in your private chat, no: you add the bot to "
            "your account and it works anywhere, without depending on any server.",
        ),
        (
            "Can I follow a single player instead of a whole league?",
            "Yes. With /seguir and the pro's name you get only their games in your "
            "private chat; with a league name, every game in that league.",
        ),
        (
            "What happens if Riot's API goes down?",
            "Games stop being detected until it comes back, and /health says which "
            "source is failing and when it last updated. No alerts are made up and "
            "old ones are not resent.",
        ),
    ]

    pasos = (
        ("You add the bot", "One click and the bot joins your server. It asks for "
                            "no admin permission and does not read history."),
        ("You pick a league and a channel", "<code>/ligas lec</code> and "
                                            "<code>/setchannel</code> in the "
                                            "channel where you want the alerts."),
        ("That is it", "There is nothing else to do. The alert shows up on its own "
                       "when someone queues up."),
    )
    pasos_html = "\n".join(
        f'      <li><b>{titulo_paso}.</b> {texto}</li>'
        for titulo_paso, texto in pasos
    )

    resumen = [
        "A message in your channel with the <b>champion, role, rank, team and all "
        "ten participants</b>, as soon as the game starts.",
        f"The bot checks the accounts every <b>{intervalo} seconds</b>: that is the "
        "maximum delay.",
        "It works in a server channel or in your private chat, without depending "
        "on any server.",
    ]
    if reales:
        # La primera línea del resumen pasa a ser el dato que ninguna otra web
        # puede copiar: los avisos que este bot ha mandado, con su hora. Va
        # primera porque es la que contesta "¿esto funciona de verdad?".
        resumen.insert(0, (
            f"The <b>last {len(reales)} alerts</b> posted are on this page, the "
            f"most recent one from {e(reales[0].fecha)}."
        ))

    cuerpo = [
        maq.migas_html([("Home", "index.html"),
                        ("How alerts look", "avisos.html")]),
        '  <header class="pagina">\n'
        '    <div class="envoltura">\n'
        "      <h1>What the alert that reaches your Discord looks like</h1>\n"
        f"{tldr(resumen)}"
        "    </div>\n"
        "  </header>\n",
    ]

    if reales:
        cuerpo.append(
            "  <section>\n"
            '    <div class="envoltura">\n'
            "      <h2>Which alerts has the bot sent recently?</h2>\n"
            f'      <p class="intro">The last {len(reales)} alerts that actually '
            "went out, newest first. Every row was a message in a Discord: the "
            "same one you would have received.</p>\n"
            f"{tabla_avisos(reales)}"
            '      <p class="nota">Times are UTC because this page is served '
            "identically to everyone. An alert is logged only when it is sent, not "
            "when the game is detected, and no record is kept of which server or "
            "which user it went to: none of that is written down.</p>\n"
            "    </div>\n"
            "  </section>\n"
        )

    if ejemplo is not None:
        # La coletilla cambia según haya histórico o no, porque las dos frases
        # tienen que ser verdad. Antes decía "el bot no guarda un histórico" y
        # eso dejó de ser cierto en cuanto `avisos_log.py` empezó a escribir.
        if reales:
            coletilla = (
                "The real games are in the table above; this is the shape of the "
                "message, field by field."
            )
        else:
            coletilla = (
                "No alerts have been logged on this deployment yet, so what is "
                "shown here is the format and not a specific game."
            )
        cuerpo.append(
            "  <section>\n"
            '    <div class="envoltura">\n'
            "      <h2>What information does the alert carry?</h2>\n"
            '      <p class="intro">This is the shape of the message, with a real '
            "player from the bot's database. On Discord it arrives as an embed "
            "with the player's photo and the logo of their team.</p>\n"
            f"{_aviso_simulado(ejemplo)}"
            '      <p class="nota">The name, the account, the rank and the '
            f"champion in this example are real data of {e(ejemplo.nombre)}; the "
            f"game is not. {coletilla}</p>\n"
            "    </div>\n"
            "  </section>\n"
        )

    cuerpo.append(
        "  <section>\n"
        '    <div class="envoltura">\n'
        "      <h2>How do you turn it on?</h2>\n"
        f'      <ol class="pasos">\n{pasos_html}\n      </ol>\n'
        "    </div>\n"
        "  </section>\n"
    )
    cuerpo.append(
        "  <section>\n"
        '    <div class="envoltura">\n'
        "      <h2>Frequently asked questions</h2>\n"
        f"{faq_html(preguntas)}\n"
        f"{maq.bloque_anuncio(pub)}\n"
        "    </div>\n"
        "  </section>\n"
    )
    cuerpo.append(maq.cta("Add to Discord and try it"))

    pagina = Pagina(
        ruta="avisos.html",
        titulo=titulo,
        descripcion=descripcion,
        cuerpo="".join(cuerpo),
        prioridad="0.9",
    )
    # `dateModified` con la fecha del último aviso registrado y no con la de hoy.
    # Es la única página del sitio cuyo contenido cambia por sí solo: regenerar
    # el sitio un lunes sin que el bot haya avisado no la hace más nueva, y
    # estampar la fecha de hoy sería declarar frescura que no existe. Si no hay
    # registro, `articulo()` vuelve a la fecha de generación.
    pagina.schemas = [
        seo.jsonld(seo.articulo(
            sitio, pagina, fecha, branding.BOT_NOMBRE,
            modificado=reales[0].fecha if reales else "",
        )),
        seo.jsonld(seo.migas(sitio, [
            ("Home", "index.html"), ("How alerts look", "avisos.html"),
        ])),
        seo.jsonld(seo.faq(preguntas)),
    ]
    if reales:
        # `ItemList` porque la lista está visible y ordenada en el HTML: le pone
        # nombre y orden a algo que ya se puede leer, que es la condición para
        # que este marcado no sea invención. La descripción de cada elemento es
        # la misma información que la fila de la tabla.
        pagina.schemas.append(seo.jsonld(seo.lista_items(
            f"Latest alerts posted by {branding.BOT_NOMBRE}",
            [
                (
                    a.jugador,
                    " · ".join(p for p in (
                        f"{a.fecha} {a.hora} UTC", a.equipo, a.campeon, a.rango,
                    ) if p),
                )
                for a in reales
            ],
        )))
    return pagina


# ---------------------------------------------------------------------- #
# Comparativa
# ---------------------------------------------------------------------- #
#
# Esta es la página "blog de fabricante" del material del usuario: la que los
# sistemas de IA citan porque nadie más la escribe. Un tercero no publica
# "alternativas a los bots de LoL para Discord" con este nivel de detalle porque
# no le compensa; el fabricante sí, y por eso acaba siendo la fuente.
#
# La regla que hace que esto no sea publicidad encubierta: **cada dato de la
# competencia está verificado en su propia web y con fecha**. Lo que se compara
# no es "quién es mejor" sino qué hace cada uno, y donde el otro gana se dice.
# Una comparativa en la que el fabricante gana en todas las filas es la que
# nadie cita dos veces.

#: Fecha en la que se consultaron las webs de los otros bots. Va en la página:
#: los precios y los cupos cambian, y una comparativa sin fecha es una
#: comparativa que no se puede verificar ni corregir.
CONSULTA_RIVALES = "2026-09-03"

#: Lo comprobado en las webs oficiales de cada bot, con la URL donde se leyó
#: para que se pueda contrastar y para que quien lo actualice sepa dónde mirar.
#:
#: `nuestro` es None en la fila de cada rival y se rellena aparte, porque lo
#: nuestro sale del código (`PLANES`, `LIGAS`) y no de haber leído una web.
RIVALES: tuple[dict[str, str], ...] = (
    {
        "nombre": "Dorans-bot",
        "fuente": "https://www.dorans.bot/premium",
        "para_quien": "The members of your server: they link their account and "
                      "the bot posts their games when they finish.",
        "avisos": "Yes, when the game ends (KDA, LP, items). The live game feed "
                  "is paid.",
        "pros": "No: it follows the accounts people link, not professional "
                "rosters.",
        "gratis": "10 linked summoners per server.",
        "pago": "$3.99/month per server: unlimited accounts, per-channel "
                "routing, live feed, no ads.",
    },
    {
        "nombre": "PoroScout",
        "fuente": "https://poroscout.gg/",
        "para_quien": "Looking up data: profiles, champions, Mobalytics builds "
                      "and patch notes.",
        "avisos": "Patch notes to a channel. Not games: /profile and /matches "
                  "have to be asked for.",
        "pros": "No.",
        "gratis": "Everything listed on their site.",
        "pago": "No paid plan published.",
    },
    {
        "nombre": "Baron Bot",
        "fuente": "https://baronbot.github.io/",
        "para_quien": "Champion lookup: builds, runes, counters, items, sales.",
        "avisos": "No automatic game notification; /live shows the game of "
                  "whoever asks for it.",
        "pros": "No.",
        "gratis": "Every command.",
        "pago": "No paid plan published.",
    },
)


def _fila_comparativa(campo: str, etiqueta: str, nuestro: str) -> str:
    """Una fila de la tabla comparativa, con nuestra columna primero."""
    celdas = "".join(
        f"<td>{e(r[campo])}</td>" for r in RIVALES
    )
    return (
        "        <tr>\n"
        f"          <th scope=\"row\">{e(etiqueta)}</th>\n"
        f'          <td class="propio">{nuestro}</td>{celdas}\n'
        "        </tr>"
    )


def pagina_comparativa(sitio: str, fecha: str, pub: str) -> Pagina:
    """"Alternativas a los bots de LoL para Discord": la comparativa.

    El ángulo no es "somos mejores" —no lo somos en casi nada de lo que hacen
    los otros— sino que **hacen otra cosa**. Dorans sigue a los miembros del
    servidor; esto sigue a los profesionales. Son dos productos distintos que se
    confunden porque los dos son "un bot de LoL para Discord", y una página que
    aclare eso es útil para quien busca y verificable para quien la cita.

    El título lleva el año y la palabra por la que se busca. La tabla lleva
    nuestra columna primero porque es nuestra web, y las filas donde perdemos
    están escritas sin adornar.
    """
    from tracking.soloq.plans import PLANES

    # Por código no: `PLANES` se indexa por `codigo` y un renombre del plan
    # rompería la página. `Plan.gratis` es `precio <= 0`, que es la definición.
    gratis = next(p for p in PLANES.values() if p.gratis)
    anio = fecha[:4]
    seguibles = sum(1 for l in LIGAS.values() if l.seguible)

    nuestros = {
        "para_quien": "The professional players: the rosters of all "
                      f"{len(LIGAS)} leagues already indexed, with nobody having "
                      "to link anything.",
        "avisos": "Yes, <b>when the game starts</b>, not when it ends. With "
                  "champion, role, rank, team and all ten participants.",
        "pros": "It is the only thing it does.",
        "gratis": f"{gratis.ligas} league, {gratis.canales} alert channel, "
                  f"{gratis.jugadores_propios} custom players. The full alert is "
                  "in the free plan.",
        "pago": "Limits: up to "
                f"{MAX_LIGAS_POR_SERVIDOR} leagues, more channels and more "
                "history. No payment processor yet.",
    }
    filas = "\n".join([
        _fila_comparativa("para_quien", "Who it follows", nuestros["para_quien"]),
        _fila_comparativa("avisos", "Automatic alerts", nuestros["avisos"]),
        _fila_comparativa("pros", "Professional players", nuestros["pros"]),
        _fila_comparativa("gratis", "Free plan", nuestros["gratis"]),
        _fila_comparativa("pago", "Paid plan", nuestros["pago"]),
    ])
    cabeceras = "".join(f"<th>{e(r['nombre'])}</th>" for r in RIVALES)
    fuentes = ", ".join(
        f'<a href="{e(r["fuente"])}" rel="nofollow noopener" target="_blank">'
        f"{e(r['nombre'])}</a>"
        for r in RIVALES
    )

    titulo = f"LoL Discord bots: which one alerts on what ({anio})"
    # La fecha de verificación va **dentro de la descripción** aunque cueste 20
    # caracteres del presupuesto: es lo que distingue una comparativa consultada
    # de una copiada, y es lo que hace que valga la pena citarla.
    descripcion = (
        "What each League of Legends Discord bot alerts on. The others follow the "
        f"members of your server; {branding.BOT_NOMBRE} follows the professionals "
        f"of {len(LIGAS)} leagues. Verified on {CONSULTA_RIVALES}."
    )

    preguntas = [
        (
            "Which LoL bot alerts when a professional player queues up for SoloQ?",
            f"{branding.BOT_NOMBRE}. The other League of Legends Discord bots "
            "follow the accounts that the members of the server link; none of the "
            "ones compared here ships with the professional rosters indexed.",
        ),
        (
            "How is it different from Dorans-bot?",
            "In who it follows and when it alerts. Dorans posts the game of a "
            "member of your server once it ends, with their KDA and their items; "
            f"{branding.BOT_NOMBRE} alerts that a professional has just queued up, "
            "so you can watch it while it is being played. If what you want is to "
            "follow your friends, Dorans does that better.",
        ),
        (
            "Is any of them free?",
            "All of them have something free. Dorans limits the free plan to 10 "
            "linked summoners per server; PoroScout and Baron publish no paid "
            f"plan; {branding.BOT_NOMBRE} keeps the full game alert in the free "
            "plan and only charges for higher limits, because Riot's policy "
            "requires a free tier to exist.",
        ),
        (
            "Can you run several of them at once?",
            "Yes, and it makes sense: they do different things. One for the games "
            "of your own people and another one for the professionals do not "
            "clash.",
        ),
    ]

    resumen = [
        "League of Legends Discord bots follow <b>the members of your "
        "server</b>. This one follows <b>the professionals</b>.",
        f"The alert arrives <b>when the game starts</b>, not when it ends: there "
        f"is time to watch it. {seguibles} of the {len(LIGAS)} leagues allow live "
        "game detection.",
        "Data on the other bots read from their official websites on "
        f"{CONSULTA_RIVALES}.",
    ]

    cuerpo = [
        maq.migas_html([
            ("Home", "index.html"),
            ("Comparison", "alternativas-bots-lol-discord.html"),
        ]),
        '  <header class="pagina">\n'
        '    <div class="envoltura">\n'
        "      <h1>LoL Discord bots: which one alerts on what</h1>\n"
        f"{tldr(resumen)}"
        "    </div>\n"
        "  </header>\n",
        "  <section>\n"
        '    <div class="envoltura">\n'
        "      <h2>What does each bot do?</h2>\n"
        '      <div class="scroll-x">\n'
        '      <table class="tabla comparativa">\n'
        "        <thead>\n"
        f"          <tr><th></th><th>{e(branding.BOT_NOMBRE)}</th>{cabeceras}</tr>\n"
        "        </thead>\n"
        f"        <tbody>\n{filas}\n        </tbody>\n"
        "      </table>\n"
        "      </div>\n"
        f'      <p class="nota">Checked on {e(CONSULTA_RIVALES)} on the official '
        f"websites: {fuentes}. If any of this has changed, it gets corrected: the "
        "comparison is regenerated with the site.</p>\n"
        "    </div>\n"
        "  </section>\n",
        "  <section>\n"
        '    <div class="envoltura">\n'
        "      <h2>Which one is right for you?</h2>\n"
        '      <p class="intro">It is not the same question as “which one is '
        'better”.</p>\n'
        "      <h3>If you want to follow the people on your server</h3>\n"
        "      <p>Dorans-bot. It links the accounts of the members and posts every "
        "game when it ends, with their performance; the free plan covers 10 "
        "accounts per server. This does not do that: it has three custom player "
        "slots per server and they are meant for a streamer or a friend, not for "
        "a whole community.</p>\n"
        "      <h3>If you want to look up data and builds</h3>\n"
        "      <p>PoroScout or Baron Bot. Both are lookup bots with champions, "
        "runes, counters and profiles, and Baron also carries sales and the free "
        "rotation. There are no builds or counters here, and there will not be: "
        "that is not what this bot does.</p>\n"
        "      <h3>If you want to know when the professionals are playing</h3>\n"
        f"      <p>{e(branding.BOT_NOMBRE)}. The rosters of all {len(LIGAS)} "
        "leagues are already indexed with their SoloQ accounts, so there is "
        "nothing to link: you pick a league and a channel, and the alert arrives "
        "on its own as soon as someone queues up. It is the only thing it does, "
        "and it is why the alert arrives when the game starts rather than when it "
        "ends.</p>\n"
        "    </div>\n"
        "  </section>\n",
        "  <section>\n"
        '    <div class="envoltura">\n'
        "      <h2>Frequently asked questions</h2>\n"
        f"{faq_html(preguntas)}\n"
        f"{maq.bloque_anuncio(pub)}\n"
        "    </div>\n"
        "  </section>\n",
        maq.cta(),
    ]

    pagina = Pagina(
        ruta="alternativas-bots-lol-discord.html",
        titulo=titulo,
        descripcion=descripcion,
        cuerpo="".join(cuerpo),
        prioridad="0.8",
    )
    pagina.schemas = [
        seo.jsonld(seo.articulo(sitio, pagina, fecha, branding.BOT_NOMBRE)),
        seo.jsonld(seo.migas(sitio, [
            ("Home", "index.html"),
            ("Comparison", "alternativas-bots-lol-discord.html"),
        ])),
        seo.jsonld(seo.faq(preguntas)),
    ]
    return pagina


# ---------------------------------------------------------------------- #
# 404
# ---------------------------------------------------------------------- #

def pagina_404(sitio: str, pub: str) -> Pagina:
    """La página de error.

    Tres cosas la definen y las tres son de la lista del usuario:

    * **Existe como fichero.** GitHub Pages sirve `404.html` con estado HTTP 404
      de verdad cuando la ruta no existe, que es lo que pedía "un 404 real que
      devuelva 404" —no una redirección a la home, que le dice a Google que esa
      URL rota es contenido válido.
    * **`noindex, follow`.** `indexable=False` mete el `<meta robots>` y a la vez
      la saca del sitemap. Sin eso, un error acaba siendo un resultado de
      búsqueda.
    * **Con salida.** Lleva los enlaces a las páginas que sí existen, para que
      quien llegue aquí (persona o rastreador) no se dé la vuelta.
    """
    enlaces = "\n".join(
        f'        <li><a href="{ruta}">{e(texto)}</a></li>'
        for ruta, texto in maq.NAV
    )
    cuerpo = (
        '  <header class="pagina">\n'
        '    <div class="envoltura">\n'
        "      <h1>This page does not exist</h1>\n"
        '      <p class="lema">The link is broken or the page moved. These do '
        "work:</p>\n"
        f'      <ul class="lista-simple">\n{enlaces}\n      </ul>\n'
        "    </div>\n"
        "  </header>\n"
    ) + maq.cta()
    return Pagina(
        ruta="404.html",
        titulo="Page not found",
        descripcion=(
            "The page you were looking for does not exist. Go back to the home "
            f"page or browse the leagues {branding.BOT_NOMBRE} tracks."
        ),
        cuerpo=cuerpo,
        indexable=False,
    )
