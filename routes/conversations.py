from flask import Blueprint, request, jsonify
from database.repositories.conversation_repo import ConversationRepository
from services.message_service import MessageService
from utils.security import api_key_required

conversations_bp = Blueprint("conversations", __name__)
repo = ConversationRepository()
message_service = MessageService()

@conversations_bp.route("/conversations", methods=["GET"])
@api_key_required
def list_conversations():
    filters = {
        "status": request.args.get("status"),
        "assigned_to": request.args.get("assigned_to"),
        "unread_only": request.args.get("unread_only") == "true"
    }
    
    limit = int(request.args.get("limit", 50))
    conversations = repo.list_conversations(filters, limit)
    
    # Clean up _id for JSON serialization
    for conv in conversations:
        conv["_id"] = str(conv["_id"])
        if conv.get("last_message_id"):
            conv["last_message_id"] = str(conv["last_message_id"])
            
    return jsonify(conversations), 200

@conversations_bp.route("/conversations/<conversation_key>/profile", methods=["GET"])
@api_key_required
def get_conversation_profile(conversation_key):
    conv = repo.get_by_key(conversation_key)
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    
    profile = conv.get("client_profile", {})
    return jsonify(profile), 200

@conversations_bp.route("/conversations/<conversation_key>", methods=["PATCH"])
@api_key_required
def update_conversation(conversation_key):
    data = request.json
    
    # If updating assignment, use the service for dual-write
    if "assigned_to" in data and len(data) == 1:
        success = message_service.assign_conversation(conversation_key, data["assigned_to"])
        if success:
            return jsonify({"status": "updated", "assigned_to": data["assigned_to"]}), 200
        return jsonify({"error": "Conversation not found"}), 404

    # For other updates or mixed updates
    result = repo.update_conversation(conversation_key, data)
    
    # If assigned_to was part of a larger update, ensure Postgres is updated too
    if "assigned_to" in data:
        message_service.assign_conversation(conversation_key, data["assigned_to"])

    if result.matched_count:
        return jsonify({"status": "updated"}), 200
    return jsonify({"error": "Conversation not found"}), 404

@conversations_bp.route("/conversations/<conversation_key>/read", methods=["POST"])
@api_key_required
def mark_as_read(conversation_key):
    repo.reset_unread(conversation_key)
    return jsonify({"status": "read"}), 200

@conversations_bp.route("/conversations/<conversation_key>", methods=["DELETE"])
@api_key_required
def delete_conversation(conversation_key):
    success, message = message_service.delete_conversation_complete(conversation_key)
    if success:
        return jsonify({"status": "success", "message": message}), 200
    return jsonify({"status": "error", "message": message}), 404
