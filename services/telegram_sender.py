import requests
import logging
from config.config import Config

logger = logging.getLogger(__name__)

class TelegramSender:
    @staticmethod
    def send_action(chat_id, action="typing"):
        """
        Sends a chat action (like 'typing') to Telegram.
        """
        if not Config.TELEGRAM_BOT_TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN not configured")
            return
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendChatAction"
        payload = {
            "chat_id": chat_id,
            "action": action
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Error sending telegram action: {e}")

    @staticmethod
    def send_telegram(chat_id, text=None, reply_to_message_id=None, reaction=None, media_type=None, media_url=None, media_id=None, caption=None):
        """Sends a message, reaction, or media using Telegram Bot API."""
        if not Config.TELEGRAM_BOT_TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN not configured")
            return {"success": False, "error": "Telegram token missing"}

        # 1. Handle Reactions
        if reaction:
            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/setMessageReaction"
            try:
                msg_id = int(reply_to_message_id) if reply_to_message_id else None
                if not msg_id:
                    return {"success": False, "error": "message_id is required for reactions"}
                payload = {
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "reaction": [{"type": "emoji", "emoji": reaction}]
                }
            except (ValueError, TypeError):
                return {"success": False, "error": f"Invalid message_id for Telegram: {reply_to_message_id}"}
        
        # 2. Handle Media
        elif media_type:
            methods = {
                "image": "sendPhoto",
                "audio": "sendAudio",
                "voice": "sendVoice",
                "video": "sendVideo",
                "document": "sendDocument"
            }
            method = methods.get(media_type, "sendDocument")
            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/{method}"
            
            # Param name varies by method (photo, audio, etc)
            param_name = "photo" if media_type == "image" else media_type
            payload = {
                "chat_id": chat_id,
                param_name: media_url if media_url else media_id,
                "caption": caption or text
            }
            if reply_to_message_id:
                payload["reply_parameters"] = {"message_id": int(reply_to_message_id)}

        # 3. Handle Text (Default)
        else:
            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text
            }
            if reply_to_message_id:
                try:
                    payload["reply_parameters"] = {"message_id": int(reply_to_message_id)}
                except (ValueError, TypeError):
                    logger.warning(f"Could not cast reply_to_message_id to int: {reply_to_message_id}")
        
        logger.debug(f"Sending Telegram payload to {url}: {payload}")
        return TelegramSender._make_request(url, payload)

    @staticmethod
    def _make_request(url, payload):
        try:
            response = requests.post(url, json=payload, timeout=5)
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get("ok"):
                logger.info(f"Telegram request successful: {response_data}")
                
                # Some methods return a Message object, others return True (boolean)
                result = response_data.get("result")
                external_id = None
                if isinstance(result, dict):
                    external_id = str(result.get("message_id"))
                elif isinstance(result, bool):
                    # For reactions, we don't have a new message ID, 
                    # we generate a unique one to avoid Mongo index collisions
                    import uuid
                    external_id = f"reaction_tg_{uuid.uuid4().hex[:12]}"

                return {
                    "success": True, 
                    "external_id": external_id
                }
            else:
                logger.error(f"Error in Telegram request: {response_data}")
                return {"success": False, "error": response_data.get("description", "Unknown error")}
                
        except Exception as e:
            logger.error(f"Exception in Telegram request: {e}")
            return {"success": False, "error": str(e)}
