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

@webhook_bp.route("/webhook/telegram/status", methods=["GET"])
def telegram_webhook_status():
    """Devuelve el estado actual del webhook registrado en Telegram."""
    from services.telegram_webhook_manager import TelegramWebhookManager
    info = TelegramWebhookManager.get_webhook_info()
    target_url = Config.get_telegram_webhook_url()
    current_url = info.get("current_url", "")
    is_active = info.get("is_active", False)
    matches_target = bool(is_active and target_url and current_url.rstrip("/") == target_url.rstrip("/"))
    
    return jsonify({
        "domain": Config.get_public_domain(),
        "base_url": Config.get_base_url(),
        "target_url": target_url,
        "media_url_base": Config.get_media_url_base(),
        "is_active": is_active,
        "matches_target": matches_target,
        "bot_token_configured": bool(Config.TELEGRAM_BOT_TOKEN and not Config.TELEGRAM_BOT_TOKEN.startswith("your_")),
        "secret_token_configured": bool(Config.TELEGRAM_SECRET_TOKEN and not Config.TELEGRAM_SECRET_TOKEN.startswith("your_")),
        "telegram_api": info
    }), (200 if info.get("ok") else 503)


@webhook_bp.route("/webhook/telegram/setup", methods=["POST"])
def telegram_webhook_setup():
    """Fuerza la sincronización y registro del webhook de Telegram."""
    from services.telegram_webhook_manager import TelegramWebhookManager
    data = request.get_json(silent=True) or {}
    custom_url = data.get("url") or request.args.get("url")
    drop_pending = data.get("drop_pending_updates", False)
    
    res = TelegramWebhookManager.set_webhook(
        webhook_url=custom_url,
        drop_pending_updates=drop_pending
    )
    return jsonify(res), (200 if res.get("ok") else 400)

