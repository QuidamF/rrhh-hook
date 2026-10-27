import sys
import os
import json
import logging
import time
import requests

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.stream_client import StreamClient
from database.db_client import DBClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FrontendDispatcher")

def run():
    client = StreamClient()
    pg_db = DBClient()
    
    # We listen to processed messages (after media download) 
    # and delivery receipts (from our own Dispatcher)
    streams = {
        "message.processed": ">",
        "message.status_updated": ">"
    }
    
    group_name = "frontend-dispatcher-group"
    consumer_name = "worker-1"
    
    for stream in streams.keys():
        client.create_group(stream, group_name)
    
    logger.info(f"Frontend Dispatcher started. Reading from {list(streams.keys())}...")
    
    while True:
        results = client.read_group(streams, group_name, consumer_name)
        if not results:
            continue
            
        for stream_name, msgs in results:
            for msg_id, data in msgs:
                try:
                    payload = json.loads(data["payload"])
                    
                    # Wrap payload based on stream origin
                    if stream_name == "message.processed":
                        event_type = "message.normalized" # We keep the event name for subscribers
                        outbound_payload = {
                            "event": "message.received",
                            "data": payload
                        }
                    elif stream_name == "message.status_updated":
                        event_type = "message.status_updated"
                        outbound_payload = payload # Already wrapped by dispatcher_worker
                    else:
                        event_type = stream_name
                        outbound_payload = payload
                    
                    # 1. Get Active Subscribers for this event
                    subscribers = pg_db.get_subscribers(event_type)
                    
                    # 2. Dispatch to all subscribers
                    for sub in subscribers:
                        dispatch_to_webhook(sub["webhook_url"], sub["auth_token"], outbound_payload)
                    
                    # 3. ACK the message in Redis
                    client.ack(stream_name, group_name, msg_id)
                    
                except Exception as e:
                    logger.error(f"Error processing {stream_name} for frontends: {e}")

def dispatch_to_webhook(url, token, payload):
    """
    Sends an HTTP POST to the subscriber URL.
    Uses a short timeout to prevent this worker from blocking.
    """
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    try:
        logger.info(f"Dispatching event '{payload.get('event')}' to {url}")
        # 3 seconds timeout to avoid hanging the worker if Odoo is slow
        response = requests.post(url, json=payload, headers=headers, timeout=3.0)
        
        if response.status_code >= 400:
            logger.warning(f"Subscriber {url} returned HTTP {response.status_code}")
    except requests.exceptions.Timeout:
        logger.error(f"Timeout dispatching to {url}")
    except Exception as e:
        logger.error(f"Failed to dispatch to {url}: {e}")

if __name__ == "__main__":
    run()
