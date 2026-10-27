import sys
import os
import json
import logging
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.stream_client import StreamClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BrainWorker")

def run():
    client = StreamClient()
    
    stream_in = "message.processed"
    stream_out = "message.decided"
    group_name = "brain-group"
    consumer_name = "worker-1"
    
    client.create_group(stream_in, group_name)
    
    logger.info(f"Brain Worker (Pass-through) started. Reading from {stream_in}...")
    
    while True:
        messages = client.read_group(stream_in, group_name, consumer_name)
        if not messages:
            continue
            
        for stream, msgs in messages:
            for msg_id, data in msgs:
                try:
                    imo = json.loads(data["payload"])
                    
                    # LOGIC: For now, we just pass it through or 
                    # we could add simple auto-replies here.
                    
                    decision = {
                        "action": "ignore", # Default: just log and ignore
                        "payload": imo
                    }
                    
                    # If it's a specific test message, we could reply
                    if "test" in str(imo.get("content", {})).lower():
                        decision = {
                            "action": "reply",
                            "payload": {
                                "channel": imo["channel"],
                                "to": imo["actor_id"],
                                "text": f"Echo: Recibí tu mensaje correctamente via {imo['channel']}!"
                            }
                        }
                    
                    client.push(stream_out, decision)
                    client.ack(stream_in, group_name, msg_id)
                    logger.info(f"Decided action for {imo.get('external_id')}: {decision['action']}")
                    
                except Exception as e:
                    logger.error(f"Error in Brain Worker: {e}")

if __name__ == "__main__":
    run()
