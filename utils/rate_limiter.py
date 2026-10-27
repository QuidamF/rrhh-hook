import redis
import time
import logging
from functools import wraps
from flask import request, jsonify
from config.config import Config

logger = logging.getLogger(__name__)

# Shared Redis connection for rate limiting
try:
    _redis = redis.from_url(Config.REDIS_URL, decode_responses=True)
    _redis.ping()
except Exception as e:
    logger.error(f"RateLimiter: Could not connect to Redis: {e}")
    _redis = None

import random

def get_dynamic_limit(identifier, base_limit):
    """
    Generates a slightly randomized limit per identifier to prevent 
    attackers from precisely measuring the rate limit.
    The limit is persisted in Redis for 1 hour to maintain consistency for the user.
    """
    if not _redis:
        return base_limit
        
    limit_key = f"limit_val:{identifier}"
    try:
        assigned_limit = _redis.get(limit_key)
        if not assigned_limit:
            # Randomize between 85% and 115% of the base limit
            variation = int(base_limit * 0.15)
            assigned_limit = base_limit + random.randint(-variation, variation)
            _redis.set(limit_key, assigned_limit, ex=3600) # Change every hour
        return int(assigned_limit)
    except Exception:
        return base_limit

def rate_limit(limit=60, window=60, key_prefix="rl"):
    """
    Rate limiting decorator with dynamic limits.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not _redis:
                return f(*args, **kwargs)

            api_key = request.headers.get("X-API-Key")
            identifier = api_key if api_key else request.remote_addr
            
            # Get the randomized limit for this specific identifier
            dynamic_limit = get_dynamic_limit(identifier, limit)
            
            current_window = int(time.time() / window)
            key = f"{key_prefix}:{identifier}:{current_window}"
            
            try:
                pipe = _redis.pipeline()
                pipe.incr(key)
                pipe.expire(key, window + 10)
                results = pipe.execute()
                
                count = results[0]
                
                if count > dynamic_limit:
                    logger.warning(f"Dynamic rate limit ({dynamic_limit}) exceeded for {identifier}")
                    return jsonify({
                        "error": "Too many requests",
                        "message": "Rate limit exceeded. Try again later.",
                        "retry_after": window - (int(time.time()) % window)
                    }), 429
                    
            except Exception as e:
                logger.error(f"Error in rate limiter: {e}")
                return f(*args, **kwargs)
                
            return f(*args, **kwargs)
        return wrapped
    return decorator
