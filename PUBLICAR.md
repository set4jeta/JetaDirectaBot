# PUBLICAR.md — 3 pasos para que la web se vea

Documento corto a propósito. El detalle completo está en `DESPLIEGUE.md`.

**Importante: estás en la página correcta de GitHub.** El desplegable que buscas
se llama **Origen** y está en el bloque de **arriba**, no en el de abajo. En el
bloque de abajo es donde pone "Agregar dominio" (eso es para un dominio propio,
no lo necesitas ahora).

---

## Paso 1 — El push (2 comandos)

Abre una terminal en `C:\jetabot res 8\JetaDirectaBot` y pega estos dos
comandos, uno detrás del otro:

```bash
git push origin f7393174b2d21cb66cf8ef537ec9944415f960b1:refs/heads/backup-oct-2025
git push --force-with-lease origin HEAD:main
```

- El primero **guarda una copia** de lo que hay hoy en GitHub en una rama
  llamada `backup-oct-2025`. No borra nada.
- El segundo sube el código bueno a `main`.
- Si pide usuario y contraseña: usuario tu nombre de GitHub, contraseña un
  **token** (GitHub no acepta la contraseña de la cuenta). Si Windows abre una
  ventana del navegador, inicia sesión ahí y listo.

**No uses `git push` a secas**: se rechaza, porque el repo de GitHub y tu
carpeta no comparten historia. Tiene que ser el segundo comando tal cual.

## Paso 2 — El interruptor de Pages (2 clics)

Abre exactamente esta dirección:

**https://github.com/set4jeta/JetaDirectaBot/settings/pages**

En esa página, de arriba abajo:

1. **Compilación e implementación** (en inglés *Build and deployment*). Aquí
   está el desplegable **Origen** (*Source*).
2. Cámbialo de **"Implementar desde una rama"** a **"GitHub Actions"**.
3. Ya está. No toques nada del bloque de abajo (**Dominio personalizado** /
   "Agregar dominio"): eso es para poner un dominio propio de pago, no lo
   necesitas.

> Si no ves el desplegable **Origen**: sube un poco. Está justo **encima** del
> bloque donde pone "Agregar dominio". Y comprueba que estás en `Settings` de
> **JetaDirectaBot**, no en los ajustes de tu cuenta.

## Paso 3 — Comprobar

1. Ve a **https://github.com/set4jeta/JetaDirectaBot/actions**. Tiene que
   aparecer una ejecución llamada **"Publicar web"** con un círculo amarillo
   (en curso) que pasa a **verde** en un minuto.
2. Cuando esté verde, abre **https://set4jeta.github.io/JetaDirectaBot/**
   (dale a recargar forzado, Ctrl+F5). Tienes que ver la web nueva: cabecera
   "onair", la tira de equipos y el feed, no el README de texto.

Si la raíz sigue enseñando el README, es que el paso 2 no se guardó.

---

## Si algo falla

- **El paso 1 da "rejected" o "non-fast-forward"**: estás usando `git push` a
  secas. Copia el segundo comando completo, con `--force-with-lease`.
- **La ejecución de "Publicar web" sale en rojo**: ábrela, copia el mensaje de
  error y pásamelo. Lo más probable es un permiso de Actions.
- **No aparece ninguna ejecución en Actions**: mira en Settings → Actions →
  General que las acciones estén permitidas (opción *Allow all actions*).
- **La web se ve, pero sin datos en vivo**: es normal. El feed se rellena con
  `python scripts/bridge_web.py`, que hoy hay que lanzar a mano.

---

## Si prefieres no pelearte con esto

Con un **token de GitHub** lo hago yo todo desde aquí en un minuto: el push, el
cambio de Pages a GitHub Actions y la comprobación de que la web responde.

Cómo se crea: GitHub → foto de perfil → **Settings** → **Developer settings** →
**Personal access tokens** → **Fine-grained tokens** → *Generate new token*.

- **Repository access**: *Only select repositories* → `JetaDirectaBot`
- **Permissions**:
  - `Contents` → **Read and write** (para el push)
  - `Pages` → **Read and write** (para el interruptor de Pages)

Caduca solo si le pones fecha, y se puede revocar en cuanto termine.
