# Base de conocimiento de SEO

Esto no es documentación del proyecto. Es **lo que he leído y verificado sobre
SEO**, guardado para no volver a investigarlo desde cero cada vez que se toca la
web. Cada afirmación fuerte lleva quién la dijo y cuándo, porque en SEO la mitad
de los consejos que circulan caducaron hace tres años y la otra mitad nunca
fueron ciertos.

## Cómo está organizado

| Archivo | Qué contiene |
|---|---|
| `01-como-rankea-google.md` | Los sistemas de ranking reales, según el juicio antimonopolio y lo que dice Google |
| `02-busqueda-con-ia.md` | AI Overviews, cero clics, GEO/AEO, *query fan-out*. Es el cambio más grande del sector |
| `03-seo-tecnico.md` | La lista de comprobación técnica: indexación, canónicos, `hreflang`, schema |
| `04-estrategia-ingles.md` | Por qué la web va a ser bilingüe con el inglés como idioma principal, y cómo |
| `05-plan-jetadirectabot.md` | El plan concreto para esta web, con lo que ya está hecho y lo que falta |
| `_datos/` | Los posts crudos cosechados de X, por si hace falta releer el original |

## De dónde sale

Cosechado de X con `scripts/cosechar_seo_x.py`, que lee los *timelines* de 30
referentes (20 en inglés, 10 en español) en vez de buscar la palabra "SEO".

El motivo del cambio: `twitter search` devuelve HTTP 404 en esta versión del CLI
(el endpoint interno de X cambió), pero además **buscar "SEO" es mala idea**. Esa
consulta está tomada por agencias vendiendo servicios y bots de "SEO $5". Los
*timelines* de gente que trabaja en esto dan señal en vez de ruido.

Del primer barrido: **684 posts leídos, 181 con contenido real** en inglés. El
filtro descarta retweets, textos de menos de 60 caracteres, cualquier cosa sin
un término técnico reconocible y lo que no llega a 3 «me gusta» o 2 guardados.

## La regla que gobierna todo lo demás

Google lleva años diciendo lo mismo y el juicio antimonopolio lo confirmó: **no
hay fórmula de página perfecta**. Danny Sullivan (`@searchliaison`, 2024-01-09,
420 likes) lo escribió así:

> There isn't [a perfect page formula], and no one should feel they must work to
> some type of mythical formula. […] Put your readers and audience first.

Esto no es una frase para enmarcar. Tiene una consecuencia operativa dura: cada
vez que aparezca la tentación de hacer algo *porque posiciona* en vez de *porque
sirve a alguien*, es probable que sea un patrón que una actualización de spam va
a castigar. Sullivan pone el ejemplo del *byline*: ponlo si tu lector se
beneficia, no porque hayas oído que rankea, porque no rankea.
