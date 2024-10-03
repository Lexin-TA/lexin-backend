from datetime import datetime, timezone

from sqlmodel import SQLModel, Field, Relationship

from models.UserModel import User


# Base model.
class ChatRoomBase(SQLModel):
    pass


# Database model used for tables in the db.
class ChatRoom(ChatRoomBase, table=True):
    __tablename__ = "chat_room"

    # Attributes.
    id: int | None = Field(default=None, primary_key=True)
    title: str
    creation_time: datetime = Field(default=datetime.now(timezone.utc))
    bookmark: bool = Field(default=False)
    user_id: int = Field(foreign_key='users.id')

    # Relationships.
    user: User = Relationship(back_populates='chat_rooms')
    chat_messages: list['ChatMessage'] = Relationship(back_populates='chat_room',
                                                      sa_relationship_kwargs={'cascade': 'all, delete, delete-orphan'})


# Data model used for requests/responses in the application.
class ChatRoomCreate(ChatRoomBase):
    title: str


class ChatRoomRead(ChatRoomBase):
    id: int
    title: str
    creation_time: datetime
    bookmark: bool
    user_id: int


class ChatRoomUpdate(ChatRoomBase):
    bookmark: bool | None = None
