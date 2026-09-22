"""La imagen social (`og.png`) y el favicon, dibujados sin dependencias.

Por qué se generan y no se guarda un PNG hecho a mano en el repositorio
----------------------------------------------------------------------
`web_seo.meta_seo()` declara `og:image` con `og:image:width` y `og:image:height`
en **todas** las páginas. Eso convierte la imagen en obligatoria, no en un
adorno: una tarjeta que apunta a un 404 se pinta sin imagen y —esto es lo
caro— Discord y X **cachean** el resultado la primera vez que alguien comparte
la URL. Si el fichero llega después, la primera compartición ya salió mal y
sigue saliendo mal.

Además la imagen lleva datos que cambian (el número de ligas). Generarla desde
`LIGAS` es la misma regla que gobierna el resto de la web: si el catálogo crece,
la tarjeta crece con él en vez de quedarse en un número viejo.

Por qué a mano con `zlib` y no con Pillow
-----------------------------------------
Por lo mismo que `web_datos.medir_imagen()`: el intérprete con el que se lanzan
los scripts (3.13) **no tiene PIL** —solo lo tiene el 3.12 con el que corre el
bot—, así que importarlo aquí haría que generar la web fallara según con qué
python se ejecutara. Un PNG sin filtros ni entrelazado son tres chunks y un
`zlib.compress`.

La tipografía es un mapa de bits 5x7 incrustado más abajo. Incrustar una fuente
real serían megabytes y un lector de TrueType; a escala x10 el título mide 70 px
de alto sobre 630, que es de sobra legible en la tarjeta.
"""

from __future__ import annotations

import struct
import zlib

ANCHO, ALTO = 1200, 630

#: Los mismos colores que `web/styles.css`. Si la tarjeta no se parece a la web,
#: quien pulsa el enlace cree que se ha equivocado de sitio.
FONDO = (0x0F, 0x11, 0x15)
VERDE = (0x1F, 0x8B, 0x4C)
VERDE_CLARO = (0x2E, 0xCC, 0x71)
TEXTO = (0xE6, 0xE9, 0xEF)
SUAVE = (0x9A, 0xA4, 0xB2)


# ---------------------------------------------------------------------- #
# Escritura de PNG
# ---------------------------------------------------------------------- #

def _chunk(tipo: bytes, datos: bytes) -> bytes:
    """Un chunk de PNG: longitud, tipo, datos y CRC32 de tipo+datos."""
    return (
        struct.pack(">I", len(datos))
        + tipo
        + datos
        + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
    )


def png(ancho: int, alto: int, pixeles: bytearray) -> bytes:
    """Un PNG RGB de 8 bits desde un buffer plano de `ancho*alto*3` bytes.

    Cada fila va precedida por su byte de filtro a 0 ("sin filtro"), que es lo
    que exige el formato y lo único que hace falta aquí: filtrar solo sirve para
    que comprima mejor, y una tarjeta de 1200x630 con cuatro colores planos ya
    baja de 30 kB.
    """
    filas = bytearray()
    paso = ancho * 3
    for y in range(alto):
        filas.append(0)
        filas += pixeles[y * paso:(y + 1) * paso]
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(filas), 9))
        + _chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------- #
# Tipografía 5x7
# ---------------------------------------------------------------------- #
#
# Cada carácter son 7 filas de 5 bits, el bit 4 es la columna de la izquierda.
# Solo mayúsculas, dígitos y cuatro signos: es lo que necesita una tarjeta
# social, y cada glifo que no se usa es una línea que hay que leer sin motivo.

FUENTE: dict[str, tuple[int, ...]] = {
    " ": (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
    "A": (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "B": (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E),
    "C": (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E),
    "D": (0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F),
    "F": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10),
    "G": (0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0E),
    "H": (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "I": (0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "J": (0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C),
    "K": (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11),
    "L": (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    "M": (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11),
    "N": (0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11),
    "O": (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "P": (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10),
    "Q": (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D),
    "R": (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    "S": (0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E),
    "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "U": (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "V": (0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04),
    "W": (0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11),
    "X": (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11),
    "Y": (0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04),
    "Z": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F),
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F),
    "3": (0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E),
    "4": (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
    "5": (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
    "6": (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E),
    "7": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    "8": (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
    "9": (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C),
    "·": (0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00),
    ".": (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04),
    ":": (0x00, 0x00, 0x04, 0x00, 0x04, 0x00, 0x00),
    "-": (0x00, 0x00, 0x00, 0x0E, 0x00, 0x00, 0x00),
    "/": (0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10),
}

#: Ancho de un carácter con su separación, en unidades de rejilla.
_PASO = 6


def ancho_texto(texto: str, escala: int) -> int:
    """Cuánto ocupa un texto ya escalado. Hace falta para poder centrarlo."""
    return (len(texto) * _PASO - 1) * escala


class Lienzo:
    """Un buffer RGB con lo justo para dibujar la tarjeta.

    No es una librería de gráficos: son rectángulos y texto en rejilla, que es
    todo lo que lleva la imagen. Cualquier cosa más complicada querría Pillow, y
    Pillow es la dependencia que aquí no se puede tener.
    """

    def __init__(self, ancho: int, alto: int, fondo: tuple[int, int, int]):
        self.ancho = ancho
        self.alto = alto
        self.buf = bytearray(bytes(fondo) * (ancho * alto))

    def rect(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
        """Rectángulo relleno, recortado al lienzo."""
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.ancho, x + w), min(self.alto, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        fila = bytes(color) * (x1 - x0)
        for fy in range(y0, y1):
            inicio = (fy * self.ancho + x0) * 3
            self.buf[inicio:inicio + len(fila)] = fila

    def texto(self, x: int, y: int, texto: str, escala: int,
              color: tuple[int, int, int]) -> None:
        """Texto en la rejilla 5x7, escalado por `escala`.

        Lo que no está en `FUENTE` se dibuja como espacio en vez de romper: los
        nombres de liga y de bot pueden traer acentos, y una tarjeta con un
        hueco es mejor que un `KeyError` que impide generar la web.
        """
        for i, ch in enumerate(texto.upper()):
            glifo = FUENTE.get(ch)
            if not glifo:
                continue
            base_x = x + i * _PASO * escala
            for fy, fila in enumerate(glifo):
                for fx in range(5):
                    if fila & (1 << (4 - fx)):
                        self.rect(base_x + fx * escala, y + fy * escala,
                                  escala, escala, color)

    def centrado(self, y: int, texto: str, escala: int,
                 color: tuple[int, int, int]) -> None:
        self.texto((self.ancho - ancho_texto(texto, escala)) // 2, y,
                   texto, escala, color)


def tarjeta(nombre: str, ligas: int, lema: str) -> bytes:
    """La imagen social: nombre, lema y el número de ligas medido.

    El texto es corto a propósito. Discord pinta la tarjeta a ~500 px de ancho
    en un móvil, así que a esa escala solo se lee el titular; meter tres líneas
    de descripción produce una imagen que parece llena y no dice nada. La
    descripción larga ya va en `og:description`, que es texto de verdad y se
    puede seleccionar.
    """
    c = Lienzo(ANCHO, ALTO, FONDO)

    # Barra superior verde: es la marca del bot (0x1F8B4C, el color de /help) y
    # lo único que hace reconocible la tarjeta de un vistazo en un canal.
    c.rect(0, 0, ANCHO, 10, VERDE)

    # Un degradado por franjas en la esquina, imitando el radial del `header`.
    # Se hace con 24 rectángulos porque interpolar por píxel sobre 756.000
    # píxeles en Python tarda más que todo el resto del script junto.
    for i in range(24):
        alfa = (24 - i) / 24 * 0.22
        color = tuple(
            round(FONDO[j] + (VERDE[j] - FONDO[j]) * alfa) for j in range(3)
        )
        c.rect(0, 10 + i * 7, ANCHO, 7, color)  # type: ignore[arg-type]

    c.centrado(200, nombre, 9, TEXTO)
    c.centrado(310, lema, 4, VERDE_CLARO)
    c.centrado(390, f"{ligas} LIGAS · SOLOQ EN VIVO", 4, SUAVE)
    c.centrado(470, "GRATIS · DISCORD", 3, SUAVE)

    c.rect(0, ALTO - 6, ANCHO, 6, VERDE)
    return png(ANCHO, ALTO, c.buf)


def favicon(nombre: str) -> str:
    """El favicon, en SVG.

    SVG y no ICO porque `<link rel="icon" type="image/svg+xml">` lo soportan
    todos los navegadores actuales, escala a cualquier tamaño y son 300 bytes de
    texto que se pueden leer en un diff. Un .ico serían cuatro mapas de bits
    empaquetados en un formato de 1995 que no se puede revisar.

    La letra es la inicial del nombre del bot para que siga funcionando si
    `BOT_NOMBRE` cambia, que es exactamente lo que `branding` permite hacer.
    """
    inicial = (nombre.strip() or "J")[0].upper()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
        'role="img" aria-label="' + inicial + '">\n'
        '  <rect width="64" height="64" rx="14" fill="#0f1115"/>\n'
        '  <rect x="2" y="2" width="60" height="60" rx="12" fill="none" '
        'stroke="#1f8b4c" stroke-width="4"/>\n'
        '  <text x="32" y="45" text-anchor="middle" fill="#2ecc71" '
        'font-family="system-ui,sans-serif" font-size="38" '
        'font-weight="700">' + inicial + "</text>\n"
        "</svg>\n"
    )
