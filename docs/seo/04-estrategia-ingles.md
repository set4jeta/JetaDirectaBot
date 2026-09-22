# 04 · Estrategia en inglés: la web se convierte en bilingüe con el inglés primero

Decisión tomada por el dueño del proyecto, textualmente:

> es más probable que gente en inglés tenga dinero y quiera pagar por el bot así
> que oriéntalo por ahí

Este archivo comprueba si eso se sostiene con datos, y define cómo se hace.

## ¿Se sostiene? Sí, y por más razones de las que se dijo

**1. El mercado de League of Legends en inglés es el que más paga.**
Los servidores de Discord de LoL más grandes son en inglés. La región con más
gasto por usuario en cosméticos y suscripciones es Norteamérica. Un bot de pago a
3,99 € tiene un techo mucho más alto en un servidor de 40.000 miembros de NA que
en uno de 800 de España.

**2. El RPM de AdSense multiplica por 3-5.**
Esto ya se midió en la investigación previa: España está en el segundo nivel,
~10 $ por 1000 páginas vistas. Estados Unidos, Reino Unido, Canadá y Australia
están en el primero. Y *gaming* es uno de los nichos con RPM más bajo (2-10 $
frente a 20-60 $ de finanzas o seguros), lo que hace que el país sea la única
palanca disponible sobre el RPM.

**3. Volumen de búsqueda.** "lol discord bot" tiene un orden de magnitud más de
búsquedas que "bot de discord de lol". No hace falta una herramienta de pago para
saberlo: la población que juega LoL en inglés es varias veces la hispanohablante.

**4. El matiz que hay que tener en cuenta, del barrido de X.** Fishkin midió el
cero-clic por país (2026-06-17): **Reino Unido es el país con más cero-clic** de
los seis analizados; Alemania el que menos. Los mercados anglosajones tienen más
volumen *y* más retención de tráfico en Google. Así que el inglés no es dinero
gratis: hay más búsquedas, pero una fracción menor llega a la web. Refuerza la
conclusión de `02-busqueda-con-ia.md`: hay que ir a **consultas de herramienta con
intención de instalar**, no a consultas informativas que un AI Overview resuelve.

## Cómo se hace, concretamente

### El inglés va en la raíz, el español en `/es/`

```
/                       → inglés (x-default)
/ligas.html             → NO: /leagues.html
/es/                    → español
/es/ligas.html          → español
```

Razones:

1. **La raíz es la URL que se comparte.** Si alguien pega `jetadirectabot.com` en
   un Discord, sale la versión inglesa. Es el idioma con más alcance.
2. **`x-default` apunta a la raíz.** Quien busca desde un país sin versión propia
   cae en inglés, que es lo correcto.
3. **La autoridad se acumula en la raíz.** El dominio raíz siempre concentra más
   enlaces que cualquier subcarpeta.

Coste: hay que traducir 26 páginas y **las URLs en inglés deben tener slugs en
inglés**. `/leagues.html`, no `/ligas.html`. La URL es parte del contenido que
Google lee y una URL en español en la versión inglesa es señal contradictoria.

### Lo que hay que traducir de verdad

No es solo el texto visible. La lista completa por página:

| Elemento | ¿Traducir? | Nota |
|---|---|---|
| `<html lang>` | **Sí** | `en` / `es`. Afecta a lectores de pantalla y al traductor del navegador |
| `<title>` | Sí | Con la palabra clave inglesa, no traducida literal |
| `meta description` | Sí | 150-160 caracteres; el inglés ocupa menos, cabe más |
| `og:locale` | Sí | `en_US` / `es_ES` |
| Texto del cuerpo | Sí | |
| Texto de los enlaces internos | Sí | Es señal de ranking (Anchors) |
| Migas de pan | Sí | Y el `BreadcrumbList` del JSON-LD con ellas |
| `FAQPage` | Sí | Preguntas distintas, no traducidas: un anglohablante pregunta otras cosas |
| `SoftwareApplication.description` | Sí | |
| Nombre de las ligas | **No** | LEC, LCK, LTA son nombres propios |
| Nombres de jugador y equipo | **No** | |
| Descargo de Riot | **Ya está en inglés** | `branding.descargo_riot()` incluye el original inglés. En la versión inglesa se usa solo ese, sin la traducción |
| Página legal | Sí, con cuidado | Términos y privacidad. Traducción funcional, no legal |

### Las palabras clave no se traducen: se investigan

Error clásico: traducir "bot de Discord para League of Legends" a "Discord bot for
League of Legends" y dar por hecho que eso es lo que la gente busca. Lo que se
busca de verdad, por cómo escribe la gente en inglés:

| Español (actual) | Inglés (lo que se busca) |
|---|---|
| bot de discord de lol | **lol discord bot** |
| avisos cuando juega un pro | **pro player live alerts** / **when is X streaming** |
| elo de los jugadores de la LEC | **LEC player rankings** / **LEC soloq ladder** |
| alternativas a bots de lol | **best lol discord bots** |
| saber cuándo juega Caps | **track pro players soloq** |

Nota sobre "soloq": en inglés se escribe **`soloq`**, **`solo queue`** y **`solo q`**.
Las tres. El texto debería contener las variantes de forma natural.

Y un aviso: **"pickrate", "winrate", "soloq", "smurf" son la jerga real**. Un texto
en inglés académico correcto pero sin jerga no conecta con el jugador ni con la
consulta.

### Preguntas distintas para la FAQ inglesa

Lo que pregunta un anglohablante sobre este bot no es la traducción de lo que
pregunta un español. Borrador para la FAQ en inglés:

- Is this bot free?
- Does it work with EUW / NA / KR accounts? *(la pregunta de región es la primera de un anglohablante y no existe en la versión española)*
- How fast does it notify? *(la latencia es la objeción número uno)*
- Does it need admin permissions?
- Which pro players are tracked?
- Can I add my own accounts to track?
- Is this affiliated with Riot Games? *(hay que responder que no, y ya lo cubre el descargo)*

## Lo que NO se debe hacer

**No traducir con máquina y publicar sin revisar.** No por la penalización — Google
no penaliza texto de IA, ya se vio (mitad de las URLs mejor posicionadas tienen
20-50 % de texto de IA, estudio de Ahrefs vía Shepard) — sino porque una web de
gaming con inglés de traductor pierde credibilidad ante el usuario, y ese usuario
es el que instala o no instala.

**No hacer 26 páginas inglesas de golpe.** Orden por retorno:

1. `index.html` — la que se comparte
2. La comparativa — es la página de decisión de compra (BOFU), la de más valor
3. "Cómo son los avisos" — evidencia de primera mano, no resumible por una IA
4. El hub de ligas
5. Las 20 páginas de liga — las últimas, y solo si las 4 primeras funcionan

Aleyda lo respalda: los sitios que siguen creciendo son los que no dependen de
*"shallow informational content that can be easily summarized"* y que ganan
*"where users still need help making a confident purchase"*. La comparativa es
exactamente eso, y es la que ahora mismo está tratada como una página más.

**No declarar `hreflang` antes de que existan las páginas.** El comentario de
`web_seo.py` ya avisa: apuntar a una URL que no existe es un error de rastreo.

## Consecuencia para el nombre y el dominio

Del dato de *query fan-out* (30,2 % de las subconsultas de ChatGPT usan `site:`),
un dominio propio deja de ser cosmético. `site:jetadirectabot.com` tiene que
devolver algo. En `set4jeta.github.io/JetaDirectaBot/` no devuelve nada útil.

Y una consideración de nombre que hay que decidir pronto: **"JetaDirectaBot" es
impronunciable e insignificante en inglés.** No propongo cambiarlo — el bot ya
existe con ese nombre —, pero sí que el `<title>` inglés lleve delante lo que hace
y detrás el nombre:

```
Live Pro Player SoloQ Alerts for Discord — JetaDirectaBot
```

No:

```
JetaDirectaBot — Alertas de SoloQ
```

El nombre de marca al final del título es la convención, y con una marca
desconocida en inglés es además lo único que funciona: nadie busca el nombre
todavía, buscan la función.
