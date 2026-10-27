import logging
from flask import Blueprint, jsonify
from services.message_service import MessageService
from utils.security import api_key_required

logger = logging.getLogger(__name__)
maintenance_bp = Blueprint("maintenance", __name__)
message_service = MessageService()

@maintenance_bp.route("/maintenance/reset-all", methods=["POST"])
@api_key_required
def reset_all():
    """
    DANGEROUS: Clears all messages and conversations from the database.
    Useful for testing and debugging.
    """
    try:
        message_service.reset_all_data()
        return jsonify({"status": "success", "message": "All data cleared"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@maintenance_bp.route("/debug/frontend-mock", methods=["POST"])
def frontend_mock():
    """
    Mock endpoint to simulate an external system (like Odoo) receiving webhooks.
    """
    from flask import request
    import json
    
    payload = request.json
    
    logger.info("="*50)
    logger.info("🚀 [MOCK ODOO] WEBHOOK RECEIVED!")
    logger.info(f"ID: {payload.get('data', {}).get('id', 'N/A')}")
    logger.info(f"From: {payload.get('data', {}).get('actor_id', 'N/A')} ({payload.get('data', {}).get('channel', 'N/A')})")
    logger.info(f"Event: {payload.get('event')}")
    logger.info(f"Content: {json.dumps(payload.get('data', {}).get('content'), indent=2)}")
    logger.info("="*50)
    
    return jsonify({"status": "received"}), 200
