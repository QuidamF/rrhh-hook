import logging
from services.adapter_whatsapp import WhatsAppAdapter
from services.adapter_messenger import MessengerAdapter
from services.adapter_telegram import TelegramAdapter

logger = logging.getLogger(__name__)

class Normalizer:
    @staticmethod
    def normalize_webhook(data):
        """
        Detects the source channel and delegates to the appropriate adapter.
        """
        try:
            # Telegram Detection (Update object usually has update_id)
            if "update_id" in data:
                return TelegramAdapter.normalize(data)

            # Check for entry structure (Meta Standard)
            if "entry" in data:
                entry = data.get("entry", [{}])[0]
                
                # WhatsApp Detection
                if "changes" in entry:
                    change = entry["changes"][0]
                    if change.get("field") == "messages":
                        return WhatsAppAdapter.normalize(data)
                
                # Messenger Detection
                if "messaging" in entry:
                    return MessengerAdapter.normalize(data)
                
            logger.warning(f"Unknown webhook structure or field: {data}")
            return None
            
        except Exception as e:
            logger.error(f"Error during normalization: {e}")
            return None
