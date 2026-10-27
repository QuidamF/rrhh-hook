import sys
import os
import json
import time
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.stream_client import StreamClient
from services.normalizer import Normalizer
from services.imo_schema import IMOv2
from database.db_client import DBClient
from database.repositories.conversation_repo import ConversationRepository
from database.repositories.message_repo import MessageRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NormalizerWorker")

def run():
    client = StreamClient()
    db = DBClient()
    
    # REPOS FOR DUAL-WRITE (MONGO)
    mongo_conv_repo = ConversationRepository()
    mongo_msg_repo = MessageRepository()
    
    stream_name = "inbound.raw"
    group_name = "normalizer-group"
    consumer_name = "worker-1"
    
    client.create_group(stream_name, group_name)
    
    logger.info(f"Worker started. Reading from {stream_name}...")
    
    while True:
        messages = client.read_group(stream_name, group_name, consumer_name)
        if not messages:
            continue
            
        for stream, msgs in messages:
            for msg_id, data in msgs:
                try:
                    raw_payload = json.loads(data["payload"])
                    
                    # 1. Normalize
                    imo_dict = Normalizer.normalize_webhook(raw_payload)
                    if not imo_dict:
                        client.ack(stream_name, group_name, msg_id)
                        continue
                        
                    # 1.1 Handle Status Updates (Skip database for now)
                    if imo_dict.get("type") == "status_update":
                        logger.info(f"Status update received: {imo_dict.get('status')}")
                        client.ack(stream_name, group_name, msg_id)
                        continue

                    # 2. Persist Conversation & Get ID (POSTGRES)
                    conv_id, state, assigned_to = db.upsert_conversation(
                        imo_dict["channel"], imo_dict["actor_id"]
                    )
                    
                    # 3. Finalize IMO
                    imo_dict["conversation_id"] = conv_id
                    imo_dict["conversation_state"] = state
                    imo = IMOv2.from_dict(imo_dict)
                    
                    # 4. Persist Message (POSTGRES)
                    db.insert_message(imo)

                    # 5. DUAL-WRITE (MONGO)
                    mongo_conv = mongo_conv_repo.upsert_from_inbound(
                        channel=imo.channel,
                        external_user_id=imo.actor_id,
                        last_text=imo.content.get("body", f"[{imo.content.get('type')}]")
                    )
                    mongo_msg_repo.save({
                        "conversation_id": mongo_conv["_id"],
                        "external_id": imo.external_id,
                        "direction": "inbound",
                        "sender_type": "user",
                        "status": "received",
                        "type": imo.content.get("type"),
                        "content": {"normalized": imo.content},
                        "channel": imo.channel,
                        "channel_account_id": imo.channel_account_id,
                        "timestamp": imo.created_at,
                        "created_at": imo.created_at
                    })
                    
                    # 6. Push to next stream
                    client.push("message.normalized", imo.to_dict())
                    
                    # 7. ACK
                    client.ack(stream_name, group_name, msg_id)
                    logger.info(f"Processed message {imo.external_id} (Dual-Write OK)")
                    
                except Exception as e:
                    logger.error(f"Error processing message {msg_id}: {e}")
                    # In a real scenario, handle retries or move to failed stream here

if __name__ == "__main__":
    run()
