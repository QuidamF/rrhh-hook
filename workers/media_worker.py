import sys
import os
import json
import logging
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.stream_client import StreamClient
from database.db_client import DBClient
from database.repositories.message_repo import MessageRepository
from services.media_service import MediaService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MediaWorker")

def run():
    client = StreamClient()
    pg_db = DBClient()
    mongo_repo = MessageRepository()
    media_service = MediaService()
    
    stream_in = "message.normalized"
    stream_out = "message.processed"
    group_name = "media-worker-group"
    consumer_name = "worker-1"
    
    client.create_group(stream_in, group_name)
    
    logger.info(f"Media Worker started. Monitoring {stream_in}...")
    
    while True:
        results = client.read_group({stream_in: ">"}, group_name, consumer_name)
        if not results:
            continue
            
        for stream_name, msgs in results:
            for msg_id, data in msgs:
                try:
                    payload = json.loads(data["payload"])
                    content = payload.get("content", {})
                    media_id = content.get("media_id")
                    
                    # 1. If has media, download it
                    if media_id:
                        logger.info(f"Downloading media {media_id} for conversation {payload['conversation_id']}")
                        
                        media_url = media_service.download_media(
                            channel=payload["channel"],
                            media_id=media_id,
                            conversation_id=payload["conversation_id"]
                        )
                        
                        if media_url:
                            # Update local payload
                            content["media_url"] = media_url
                            payload["content"] = content
                            
                            # 2. Update Dual-Write DBs
                            # Update PostgreSQL
                            pg_db.update_message_content(payload["id"], content)
                            # Update MongoDB
                            mongo_repo.update_content_by_imo_id(payload["id"], content)
                            
                            logger.info(f"Media downloaded and DBs updated: {media_url}")

                    # 3. Push to processed stream
                    client.push(stream_out, payload)
                    
                    # 4. ACK
                    client.ack(stream_in, group_name, msg_id)
                    
                except Exception as e:
                    logger.error(f"Error processing media for message: {e}")

if __name__ == "__main__":
    run()
