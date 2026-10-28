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
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN", "").strip()
    TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "").strip()

    # Dominio o Subdominio público para Webhook (ej. 'beatifically-combatable-lorette.ngrok-free.dev' o 'webhook.mi-empresa.com')
    WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", os.getenv("PUBLIC_DOMAIN", "")).strip()

    @classmethod
    def get_public_domain(cls) -> str:
        """
        Retorna el dominio o subdominio configurado limpio de protocolo y rutas
        (ej. 'beatifically-combatable-lorette.ngrok-free.dev').
        """
        raw = cls.WEBHOOK_DOMAIN or os.getenv("PUBLIC_DOMAIN", "")
        if not raw and cls.TELEGRAM_WEBHOOK_URL:
            raw = cls.TELEGRAM_WEBHOOK_URL
        if not raw and os.getenv("MEDIA_URL_BASE"):
            raw = os.getenv("MEDIA_URL_BASE")
        
        clean = (raw or "").strip()
        clean = clean.replace("https://", "").replace("http://", "")
        clean = clean.split("/")[0].strip()
        return clean

    @classmethod
    def get_base_url(cls) -> str:
        """
        Retorna la URL base pública HTTPS a partir del dominio/subdominio configurado.
        Ejemplo: 'https://beatifically-combatable-lorette.ngrok-free.dev'
        """
        domain = cls.get_public_domain()
        if domain and not domain.lower().startswith("your_") and not "placeholder" in domain.lower():
            return f"https://{domain}"
        return ""

    @classmethod
    def get_telegram_webhook_url(cls) -> str:
        """
        Obtiene la URL pública HTTPS para el webhook de Telegram con prioridad:
        1. TELEGRAM_WEBHOOK_URL explícita en .env si está configurada
        2. Derivada de WEBHOOK_DOMAIN / PUBLIC_DOMAIN (https://<dominio>/webhook)
        3. Derivada de MEDIA_URL_BASE (sustituyendo /media por /webhook)
        """
        if cls.TELEGRAM_WEBHOOK_URL and "http" in cls.TELEGRAM_WEBHOOK_URL:
            return cls.TELEGRAM_WEBHOOK_URL.strip()
        
        base = cls.get_base_url()
        if base:
            return f"{base}/webhook"

        if cls.MEDIA_URL_BASE and "http" in cls.MEDIA_URL_BASE:
            m_base = cls.MEDIA_URL_BASE.rstrip('/')
            if m_base.endswith('/media'):
                return m_base[:-6] + '/webhook'
            return f"{m_base}/webhook"
        return ""

    @classmethod
    def get_media_url_base(cls) -> str:
        """
        Retorna la URL base pública para servir archivos multimedia (ej. PDFs, audios, fotos).
        Si existe un WEBHOOK_DOMAIN configurado, unifica la URL hacia dicho dominio.
        """
        env_media = os.getenv("MEDIA_URL_BASE", "").strip()
        if env_media and env_media != "https://omnichanel.jpm-dev.mx/media":
            return env_media
        base = cls.get_base_url()
        if base:
            return f"{base}/media"
        return env_media or "https://omnichanel.jpm-dev.mx/media"


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

    # AI / LLM Providers (OpenAI, Gemini & Ollama)
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").lower()
    
    # OpenAI
    USE_OPENAI = os.getenv("USE_OPENAI", "false").lower() == "true"
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # Gemini
    USE_GEMINI = os.getenv("USE_GEMINI", "false").lower() == "true"
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")

    # Ollama
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
    
    # AI UX
    ENABLE_TYPING_DELAY = os.getenv("ENABLE_TYPING_DELAY", "true").lower() == "true"

    @classmethod
    def get_active_provider(cls) -> str:
        """
        Determina dinámicamente el proveedor activo de IA con prioridad:
        1. LLM_PROVIDER explícito ('openai' | 'gemini' | 'ollama')
        2. USE_OPENAI=true o presencia de OPENAI_API_KEY
        3. USE_GEMINI=true con GEMINI_API_KEY
        4. Fallback a Ollama local
        """
        if cls.LLM_PROVIDER in ["openai", "gemini", "ollama"]:
            return cls.LLM_PROVIDER
        if cls.USE_OPENAI and cls.OPENAI_API_KEY:
            return "openai"
        if cls.USE_GEMINI and cls.GEMINI_API_KEY:
            return "gemini"
        if cls.OPENAI_API_KEY and not cls.USE_GEMINI:
            return "openai"
        return "ollama"

    @staticmethod
    def validate():
        missing = []
        if not Config.VERIFY_TOKEN: missing.append("VERIFY_TOKEN")
        if not Config.TELEGRAM_BOT_TOKEN: missing.append("TELEGRAM_BOT_TOKEN")
        if Config.API_KEY == "default_secret" or not Config.API_KEY:
            print("SECURITY WARNING: API_KEY is using default value ('default_secret') or not set. Please set a secure key in .env.")
        
        if missing:
            print(f"WARNING: Missing environment variables: {', '.join(missing)}")
