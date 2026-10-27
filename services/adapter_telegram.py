from datetime import datetime

class TelegramAdapter:
    @staticmethod
    def normalize(data):
        """
        Translates Telegram webhook payload to IMOv2 dict.
        """
        # Handle message or edited message
        message = data.get("message") or data.get("edited_message")
        
        # Handle reactions (separate update type in Telegram)
        if "message_reaction" in data:
            reaction_data = data["message_reaction"]
            chat = reaction_data.get("chat", {})
            user = reaction_data.get("user", {})
            new_reactions = reaction_data.get("new_reaction", [])
            
            # If reaction was removed, body will be None
            emoji = new_reactions[0].get("emoji") if new_reactions else None
            
            return {
                "channel": "telegram",
                "direction": "inbound",
                "actor_type": "user",
                "actor_id": str(user.get("id")),
                "external_id": f"react_{user.get('id')}_{reaction_data.get('message_id')}_{int(datetime.utcnow().timestamp())}",
                "content": {
                    "type": "reaction",
                    "body": emoji,
                    "target_message_id": str(reaction_data.get("message_id")),
                    "action": "added" if emoji else "removed"
                },
                "metadata": {"username": user.get("username")},
                "provider_at": datetime.utcnow(),
                "channel_account_id": str(chat.get("id"))
            }

        if not message:
            return None

        chat = message.get("chat", {})
        sender = message.get("from", {})
        actor_id = str(sender.get("id"))
        
        content = {"type": "text", "body": None, "media_url": None, "media_id": None}
        
        # Detect Reply context
        reply_to = message.get("reply_to_message")
        if reply_to:
            content["reply_to"] = str(reply_to.get("message_id"))

        if "text" in message:
            content["type"] = "text"
            content["body"] = message.get("text")
        elif "photo" in message:
            content["type"] = "image"
            photo = message["photo"][-1]
            content["media_id"] = photo.get("file_id")
            content["body"] = message.get("caption")
        elif "video" in message:
            content["type"] = "video"
            content["media_id"] = message["video"].get("file_id")
            content["body"] = message.get("caption")
        elif "document" in message:
            content["type"] = "document"
            content["media_id"] = message["document"].get("file_id")
            content["body"] = message.get("caption")
        elif "audio" in message:
            content["type"] = "audio"
            content["media_id"] = message["audio"].get("file_id")
            content["body"] = message.get("caption")
        elif "voice" in message:
            content["type"] = "voice"
            content["media_id"] = message["voice"].get("file_id")
        
        return {
            "channel": "telegram",
            "direction": "inbound",
            "actor_type": "user",
            "actor_id": actor_id,
            "external_id": str(message.get("message_id")),
            "content": content,
            "metadata": {
                "first_name": sender.get("first_name"),
                "last_name": sender.get("last_name"),
                "username": sender.get("username"),
                "is_bot": sender.get("is_bot")
            },
            "provider_at": datetime.fromtimestamp(message.get("date", datetime.utcnow().timestamp())),
            "channel_account_id": str(chat.get("id"))
        }
