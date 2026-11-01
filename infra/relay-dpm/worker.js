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
// dpm.lol (`DPM_RELAY_URL`) y vuelve a poder refrescar los rosters solo, sin
// depender de que un runner de GitHub tenga suerte con la IP.
//
// Qué NO hace
// -----------
// Solo habla con `dpm.lol` por https y solo con las rutas que usa el bot
// (`/v1/…` y `/esport/…`). No es un proxy abierto: sin la clave no responde, y
// con la clave sigue sin poder pedir otro dominio. Eso importa porque un proxy
// abierto lo acaba usando cualquiera y entonces sí nos bloquean a nosotros.
//
// Despliegue: ver README.md de esta carpeta.

const HOST_PERMITIDO = "dpm.lol";
const PREFIJOS = ["/v1/", "/esport/"];

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

    let respuesta;
    try {
      respuesta = await fetch(destino.toString(), {
        headers: CABECERAS,
        redirect: "follow",
      });
    } catch (exc) {
      // Que el fallo se vea en el cliente: si el relay devolviera 200 vacío, el
      // bot lo tomaría por una respuesta buena y guardaría un roster vacío.
      return new Response(`relay: ${exc}`, { status: 502 });
    }

    return new Response(respuesta.body, {
      status: respuesta.status,
      headers: {
        "content-type":
          respuesta.headers.get("content-type") || "application/octet-stream",
        // Para que se pueda diagnosticar desde el otro lado sin adivinar.
        "x-relay-upstream": String(respuesta.status),
        "cache-control": "no-store",
      },
    });
  },
};
