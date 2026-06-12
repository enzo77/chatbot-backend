from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()
from datetime import datetime
import json
import requests

app = FastAPI(title="ChANtbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

SYSTEM_PROMPT = (
    "Eres el asistente virtual de Narcóticos Anónimos (NA). "
    "Responde siempre en español, de forma cálida, directa y breve: máximo 3 oraciones salvo que el usuario pida una explicación detallada. "
    "Evita repetir lo que ya dijiste en la conversación. "
    "Si alguien está en crisis o con riesgo inmediato, recomiéndales llamar a su padrino/madrina o asistir a la reunión más cercana. "
    "No des consejos médicos ni diagnósticos."
)

# Almacenamiento en memoria: se pierde cuando el servidor se reinicia.
# Requiere correr con UN solo worker (cada proceso tendría su propia copia).
# Estructura: {conversation_id: {"id", "created", "user_id", "messages": [...]}}
conversaciones = {}


class ChatRequest(BaseModel):
    message: str | None = None
    conversation_id: str | None = None
    user_id: str = "default"


def con_sistema(historial):
    return [{"role": "system", "content": SYSTEM_PROMPT}] + historial


def mem_crear_conversacion(conversation_id, user_id):
    if conversation_id not in conversaciones:
        conversaciones[conversation_id] = {
            "id": conversation_id,
            "created": datetime.now().isoformat(),
            "user_id": user_id,
            "messages": []
        }


def mem_agregar_mensaje(conversation_id, role, content):
    conversaciones[conversation_id]["messages"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })


def mem_obtener_conversacion(conversation_id):
    conv = conversaciones.get(conversation_id)
    if not conv:
        return None
    return {
        "id": conv["id"],
        "created": conv["created"],
        "messages": conv["messages"]
    }


def mem_obtener_todas(user_id):
    result = []
    for conv in conversaciones.values():
        if conv["user_id"] != user_id:
            continue
        primer_msg = conv["messages"][0]["content"] if conv["messages"] else None
        result.append({
            "id": conv["id"],
            "created": conv["created"],
            "preview": (primer_msg[:50] + "...") if primer_msg else "Sin mensajes"
        })
    result.sort(key=lambda c: c["created"], reverse=True)
    return result


def mem_eliminar_conversacion(conversation_id):
    conversaciones.pop(conversation_id, None)


def llamar_nvidia(messages):
    """Llama a la API de NVIDIA con modelo Qwen 3.5"""
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "qwen/qwen3.5-122b-a10b",
        "messages": con_sistema(messages),
        "max_tokens": 512,
        "temperature": 0.60,
        "top_p": 0.95,
        "chat_template_kwargs": {"enable_thinking": False}
    }

    try:
        response = requests.post(
            f"{NVIDIA_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error en API: {str(e)}"


@app.post("/api/chat/stream")
def chat_stream(data: ChatRequest):
    user_message = data.message
    conversation_id = data.conversation_id

    if not user_message or not conversation_id:
        return JSONResponse({"error": "Datos inválidos"}, status_code=400)

    mem_crear_conversacion(conversation_id, data.user_id)
    conv = mem_obtener_conversacion(conversation_id)

    historial_api = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in conv["messages"]
    ]
    historial_api.append({"role": "user", "content": user_message})

    def generate():
        full_response = ""
        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "qwen/qwen3.5-122b-a10b",
            "messages": con_sistema(historial_api),
            "max_tokens": 512,
            "temperature": 0.60,
            "top_p": 0.95,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": False}
        }

        try:
            with requests.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=60
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if not decoded.startswith("data: "):
                        continue
                    chunk_str = decoded[6:]
                    if chunk_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(chunk_str)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            full_response += delta
                            yield f"data: {json.dumps({'content': delta})}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        mem_agregar_mensaje(conversation_id, "user", user_message)
        mem_agregar_mensaje(conversation_id, "assistant", full_response)
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.post("/api/chat")
def chat(data: ChatRequest):
    try:
        user_message = data.message
        conversation_id = data.conversation_id

        if not user_message:
            return JSONResponse({"error": "Mensaje vacío"}, status_code=400)

        mem_crear_conversacion(conversation_id, data.user_id)
        conv = mem_obtener_conversacion(conversation_id)

        historial_api = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in conv["messages"]
        ]
        historial_api.append({"role": "user", "content": user_message})

        ai_response = llamar_nvidia(historial_api)

        mem_agregar_mensaje(conversation_id, "user", user_message)
        mem_agregar_mensaje(conversation_id, "assistant", ai_response)

        return {
            "response": ai_response,
            "conversation_id": conversation_id
        }

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/conversaciones")
def obtener_conversaciones(user_id: str = "default"):
    return mem_obtener_todas(user_id)


@app.get("/api/conversaciones/{conversation_id}")
def obtener_conversacion(conversation_id: str):
    conv = mem_obtener_conversacion(conversation_id)
    if conv:
        return conv
    return JSONResponse({"error": "Conversación no encontrada"}, status_code=404)


@app.delete("/api/conversaciones/{conversation_id}")
def eliminar_conversacion(conversation_id: str):
    if conversation_id in conversaciones:
        mem_eliminar_conversacion(conversation_id)
        return {"success": True}
    return JSONResponse({"error": "Conversación no encontrada"}, status_code=404)


@app.get("/api/ping")
def ping():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
