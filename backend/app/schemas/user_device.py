import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserRead


class UserDeviceCreate(BaseModel):
    user_id: uuid.UUID
    device_id: uuid.UUID
    is_allowed: bool = True


class UserDeviceRead(UserDeviceCreate):
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserDeviceReadWithUser(UserDeviceRead):
    user: UserRead
