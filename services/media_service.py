import os
import requests
import logging
from config.config import Config

logger = logging.getLogger(__name__)

class MediaService:
    def __init__(self):
        self.media_root = Config.MEDIA_ROOT
        self.base_url = Config.get_media_url_base()

        
        # Ensure media root exists
        if not os.path.exists(self.media_root):
            os.makedirs(self.media_root)

    def download_media(self, channel, media_id, conversation_id, filename=None):
        """
        Main entry point to download media based on channel.
        Returns the public URL of the downloaded file.
        """
        try:
            # 1. Create conversation folder if it doesn't exist
            conv_folder = os.path.join(self.media_root, str(conversation_id))
            if not os.path.exists(conv_folder):
                os.makedirs(conv_folder)
                logger.info(f"Created new media folder for conversation: {conversation_id}")

            # 2. Get file path from Provider
            file_data = None
            if channel == "telegram":
                file_data = self._get_telegram_file(media_id)
            elif channel == "whatsapp":
                # To be implemented when we have real tokens
                logger.warning("WhatsApp media download not yet implemented")
                return None
            
            if not file_data:
                return None

            # 3. Download and save
            file_path, file_extension = file_data
            if not filename:
                filename = f"{media_id}{file_extension}"
            
            local_path = os.path.join(conv_folder, filename)
            
            # Prevent re-downloading if it exists (Optional, depends on your needs)
            if os.path.exists(local_path):
                return f"{self.base_url}/{conversation_id}/{filename}"

            self._save_file(file_path, local_path, channel)
            
            # 4. Return the public URL
            return f"{self.base_url}/{conversation_id}/{filename}"

        except Exception as e:
            logger.error(f"Error downloading media from {channel}: {e}")
            return None

    def _get_telegram_file(self, file_id):
        """
        Calls Telegram API to get the relative file path.
        """
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
        response = requests.get(url).json()
        
        if response.get("ok"):
            file_path = response["result"]["file_path"]
            extension = os.path.splitext(file_path)[1]
            return file_path, extension
        return None

    def _save_file(self, remote_path, local_path, channel):
        """
        Downloads the binary from the provider and saves it locally.
        """
        download_url = ""
        if channel == "telegram":
            download_url = f"https://api.telegram.org/file/bot{Config.TELEGRAM_BOT_TOKEN}/{remote_path}"
        
        if not download_url:
            return

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(download_url, stream=True, headers=headers)
        response.raise_for_status()
        
        if response.status_code == 200:
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            size = os.path.getsize(local_path)
            
            # Diagnostic: Check file header
            with open(local_path, 'rb') as f:
                header = f.read(5)
                logger.info(f"File Diagnostic - Path: {local_path}, Size: {size} bytes, Header: {header}")
                
            logger.info(f"File saved successfully: {local_path} ({size} bytes)")
