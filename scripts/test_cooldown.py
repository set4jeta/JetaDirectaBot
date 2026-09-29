"""El freno por usuario: que frene al que machaca y no al que prueba.

Por qué existe
--------------
El limitador de la API de Riot es **global**: reparte la cuota sin distinguir
quién la pide. Y no había ningún límite por usuario en los comandos. Así que
alguien machacando `/info` en bucle no podía pasarse de la cuota —el limitador lo
impide— pero **competía con el tracker en la misma cola**, y el tracker es lo que
manda los avisos: un solo usuario podía retrasar los de todos. No tumbaba el bot;
lo degradaba, que es más difícil de ver.

Lo que esta prueba protege, por orden de importancia:

1. **Que un usuario normal no lo note NUNCA.** Es lo más importante: un freno que
   molesta a quien usa el bot bien es peor que el problema que resuelve. Por eso
   la prueba simula a alguien explorando el bot, que es el caso más exigente que
   hace una persona de verdad.
2. **Que al que machaca sí se le frene**, y a partir de cuántos comandos.
3. **Que frene solo a quien machaca**: el usuario de al lado no puede pagar el
   pato.
4. **Que el freno esté en los tres envoltorios**, porque si se pone en dos y el
   tercero se olvida, el comando que falte es la puerta abierta.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import cooldown  # noqa: E402
from utils.i18n import t  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


# --------------------------------------------------------------------- #
# 1. El usuario normal no lo nota
# --------------------------------------------------------------------- #

def prueba_usuario_normal() -> None:
    print("\n=== quien usa el bot bien no lo nota ===")

    # Explorar el bot: mirar en vivo, el ranking, una ficha, el equipo, la ayuda
    # y volver al ranking. Seis comandos seguidos, que es mucho más de lo que
    # hace nadie sin pararse a leer.
    cooldown.reiniciar()
    explorando = [1001] * 6
    frenado = [i for i, u in enumerate(explorando, 1) if cooldown.permitir(u) > 0]
    ok(not frenado, "seis comandos seguidos no se frenan",
       f"frenado en el {frenado[0]}" if frenado else "ninguno")

    # Y el caso real: una persona que lee entre comando y comando. Se simula
    # adelantando el reloj del cubo en vez de esperar de verdad.
    cooldown.reiniciar()
    usuario = 1002
    for _ in range(cooldown.CAPACIDAD + 5):
        cooldown.permitir(usuario)
        cooldown._cubos[usuario].ultimo -= cooldown.REPOSICION_S  # pasan segundos
    ok(cooldown.permitir(usuario) == 0.0,
       "leyendo entre comando y comando nunca se frena",
       f"ritmo de 1 comando cada {cooldown.REPOSICION_S:.0f}s")


# --------------------------------------------------------------------- #
# 2. Al que machaca se le frena
# --------------------------------------------------------------------- #

def prueba_machacon() -> None:
    print("\n=== a quien machaca sí se le frena ===")

    cooldown.reiniciar()
    usuario = 2001
    primeras = [cooldown.permitir(usuario) for _ in range(cooldown.CAPACIDAD)]
    ok(all(e == 0.0 for e in primeras),
       f"los primeros {int(cooldown.CAPACIDAD)} pasan", "es la capacidad del cubo")

    espera = cooldown.permitir(usuario)
    ok(espera > 0, "el siguiente se frena", f"espera {espera:.1f}s")

    # El mensaje necesita el número de segundos: un «no» seco se lee como que el
    # bot está roto. Por eso `permitir()` devuelve el tiempo y no un booleano.
    ok(espera <= cooldown.REPOSICION_S * 1.5,
       "la espera que se le dice es razonable", f"{espera:.1f}s")
    ok(round(espera) >= 1,
       "y redondeada nunca da 0, que se leería como «espera 0 segundos»")

    # Y el contador sube, que es lo que se ve en el log.
    ok(cooldown.frenados > 0, "queda registrado que se ha frenado",
       str(cooldown.frenados))


# --------------------------------------------------------------------- #
# 3. El freno es por usuario, no global
# --------------------------------------------------------------------- #

def prueba_aislamiento() -> None:
    print("\n=== el freno es de quien machaca, no de todos ===")

    cooldown.reiniciar()
    machacon, vecino = 3001, 3002
    for _ in range(cooldown.CAPACIDAD + 3):
        cooldown.permitir(machacon)

    ok(cooldown.permitir(machacon) > 0, "el que machaca sigue frenado")
    ok(cooldown.permitir(vecino) == 0.0,
       "y el de al lado no paga el pato", "cubos independientes")

    # Este es el punto entero: sin esto, un usuario insistente retrasaría los
    # avisos de todo el mundo.
    ok(cooldown.permitir(3003) == 0.0, "ni un tercero cualquiera")


# --------------------------------------------------------------------- #
# 4. Se repone con el tiempo
# --------------------------------------------------------------------- #

def prueba_reposicion() -> None:
    print("\n=== se repone solo, sin intervención ===")

    cooldown.reiniciar()
    usuario = 4001
    for _ in range(cooldown.CAPACIDAD):
        cooldown.permitir(usuario)
    ok(cooldown.permitir(usuario) > 0, "el cubo se vacía")

    # Se adelanta el reloj del cubo en vez de dormir la prueba: esperar 3 s de
    # verdad por cada ficha haría la prueba lenta sin comprobar nada más.
    cooldown._cubos[usuario].ultimo -= cooldown.REPOSICION_S * 2
    ok(cooldown.permitir(usuario) == 0.0, "con el tiempo repuesto, vuelve a pasar")

    # Y nunca se pasa del tope: un usuario que lleva horas sin usar el bot no
    # acumula un cubo gigante.
    cooldown._cubos[usuario].ultimo -= 86400
    cooldown.permitir(usuario)
    ok(cooldown._cubos[usuario].fichas <= cooldown.CAPACIDAD,
       "el cubo no acumula más allá del tope",
       f"{cooldown._cubos[usuario].fichas:.1f} de {cooldown.CAPACIDAD:.0f}")


def prueba_memoria() -> None:
    print("\n=== la tabla no crece para siempre ===")

    cooldown.reiniciar()
    for u in range(1000):
        cooldown.permitir(u)
    antes = len(cooldown._cubos)
    # Se envejecen todos y se mete uno nuevo, que dispara la limpieza.
    for c in cooldown._cubos.values():
        c.ultimo -= cooldown.CAPACIDAD * cooldown.REPOSICION_S + 1
    cooldown.permitir(9999)
    ok(len(cooldown._cubos) < antes,
       "los cubos viejos se sueltan", f"{antes} -> {len(cooldown._cubos)}")
    ok(9999 in cooldown._cubos, "y el nuevo se queda")


# --------------------------------------------------------------------- #
# 5. Está enganchado donde tiene que estar
# --------------------------------------------------------------------- #

def prueba_enganche() -> None:
    print("\n=== el freno cubre todos los comandos ===")

    import inspect

    from core import dual_command

    for envoltorio in ("slash", "slash_texto", "slash_opciones"):
        fuente = inspect.getsource(getattr(dual_command, envoltorio))
        ok("_frenar(" in fuente, f"{envoltorio} pasa por el freno")

    # Y corta ANTES de llamar al cuerpo del comando, que es el punto entero: si
    # se comprobara después, el gasto de cuota de Riot ya estaría hecho.
    fuente = inspect.getsource(dual_command._frenar)
    ok("permitir(" in fuente, "el freno consulta el cubo")

    for envoltorio in ("slash", "slash_texto", "slash_opciones"):
        fuente = inspect.getsource(getattr(dual_command, envoltorio))
        pos_freno = fuente.find("_frenar(")
        pos_cuerpo = fuente.find("await cuerpo(")
        ok(0 <= pos_freno < pos_cuerpo,
           f"{envoltorio}: el freno va antes de gastar cuota")

    # El mensaje tiene que existir en los dos idiomas y decir los segundos.
    for idioma in ("es", "en"):
        texto = t("freno.espera", idioma, segundos=4)
        ok(texto != "freno.espera" and "4" in texto,
           f"[{idioma}] el mensaje existe y dice los segundos", texto[:44])


def main() -> None:
    prueba_usuario_normal()
    prueba_machacon()
    prueba_aislamiento()
    prueba_reposicion()
    prueba_memoria()
    prueba_enganche()

    print(f"\nfallos : {len(fallos)}")
    if fallos:
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
