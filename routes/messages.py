from flask import Blueprint, request, jsonify
from database.repositories.conversation_repo import ConversationRepository
from database.repositories.message_repo import MessageRepository
from services.message_service import MessageService
from utils.security import api_key_required
from utils.rate_limiter import rate_limit

messages_bp = Blueprint("messages", __name__)
message_service = MessageService()
msg_repo = MessageRepository()
conv_repo = ConversationRepository()

@messages_bp.route("/messages", methods=["GET"])
@api_key_required
def get_history():
    conversation_key = request.args.get("conversation_key")
    if not conversation_key:
        return jsonify({"error": "conversation_key is required"}), 400

    conv = conv_repo.get_by_key(conversation_key)
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    limit = int(request.args.get("limit", 50))
    before = request.args.get("before")
    after = request.args.get("after")

    messages = msg_repo.get_history(conv["_id"], limit, before, after)
    
    # Clean up for JSON
    for msg in messages:
        msg["_id"] = str(msg["_id"])
        msg["conversation_id"] = str(msg["conversation_id"])

    return jsonify(messages), 200

@messages_bp.route("/messages/send", methods=["POST"])
@api_key_required
@rate_limit(limit=30, window=60, key_prefix="rl_outbound")
def send_message():
    data = request.json
    conversation_key = data.get("conversation_key")
    text = data.get("text")
    reply_to_message_id = data.get("reply_to_message_id")
    reaction = data.get("reaction")
    actor_id = data.get("actor_id", "human_agent")
    actor_type = data.get("actor_type", "agent")
    origin = data.get("origin", "api")
    client_id = data.get("client_id")
    media_type = data.get("media_type")
    media_url = data.get("media_url")
    media_id = data.get("media_id")
    caption = data.get("caption")
    interactive = data.get("interactive")
    
    if not conversation_key:
        return jsonify({"error": "conversation_key is required"}), 400
        
    if not any([text, reaction, media_type, interactive]):
        return jsonify({"error": "text, reaction, media or interactive content is required"}), 400

    try:
        result = message_service.send_outbound_message(
            conversation_key, 
            text=text, 
            reply_to_message_id=reply_to_message_id,
            reaction=reaction,
            actor_id=actor_id,
            actor_type=actor_type,
            origin=origin,
            client_id=client_id,
            media_type=media_type,
            media_url=media_url,
            media_id=media_id,
            caption=caption,
            interactive=interactive
        )
        return jsonify(result), 200 if result["success"] else 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
