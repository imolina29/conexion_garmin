# Phase 1 — Generalización Multi-Usuario del Garmin Coach Bot

## Intención

Convertir el bot de un coach personal hardcodeado para un solo usuario en
un sistema donde cada persona configura su propia rutina de entrenamiento,
su zona horaria, sus horarios de reportes, y recibe transparencia sobre
cómo se almacenan sus credenciales. Es el primer paso para convertir esta
integración en un skill compartible con la comunidad.

## Por qué

Hoy el bot tiene la estructura Push/Pull/Leg de Ivan hardcodeada en
`PLAN_PROMPT`, un timezone global en una variable de entorno, y horarios
de reporte fijos (7:30 AM / 8:30 PM) iguales para todos. Si un segundo
usuario se registra, hereda la rutina de Ivan, su zona horaria, y sus
horarios. Para que cualquier persona pueda usar este bot, cada usuario
necesita configurar su propio contexto.

## Objetivos

1. **Rutina configurable:** Cada usuario define su propia estructura de
   entrenamiento (días, split, tipo de ejercicio) mediante un flujo
   conversacional. El bot usa Gemini para convertir la descripción libre
   del usuario en una estructura almacenada.
2. **Config per-user:** Timezone y horarios de reportes almacenados en el
   `config.json` de cada usuario, no en env vars globales.
3. **Transparencia:** Durante el registro, informar al usuario que sus
   credenciales de Garmin se cifran con Fernet y se almacenan en disco
   — no en texto plano, pero sí almacenadas.

## No-objetivos

- No se soportan otros wearables en esta fase (Strava, Apple Watch).
  Eso es Phase 2.
- No se hace onboarding completamente guiado paso a paso (wizard). El
  flujo usa comandos: `/rutina` para definir rutina, `/config` para
  timezone y horarios.
- No se migra a base de datos. Se sigue usando el filesystem JSON actual.
- No se cambia el modelo de LLM (sigue Gemini free tier).

## Anti-objetivos

- Que un usuario nuevo reciba planes basados en la rutina de otro usuario.
- Que el bot genere reportes a horas incorrectas porque usa un timezone
  global que no corresponde al usuario.
- Que el usuario no sepa que sus credenciales están almacenadas en disco.

## Cambios requeridos

### 1. Rutina configurable por usuario

**Estado actual:** `PLAN_PROMPT` en `bot.py:269-330` tiene la tabla
Push/Pull/Leg hardcodeada. Cuando un usuario pide `/plan`, Gemini recibe
esa estructura fija como constraint.

**Estado deseado:**

- Nuevo campo `training_routine` en `config.json` del usuario. Es un
  string libre que describe la estructura de entrenamiento aprobada por
  el usuario. Ejemplo:
  ```json
  {
    "training_routine": "Lunes: Empuje (Pecho, Hombro, Tríceps) + Descanso Activo\nMartes: Descanso + Intervalos Z4/Z5\nMiércoles: Tracción (Espalda, Bíceps) + Descanso Activo\nJueves: Descanso + Base Aeróbica Z2\nViernes: Pierna (Cuádriceps, Isquios, Glúteo)\nSábado-Domingo: Libre"
  }
  ```

- Nuevo comando `/rutina` que inicia un flujo conversacional:
  1. Bot pregunta: "Describe tu rutina de entrenamiento ideal: qué días
     entrenas, qué tipo de ejercicio haces cada día, y cuántos días
     descansas."
  2. Usuario escribe su rutina en texto libre.
  3. Bot usa Gemini para parsear la descripción y generar una tabla
     estructurada legible. La muestra al usuario para aprobación.
  4. Si el usuario aprueba (responde "sí", "ok", "listo", etc.), se
     guarda en `training_routine`. Si pide cambios, itera.

- `PLAN_PROMPT` se vuelve dinámico: en vez de la tabla hardcodeada, inserta
  `training_routine` del usuario. Si no tiene rutina definida, usa un prompt
  genérico que le pide al LLM proponer una estructura basada en el perfil.

- El campo `profile` existente se mantiene para información general
  (objetivos, contexto). `training_routine` es específicamente la
  estructura semanal.

### 2. Config per-user: timezone y horarios de reportes

**Estado actual:**
- `USER_TZ` es global, leída de `USER_TIMEZONE` env var (default
  `America/Bogota`).
- `REPORT_SCHEDULE` es global: `[(7, 30, "morning"), (20, 30, "evening")]`.
- `report_loop()` usa estos valores globales para todos los usuarios.

**Estado deseado:**

- Nuevos campos en `config.json` del usuario:
  ```json
  {
    "timezone": "America/Bogota",
    "report_morning": "07:30",
    "report_evening": "20:30"
  }
  ```

- Defaults: timezone `America/Bogota`, reporte matutino 07:30, nocturno
  20:30. Si el campo no existe (usuarios legacy), se usan los defaults.

- Nuevo comando `/config` que permite al usuario cambiar:
  - Timezone: "¿En qué zona horaria estás?" (acepta nombres IANA o
    ciudades comunes: Bogotá, CDMX, Buenos Aires, Madrid, etc.)
  - Horarios: "¿A qué hora quieres el reporte de la mañana?" y "¿A qué
    hora el de la noche?"

- `report_loop()` se reescribe para manejar horarios per-user:
  - Cada minuto (o cada 30 segundos), el loop revisa todos los usuarios
    y para cada uno calcula si es hora de enviar un reporte basándose en
    su timezone y sus horarios configurados.
  - Se usa una marca `last_report_sent` por usuario y tipo para evitar
    duplicados.

- `user_today()` acepta un timezone parameter en vez de usar el global.

- **Env var `USER_TIMEZONE` se mantiene** como default para nuevos
  usuarios, pero deja de controlar el comportamiento del bot directamente.

### 3. Transparencia de credenciales

**Estado actual:** Durante el registro, el bot dice "🔒 Será cifrada y
almacenada de forma segura" cuando pide la contraseña (`bot.py:216`).
No explica qué significa "forma segura".

**Estado deseado:**

- Cambiar el mensaje durante el registro para ser explícito:
  "Tu contraseña será cifrada (Fernet/AES) y almacenada en el servidor.
  No se guarda en texto plano, pero sí se almacena de forma cifrada para
  poder conectarse a Garmin automáticamente. Si en algún momento quieres
  eliminar tus datos, usa /eliminar."

- Nuevo comando `/eliminar` (o `/borrar`) que:
  1. Pide confirmación al usuario.
  2. Elimina todo el directorio `data/users/{telegram_id}/` del usuario.
  3. Confirma la eliminación.

- Agregar al mensaje de bienvenida post-registro una nota sobre esto.

## Restricciones

- Python 3.13, mismo stack actual.
- No agregar dependencias nuevas.
- Los usuarios existentes (como Ivan) deben seguir funcionando sin acción
  — los nuevos campos usan defaults compatibles con el comportamiento
  actual.
- El flujo de `/rutina` debe funcionar con Gemini free tier (no requerir
  modelos más caros).
- Los tests existentes (34) deben seguir pasando.

## Decisiones de diseño resueltas

Estas decisiones surgieron de la revisión técnica del spec y fueron
resueltas aquí para que el builder no tenga que adivinar:

### D1: Estado conversacional de `/rutina` (builder call)

`/rutina` reutiliza el patrón existente de `registration_state` — un dict
en memoria con el user_id como key y un campo `step` que indica en qué
parte del flujo está. Mientras el usuario está en flujo de `/rutina`,
todos sus mensajes de texto se interceptan (igual que durante registro).
El usuario puede cancelar con `/cancelar`. Los reportes automáticos se
siguen enviando normalmente (son push, no dependen de mensajes entrantes).

### D2: Onboarding y comandos post-registro (builder call)

Durante el registro, después del perfil, se agrega UN paso adicional:
preguntar la zona horaria ("¿En qué país/ciudad estás?"). Esto evita que
el primer reporte matutino llegue a hora incorrecta. Es una sola pregunta,
no alarga significativamente el flujo.

`/rutina` y `/config` son comandos independientes post-registro. Un usuario
sin `training_routine` definida recibe planes genéricos basados en su
perfil — funciona, solo es menos personalizado. Los horarios de reporte
usan defaults sensatos (7:30 AM / 8:30 PM local) hasta que el usuario
los cambie con `/config`.

### D3: Plan JSON flexible para rutinas personalizadas (spec intent)

El JSON schema del plan se flexibiliza para soportar rutinas arbitrarias:
- `sessions` acepta de 1 a 7 elementos (no forzar exactamente 5).
- `weekday` acepta 0-6 (lunes a domingo).
- El prompt dinámico le dice a Gemini cuántos días y cuáles, basándose en
  la `training_routine` del usuario.
- `parse_plan_json`, `_today_plan_section`, y `generate_ics` se adaptan
  para manejar cualquier número de sesiones y cualquier día de la semana.

### D4: Rate limits de Gemini en report loop (builder call)

Para Phase 1, los reportes se envían secuencialmente con 2 segundos de
pausa entre usuarios. Esto funciona para decenas de usuarios en free tier
(~15 RPM limit). La optimización a escala (colas, batching) es tema de
una fase futura si la demanda lo justifica.

### D5: Limpieza de estado en `/eliminar` (builder call)

`/eliminar` limpia TODO: directorio en disco + entries en `conversations`,
`registration_state`, `last_sync`, y cualquier estado en memoria. Después
de eliminar, el usuario puede re-registrarse con `/start` inmediatamente.

## Qué queda para el builder

- Formato exacto del prompt que parsea la rutina del usuario.
- Mapeo de ciudades comunes a timezones IANA para `/config`.
- Si `/config` usa un flujo paso a paso o permite cambiar todo en un
  solo mensaje.
