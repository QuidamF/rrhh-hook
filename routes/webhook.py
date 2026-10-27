import hmac
import hashlib
import logging
from flask import Blueprint, request, jsonify, abort
from config.config import Config
from services.stream_client import StreamClient
from utils.rate_limiter import rate_limit

logger = logging.getLogger(__name__)
webhook_bp = Blueprint("webhook", __name__)
stream_client = StreamClient()

def verify_meta_signature(data, signature):
    """Verifies that the payload comes from Meta using HMAC-SHA256."""
    if not Config.APP_SECRET:
        logger.warning("APP_SECRET not configured, skipping signature verification.")
        return True
    
    if not signature:
        return False
        
    expected_sig = "sha256=" + hmac.new(
        Config.APP_SECRET.encode('utf-8'),
        data,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_sig, signature)

def verify_telegram_token(token):
    """Verifies the secret token from Telegram."""
    if not Config.TELEGRAM_SECRET_TOKEN:
        return True
    return hmac.compare_digest(Config.TELEGRAM_SECRET_TOKEN, token or "")

@webhook_bp.route("/webhook", methods=["GET"])
def verify():
    """Meta Webhook verification (Challenge)."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == Config.VERIFY_TOKEN:
            logger.info("Webhook verified successfully.")
            return challenge, 200
        else:
            logger.warning("Webhook verification failed: Invalid verify token.")
            return "Forbidden", 403
            
    return "Bad Request", 400

@webhook_bp.route("/webhook", methods=["POST"])
@rate_limit(limit=100, window=60, key_prefix="rl_webhook")
def handle_webhook():
    """Receives and pushes raw webhooks after security checks."""
    
    # 1. Identity Verification
    # Meta Signature
    meta_sig = request.headers.get("X-Hub-Signature-256")
    if meta_sig:
        if not verify_meta_signature(request.data, meta_sig):
            logger.error("Invalid Meta signature")
            abort(403)
            
    # Telegram Secret Token
    tg_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if "update_id" in request.json: # Telegram structure
        if not verify_telegram_token(tg_token):
            logger.error("Invalid Telegram secret token")
            abort(403)

    data = request.json
    logger.info(f"Received verified webhook from {request.remote_addr}")
    
    try:
        # PUSH TO INBOUND.RAW
        stream_client.push("inbound.raw", data)
        return jsonify({"status": "accepted"}), 202
    except Exception as e:
        logger.error(f"Error ingesting webhook: {e}")
        return jsonify({"error": "Ingestion failed"}), 500
