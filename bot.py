#!/usr/bin/env python3
"""Multi-user Telegram bot — Garmin training coach powered by Gemini."""

import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google import genai
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from analysis import build_context_snapshot
from calendar_server import parse_plan_json, plan_start_date, start_calendar_server
from sync import create_client, sync_activities, sync_daily_stats
from users import UserManager

logger = logging.getLogger(__name__)

SYNC_COOLDOWN_MINUTES = 15
USER_TZ = ZoneInfo(os.getenv("USER_TIMEZONE", "America/Mexico_City"))


def user_today() -> date:
    return datetime.now(tz=USER_TZ).date()

METRIC_REFERENCE = """
## Referencia de métricas Garmin

**FC en reposo (Frecuencia Cardíaca en reposo):** Tu pulso más bajo en el día, medido generalmente al dormir. Es un indicador de fitness cardiovascular — más bajo = mejor condición física. Rango típico: 40-60 bpm para personas activas. Un aumento sostenido puede indicar fatiga, estrés o enfermedad.

**HRV (Variabilidad del Ritmo Cardíaco):** Mide la variación en tiempo entre latidos. Refleja el estado de tu sistema nervioso autónomo. Valores más altos = mejor recuperado y adaptado al entrenamiento. Se mide durante el sueño. Varía mucho día a día — la tendencia semanal importa más que un solo valor.

**Training Readiness (Preparación para Entrenar):** Score de 0-100 que combina: calidad de sueño, tiempo de recuperación, carga de entrenamiento, HRV y estrés. >60 = listo para entrenar fuerte. 30-60 = entrenamiento moderado. <30 = priorizar descanso.

**Sleep Score (Puntuación de Sueño):** Score de 0-100 basado en: duración total, porcentaje de sueño profundo (reparación física, ideal 16-33%), REM (consolidación de memoria, ideal 21-31%), ligero (transición), despertares y estrés nocturno.

**Body Battery:** Energía estimada de 0-100 basada en HRV, estrés, sueño y actividad. Se carga con descanso y sueño, se descarga con actividad y estrés.

**Zonas de FC durante ejercicio:**
- Zona 1 (50-60% FC max): Calentamiento, recuperación activa
- Zona 2 (60-70%): Resistencia aeróbica base — donde se construye la base
- Zona 3 (70-80%): Tempo, umbral aeróbico
- Zona 4 (80-90%): Umbral anaeróbico, mejora velocidad
- Zona 5 (90-100%): Esfuerzo máximo, sprints

**Ritmo (Pace):** Tiempo por kilómetro en running. Menos = más rápido. La mejora se mide en segundos/km ganados a lo largo de semanas.

**Monotonía de entrenamiento:** Hacer siempre lo mismo (mismo ritmo, misma distancia, mismos ejercicios) limita la adaptación. La variación es clave para mejorar.
"""


def build_system_prompt(garmin_snapshot: str, user_profile: str) -> str:
    if user_profile:
        profile_section = user_profile
    else:
        profile_section = (
            "No se ha configurado un perfil específico. "
            "Pregunta al usuario sobre su rutina para poder dar mejores recomendaciones, "
            "o sugiérele que use /perfil para configurarlo."
        )

    t = user_today()
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    today_str = f"{dias[t.weekday()]} {t.day} de {meses[t.month - 1]} de {t.year}"
    return f"""Eres un coach de entrenamiento personal inteligente que analiza datos reales de un reloj Garmin.

📅 Fecha actual: {today_str}

Tu personalidad:
- Hablas en español, claro y directo
- Eres CRÍTICO y OBJETIVO — tu trabajo no es hacer sentir bien al usuario, es ayudarlo a mejorar
- No adornes los resultados: si el entrenamiento fue mediocre, dilo. Si no hubo progreso, señálalo
- Eres como un coach profesional exigente: reconoces lo bueno pero nunca dejas pasar lo mejorable
- Cuando los datos muestran estancamiento, falta de intensidad o inconsistencia, lo dices sin rodeos
- Usas SUS datos reales para responder, nunca respuestas genéricas
- Usas comparaciones concretas con números ("tu ritmo empeoró 15 seg/km vs la semana pasada")
- Si detectas algo preocupante (HRV muy bajo, Training Readiness <20, FC reposo subiendo), lo marcas como alerta
- Da recomendaciones accionables y específicas, no generalidades como "descansa más" — di exactamente qué hacer

{METRIC_REFERENCE}

## Datos actuales del usuario

{garmin_snapshot}

## Perfil del usuario
{profile_section}

## Notas sobre datos Garmin
- Las actividades de fuerza en Garmin no registran bien los nombres de ejercicios — si el usuario te dice qué hizo (ej: "hoy fue pecho"), úsalo para interpretar los datos de esa sesión
- El usuario puede decirte antes de entrenar qué planea hacer — recuérdalo para cuando pregunte después cómo le fue

## Instrucciones
- Responde basándote en los datos reales mostrados arriba
- Si el usuario pregunta por una métrica, explica qué es Y qué significa su valor específico
- Detecta tendencias: ¿está mejorando, estancado, o empeorando? Sé explícito sobre cuál es
- Si ves monotonía en entrenamientos (mismo tipo/ritmo/duración repetido), confronta al usuario: "llevas 3 semanas corriendo al mismo ritmo, no estás progresando"
- Si hay señales de sobreentrenamiento (HRV bajo + Training Readiness bajo + FC reposo alta), alerta con urgencia
- Si el usuario dice que va a entrenar fuerte pero sus métricas dicen que debería descansar, díselo directamente — no le des permiso de sobreentrenarse
- Mantén respuestas concisas pero contundentes — no más de 300 palabras por respuesta
- No inventes datos que no estén en el snapshot
- Cuando el usuario te cuente su plan de entrenamiento, evalúalo críticamente contra sus datos: ¿es realista? ¿se alinea con sus métricas actuales? ¿va a generar progreso o es más de lo mismo?
- NUNCA respondas solo con "buen trabajo" o "sigue así" — siempre agrega qué podría ser mejor"""


class ConversationHistory:
    def __init__(self, max_messages: int = 20):
        self._messages: list[dict] = []
        self._max = max_messages

    def add(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})
        if len(self._messages) > self._max:
            self._messages = self._messages[-self._max:]
        while self._messages and self._messages[0]["role"] == "model":
            self._messages.pop(0)

    def get_messages(self) -> list[dict]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()


conversations: dict[int, ConversationHistory] = {}
registration_state: dict[int, dict] = {}
last_sync: dict[int, datetime] = {}
user_manager: UserManager | None = None
gemini_client: genai.Client | None = None


def run_sync_safe(telegram_id: int) -> bool:
    now = datetime.now(tz=timezone.utc)
    if telegram_id in last_sync:
        elapsed = (now - last_sync[telegram_id]).total_seconds() / 60
        if elapsed < SYNC_COOLDOWN_MINUTES:
            return True

    try:
        creds = user_manager.get_garmin_credentials(telegram_id)
        if not creds:
            return False
        email, password = creds

        client = create_client(email, password, user_manager.token_store_path(telegram_id))
        today = user_today()
        today_str = today.isoformat()
        activities_dir = user_manager.activities_dir(telegram_id)
        is_first_sync = not any(activities_dir.glob("*.json"))
        lookback = 90 if is_first_sync else 2
        start = (today - timedelta(days=lookback)).isoformat()

        sync_activities(client, start, today_str, user_manager.activities_dir(telegram_id))
        sync_daily_stats(client, start, today_str, user_manager.stats_dir(telegram_id))

        last_sync[telegram_id] = now
        return True
    except Exception as e:
        logger.warning("Sync failed for user %d: %s", telegram_id, e)
        return False


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_manager.user_exists(user_id):
        await update.message.reply_text(
            "Ya estás registrado. Escríbeme directamente para analizar tu entrenamiento.\n"
            "Usa /perfil para actualizar tu perfil de entrenamiento."
        )
        return

    registration_state[user_id] = {"step": "awaiting_email"}
    await update.message.reply_text(
        "¡Hola! Soy tu coach de entrenamiento personal.\n\n"
        "Para empezar necesito conectarme a tu cuenta de Garmin Connect.\n\n"
        "Envíame tu email de Garmin Connect:"
    )


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not user_manager.user_exists(user_id):
        await update.message.reply_text("Primero regístrate con /start")
        return

    registration_state[user_id] = {"step": "awaiting_profile", "update_only": True}
    await update.message.reply_text(
        "Cuéntame sobre tu entrenamiento en un solo mensaje:\n"
        "- ¿Qué tipo de ejercicio haces?\n"
        "- ¿Con qué frecuencia?\n"
        "- ¿Tienes algún objetivo específico?"
    )


async def handle_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    state = registration_state.get(user_id)
    if not state:
        return

    text = update.message.text
    step = state["step"]
    chat_id = update.effective_chat.id

    if step == "awaiting_email":
        state["email"] = text.strip()
        state["step"] = "awaiting_password"
        await update.message.reply_text(
            "Ahora envíame tu contraseña de Garmin Connect.\n"
            "🔒 Será cifrada y almacenada de forma segura."
        )

    elif step == "awaiting_password":
        state["password"] = text
        try:
            await update.message.delete()
        except Exception:
            pass

        await context.bot.send_message(chat_id=chat_id, text="Verificando conexión con Garmin... ⏳")

        try:
            token_store = user_manager.token_store_path(user_id)
            token_store.parent.mkdir(parents=True, exist_ok=True)
            create_client(state["email"], state["password"], token_store)

            user_manager.create_user(user_id, state["email"], state["password"])

            state["step"] = "awaiting_profile"
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "✅ Conectado a Garmin!\n\n"
                    "Ahora cuéntame sobre tu entrenamiento en un solo mensaje:\n"
                    "- ¿Qué tipo de ejercicio haces? (gym, correr, ambos, etc.)\n"
                    "- ¿Con qué frecuencia?\n"
                    "- ¿Tienes algún objetivo específico?"
                ),
            )
        except Exception as e:
            logger.warning("Garmin auth failed for user %d: %s", user_id, e)
            del registration_state[user_id]
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ No pude conectar con Garmin. Verifica tu email y contraseña e intenta de nuevo con /start",
            )

    elif step == "awaiting_profile":
        user_manager.update_profile(user_id, text)
        del registration_state[user_id]
        if state.get("update_only"):
            await update.message.reply_text("✅ Perfil actualizado.")
        else:
            limit = user_manager.check_rate_limit(user_id)[1]
            await update.message.reply_text(
                f"✅ ¡Listo! Tu perfil está configurado.\n\n"
                f"Ya puedes preguntarme lo que quieras sobre tu entrenamiento.\n"
                f"Tu límite diario es de {limit} mensajes."
            )


PLAN_PROMPT = """Genera un plan de entrenamiento semanal para este usuario.

Basándote en:
1. Sus datos de Garmin (actividades recientes, métricas de recuperación)
2. Su perfil de entrenamiento
3. La conversación reciente (si discutieron preferencias o ajustes)

## Estructura base del cronograma (Lunes a Viernes)

El usuario tiene esta estructura aprobada como punto de partida. Respétala como orden base,
puedes ajustar ejercicios, volúmenes e intensidades según los datos de Garmin, pero NO cambies
la distribución de días ni el split de fuerza/carrera:

| Día       | Fuerza (Gym)                          | Carrera (Cinta/Calle)              |
|-----------|---------------------------------------|------------------------------------|
| Lunes     | EMPUJE (Pecho, Hombro, Tríceps)       | Descanso Activo                    |
| Martes    | Descanso                              | Intervalos (Z4/Z5)                 |
| Miércoles | TRACCIÓN (Espalda, Bíceps)            | Descanso Activo                    |
| Jueves    | Descanso                              | Base Aeróbica (Z2)                 |
| Viernes   | PIERNA (Cuádriceps, Isquios, Glúteo)  | Descanso (Opcional ligero)         |

- Los días de "Descanso Activo" implican caminar al menos 5,000 pasos o movilidad
- Sábado y Domingo son días libres — NO incluirlos en el JSON
- El plan tiene 5 sesiones (una por cada día de lunes a viernes)

IMPORTANTE: Responde con DOS partes separadas:

PARTE 1 — Tu respuesta normal en español explicando el plan al usuario. Sé crítico y específico como siempre.
Presenta el plan en formato de tabla similar a la estructura base.

PARTE 2 — Al final, incluye un bloque JSON con este formato EXACTO (sin comentarios dentro del JSON):

```json
{
  "sessions": [
    {
      "weekday": 0,
      "time": "18:00",
      "duration_minutes": 60,
      "title": "Título corto",
      "description": "Descripción detallada de ejercicios"
    }
  ],
  "weeks": 4
}
```

Reglas para el JSON:
- OBLIGATORIO: Incluir EXACTAMENTE 5 sesiones, una para cada día de lunes (0) a viernes (4)
- weekday: 0=Lunes, 1=Martes, 2=Miércoles, 3=Jueves, 4=Viernes
- Lunes (0): sesión de fuerza EMPUJE + nota de descanso activo
- Martes (1): sesión de carrera intervalos
- Miércoles (2): sesión de fuerza TRACCIÓN + nota de descanso activo
- Jueves (3): sesión de carrera base aeróbica
- Viernes (4): sesión de fuerza PIERNA
- time: hora en formato HH:MM (24h). Gym a las 18:00, carrera según preferencia del usuario
- duration_minutes: duración estimada en minutos
- title: título corto para el calendario (ej: "Empuje — Pecho/Hombro/Tríceps", "Intervalos Z4/Z5")
- description: detalle de ejercicios, series, repeticiones, zonas de FC objetivo
- weeks: número de semanas que dura el plan (típico: 4)
- NO incluir sábado ni domingo
"""


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not user_manager.user_exists(user_id):
        await update.message.reply_text("Primero regístrate con /start")
        return

    if gemini_client is None:
        await update.message.reply_text("Error: bot no configurado.")
        return

    await update.message.reply_text("Generando tu plan semanal... ⏳")

    activities_dir = user_manager.activities_dir(user_id)
    stats_dir = user_manager.stats_dir(user_id)

    run_sync_safe(user_id)
    snapshot = build_context_snapshot(activities_dir, stats_dir, days=90, today=user_today())
    profile = user_manager.get_profile(user_id)
    system_prompt = build_system_prompt(snapshot, profile)

    if user_id not in conversations:
        conversations[user_id] = ConversationHistory(max_messages=20)
    conversation = conversations[user_id]

    conversation.add("user", "/plan — genera mi plan semanal de entrenamiento")

    gemini_messages = []
    for msg in conversation.get_messages():
        role = "model" if msg["role"] == "model" else "user"
        gemini_messages.append({"role": role, "parts": [{"text": msg["content"]}]})

    full_system = system_prompt + "\n\n" + PLAN_PROMPT

    models = ["gemini-3.1-flash-lite", "gemini-3.1-flash", "gemini-2.0-flash"]
    reply = None
    for model_name in models:
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=gemini_messages,
                config={"system_instruction": full_system, "max_output_tokens": 2048},
            )
            reply = response.text
            if reply:
                break
        except Exception as e:
            logger.warning("Model %s failed for plan: %s", model_name, str(e)[:100])
            continue

    if not reply:
        await update.message.reply_text("No pude generar el plan ahora. Intenta de nuevo en unos minutos.")
        return

    plan_data = parse_plan_json(reply)
    display_text = re.sub(r"```json\s*\{.*?\}\s*```", "", reply, flags=re.DOTALL).strip()

    if plan_data and plan_data.get("sessions"):
        plan_data["valid_from"] = plan_start_date()
        plan_data["created_at"] = datetime.now(tz=timezone.utc).isoformat()
        user_manager.save_plan(user_id, plan_data)

        token = user_manager.get_calendar_token(user_id)
        base_url = os.getenv("CALENDAR_BASE_URL", "").rstrip("/")

        if base_url:
            cal_url = f"{base_url}/cal/{token}.ics"
            display_text += (
                f"\n\n📅 Tu calendario está listo:\n\n"
                f"{cal_url}\n\n"
                f"Suscríbete desde iPhone:\n"
                f"Ajustes → Calendario → Cuentas → Añadir cuenta → Otra → "
                f"Añadir calendario suscrito → pega la URL"
            )
        else:
            display_text += "\n\n📅 Plan guardado. El calendario estará disponible cuando se configure la URL pública."

    conversation.add("model", display_text)
    user_manager.increment_usage(user_id)

    if len(display_text) > 4096:
        for i in range(0, len(display_text), 4096):
            await update.message.reply_text(display_text[i : i + 4096])
    else:
        await update.message.reply_text(display_text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id

    if user_id in registration_state:
        await handle_registration(update, context)
        return

    if not user_manager.user_exists(user_id):
        await update.message.reply_text("No estás registrado. Usa /start para comenzar.")
        return

    if gemini_client is None:
        await update.message.reply_text("Error: el bot no está configurado correctamente.")
        return

    allowed, remaining = user_manager.check_rate_limit(user_id)
    if not allowed:
        await update.message.reply_text("Has alcanzado tu límite diario de mensajes. Vuelve mañana.")
        return

    user_text = update.message.text

    activities_dir = user_manager.activities_dir(user_id)
    stats_dir = user_manager.stats_dir(user_id)

    synced = run_sync_safe(user_id)
    snapshot = build_context_snapshot(activities_dir, stats_dir, days=90, today=user_today())

    if not synced:
        snapshot = "⚠️ No se pudieron actualizar los datos, usando última sincronización disponible.\n\n" + snapshot

    profile = user_manager.get_profile(user_id)
    system_prompt = build_system_prompt(snapshot, profile)

    if user_id not in conversations:
        conversations[user_id] = ConversationHistory(max_messages=20)
    conversation = conversations[user_id]

    conversation.add("user", user_text)

    gemini_messages = []
    for msg in conversation.get_messages():
        role = "model" if msg["role"] == "model" else "user"
        gemini_messages.append({"role": role, "parts": [{"text": msg["content"]}]})

    models = ["gemini-3.1-flash-lite", "gemini-3.1-flash", "gemini-2.0-flash"]
    reply = None
    for model_name in models:
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=gemini_messages,
                config={
                    "system_instruction": system_prompt,
                    "max_output_tokens": 1024,
                },
            )
            reply = response.text
            if reply:
                logger.info("Response from %s for user %d (%d chars)", model_name, user_id, len(reply))
                conversation.add("model", reply)
                break
        except Exception as e:
            logger.warning("Model %s failed: %s", model_name, str(e)[:100])
            continue

    if not reply:
        reply = "Todos los modelos están con alta demanda. Intenta de nuevo en unos minutos."
    else:
        user_manager.increment_usage(user_id)
        remaining -= 1

    if 0 < remaining <= 5:
        reply += f"\n\n📊 Te quedan {remaining} mensajes hoy."

    await update.message.reply_text(reply)


def main() -> None:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    api_key = os.getenv("GEMINI_API_KEY")
    encryption_key = os.getenv("ENCRYPTION_KEY")

    if not token:
        print("Error: TELEGRAM_BOT_TOKEN debe estar en .env")
        return
    if not api_key:
        print("Error: GEMINI_API_KEY debe estar en .env")
        return

    global gemini_client, user_manager
    gemini_client = genai.Client(api_key=api_key)
    user_manager = UserManager(encryption_key=encryption_key)

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    cal_port = int(os.getenv("PORT", "8080"))
    start_calendar_server(user_manager, port=cal_port)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("perfil", cmd_profile))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"Bot multi-usuario iniciado. Calendario en puerto {cal_port}. Esperando mensajes...")
    app.run_polling()


if __name__ == "__main__":
    main()
