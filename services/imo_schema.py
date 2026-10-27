from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
import uuid

@dataclass
class IMOv2:
    channel: str
    direction: str
    actor_type: str
    actor_id: str
    content: Dict[str, Any]
    external_id: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: Optional[str] = None
    conversation_key: Optional[str] = None
    channel_account_id: Optional[str] = None
    reply_to: Optional[str] = None
    status: str = "received"
    conversation_state: str = "new_lead"
    metadata: Dict[str, Any] = field(default_factory=dict)
    provider_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self):
        d = self.__dict__.copy()
        if isinstance(d["provider_at"], datetime):
            d["provider_at"] = d["provider_at"].isoformat()
        if isinstance(d["created_at"], datetime):
            d["created_at"] = d["created_at"].isoformat()
        return d

    @classmethod
    def from_dict(cls, data):
        data = data.copy() # Avoid mutating original
        if "provider_at" in data and data["provider_at"]:
            if isinstance(data["provider_at"], str):
                data["provider_at"] = datetime.fromisoformat(data["provider_at"])
        if "created_at" in data and data["created_at"]:
            if isinstance(data["created_at"], str):
                data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)
