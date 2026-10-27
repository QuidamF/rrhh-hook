from datetime import datetime
from database.mongo_client import MongoDB

class ConversationRepository:
    def __init__(self):
        self.collection = MongoDB.get_db().conversations

    def upsert_from_inbound(self, channel, external_user_id, last_text, message_id=None):
        """
        Atomically updates a conversation from an inbound message.
        Increments unread_count and sets last_message metadata.
        """
        conversation_key = f"{channel}:{external_user_id}"
        now = datetime.utcnow()

        result = self.collection.find_one_and_update(
            {"conversation_key": conversation_key},
            {
                "$inc": {"unread_count": 1},
                "$set": {
                    "last_message_text": last_text,
                    "last_message_id": message_id,
                    "updated_at": now,
                    "status": "open" # Re-open if closed or new
                },
                "$setOnInsert": {
                    "conversation_key": conversation_key,
                    "channel": channel,
                    "external_user_id": external_user_id,
                    "created_at": now,
                    "assigned_to": None
                }
            },
            upsert=True,
            return_document=True
        )
        return result

    def get_by_key(self, conversation_key):
        return self.collection.find_one({"conversation_key": conversation_key})

    def list_conversations(self, filters=None, limit=50):
        query = {}
        if filters:
            if filters.get("status"):
                query["status"] = filters["status"]
            if filters.get("assigned_to"):
                query["assigned_to"] = filters["assigned_to"]
            if filters.get("unread_only"):
                query["unread_count"] = {"$gt": 0}
        
        return list(self.collection.find(query).sort("updated_at", -1).limit(limit))

    def update_conversation(self, conversation_key, update_data):
        update_data["updated_at"] = datetime.utcnow()
        return self.collection.update_one(
            {"conversation_key": conversation_key},
            {"$set": update_data}
        )

    def reset_unread(self, conversation_key):
        return self.collection.update_one(
            {"conversation_key": conversation_key},
            {"$set": {"unread_count": 0, "last_read_at": datetime.utcnow()}}
        )

    def delete_by_key(self, conversation_key):
        """Deletes a single conversation document."""
        return self.collection.delete_one({"conversation_key": conversation_key})

    def delete_all(self):
        """Clears the entire conversations collection."""
        return self.collection.delete_many({})
