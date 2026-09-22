/* live.js — Puente entre el bot y la web estática.
 *
 * El bot escribe un registro de avisos (avisos.jsonl) y, opcionalmente, un
 * volcado JSON (api/live.json) con los últimos avisos y los equipos seguidos.
 * Este script lee ese JSON y pinta dos zonas de index.html:
 *
 *   1. #teams-strip  → tira de logos de equipos (si el JSON trae `equipos`)
 *   2. #feed         → lista de "partidas recientes" con el formato del aviso
 *
 * Si el JSON no existe (despliegue estático sin bot) o está vacío, la zona
 * #feed muestra un mensaje neutro y no rompe la página. Todo el pintado es
 * defensivo: un campo ausente no lanza.
 *
 * El JSON se genera con `scripts/generar_web.py` y se sube junto a la web.
 * No hay llamadas a la API de Riot desde el navegador: la web nunca expone
 * la key ni hace CORS a Riot.
 */
(function () {
  "use strict";

  var RUTA = "api/live.json";
  var feed = document.getElementById("feed");
  var strip = document.getElementById("teams-strip");

  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }

  function tiempoRelativo(ts) {
    if (!ts) return "";
    var s = Math.floor(Date.now() / 1000 - ts);
    if (s < 60) return "hace " + s + " s";
    if (s < 3600) return "hace " + Math.floor(s / 60) + " min";
    if (s < 86400) return "hace " + Math.floor(s / 3600) + " h";
    return "hace " + Math.floor(s / 86400) + " d";
  }

  function pintarEquipos(equipos) {
    if (!strip || !equipos || !equipos.length) return;
    strip.innerHTML = "";
    equipos.slice(0, 24).forEach(function (eq) {
      var item = el("span", "team");
      if (eq.imagen) {
        var img = el("img");
        img.src = eq.imagen;
        img.alt = eq.nombre || eq.code || "";
        img.loading = "lazy";
        item.appendChild(img);
      }
      item.appendChild(document.createTextNode(eq.code || eq.nombre || ""));
      strip.appendChild(item);
    });
  }

  function pintarFeed(avisos) {
    if (!feed) return;
    if (!avisos || !avisos.length) {
      feed.innerHTML =
        '<div class="vacio">Aún no hay avisos registrados en este despliegue. ' +
        "Cuando un pro entre en SoloQ, el aviso aparece aquí en tiempo real.</div>";
      return;
    }
    feed.innerHTML = "";
    avisos.slice(0, 12).forEach(function (a) {
      var card = el("div", "card");
      var head =
        '<div class="ico">🎯</div><h3>' +
        escapeHtml(a.jugador || "Jugador") +
        (a.equipo ? ' <span style="color:var(--texto-suave)">· ' + escapeHtml(a.equipo) + "</span>" : "") +
        "</h3>";
      var lineas = [];
      if (a.liga) lineas.push("<b>Liga:</b> " + escapeHtml(a.liga.toUpperCase()));
      if (a.campeon) lineas.push("<b>Campeón:</b> " + escapeHtml(a.campeon));
      if (a.rango) lineas.push("<b>Elo:</b> " + escapeHtml(a.rango));
      if (a.servidor) lineas.push("<b>Servidor:</b> " + escapeHtml(a.servidor));
      var pie = '<p style="color:var(--texto-suave);font-size:0.82rem;margin-top:8px">' +
        tiempoRelativo(a.ts) + "</p>";
      card.innerHTML = head + "<p>" + lineas.join("<br>") + "</p>" + pie;
      feed.appendChild(card);
    });
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  fetch(RUTA, { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (data) {
      pintarEquipos(data.equipos);
      pintarFeed(data.avisos);
    })
    .catch(function () {
      // Silencioso: la web estática funciona sin el bot.
      if (feed) {
        feed.innerHTML =
          '<div class="vacio">Datos en vivo no disponibles en este despliegue. ' +
          "El aviso se publica en Discord en cuanto un pro entra en partida.</div>";
      }
    });
})();
