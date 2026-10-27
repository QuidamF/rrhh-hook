import sys
import os
import json
import time
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.stream_client import StreamClient
from services.imo_schema import IMOv2
from database.db_client import DBClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MCPWorker")

def run():
    client = StreamClient()
    db = DBClient()
    
    stream_name = "message.normalized"
    group_name = "brain-group"
    consumer_name = "worker-1"
    
    client.create_group(stream_name, group_name)
    
    logger.info(f"Brain Worker started. Reading from {stream_name}...")
    
    while True:
        messages = client.read_group(stream_name, group_name, consumer_name)
        if not messages:
            continue
            
        for stream, msgs in messages:
            for msg_id, data in msgs:
                try:
                    imo_data = json.loads(data["payload"])
                    imo = IMOv2.from_dict(imo_data)
                    
                    # 1. LOCK PER CONVERSATION
                    lock_key = f"lock:conv:{imo.conversation_id}"
                    if not client.set_lock(lock_key, ttl=30):
                        # Fail to acquire: Re-enqueue with retry logic
                        retries = imo.metadata.get("retries", 0)
                        if retries < 3:
                            imo.metadata["retries"] = retries + 1
                            logger.info(f"Lock busy for {imo.conversation_id}. Re-queuing ({retries+1}/3)")
                            time.sleep(0.5) # Small delay before re-enqueue
                            client.push(stream_name, imo.to_dict())
                            client.ack(stream_name, group_name, msg_id)
                        else:
                            logger.warning(f"Max retries reached for {imo.id}. Moving to failed.")
                            client.push("message.failed", {"imo": imo.to_dict(), "error": "lock_timeout"})
                            client.ack(stream_name, group_name, msg_id)
                        continue

                    try:
                        # 2. FETCH CONTEXT & DECIDE
                        # (In a real scenario, this calls the MCP Server)
                        history = db.get_history(imo.conversation_id, limit=5)
                        
                        # MOCK MCP DECISION
                        decision = {
                            "imo_id": imo.id,
                            "action": "reply",
                            "payload": {
                                "text": f"He recibido tu mensaje: '{imo.content.get('body')}'",
                                "channel": imo.channel,
                                "to": imo.actor_id
                            }
                        }
                        
                        # 3. PUSH TO DECIDED
                        client.push("message.decided", decision)
                        logger.info(f"Decision made for {imo.id}: {decision['action']}")
                        
                        # 4. ACK
                        client.ack(stream_name, group_name, msg_id)
                        
                    finally:
                        client.release_lock(lock_key)
                        
                except Exception as e:
                    logger.error(f"Error in Brain Worker: {e}")

if __name__ == "__main__":
    run()
