# Garmin Coach — Bot de Telegram con IA

## Intención

Un bot de Telegram que actúa como coach personal inteligente: lee los
datos de Garmin Connect del usuario, los interpreta, y responde preguntas
en español y lenguaje natural. El usuario lo abre después de entrenar
y puede preguntar lo que quiera sobre su rendimiento, métricas, tendencias
y recuperación.

## Por qué

La app de Garmin muestra números sin explicar qué significan ni cómo se
relacionan entre sí. El usuario no sabe si está mejorando, si sus
entrenamientos son monótonos, o si debería descansar. Quiere un análisis
personalizado accesible desde el teléfono, sin abrir laptop.

## Objetivos

1. **Conversacional:** El usuario pregunta en lenguaje natural y recibe
   respuestas claras basadas en sus datos reales.
2. **Educativo:** Cada métrica se explica en contexto — no solo "tu HRV
   es 45" sino qué significa eso para él y qué hacer al respecto.
3. **Analítico:** Detectar tendencias (mejora/estancamiento en ritmo,
   fuerza), monotonía en entrenamientos, y señales de sobreentrenamiento
   o falta de descanso.
4. **Accesible:** Telegram desde el teléfono, sin fricción, disponible
   post-entrenamiento.

## No-objetivos

- No es un plan de entrenamiento prescriptivo (no genera rutinas).
- No reemplaza a un médico o entrenador certificado.
- No necesita interfaz web en esta fase.
- No necesita funcionar para múltiples usuarios — es personal.

## Anti-objetivos (qué haría esto un fracaso)

- Respuestas genéricas que no usen los datos reales del usuario.
- Que sea complicado de usar o requiera comandos específicos.
- Que el usuario tenga que sincronizar datos manualmente cada vez.

## Contexto actual

- `sync.py` ya descarga actividades y stats diarios de Garmin Connect
  a JSON local (actividades, sueño, HRV, training readiness, FC reposo,
  pasos).
- Los datos cubren: running (exterior y cinta), strength training,
  stats diarios.
- Stack actual: Python 3.13, garminconnect, pandas.
- El usuario tiene credenciales de Garmin configuradas en `.env`.

## Métricas disponibles en los datos

### Por actividad
- Tipo (running, treadmill, strength), duración, distancia, calorías
- FC promedio, FC máxima, zonas de FC
- Ritmo (pace) y splits para running
- Series y ejercicios para fuerza
- Laps

### Diarias
- FC en reposo
- Pasos
- Sleep score y datos de sueño
- Training Readiness score
- HRV

## Arquitectura — decisiones del usuario

- **Interfaz:** Bot de Telegram (gratuito, accesible desde teléfono)
- **Idioma:** Español
- **LLM:** Claude API como cerebro para interpretar datos y conversar
- **Sync:** Automático (el bot sincroniza antes de responder, o en
  intervalo)
- **Despliegue:** Un solo usuario (el dueño)

## Arquitectura — decisiones del builder

- Cómo estructurar el contexto de datos para el LLM (resúmenes vs raw)
- Framework del bot de Telegram (python-telegram-bot, aiogram, etc.)
- Cómo manejar el sync automático (pre-respuesta, cron, o ambos)
- Almacenamiento de historial de conversación
- Cómo y dónde correr el bot (local, VPS, etc.)

## Fases

### Fase 1 — Motor de análisis + explicación de métricas
Módulo Python que lee los JSON descargados, calcula tendencias, compara
períodos, detecta monotonía, y genera texto interpretativo para cada
métrica.

### Fase 2 — Bot de Telegram con LLM
Bot que recibe mensajes del usuario, construye contexto con los datos
de Garmin, lo envía a Claude, y devuelve la respuesta.

### Fase 3 — Sync automático
El bot sincroniza datos de Garmin automáticamente antes de responder
o en intervalos regulares, sin intervención manual.

### Fase 4 — Dashboard web (opcional, futuro)
Visualización de tendencias en gráficas accesibles desde el navegador
del teléfono.
