from datetime import datetime

class MessengerAdapter:
    @staticmethod
    def normalize(data):
        """
        Translates Messenger webhook payload to IMOv2 dict.
        """
        entry = data.get("entry", [{}])[0]
        messaging = entry.get("messaging", [{}])[0]
        
        sender_id = messaging.get("sender", {}).get("id")
        recipient_id = messaging.get("recipient", {}).get("id")
        
        # Handle status updates
        if "delivery" in messaging:
            return {
                "type": "status_update",
                "external_ids": messaging["delivery"].get("mids", []),
                "status": "delivered"
            }
        
        if "read" in messaging:
            return {
                "type": "status_update",
                "status": "read"
            }

        # Handle incoming messages
        if "message" in messaging:
            msg = messaging["message"]
            if msg.get("is_echo"):
                return None

            content = {"type": "text", "body": None, "media_url": None}
            if "text" in msg:
                content["body"] = msg.get("text")
            elif "attachments" in msg:
                attach = msg["attachments"][0]
                content["type"] = attach.get("type")
                content["media_url"] = attach.get("payload", {}).get("url")

            return {
                "channel": "messenger",
                "direction": "inbound",
                "actor_type": "user",
                "actor_id": str(sender_id),
                "external_id": msg.get("mid"),
                "content": content,
                "metadata": {},
                "provider_at": datetime.fromtimestamp(messaging.get("timestamp", 0) / 1000.0),
                "channel_account_id": str(recipient_id)
            }

        return None
