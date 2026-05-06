from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import os
from datetime import datetime
import json
import requests
import psycopg2
import psycopg2.extras

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversaciones (
            id TEXT PRIMARY KEY,
            created TEXT NOT NULL,
            user_id TEXT DEFAULT 'default'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mensajes (
            id SERIAL PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversaciones(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    # migración: agrega user_id si la tabla ya existía sin esa columna
    cur.execute("""
        ALTER TABLE conversaciones ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT 'default'
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()
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

def db_crear_conversacion(conversation_id, user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO conversaciones (id, created, user_id) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
        (conversation_id, datetime.now().isoformat(), user_id)
    )
    conn.commit()
    cur.close()
    conn.close()

def db_agregar_mensaje(conversation_id, role, content):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO mensajes (conversation_id, role, content, timestamp) VALUES (%s, %s, %s, %s)",
        (conversation_id, role, content, datetime.now().isoformat())
    )
    conn.commit()
    cur.close()
    conn.close()

def db_obtener_conversacion(conversation_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id, created FROM conversaciones WHERE id = %s", (conversation_id,)
    )
    conv = cur.fetchone()
    if not conv:
        cur.close()
        conn.close()
        return None
    cur.execute(
        "SELECT role, content, timestamp FROM mensajes WHERE conversation_id = %s ORDER BY id",
        (conversation_id,)
    )
    mensajes = cur.fetchall()
    cur.close()
    conn.close()
    return {
        "id": conv["id"],
        "created": conv["created"],
        "messages": [dict(m) for m in mensajes]
    }

def db_obtener_todas(user_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id, created FROM conversaciones WHERE user_id = %s ORDER BY created DESC",
        (user_id,)
    )
    convs = cur.fetchall()
    result = []
    for conv in convs:
        cur.execute(
            "SELECT content FROM mensajes WHERE conversation_id = %s ORDER BY id LIMIT 1",
            (conv["id"],)
        )
        primer_msg = cur.fetchone()
        result.append({
            "id": conv["id"],
            "created": conv["created"],
            "preview": (primer_msg["content"][:50] + "...") if primer_msg else "Sin mensajes"
        })
    cur.close()
    conn.close()
    return result

def db_eliminar_conversacion(conversation_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM mensajes WHERE conversation_id = %s", (conversation_id,))
    cur.execute("DELETE FROM conversaciones WHERE id = %s", (conversation_id,))
    conn.commit()
    cur.close()
    conn.close()

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

    user_id = data.get("user_id", "default")
    db_crear_conversacion(conversation_id, user_id)
    conv = db_obtener_conversacion(conversation_id)

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

        db_agregar_mensaje(conversation_id, "user", user_message)
        db_agregar_mensaje(conversation_id, "assistant", full_response)
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
        
        user_id = data.get("user_id", "default")
        db_crear_conversacion(conversation_id, user_id)
        conv = db_obtener_conversacion(conversation_id)

        historial_api = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in conv["messages"]
        ]
        historial_api.append({"role": "user", "content": user_message})

        ai_response = llamar_nvidia(historial_api)

        db_agregar_mensaje(conversation_id, "user", user_message)
        db_agregar_mensaje(conversation_id, "assistant", ai_response)
        
        return jsonify({
            "response": ai_response,
            "conversation_id": conversation_id
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/conversaciones", methods=["GET"])
def obtener_conversaciones():
    user_id = request.args.get("user_id", "default")
    return jsonify(db_obtener_todas(user_id))

@app.route("/api/conversaciones/<conversation_id>", methods=["GET"])
def obtener_conversacion(conversation_id):
    conv = db_obtener_conversacion(conversation_id)
    if conv:
        return jsonify(conv)
    return jsonify({"error": "Conversación no encontrada"}), 404

@app.route("/api/conversaciones/<conversation_id>", methods=["DELETE"])
def eliminar_conversacion(conversation_id):
    conv = db_obtener_conversacion(conversation_id)
    if conv:
        db_eliminar_conversacion(conversation_id)
        return jsonify({"success": True})
    return jsonify({"error": "Conversación no encontrada"}), 404

@app.route("/api/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok"})

@app.route("/api/db", methods=["GET"])
def ver_db():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, created FROM conversaciones ORDER BY created DESC")
    convs = cur.fetchall()
    resultado = []
    for conv in convs:
        cur.execute(
            "SELECT role, content, timestamp FROM mensajes WHERE conversation_id = %s ORDER BY id",
            (conv["id"],)
        )
        mensajes = cur.fetchall()
        resultado.append({
            "id": conv["id"],
            "created": conv["created"],
            "total_mensajes": len(mensajes),
            "mensajes": [dict(m) for m in mensajes]
        })
    cur.close()
    conn.close()
    return jsonify({
        "total_conversaciones": len(resultado),
        "conversaciones": resultado
    })

@app.route("/api/mensajes/recientes", methods=["GET"])
def mensajes_recientes():
    limite = request.args.get("n", 20, type=int)
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM mensajes ORDER BY id DESC LIMIT %s",
        (limite,)
    )
    mensajes = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(m) for m in mensajes])

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)