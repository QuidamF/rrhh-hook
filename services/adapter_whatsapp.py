from services.imo_schema import IMOv2

class WhatsAppAdapter:
    @staticmethod
    def normalize(data):
        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        
        if "messages" in value:
            msg = value["messages"][0]
            contact = value.get("contacts", [{}])[0]
            msg_type = msg.get("type")
            
            content = {"type": msg_type, "body": None, "media_url": None, "media_id": None}
            
            if msg_type == "text":
                content["body"] = msg.get("text", {}).get("body")
            elif msg_type in ["image", "audio", "video", "document", "voice"]:
                media_data = msg.get(msg_type, {})
                content["media_id"] = media_data.get("id")
                content["body"] = media_data.get("caption")
            elif msg_type == "interactive":
                interactive = msg.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    content["body"] = interactive["button_reply"].get("title")
                    content["interactive_id"] = interactive["button_reply"].get("id")
                elif interactive.get("type") == "list_reply":
                    content["body"] = interactive["list_reply"].get("title")
                    content["interactive_id"] = interactive["list_reply"].get("id")
            
            return {
                "channel": "whatsapp",
                "direction": "inbound",
                "actor_type": "user",
                "actor_id": msg.get("from"),
                "external_id": msg.get("id"),
                "content": content,
                "metadata": {
                    "sender_name": contact.get("profile", {}).get("name"),
                    "reply_to": msg.get("context", {}).get("id")
                },
                "provider_at": msg.get("timestamp"),
                "channel_account_id": value.get("metadata", {}).get("display_phone_number")
            }
        return None
