import logging
from flask import Blueprint, request, jsonify
from database.db_client import DBClient
from utils.security import api_key_required

logger = logging.getLogger(__name__)
subscriptions_bp = Blueprint('subscriptions', __name__)

db_client = DBClient()

@subscriptions_bp.route('/', methods=['POST'])
@api_key_required
def add_subscription():
    """
    Registra un nuevo webhook (suscriptor) en el sistema.
    """
    data = request.json
    name = data.get("name")
    webhook_url = data.get("webhook_url")
    auth_token = data.get("auth_token")
    events = data.get("events", ["message.normalized", "message.status_updated"])

    if not name or not webhook_url:
        return jsonify({"error": "name and webhook_url are required"}), 400

    try:
        sub_id = db_client.add_subscription(name, webhook_url, auth_token, events)
        return jsonify({
            "success": True, 
            "message": "Subscription added successfully", 
            "subscription_id": sub_id
        }), 201
    except Exception as e:
        logger.error(f"Error adding subscription: {e}")
        return jsonify({"error": str(e)}), 500

@subscriptions_bp.route('/', methods=['GET'])
@api_key_required
def list_subscriptions():
    """
    Lista todos los webhooks registrados.
    """
    try:
        subs = db_client.get_all_subscriptions()
        return jsonify({"success": True, "subscriptions": subs}), 200
    except Exception as e:
        logger.error(f"Error listing subscriptions: {e}")
        return jsonify({"error": str(e)}), 500
