import logging
from flask import Flask, jsonify
from config.config import Config
from database.mongo_client import MongoDB

# Logging Setup (Must be first)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    # Init DB
    Config.validate()
    MongoDB.connect()
    
    # Delayed Imports to ensure logging is ready and config is validated
    from routes.webhook import webhook_bp
    from routes.conversations import conversations_bp
    from routes.messages import messages_bp
    from routes.maintenance import maintenance_bp
    from routes.subscriptions import subscriptions_bp
    
    # Register Blueprints
    app.register_blueprint(webhook_bp)
    app.register_blueprint(conversations_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(subscriptions_bp, url_prefix='/subscriptions')
    
    # Auto-configuración de Telegram Webhook al levantar la aplicación
    try:
        from services.telegram_webhook_manager import TelegramWebhookManager
        TelegramWebhookManager.auto_configure_on_startup()
    except Exception as e:
        logger.warning(f"No se pudo ejecutar auto-configuración de Telegram al iniciar: {e}")

    
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "healthy"}), 200

    @app.route("/media/<path:filename>")
    def serve_media(filename):
        from flask import send_from_directory
        import mimetypes
        mimetypes.add_type('application/pdf', '.pdf')
        return send_from_directory(Config.MEDIA_ROOT, filename)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=Config.PORT)
