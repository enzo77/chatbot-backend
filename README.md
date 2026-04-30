# Backend — ChANtbot

API REST en Python/Flask que gestiona las conversaciones del chatbot y se comunica con la IA de NVIDIA.

---

## Tecnologías

| Tecnología | Para qué |
|-----------|---------|
| **Python 3.11** | Lenguaje principal |
| **Flask** | Framework web / API REST |
| **PostgreSQL** | Base de datos persistente en la nube |
| **psycopg2** | Conector Python → PostgreSQL |
| **NVIDIA API** | Modelo de IA (Qwen 3.5 122B) |
| **Gunicorn** | Servidor de producción |

---

## Estructura de archivos

```
backend/
├── app.py            # Aplicación principal
├── requirements.txt  # Dependencias Python
├── Procfile          # Comando de arranque para Render
└── runtime.txt       # Versión de Python (3.11.9)
```

---

## Base de datos (PostgreSQL)

### Tabla `conversaciones`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | TEXT | ID único de la conversación |
| created | TEXT | Fecha de creación |
| user_id | TEXT | ID del navegador del usuario |

### Tabla `mensajes`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | SERIAL | Autoincremental |
| conversation_id | TEXT | FK → conversaciones |
| role | TEXT | "user" o "assistant" |
| content | TEXT | Contenido del mensaje |
| timestamp | TEXT | Fecha del mensaje |

---

## Endpoints API

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/chat` | Enviar mensaje (sin streaming) |
| POST | `/api/chat/stream` | Enviar mensaje (con streaming) |
| GET | `/api/conversaciones?user_id=X` | Listar conversaciones del usuario |
| GET | `/api/conversaciones/:id` | Ver una conversación |
| DELETE | `/api/conversaciones/:id` | Eliminar conversación |
| GET | `/api/ping` | Health check (keep-alive) |
| GET | `/api/db` | Ver toda la BD (debug) |

---

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `NVIDIA_API_KEY` | Clave de la API de NVIDIA |
| `DATABASE_URL` | URL de conexión a PostgreSQL |
| `PORT` | Puerto del servidor (por defecto 10000) |
| `PYTHON_VERSION` | Versión de Python (3.11.9) |

---

## Arrancar en local

```bash
pip install -r requirements.txt
export NVIDIA_API_KEY=tu_clave
export DATABASE_URL=tu_url_postgresql
python app.py
```
