// Relay de dpm.lol en un Worker de Cloudflare.
//
// Por qué existe
// --------------
// dpm.lol está detrás de Cloudflare y contesta **403 a las IPs de datacenter**.
// Medido el 01-11-2026: desde Render, 403 con los dos transportes (cloudscraper
// y curl_cffi) en el 100 % de las peticiones; desde un runner de GitHub, 403 en
// todo en 5 de cada 6 ejecuciones; desde una IP doméstica, 200 siempre.
//
// Este Worker hace la petición **desde la red de Cloudflare**, que es la misma
// que la protege, y devuelve el cuerpo tal cual. El bot lo llama como si fuera
// dpm.lol (`DPM_RELAY_URL`).
//
// Lo que se aprendió al ponerlo en marcha
// ---------------------------------------
// La primera petición volvió con `upstream=200` y datos reales, así que el
// camino existe. Pero al rato dpm.lol empezó a contestar al Worker con la página
// de desafío («Just a moment…»): las subpeticiones de un Worker salen por un
// **pool compartido** de IPs, y ese pool también tiene mala reputación. De ahí
// el bucle de reintentos: la IP de salida cambia entre subpeticiones, así que
// reintentar dentro del Worker **sí** puede cambiar el resultado, a diferencia de
// reintentar desde Render (donde la IP es fija y siempre la misma).
//
// Qué NO hace
// -----------
// Solo habla con `dpm.lol` por https y solo con las rutas que usa el bot. No es
// un proxy abierto: sin la clave no responde, y con la clave sigue sin poder
// pedir otro dominio. Eso importa porque un proxy abierto lo acaba usando
// cualquiera y entonces sí nos bloquean a nosotros.
//
// Despliegue: `python scripts/desplegar_relay.py` (o ver README.md).

const HOST_PERMITIDO = "dpm.lol";

// Las rutas que pide el bot, ni una más. Salieron de buscar `dpm.lol/` en el
// código: `/v1/…` (API), `/esport/…` (leaderboards y fichas), `/tierlist` y
// `/pro/…` (páginas de jugador). `/tierlist` y `/pro/` entraron el 01-11-2026:
// sin ellas, el bot recibía un 400 **del propio relay** y el log lo contaba como
// si dpm.lol estuviera bloqueando.
const PREFIJOS = ["/v1/", "/esport/", "/tierlist", "/pro/"];

// Un navegador de verdad. El Worker no hereda las cabeceras del cliente, así que
// sin esto dpm.lol ve la petición como lo que es: un `fetch` sin UA.
const CABECERAS = {
  "user-agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  accept: "application/json, text/plain, */*",
  "accept-language": "es-ES,es;q=0.9,en;q=0.8",
  referer: "https://dpm.lol/",
};

//: Intentos por petición. Tres basta: si tres IPs seguidas del pool están
//: marcadas, la cuarta tampoco iba a estarlo menos, y cada intento cuesta tiempo
//: del que el bot no tiene (una pasada de rosters son ~50 fichas por liga).
const INTENTOS = 3;

//: Pausa entre intentos. Corta: el bot está esperando y lo que cambia el
//: resultado es la IP, no el tiempo.
const ESPERA_MS = 250;

const MARCAS_DESAFIO = [
  "just a moment",
  "attention required",
  "cf-chl",
  "checking your browser",
  "enable javascript and cookies",
];

function esDesafio(texto) {
  const bajo = (texto || "").toLowerCase();
  return MARCAS_DESAFIO.some((m) => bajo.includes(m));
}

async function pedir(destino) {
  let ultima = null;
  for (let intento = 1; intento <= INTENTOS; intento++) {
    let respuesta;
    try {
      respuesta = await fetch(destino, { headers: CABECERAS, redirect: "follow" });
    } catch (exc) {
      ultima = { error: String(exc), intento };
      continue;
    }

    // Solo se lee el cuerpo cuando hay que decidir si es un desafío. Leerlo
    // siempre duplicaría el trabajo en el caso bueno, que es el que importa.
    if (respuesta.status !== 200) {
      const texto = await respuesta.clone().text();
      if (esDesafio(texto)) {
        ultima = { status: respuesta.status, desafio: true, intento };
        if (intento < INTENTOS) {
          await new Promise((r) => setTimeout(r, ESPERA_MS));
          continue;
        }
      }
      return { respuesta, intento, desafio: esDesafio(texto) };
    }
    return { respuesta, intento, desafio: false };
  }
  return { respuesta: null, ...ultima };
}

export default {
  async fetch(peticion, env) {
    const url = new URL(peticion.url);

    // La clave puede venir en la cabecera (lo normal) o en `?k=`, para poder
    // probarlo desde el navegador con una barra de direcciones.
    const clave =
      peticion.headers.get("x-relay-key") || url.searchParams.get("k") || "";
    if (!env.RELAY_KEY || clave !== env.RELAY_KEY) {
      return new Response("forbidden", { status: 403 });
    }

    const crudo = url.searchParams.get("u");
    if (!crudo) {
      return new Response("falta el parámetro u", { status: 400 });
    }

    let destino;
    try {
      destino = new URL(crudo);
    } catch {
      return new Response("u no es una URL", { status: 400 });
    }
    if (destino.protocol !== "https:" || destino.hostname !== HOST_PERMITIDO) {
      return new Response("solo https://dpm.lol", { status: 400 });
    }
    if (!PREFIJOS.some((p) => destino.pathname.startsWith(p))) {
      return new Response("ruta no permitida", { status: 400 });
    }

    const salida = await pedir(destino.toString());

    if (!salida.respuesta) {
      // Que el fallo se vea en el cliente: si el relay devolviera 200 vacío, el
      // bot lo tomaría por una respuesta buena y guardaría un roster vacío.
      return new Response(`relay: ${salida.error || "sin respuesta"}`, {
        status: 502,
        headers: { "x-relay-intentos": String(salida.intento || 0) },
      });
    }

    return new Response(salida.respuesta.body, {
      status: salida.respuesta.status,
      headers: {
        "content-type":
          salida.respuesta.headers.get("content-type") || "application/octet-stream",
        // Para que se pueda diagnosticar desde el otro lado sin adivinar:
        // qué contestó dpm.lol, cuántos intentos hicieron falta y si el cuerpo
        // que llega es el desafío y no el JSON.
        "x-relay-upstream": String(salida.respuesta.status),
        "x-relay-intentos": String(salida.intento),
        "x-relay-desafio": salida.desafio ? "1" : "0",
        "cache-control": "no-store",
      },
    });
  },
};
