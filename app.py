from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import os
from datetime import datetime
import json
import requests

app = Flask(__name__)
CORS(app)

CONVERSACIONES_FILE = "conversaciones.json"
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

SYSTEM_PROMPT = (
    "Eres el asistente virtual de Narcóticos Anónimos (NA). "
    "Responde siempre en español, de forma cálida, directa y breve: máximo 3 oraciones salvo que el usuario pida una explicación detallada. "
    "Evita repetir lo que ya dijiste en la conversación. "
    "Si alguien está en crisis o con riesgo inmediato, recomiéndales llamar a su padrino/madrina o asistir a la reunión más cercana. "
    "No des consejos médicos ni diagnósticos."
)

def con_sistema(historial):
    return [{"role": "system", "content": SYSTEM_PROMPT}] + historial

def cargar_conversaciones():
    if os.path.exists(CONVERSACIONES_FILE):
        with open(CONVERSACIONES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar_conversaciones(conversaciones):
    with open(CONVERSACIONES_FILE, "w", encoding="utf-8") as f:
        json.dump(conversaciones, f, ensure_ascii=False, indent=2)

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

@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    data = request.json
    user_message = data.get("message")
    conversation_id = data.get("conversation_id")

    if not user_message or not conversation_id:
        return jsonify({"error": "Datos inválidos"}), 400

    conversaciones = cargar_conversaciones()
    if conversation_id not in conversaciones:
        conversaciones[conversation_id] = {
            "id": conversation_id,
            "created": datetime.now().isoformat(),
            "messages": []
        }

    historial_api = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in conversaciones[conversation_id]["messages"]
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

        convs = cargar_conversaciones()
        if conversation_id not in convs:
            convs[conversation_id] = {
                "id": conversation_id,
                "created": datetime.now().isoformat(),
                "messages": []
            }
        convs[conversation_id]["messages"].append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now().isoformat()
        })
        convs[conversation_id]["messages"].append({
            "role": "assistant",
            "content": full_response,
            "timestamp": datetime.now().isoformat()
        })
        guardar_conversaciones(convs)
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_message = data.get("message")
        conversation_id = data.get("conversation_id")
        
        if not user_message:
            return jsonify({"error": "Mensaje vacío"}), 400
        
        conversaciones = cargar_conversaciones()
        
        if conversation_id not in conversaciones:
            conversaciones[conversation_id] = {
                "id": conversation_id,
                "created": datetime.now().isoformat(),
                "messages": []
            }
        
        historial_api = []
        for msg in conversaciones[conversation_id]["messages"]:
            historial_api.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        historial_api.append({"role": "user", "content": user_message})
        
        # Llamar a NVIDIA con Qwen
        ai_response = llamar_nvidia(historial_api)
        
        conversaciones[conversation_id]["messages"].append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now().isoformat()
        })
        conversaciones[conversation_id]["messages"].append({
            "role": "assistant",
            "content": ai_response,
            "timestamp": datetime.now().isoformat()
        })
        
        guardar_conversaciones(conversaciones)
        
        return jsonify({
            "response": ai_response,
            "conversation_id": conversation_id
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/conversaciones", methods=["GET"])
def obtener_conversaciones():
    conversaciones = cargar_conversaciones()
    lista = []
    for conv_id, conv in conversaciones.items():
        primer_mensaje = conv["messages"][0]["content"] if conv["messages"] else "Sin mensajes"
        lista.append({
            "id": conv_id,
            "created": conv["created"],
            "preview": primer_mensaje[:50] + "..."
        })
    return jsonify(lista)

@app.route("/api/conversaciones/<conversation_id>", methods=["GET"])
def obtener_conversacion(conversation_id):
    conversaciones = cargar_conversaciones()
    if conversation_id in conversaciones:
        return jsonify(conversaciones[conversation_id])
    return jsonify({"error": "Conversación no encontrada"}), 404

@app.route("/api/conversaciones/<conversation_id>", methods=["DELETE"])
def eliminar_conversacion(conversation_id):
    conversaciones = cargar_conversaciones()
    if conversation_id in conversaciones:
        del conversaciones[conversation_id]
        guardar_conversaciones(conversaciones)
        return jsonify({"success": True})
    return jsonify({"error": "Conversación no encontrada"}), 404

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)