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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SummaryWorker")

SUMMARY_PROMPT = """
Eres un analista de soporte técnico experto. 
Tu tarea es resumir la siguiente conversación entre un cliente y Samanta (la IA). 
Proporciona un resumen ejecutivo breve (máximo 50 palabras) que incluya:
1. El problema o interés principal del cliente.
2. Por qué se está transfiriendo la conversación a un humano.
3. Datos clave (si los hay, como nombres de productos o IDs).

Formato de salida:
RESUMEN DE TRASPASO: [Tu resumen aquí]
"""

def run():
    client = StreamClient()
    pg_db = DBClient()
    
    stream_in = "handoff.requested"
    group_name = "summary-group"
    consumer_name = "worker-1"
    
    client.create_group(stream_in, group_name)
    
    logger.info(f"Summary Agent Worker started. Monitoring {stream_in}...")
    
    while True:
        results = client.read_group({stream_in: ">"}, group_name, consumer_name)
        if not results:
            continue
            
        for stream_name, msgs in results:
            for msg_id, data in msgs:
                try:
                    payload = json.loads(data["payload"])
                    conv_id = payload["conversation_id"]
                    
                    logger.info(f"Generating summary for handoff in conversation {conv_id}...")

                    # 1. Get longer history for context (last 15 messages)
                    history = pg_db.get_history(conv_id, limit=15)
                    context = ""
                    for h in reversed(history):
                        direction = h.get("direction")
                        content = h.get("content", {})
                        role = "Usuario" if direction == "inbound" else "Samanta"
                        text = content.get("body", "")
                        context += f"{role}: {text}\n"
                    
                    # 2. Ask LLM (OpenAI, Gemini or Ollama) for the summary
                    from workers.ai_worker import call_llm
                    summary_text = call_llm(
                        Config.OLLAMA_MODEL,
                        system_prompt=SUMMARY_PROMPT,
                        user_prompt=f"Conversación:\n{context}\n\nAnalista:",
                        temperature=0.1
                    ).strip()
                    # 3. Notify Odoo (Mock)
                    # We send a special event 'handoff'
                    odoo_payload = {
                        "event": "handoff.summary",
                        "message_uuid": conv_id,
                        "actor_id": payload["user_id"],
                        "channel": payload["channel"],
                        "content": {
                            "summary": summary_text,
                            "type": "handoff_report"
                        }
                    }
                    
                    # Use local URL for the mock
                    requests.post("http://127.0.0.1:5020/debug/frontend-mock", json=odoo_payload)
                    logger.info(f"Summary generated and sent to Odoo for {conv_id}")

                    # 4. ACK
                    client.ack(stream_in, group_name, msg_id)
                    
                except Exception as e:
                    logger.error(f"Error in Summary Worker: {e}")

if __name__ == "__main__":
    run()
