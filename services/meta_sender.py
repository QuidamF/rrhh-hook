import requests
import logging
from config.config import Config

logger = logging.getLogger(__name__)

class MetaSender:
    @staticmethod
    def send_whatsapp(to, text, reply_to_message_id=None, reaction=None, media_type=None, media_url=None, media_id=None, caption=None, interactive=None):
        """Sends a message using WhatsApp Cloud API, supporting text, media, reactions, and interactive buttons."""
        url = f"https://graph.facebook.com/v20.0/{Config.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {Config.WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to
        }

        # 1. Handle Reactions
        if reaction:
            payload["type"] = "reaction"
            payload["reaction"] = {"message_id": reply_to_message_id, "emoji": reaction}
        
        # 2. Handle Interactive (Buttons/Lists)
        elif interactive:
            payload["type"] = "interactive"
            payload["interactive"] = interactive

        # 3. Handle Media (image, video, audio, document)
        elif media_type:
            payload["type"] = media_type
            media_obj = {}
            if media_url:
                media_obj["link"] = media_url
            else:
                media_obj["id"] = media_id
            
            if caption:
                media_obj["caption"] = caption
                
            payload[media_type] = media_obj

        # 4. Handle Text (Default)
        else:
            payload["type"] = "text"
            payload["text"] = {"body": text}
        
        # Add Context (Reply) for non-reaction messages
        if reply_to_message_id and not reaction:
            payload["context"] = {"message_id": reply_to_message_id}
        
        return MetaSender._make_request(url, headers, payload)

    @staticmethod
    def send_messenger(psid, text, reply_to_message_id=None):
        """Sends a text message using Messenger Graph API, supporting replies."""
        url = f"https://graph.facebook.com/v20.0/me/messages?access_token={Config.PAGE_ACCESS_TOKEN}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "recipient": {"id": psid},
            "message": {"text": text}
        }
        
        if reply_to_message_id:
            payload["reply_to"] = {"mid": reply_to_message_id}
            
        return MetaSender._make_request(url, headers, payload)

    @staticmethod
    def _make_request(url, headers, payload):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            response_data = response.json()
            
            if response.status_code == 200:
                logger.info(f"Message sent successfully: {response_data}")
                return {
                    "success": True, 
                    "external_id": response_data.get("messages", [{}])[0].get("id") if "messages" in response_data else response_data.get("message_id")
                }
            else:
                logger.error(f"Error sending message: {response_data}")
                return {"success": False, "error": response_data.get("error", {}).get("message")}
                
        except Exception as e:
            logger.error(f"Exception sending message: {e}")
            return {"success": False, "error": str(e)}
