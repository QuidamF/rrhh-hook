import logging
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import OperationFailure
from config.config import Config

logger = logging.getLogger(__name__)

class MongoDB:
    client: MongoClient = None
    db = None

    @classmethod
    def connect(cls):
        try:
            cls.client = MongoClient(Config.MONGO_URI)
            cls.db = cls.client[Config.DATABASE_NAME]
            logger.info("Successfully connected to MongoDB.")
            cls._ensure_indexes()
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {e}")
            raise

    @classmethod
    def _ensure_indexes(cls):
        """Creates necessary indexes for performance and deduplication."""
        try:
            # Conversations Indexes
            cls.db.conversations.create_index([("conversation_key", ASCENDING)], unique=True)
            cls.db.conversations.create_index([("updated_at", DESCENDING)])
            cls.db.conversations.create_index([("assigned_to", ASCENDING), ("status", ASCENDING)])
            
            # Messages Indexes
            cls.db.messages.create_index([("external_id", ASCENDING)], unique=True, sparse=True)
            cls.db.messages.create_index([("conversation_id", ASCENDING), ("_id", DESCENDING)])
            cls.db.messages.create_index([("client_id", ASCENDING)], sparse=True) # For outbound tracking
            
            logger.info("MongoDB indexes verified/created.")
        except OperationFailure as e:
            if e.code == 86: # IndexKeySpecsConflict
                logger.warning("Index conflict detected. Dropping 'external_id_1' to apply new specs...")
                cls.db.messages.drop_index("external_id_1")
                # Retry ensuring indexes
                cls._ensure_indexes()
            else:
                logger.error(f"Error creating indexes: {e}")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")

    @classmethod
    def get_db(cls):
        if cls.db is None:
            cls.connect()
        return cls.db
