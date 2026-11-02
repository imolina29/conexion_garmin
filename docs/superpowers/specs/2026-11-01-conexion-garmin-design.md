# Conexión Garmin — Diseño del Proyecto

## Intención

Crear un entorno de entrenador personal en terminal que se alimente de
datos reales del Garmin Forerunner 970 de Iván. Cada vez que abra el
proyecto en Claude Code, puede conversar sobre sus entrenamientos,
recibir análisis de métricas, sugerencias de mejora y planes de
alimentación — todo basado en datos actualizados de Garmin Connect.

## Por qué

Iván entrena fuerza y carrera regularmente. Su reloj captura datos
detallados pero revisarlos en la app de Garmin no le da recomendaciones
personalizadas ni planes de acción. Quiere un coach que conozca sus
números y le diga qué hacer, qué comer, y cómo mejorar.

## Perfil del atleta

- **Edad:** 33 años (cumple 34 pronto)
- **Peso:** 94 kg
- **Estatura:** 193 cm
- **IMC estimado:** ~25.2
- **Entrenamiento:** Tarde, ~5 días/semana
- **Fuerza:** Pierna, pecho, espalda, brazo, hombro (split por sesión)
- **Carrera:** 3-4 km en caminadora, 2-3 veces/semana
- **Benchmark actual:** 4 km en ~30 min
- **Restricciones alimentarias:** Ninguna

## Objetivos

1. **Ganar masa muscular** — prioridad principal
2. **Correr 5 km con buen tiempo** — objetivo secundario de cardio
3. **Tener recomendaciones de alimentación** ricas en proteína, organizadas por día

## No-objetivos

- No es una app web ni un dashboard visual
- No es un sistema de notificaciones push
- No reemplaza al médico — no diagnostica lesiones ni condiciones

## Anti-objetivos (qué haría que esto sea un fracaso)

- Que la sincronización sea tan complicada que Iván deje de usarla
- Que las recomendaciones sean genéricas y no usen sus datos reales
- Que requiera pasos manuales cada vez que quiera hablar de sus entrenamientos

## Arquitectura

```
conexion_Garmin/
├── CLAUDE.md                  # Contexto de entrenador personal
├── .env                       # Credenciales Garmin (gitignored)
├── requirements.txt           # Dependencias Python
├── sync.py                    # Script principal de sincronización
├── analyze.py                 # Procesamiento de datos crudos → resúmenes
├── data/
│   ├── raw/                   # JSON crudo de Garmin Connect
│   │   ├── activities/        # Una actividad por archivo
│   │   └── stats/             # Estadísticas diarias (peso, HR reposo, etc.)
│   ├── summaries/
│   │   ├── weekly_summary.json    # Resumen semanal actual
│   │   ├── running_progress.json  # Progreso de carrera
│   │   └── strength_log.json      # Registro de fuerza
│   └── profile.json           # Perfil del atleta (datos fijos + calculados)
├── docs/
│   └── superpowers/specs/     # Este documento
└── .gitignore
```

## Piezas técnicas

### 1. Sincronización (sync.py)

Usa la librería `garminconnect` v0.3.20 para conectar con la API de
Garmin Connect.

**Datos que se extraen:**
- Actividades recientes (últimos 30 días por defecto, configurable)
  - Tipo (carrera, fuerza, etc.)
  - Duración, distancia, calorías
  - Frecuencia cardíaca (promedio, máxima, zonas)
  - Para carrera: ritmo, cadencia, splits por km
  - Para fuerza: sets, ejercicios (si están disponibles en la API)
- Estadísticas del día: peso (si registra en Garmin), HR en reposo, estrés, sueño
- Resumen de últimas semanas de entrenamiento

**Autenticación:**
- Email y contraseña de Garmin en `.env`
- Manejo de token/session para no pedir credenciales cada vez
- Sin MFA — Iván no tiene doble factor activado, así que login directo con email/password

**Uso:**
```bash
python3 sync.py              # Sincroniza últimos 30 días
python3 sync.py --days 90    # Sincroniza últimos 90 días
python3 sync.py --today      # Solo hoy
```

### 2. Análisis (analyze.py)

Procesa los JSON crudos y genera resúmenes legibles:

- **weekly_summary.json:** Total de sesiones, volumen de fuerza, km corridos, tiempo total, HR promedio, tendencias vs semana anterior
- **running_progress.json:** Evolución de ritmo por km, distancia máxima, mejor tiempo en 1km/3km/4km/5km, zonas de HR en carrera
- **strength_log.json:** Frecuencia por grupo muscular, volumen por sesión, tendencias
- **profile.json:** Datos fijos del atleta + métricas calculadas (TDEE estimado, requerimiento proteico, zonas de HR)

**Uso:**
```bash
python3 analyze.py           # Regenera todos los resúmenes
```

### 3. CLAUDE.md — El entrenador

Configura el contexto para que cada conversación en Claude Code arranque
con la personalidad de entrenador personal y acceso a los datos:

- Perfil completo del atleta
- Objetivos y prioridades
- Instrucciones para leer los archivos de data/summaries/ al inicio
- Guías de nutrición: cálculo de macros, ~1.8-2g proteína/kg, distribución de comidas
- Protocolos de sugerencia: cómo analizar una carrera, cómo sugerir split de fuerza, cuándo sugerir descanso
- Recetas y opciones de comidas organizables por día

### 4. Dependencias (requirements.txt)

```
garminconnect>=0.3.20
pandas>=2.0
python-dotenv>=1.0
```

## Flujo de uso

1. **Primera vez:** Iván corre `pip3 install -r requirements.txt`, crea `.env` con sus credenciales, y corre `python3 sync.py --days 90` para traer historial
2. **Uso regular:** Un hook de Claude Code (`ConversationStart`) corre automáticamente `sync.py --new` al abrir el proyecto — detecta si hay actividades nuevas desde la última sincronización y las descarga + analiza sin intervención manual
3. **Conversación:** Abre Claude Code en el directorio, pregunta lo que quiera — el CLAUDE.md le dice a Claude que lea los resúmenes bajo demanda con la herramienta Read y actúe como entrenador

## Decisiones del constructor

- **Datos en CLAUDE.md:** El CLAUDE.md NO incluye datos inline. Contiene instrucciones para que Claude use Read sobre `data/summaries/` cuando necesite métricas. Así el archivo se mantiene limpio y los datos siempre están frescos.
- **Datos crudos en git:** `data/raw/` va en `.gitignore`. Son cache local — se regeneran con `sync.py --days 90`. Los resúmenes (`data/summaries/`) sí se versionan para tener historial.
- **Nombres de ejercicios:** El modo "Fuerza > Libre" no da nombres confiables de ejercicios. El coach preguntará qué grupo muscular trabajó cuando lo necesite, y puede inferir del patrón semanal.

## Restricciones

- Garmin Connect no tiene API pública oficial — `garminconnect` es una librería no-oficial que hace scraping de la API interna. Puede romperse si Garmin cambia endpoints
- Los datos de fuerza vienen del modo "Fuerza > Libre" del Forerunner 970 — el reloj auto-detecta sets y reps pero no siempre identifica el ejercicio. Tendremos: número de sets, reps por set, duración por set, descanso entre sets, HR durante el ejercicio. No tendremos nombres de ejercicios confiables — el coach puede preguntar qué grupo muscular trabajó
- Las credenciales se guardan localmente en `.env`, nunca se commitean

## Lo que queda para el constructor

- Implementar sync.py con manejo robusto de errores y reintentos
- Implementar analyze.py con los cálculos de resúmenes
- Escribir el CLAUDE.md con el prompt de entrenador completo
- Crear profile.json con cálculos de TDEE y macros
- Testear el flujo completo de sincronización → análisis → conversación
