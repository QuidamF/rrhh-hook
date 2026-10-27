import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Config:
    # Server
    PORT = int(os.getenv("PORT", 5000))
    API_KEY = os.getenv("API_KEY", "default_secret")

    # Meta
    VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
    APP_SECRET = os.getenv("APP_SECRET")
    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
    PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN")

    # MongoDB (Keep for legacy or hybrid)
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://host.docker.internal:27018/omnicanal")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "omnicanal")

    # Redis (Streams and Locking)
    REDIS_URL = os.getenv("REDIS_URL", "redis://host.docker.internal:6388/0")

    # PostgreSQL (Core persistence)
    PG_URL = os.getenv("PG_URL", "postgresql://admin:admin123@host.docker.internal:5444/omnicanal")

    # Media Storage
    MEDIA_ROOT = os.getenv("MEDIA_ROOT", "media")
    MEDIA_URL_BASE = os.getenv("MEDIA_URL_BASE", "https://omnichanel.jpm-dev.mx/media")

    # AI / Ollama & Gemini
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
    USE_GEMINI = os.getenv("USE_GEMINI", "false").lower() == "true"
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    
    # AI UX
    ENABLE_TYPING_DELAY = os.getenv("ENABLE_TYPING_DELAY", "true").lower() == "true"

    @staticmethod
    def validate():
        missing = []
        if not Config.VERIFY_TOKEN: missing.append("VERIFY_TOKEN")
        if not Config.TELEGRAM_BOT_TOKEN: missing.append("TELEGRAM_BOT_TOKEN")
        if Config.API_KEY == "default_secret" or not Config.API_KEY:
            print("SECURITY WARNING: API_KEY is using default value ('default_secret') or not set. Please set a secure key in .env.")
        
        if missing:
            print(f"WARNING: Missing environment variables: {', '.join(missing)}")
