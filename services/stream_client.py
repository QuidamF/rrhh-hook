import redis
import json
import logging
import time
from config.config import Config

logger = logging.getLogger(__name__)

class StreamClient:
    def __init__(self):
        self.redis = redis.from_url(Config.REDIS_URL, decode_responses=True)
        # Verify connection immediately with ping
        max_retries = 5
        for i in range(max_retries):
            try:
                self.redis.ping()
                logger.info("Successfully connected to Redis")
                break
            except Exception as e:
                logger.warning(f"Redis connection attempt {i+1} failed: {e}")
                if i < max_retries - 1:
                    time.sleep(2)
                else:
                    raise

    def push(self, stream_name, data):
        """Pushes a dictionary to a Redis stream."""
        try:
            return self.redis.xadd(stream_name, {"payload": json.dumps(data)})
        except Exception as e:
            logger.error(f"Error pushing to stream {stream_name}: {e}")
            raise

    def create_group(self, stream_name, group_name):
        """Ensures a consumer group exists for a stream."""
        try:
            self.redis.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except redis.exceptions.ResponseError as e:
            if "already exists" not in str(e):
                logger.error(f"Error creating group {group_name}: {e}")
                raise

    def read_group(self, streams, group_name, consumer_name, count=1, block=5000):
        """
        Reads messages from a consumer group.
        'streams' can be a string (single stream) or a dict {stream_name: ">"}.
        """
        if isinstance(streams, str):
            streams = {streams: ">"}
            
        try:
            messages = self.redis.xreadgroup(
                group_name, consumer_name, streams, count=count, block=block
            )
            return messages
        except Exception as e:
            logger.error(f"Error reading from streams {streams.keys()}: {e}")
            return []

    def ack(self, stream_name, group_name, msg_id):
        """Acknowledges a message in a consumer group."""
        try:
            return self.redis.xack(stream_name, group_name, msg_id)
        except Exception as e:
            logger.error(f"Error acking message {msg_id}: {e}")

    def set_lock(self, key, ttl=30):
        """Sets a non-blocking lock."""
        return self.redis.set(key, "locked", ex=ttl, nx=True)

    def release_lock(self, key):
        """Releases a lock."""
        return self.redis.delete(key)
