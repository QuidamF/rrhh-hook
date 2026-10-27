import sys
import os
import json
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.stream_client import StreamClient
from services.meta_sender import MetaSender
from services.telegram_sender import TelegramSender
from database.repositories.conversation_repo import ConversationRepository
from database.repositories.message_repo import MessageRepository
from database.db_client import DBClient
from services.imo_schema import IMOv2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DispatcherWorker")

def run():
    client = StreamClient()
    
    # REPOS
    mongo_conv_repo = ConversationRepository()
    mongo_msg_repo = MessageRepository()
    pg_db = DBClient()
    
    streams = {
        "message.decided": ">",   # AI / Automated replies
        "message.outbound": ">"   # Manual API replies
    }
    group_name = "dispatcher-group"
    consumer_name = "worker-1"
    
    # Ensure groups exist for both streams
    for stream in streams.keys():
        client.create_group(stream, group_name)
    
    logger.info(f"Dispatcher Worker started. Reading from {list(streams.keys())}...")
    
    while True:
        results = client.read_group(streams, group_name, consumer_name)
        if not results:
            continue
            
        for stream_name, msgs in results:
            for msg_id, data in msgs:
                try:
                    payload = json.loads(data["payload"])
                    
                    if stream_name == "message.decided":
                        # HANDLE AI/AUTOMATED REPLY
                        handle_automated_reply(payload, mongo_conv_repo, mongo_msg_repo, pg_db, client)
                    
                    elif stream_name == "message.outbound":
                        # HANDLE MANUAL API REPLY (PENDING -> SENT)
                        handle_manual_reply(payload, mongo_conv_repo, mongo_msg_repo, pg_db, client)
                    
                    # ACK the message
                    client.ack(stream_name, group_name, msg_id)
                    
                except Exception as e:
                    logger.error(f"Error processing message from {stream_name}: {e}")

def handle_automated_reply(decision, conv_repo, msg_repo, pg_db, client):
    action = decision.get("action")
    payload = decision.get("payload", {})
    
    if action == "reply":
        channel = payload.get("channel")
        to = payload.get("to")
        text = payload.get("text")
        
        logger.info(f"Sending automated reply via {channel} to {to}")
        
        result = send_via_provider(channel, to, text)
        
        if result["success"]:
            # SAVE TO MONGO
            mongo_conv = conv_repo.upsert_from_inbound(channel, to, text)
            msg_repo.save({
                "conversation_id": mongo_conv["_id"],
                "external_id": result.get("external_id"),
                "direction": "outbound",
                "sender_type": "bot",
                "status": "sent",
                "type": "text",
                "content": {"normalized": {"text": text}},
                "channel": channel,
                "timestamp": datetime.utcnow()
            })
            # SAVE TO POSTGRES
            try:
                pg_conv_id, _, _ = pg_db.upsert_conversation(channel, to)
                imo = IMOv2(
                    channel=channel, direction="outbound", actor_type="bot", actor_id="bot",
                    content={"type": "text", "body": text}, external_id=result.get("external_id"),
                    conversation_id=pg_conv_id
                )
                pg_db.insert_message(imo)
            except Exception as e:
                logger.error(f"Error dual-writing automated reply to Postgres: {e}")

def handle_manual_reply(task, conv_repo, msg_repo, pg_db, client):
    """Processes a manual message that was already saved as 'pending'."""
    client_id = task.get("client_id")
    channel = task.get("channel")
    to = task.get("to")
    text = task.get("text")
    reaction = task.get("reaction")
    reply_to = task.get("reply_to_message_id")
    media_type = task.get("media_type")
    media_url = task.get("media_url")
    media_id = task.get("media_id")
    caption = task.get("caption")
    interactive = task.get("interactive")
    
    # Resolve reply_to external_id if needed
    external_reply_to = None
    if reply_to:
        orig = msg_repo.get_by_id(reply_to)
        if orig:
            external_reply_to = orig.get("external_id")

    logger.info(f"Sending manual reply ({client_id}) via {channel} to {to}")
    
    result = send_via_provider(
        channel, to, text, external_reply_to, reaction, 
        media_type, media_url, media_id, caption, interactive
    )
    
    # UPDATE STATUS IN BOTH DBS
    status = "sent" if result["success"] else "failed"
    error = result.get("error")
    ext_id = result.get("external_id")
    
    # 1. Update MongoDB
    updated = msg_repo.update_outbound_by_client_id(client_id, ext_id, status, error)
    
    if not updated and result["success"]:
        # If not found (like AI replies that didn't save first), CREATE it
        pg_conv_id, pg_uuid, mongo_id = pg_db.upsert_conversation(channel, to)
        msg_repo.save({
            "client_id": client_id,
            "conversation_id": mongo_id,
            "external_id": ext_id,
            "direction": "outbound",
            "sender_type": task.get("origin", "bot"),
            "status": "sent",
            "type": media_type or "text",
            "content": {"normalized": {"text": text or caption or "Media"}},
            "channel": channel,
            "timestamp": datetime.utcnow()
        })
    
    if result["success"]:
        conv_repo.update_conversation(f"{channel}:{to}", {"last_message_text": text or caption or reaction or "Interactive"})

    # 2. Update PostgreSQL
    try:
        if result["success"]:
            pg_conv_id, _, _ = pg_db.upsert_conversation(channel, to)
            imo = IMOv2(
                channel=channel, direction="outbound", 
                actor_type=task.get("actor_type", "agent"), 
                actor_id=task.get("actor_id", "agent"),
                content={"type": media_type or "text", "body": text or caption or reaction or "Interactive"},
                external_id=ext_id,
                conversation_id=pg_conv_id,
                reply_to=external_reply_to,
                metadata={
                    "origin": task.get("origin"),
                    "media_id": media_id,
                    "media_url": media_url
                }
            )
            pg_db.insert_message(imo)
    except Exception as e:
        logger.error(f"Error updating Postgres for manual reply: {e}")

    # 3. Publish Delivery Receipt (For Pub/Sub Subscribers like Odoo)
    try:
        receipt = {
            "event": "status_update",
            "client_id": client_id,
            "status": status,
            "external_id": ext_id,
            "channel": channel,
            "error": error
        }
        client.push("message.status_updated", receipt)
    except Exception as e:
        logger.error(f"Error publishing delivery receipt: {e}")

def send_via_provider(channel, to, text, reply_to=None, reaction=None, media_type=None, media_url=None, media_id=None, caption=None, interactive=None):
    if channel == "whatsapp":
        return MetaSender.send_whatsapp(
            to, text, reply_to, reaction, 
            media_type, media_url, media_id, caption, interactive
        )
    elif channel == "messenger":
        # Messenger media support could be added here if needed
        return MetaSender.send_messenger(to, text, reply_to)
    elif channel == "telegram":
        return TelegramSender.send_telegram(
            to, text, reply_to, reaction, 
            media_type, media_url, media_id, caption
        )
    return {"success": False, "error": f"Unsupported channel: {channel}"}

if __name__ == "__main__":
    run()
