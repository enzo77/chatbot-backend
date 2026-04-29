from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from openai import OpenAI
from datetime import datetime
import json

app = Flask(__name__)
CORS(app)

api_key = os.getenv("NVIDIA_API_KEY") or "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"

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key
)

CONVERSACIONES_FILE = "conversaciones.json"

def cargar_conversaciones():
    """Carga todas las conversaciones guardadas"""
    if os.path.exists(CONVERSACIONES_FILE):
        with open(CONVERSACIONES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar_conversaciones(conversaciones):
    """Guarda las conversaciones en archivo"""
    with open(CONVERSACIONES_FILE, "w", encoding="utf-8") as f:
        json.dump(conversaciones, f, ensure_ascii=False, indent=2)

@app.route("/api/chat", methods=["POST"])
def chat():
    """Endpoint para enviar mensaje y obtener respuesta"""
    try:
        data = request.json
        user_message = data.get("message")
        conversation_id = data.get("conversation_id")
        
        if not user_message:
            return jsonify({"error": "Mensaje vacío"}), 400
        
        # Cargar conversaciones
        conversaciones = cargar_conversaciones()
        
        # Crear o cargar conversación
        if conversation_id not in conversaciones:
            conversaciones[conversation_id] = {
                "id": conversation_id,
                "created": datetime.now().isoformat(),
                "messages": []
            }
        
        # Preparar historial para la API
        historial_api = []
        for msg in conversaciones[conversation_id]["messages"]:
            historial_api.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # Agregar nuevo mensaje del usuario
        historial_api.append({"role": "user", "content": user_message})
        
        # Llamar a NVIDIA
        completion = client.chat.completions.create(
            model="minimaxai/minimax-m2.7",
            messages=historial_api,
            max_tokens=300,
        )
        
        ai_response = completion.choices[0].message.content
        
        # Guardar en historial
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
    """Obtiene todas las conversaciones"""
    conversaciones = cargar_conversaciones()
    # Devolver solo ID y primer mensaje
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
    """Obtiene una conversación específica"""
    conversaciones = cargar_conversaciones()
    if conversation_id in conversaciones:
        return jsonify(conversaciones[conversation_id])
    return jsonify({"error": "Conversación no encontrada"}), 404

@app.route("/api/conversaciones/<conversation_id>", methods=["DELETE"])
def eliminar_conversacion(conversation_id):
    """Elimina una conversación"""
    conversaciones = cargar_conversaciones()
    if conversation_id in conversaciones:
        del conversaciones[conversation_id]
        guardar_conversaciones(conversaciones)
        return jsonify({"success": True})
    return jsonify({"error": "Conversación no encontrada"}), 404

if __name__ == "__main__":
    app.run(debug=True, port=5000)