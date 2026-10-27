from functools import wraps
from flask import request, jsonify
from config.config import Config

def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("x-api-key")
        if api_key and api_key == Config.API_KEY:
            return f(*args, **kwargs)
        else:
            return jsonify({"error": "Unauthorized: Invalid or missing API Key"}), 401
    return decorated_function
