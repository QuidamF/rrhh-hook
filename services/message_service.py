import logging
import uuid
from datetime import datetime
from services.normalizer import Normalizer
from services.meta_sender import MetaSender
from services.telegram_sender import TelegramSender
from database.repositories.conversation_repo import ConversationRepository
from database.repositories.message_repo import MessageRepository
from database.db_client import DBClient
from services.imo_schema import IMOv2
from services.stream_client import StreamClient

logger = logging.getLogger(__name__)

class MessageService:
    def __init__(self):
        self.conv_repo = ConversationRepository()
        self.msg_repo = MessageRepository()
        self.pg_db = DBClient()
        self.stream_client = StreamClient()

    def handle_inbound_webhook(self, data):
        """Orchestrates the inbound message flow."""
        # 1. Normalize
        sme = Normalizer.normalize_webhook(data)
        if not sme:
            return False

        # 2. Handle Status Updates (sent, delivered, read)
        if sme.get("type") == "status_update":
            return self._handle_status_update(sme)

        # 3. Deduplication (Unique Index in Mongo will catch this, but we check first)
        existing = self.msg_repo.get_by_external_id(sme["external_id"])
        if existing:
            logger.info(f"Duplicate message ignored: {sme['external_id']}")
            return True

        # 4. Upsert Conversation
        last_text = sme["content"]["normalized"].get("text", f"[{sme['type']}]")
        conv = self.conv_repo.upsert_from_inbound(
            channel=sme["channel"],
            external_user_id=sme["external_user_id"],
            last_text=last_text
        )

        # 5. Save Message
        message_doc = {
            "conversation_id": conv["_id"],
            "external_id": sme["external_id"],
            "direction": "inbound",
            "sender_type": sme["sender_type"],
            "status": "received",
            "type": sme["type"],
            "content": sme["content"],
            "channel": sme["channel"],
            "channel_account_id": sme["channel_account_id"],
            "timestamp": sme["timestamp"],
            "created_at": datetime.utcnow()
        }
        
        try:
            msg_result = self.msg_repo.save(message_doc)
            # Update last_message_id in conversation
            self.conv_repo.update_conversation(
                conv["conversation_key"], 
                {"last_message_id": msg_result.inserted_id}
            )
            return True
        except Exception as e:
            logger.error(f"Error saving message: {e}")
            return False

    def send_outbound_message(self, conversation_key, text=None, reply_to_message_id=None, reaction=None, actor_id="human_agent", actor_type="agent", origin="api", client_id=None, media_type=None, media_url=None, media_id=None, caption=None, interactive=None):
        """
        Orchestrates the outbound message flow asynchronously.
        Enforces idempotency using client_id and supports multimedia/interactive.
        """
        # 1. Resolve Conversation
        conv = self.conv_repo.get_by_key(conversation_key)
        if not conv:
            raise ValueError("Conversation not found")

        # 2. Check Idempotency
        if client_id:
            existing = self.msg_repo.get_by_client_id(client_id)
            if existing:
                logger.info(f"Duplicate request detected for client_id: {client_id}. Returning existing message info.")
                return {
                    "success": True, 
                    "message_id": str(existing["_id"]), 
                    "status": existing.get("status"),
                    "external_id": existing.get("external_id"),
                    "duplicate": True
                }
        else:
            client_id = str(uuid.uuid4())

        # Determine overall message type
        msg_type = "text"
        if reaction: msg_type = "reaction"
        elif interactive: msg_type = "interactive"
        elif media_type: msg_type = media_type
        
        # 3. Save Pending Message (MongoDB)
        message_doc = {
            "conversation_id": conv["_id"],
            "client_id": client_id,
            "direction": "outbound",
            "sender_type": actor_type,
            "status": "pending",
            "type": msg_type,
            "content": {
                "normalized": {
                    "text": text,
                    "reaction": reaction,
                    "reply_to": reply_to_message_id,
                    "actor_id": actor_id,
                    "origin": origin,
                    "media_type": media_type,
                    "media_url": media_url,
                    "media_id": media_id,
                    "caption": caption,
                    "interactive": interactive
                }
            },
            "channel": conv["channel"],
            "timestamp": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }
        mongo_result = self.msg_repo.save(message_doc)
        mongo_id = str(mongo_result.inserted_id)

        # 4. Save Pending Message (PostgreSQL Dual-Write)
        try:
            pg_conv_id, _, _ = self.pg_db.upsert_conversation(conv["channel"], conv["external_user_id"])
            imo_out = IMOv2(
                channel=conv["channel"],
                direction="outbound",
                actor_type=actor_type,
                actor_id=actor_id,
                content={"type": msg_type, "body": text or caption or reaction or "Interactive Message"},
                external_id=None, # Pending
                conversation_id=pg_conv_id,
                metadata={
                    "origin": origin, "client_id": client_id, "mongo_id": mongo_id,
                    "media_url": media_url, "media_id": media_id
                }
            )
            self.pg_db.insert_message(imo_out)
        except Exception as e:
            logger.error(f"Error dual-writing pending message to Postgres: {e}")

        # 5. Enqueue for Sending (Redis Stream)
        task = {
            "message_id": mongo_id,
            "client_id": client_id,
            "conversation_key": conversation_key,
            "channel": conv["channel"],
            "to": conv["external_user_id"],
            "text": text,
            "reply_to_message_id": reply_to_message_id,
            "reaction": reaction,
            "actor_id": actor_id,
            "actor_type": actor_type,
            "origin": origin,
            "media_type": media_type,
            "media_url": media_url,
            "media_id": media_id,
            "caption": caption,
            "interactive": interactive
        }
        
        try:
            self.stream_client.push("message.outbound", task)
            return {"success": True, "message_id": mongo_id, "status": "pending", "client_id": client_id}
        except Exception as e:
            self.msg_repo.update_outbound_by_client_id(client_id, None, "failed", str(e))
            return {"success": False, "error": f"Failed to enqueue message: {e}"}

    def assign_conversation(self, conversation_key, assigned_to):
        """Synchronizes conversation assignment across MongoDB and PostgreSQL."""
        # 1. Update MongoDB
        mongo_result = self.conv_repo.update_conversation(conversation_key, {"assigned_to": assigned_to})
        
        # 2. Update PostgreSQL
        try:
            self.pg_db.update_conversation_assignment(conversation_key, assigned_to)
        except Exception as e:
            logger.error(f"Error updating assignment in Postgres: {e}")
            
        return mongo_result.matched_count > 0

    def _handle_status_update(self, sme):
        """Updates internal message status based on Meta feedback."""
        if sme.get("external_id"):
            self.msg_repo.update_status_by_external_id(sme["external_id"], sme["status"])
        elif sme.get("external_ids"):
            for ext_id in sme["external_ids"]:
                self.msg_repo.update_status_by_external_id(ext_id, sme["status"])
        return True

    def delete_conversation_complete(self, conversation_key):
        """Orchestrates the deletion of a conversation and all its history."""
        conv = self.conv_repo.get_by_key(conversation_key)
        if not conv:
            return False, "Conversation not found"

        # 1. Delete Messages
        self.msg_repo.delete_by_conversation(conv["_id"])
        
        # 2. Delete Conversation
        self.conv_repo.delete_by_key(conversation_key)
        
        return True, "Conversation and history deleted"

    def reset_all_data(self):
        """Clears all messaging data (conversations and messages) across MongoDB and Postgres."""
        self.msg_repo.delete_all()
        self.conv_repo.delete_all()
        try:
            self.pg_db.delete_all()
        except Exception as e:
            logger.error(f"Error deleting from PostgreSQL during reset: {e}")
        return True
