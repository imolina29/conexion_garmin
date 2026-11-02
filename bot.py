#!/usr/bin/env python3
"""Telegram bot that acts as a Garmin training coach powered by Claude."""

import logging
import os
from datetime import date, timedelta
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from analysis import build_context_snapshot
from sync import create_client, sync_activities, sync_daily_stats, save_last_sync

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
ACTIVITIES_DIR = RAW_DIR / "activities"
STATS_DIR = RAW_DIR / "stats"

logger = logging.getLogger(__name__)

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


def build_system_prompt(garmin_snapshot: str) -> str:
    return f"""Eres un coach de entrenamiento personal inteligente que analiza datos reales de un reloj Garmin.

Tu personalidad:
- Hablas en español, claro y directo
- Eres educativo: no solo das números, explicas qué significan y por qué importan
- Eres motivador pero honesto — si algo necesita atención, lo dices
- Cuando el usuario pregunta algo, usas SUS datos para responder, no genéricos
- Usas comparaciones concretas ("tu ritmo mejoró 30 seg/km en 2 semanas")
- Si detectas algo preocupante (HRV muy bajo, Training Readiness <20 varios días), lo mencionas

{METRIC_REFERENCE}

## Datos actuales del usuario

{garmin_snapshot}

## Instrucciones
- Responde basándote en los datos reales mostrados arriba
- Si el usuario pregunta por una métrica, explica qué es Y qué significa su valor específico
- Detecta tendencias: ¿está mejorando, estancado, o empeorando?
- Si ves monotonía en entrenamientos (mismo tipo/ritmo/duración repetido), sugiérelo
- Si hay señales de sobreentrenamiento (HRV bajo + Training Readiness bajo + FC reposo alta), alerta
- Mantén respuestas concisas pero completas — no más de 300 palabras por respuesta
- No inventes datos que no estén en el snapshot"""


class ConversationHistory:
    def __init__(self, max_messages: int = 20):
        self._messages: list[dict] = []
        self._max = max_messages

    def add(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})
        if len(self._messages) > self._max:
            self._messages = self._messages[-self._max:]

    def get_messages(self) -> list[dict]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()


conversation = ConversationHistory(max_messages=20)
claude_client: anthropic.Anthropic | None = None


def run_sync_safe() -> bool:
    try:
        client = create_client()
        today = date.today().isoformat()
        start = (date.today() - timedelta(days=2)).isoformat()
        sync_activities(client, start, today)
        sync_daily_stats(client, start, today)
        save_last_sync()
        return True
    except Exception as e:
        logger.warning("Sync failed: %s", e)
        return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_text = update.message.text

    synced = run_sync_safe()
    snapshot = build_context_snapshot(ACTIVITIES_DIR, STATS_DIR, days=30)

    if not synced:
        snapshot = "⚠️ Nota: no se pudieron actualizar los datos, usando última sincronización disponible.\n\n" + snapshot

    system_prompt = build_system_prompt(snapshot)

    conversation.add("user", user_text)
    messages = conversation.get_messages()

    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        reply = response.content[0].text
    except Exception as e:
        logger.error("Claude API error: %s", e)
        reply = "Hubo un error procesando tu mensaje, intenta de nuevo."

    conversation.add("assistant", reply)
    await update.message.reply_text(reply)


def main() -> None:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not token:
        print("Error: TELEGRAM_BOT_TOKEN debe estar en .env")
        return
    if not api_key:
        print("Error: ANTHROPIC_API_KEY debe estar en .env")
        return

    global claude_client
    claude_client = anthropic.Anthropic(api_key=api_key)

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot iniciado. Esperando mensajes...")
    app.run_polling()


if __name__ == "__main__":
    main()
