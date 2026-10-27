import psycopg2
import psycopg2.extras
import psycopg2.pool
import time
import logging
from contextlib import contextmanager
from config.config import Config

logger = logging.getLogger(__name__)

class DBClient:
    _pool = None

    def __init__(self):
        if DBClient._pool is None:
            self._initialize_pool()

    def _initialize_pool(self):
        max_retries = 5
        retry_delay = 5
        for i in range(max_retries):
            try:
                DBClient._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=20,
                    dsn=Config.PG_URL
                )
                logger.info("PostgreSQL Connection Pool initialized successfully")
                break
            except Exception as e:
                logger.warning(f"Database pool initialization attempt {i+1} failed: {e}")
                if i < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logger.error("Could not initialize PostgreSQL pool")
                    raise

    @contextmanager
    def get_cursor(self):
        conn = DBClient._pool.getconn()
        conn.autocommit = True
        try:
            yield conn.cursor()
        finally:
            DBClient._pool.putconn(conn)

    def upsert_conversation(self, channel, external_user_id):
        conv_key = f"{channel}:{external_user_id}"
        with self.get_cursor() as cur:
            cur.execute("""
                INSERT INTO conversations (conversation_key, channel, external_user_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (conversation_key) DO UPDATE 
                SET updated_at = NOW()
                RETURNING id, current_state, assigned_to
            """, (conv_key, channel, external_user_id))
            return cur.fetchone()

    def update_conversation_assignment(self, conversation_key, assigned_to):
        with self.get_cursor() as cur:
            cur.execute("""
                UPDATE conversations 
                SET assigned_to = %s, updated_at = NOW()
                WHERE conversation_key = %s
            """, (assigned_to, conversation_key))

    def insert_message(self, imo):
        with self.get_cursor() as cur:
            cur.execute("""
                INSERT INTO messages (
                    id, conversation_id, external_id, channel, direction, 
                    actor_type, actor_id, content, metadata, provider_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (external_id) DO NOTHING
            """, (
                imo.id, imo.conversation_id, imo.external_id, imo.channel, 
                imo.direction, imo.actor_type, imo.actor_id, 
                psycopg2.extras.Json(imo.content), 
                psycopg2.extras.Json(imo.metadata), 
                imo.provider_at
            ))

    def update_message_content(self, message_id, new_content):
        with self.get_cursor() as cur:
            cur.execute("""
                UPDATE messages 
                SET content = content || %s::jsonb
                WHERE id = %s
            """, (psycopg2.extras.Json(new_content), message_id))

    def get_history(self, conversation_id, limit=10):
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT direction, content FROM messages 
                WHERE conversation_id = %s 
                ORDER BY created_at DESC LIMIT %s
            """, (conversation_id, limit))
            rows = cur.fetchall()
            return [{"direction": r[0], "content": r[1]} for r in rows]

    def delete_all(self):
        with self.get_cursor() as cur:
            cur.execute("DELETE FROM messages")
            cur.execute("DELETE FROM conversations")

    def add_subscription(self, name, webhook_url, auth_token=None, events=None):
        if events is None:
            events = ["message.normalized", "message.status_updated"]
        with self.get_cursor() as cur:
            cur.execute("""
                INSERT INTO subscriptions (name, webhook_url, auth_token, events)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (webhook_url) DO UPDATE 
                SET name = EXCLUDED.name, auth_token = EXCLUDED.auth_token, 
                    events = EXCLUDED.events, updated_at = NOW()
                RETURNING id
            """, (name, webhook_url, auth_token, psycopg2.extras.Json(events)))
            return cur.fetchone()[0]

    def get_subscribers(self, event_type):
        with self.get_cursor() as cur:
            # Querying JSONB array to check if it contains the event_type
            cur.execute("""
                SELECT webhook_url, auth_token FROM subscriptions 
                WHERE is_active = TRUE AND events @> %s
            """, (psycopg2.extras.Json([event_type]),))
            # fetchall returns a list of tuples like [('url', 'token'), ...]
            # We will convert it to a list of dicts for easier use
            rows = cur.fetchall()
            return [{"webhook_url": r[0], "auth_token": r[1]} for r in rows]

    def get_all_subscriptions(self):
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT id, name, webhook_url, auth_token, events, is_active, created_at
                FROM subscriptions
            """)
            rows = cur.fetchall()
            return [
                {
                    "id": str(r[0]), "name": r[1], "webhook_url": r[2], 
                    "auth_token": r[3], "events": r[4], "is_active": r[5],
                    "created_at": r[6].isoformat() if r[6] else None
                } for r in rows
            ]
