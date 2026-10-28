import sys
import os
import json
import logging
import requests
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.stream_client import StreamClient
from database.db_client import DBClient
from config.config import Config
from database.repositories.conversation_repo import ConversationRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ProfilingWorker")

PROFILING_SYSTEM_PROMPT = """
Eres un analista de datos y perfilamiento de clientes para JPM (Asesoría en Pensiones IMSS México).
Tu tarea es leer el historial de chat entre el usuario y la IA (Samanta) y extraer los datos clave del cliente en un formato JSON estricto.

Debes extraer los siguientes campos exactos:
- "nss": (string) El Número de Seguridad Social de 11 dígitos, si lo dio. Si no, null.
- "edad": (number) La edad actual del cliente, si la mencionó. Si no, null.
- "semanas_cotizadas": (number) Las semanas cotizadas que dijo tener, si las mencionó. Si no, null.
- "salario_mensual": (number) Su salario mensual o cotización registrada, si la mencionó. Extrae solo el número. Si no, null.
- "regimen_ley": (string) "Ley 73", "Ley 97" o null si aún no se sabe. REGLA ESTRICTA DE NSS: Toma los dígitos 3 y 4 del NSS. Si son 96 o menores (ej. 85, 92), es "Ley 73". Si son 97, 98, 99 o CUALQUIER NÚMERO DE LOS 2000s (ej. 00, 07, 15, 23), es "Ley 97".
- "resumen_narrativo": (string) Un resumen de 1-2 oraciones sobre su situación o inquietud principal.

REGLA DE ORO: 
1. Devuelve ÚNICAMENTE un objeto JSON válido.
2. NO incluyas markdown (como ```json).
3. NO incluyas saludos ni explicaciones, solo el raw JSON.
"""

def call_llm_json(system_prompt, user_prompt):
    """Wrapper to call OpenAI, Gemini, or Ollama and force JSON output"""
    provider = Config.get_active_provider()
    if provider == "openai":
        res = call_llm_openai_json(system_prompt, user_prompt)
        if res is not None:
            return res
        return call_llm_ollama_json(system_prompt, user_prompt)
    elif provider == "gemini":
        res = call_llm_gemini_json(system_prompt, user_prompt)
        if res is not None:
            return res
        return call_llm_ollama_json(system_prompt, user_prompt)
    else:
        return call_llm_ollama_json(system_prompt, user_prompt)

def call_llm_openai_json(system_prompt, user_prompt):
    if not Config.OPENAI_API_KEY:
        return None
    base_url = (Config.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip('/')
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    payload = {
        "model": Config.OPENAI_MODEL or "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "{}").strip()
        else:
            logger.error(f"OpenAI JSON Error {resp.status_code}: {resp.text}")
            return None
    except Exception as e:
        logger.error(f"Failed OpenAI JSON: {e}")
        return None

def call_llm_gemini_json(system_prompt, user_prompt):
    if not Config.GEMINI_API_KEY:
        return None
    gemini_base = (Config.GEMINI_BASE_URL or "https://generativelanguage.googleapis.com/v1beta").rstrip('/')
    model_name = Config.GEMINI_MODEL or "gemini-2.5-flash"
    url = f"{gemini_base}/models/{model_name}:generateContent?key={Config.GEMINI_API_KEY}"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts":[{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
        else:
            logger.error(f"Gemini JSON Error {resp.status_code}: {resp.text}")
            return None
    except Exception as e:
        logger.error(f"Failed Gemini JSON: {e}")
        return None

def call_llm_ollama_json(system_prompt, user_prompt):
    try:
        resp = requests.post(
            Config.OLLAMA_URL,
            json={
                "model": Config.OLLAMA_MODEL, 
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1}
            },
            timeout=120
        )
        return resp.json().get("response", "{}")
    except Exception as e:
        logger.error(f"Failed Ollama JSON: {e}")
        return "{}"

def run():
    client = StreamClient()
    pg_db = DBClient()
    mongo_conv_repo = ConversationRepository()
    
    stream_in = "message.processed"
    group_name = "profiling-group"
    consumer_name = "worker-1"
    
    # id="$" only processes NEW messages from now on
    try:
        client.redis.xgroup_create(stream_in, group_name, id="$", mkstream=True)
    except:
        pass
    
    logger.info(f"Profiling Agent Worker started. Monitoring {stream_in}...")
    
    while True:
        results = client.read_group({stream_in: ">"}, group_name, consumer_name)
        if not results:
            continue
            
        for stream_name, msgs in results:
            for msg_id, data in msgs:
                try:
                    payload = json.loads(data["payload"])
                    conv_key = f"{payload['channel']}:{payload['actor_id']}"
                    conv_id = payload["conversation_id"] # UUID format
                    
                    # Get recent history
                    history = pg_db.get_history(conv_id, limit=20)
                    
                    if len(history) < 2:
                        client.ack(stream_in, group_name, msg_id)
                        continue

                    context = ""
                    for h in reversed(history):
                        direction = h.get("direction")
                        content = h.get("content", {})
                        role = "Usuario" if direction == "inbound" else "Samanta"
                        text = content.get("body", "")
                        context += f"{role}: {text}\n"

                    user_prompt = f"Extrae el perfil basado en esta conversación:\n\n{context}"
                    
                    logger.info(f"Running incremental profiling for {conv_key}...")
                    json_str = call_llm_json(PROFILING_SYSTEM_PROMPT, user_prompt)
                    
                    try:
                        profile_data = json.loads(json_str)
                        # Save to MongoDB
                        mongo_conv_repo.update_conversation(conv_key, {"client_profile": profile_data})
                        logger.info(f"Profile updated for {conv_key}: {profile_data}")
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse JSON from LLM: {json_str}")

                    # ACK the message
                    client.ack(stream_in, group_name, msg_id)
                    
                except Exception as e:
                    logger.error(f"Error in Profiling Worker: {e}")

if __name__ == "__main__":
    run()
