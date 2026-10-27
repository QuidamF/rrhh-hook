from bson import ObjectId
from datetime import datetime
from database.mongo_client import MongoDB

class MessageRepository:
    def __init__(self):
        self.collection = MongoDB.get_db().messages

    def save(self, message_data):
        """Inserts a new message. Fails if external_id already exists (duplicate)."""
        if "created_at" not in message_data:
            message_data["created_at"] = datetime.utcnow()
        
        # Ensure external_id is not null (sparse index allows multiple docs MISSING the field, 
        # but only one doc HAVING it set to null)
        if message_data.get("external_id") is None:
            message_data.pop("external_id", None)
            
        return self.collection.insert_one(message_data)

    def get_by_id(self, message_id):
        """Retrieves a message by its internal MongoDB _id."""
        try:
            return self.collection.find_one({"_id": ObjectId(message_id)})
        except:
            return None

    def get_by_external_id(self, external_id):
        return self.collection.find_one({"external_id": external_id})

    def get_by_client_id(self, client_id):
        """Retrieves a message by its unique client_id."""
        return self.collection.find_one({"client_id": client_id})

    def get_history(self, conversation_id, limit=50, before=None, after=None):
        """
        Cursor-based pagination using MongoDB _id.
        'before' -> History (older messages, _id < cursor)
        'after' -> Incremental (newer messages, _id > cursor)
        """
        query = {"conversation_id": ObjectId(conversation_id)}
        
        if before:
            query["_id"] = {"$lt": ObjectId(before)}
        elif after:
            query["_id"] = {"$gt": ObjectId(after)}

        # Default Sort: DESC (latest first)
        sort_order = -1
        
        # If fetching incremental (after), we might want ASC to process them in order,
        # but the requirement states DESC for the primary list.
        # Typically, polling uses $gt followed by reverse in the client.
        
        cursor = self.collection.find(query).sort("_id", sort_order).limit(limit)
        return list(cursor)

    def update_status_by_external_id(self, external_id, status, error=None):
        update = {"$set": {"status": status}}
        if error:
            update["$set"]["error"] = error
        
        return self.collection.update_one(
            {"external_id": external_id},
            update
        )

    def update_content_by_imo_id(self, imo_id, new_content):
        """Updates the content field of a message using its unique IMO ID."""
        return self.collection.update_one(
            {"id": imo_id},
            {"$set": {"content": new_content}}
        )

    def update_outbound_by_client_id(self, client_id, external_id, status, error=None):
        update_set = {"status": status}
        if external_id is not None:
            update_set["external_id"] = external_id
        if error is not None:
            update_set["error"] = error
            
        return self.collection.update_one(
            {"client_id": client_id},
            {"$set": update_set}
        )

    def delete_by_conversation(self, conversation_id):
        """Deletes all messages associated with a specific conversation."""
        return self.collection.delete_many({"conversation_id": ObjectId(conversation_id)})

    def delete_all(self):
        """Clears the entire messages collection."""
        return self.collection.delete_many({})
