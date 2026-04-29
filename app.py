from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from datetime import datetime
import json
import requests

app = Flask(__name__)
CORS(app)

CONVERSACIONES_FILE = "conversaciones.json"
NVIDIA_API_KEY = os.getenv("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")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

def cargar_conversaciones():
    if os.path.exists(CONVERSACIONES_FILE):
        with open(CONVERSACIONES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar_conversaciones(conversaciones):
    with open(CONVERSACIONES_FILE, "w", encoding="utf-8") as f:
        json.dump(conversaciones, f, ensure_ascii=False, indent=2)

def llamar_nvidia(messages):
    """Llama a la API de NVIDIA"""
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "mistralai/mistral-medium-3.5-128b",
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.7
    }
    
    try:
        response = requests.post(
            f"{NVIDIA_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error en API: {str(e)}"

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
        
        # Llamar a NVIDIA
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
    