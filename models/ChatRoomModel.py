from datetime import datetime, timezone

from sqlmodel import SQLModel, Field, Relationship

from models.UserModel import User


# Base model.
class ChatRoomBase(SQLModel):
    title: str


# Database model used for tables in the db.
class ChatRoom(ChatRoomBase, table=True):
    __tablename__ = "chat_room"

    # Attributes.
    id: int | None = Field(default=None, primary_key=True)
    creation_time: datetime = Field(default=datetime.now(timezone.utc))
    user_id: int = Field(foreign_key='users.id')

    # Relationships.
    user: User = Relationship(back_populates='chat_rooms')
    chat_messages: list['ChatMessage'] = Relationship(back_populates='chat_room',
                                                      sa_relationship_kwargs={'cascade': 'all, delete, delete-orphan'})


# Data model used for requests/responses in the application.
class ChatRoomCreate(ChatRoomBase):
    pass


class ChatRoomRead(ChatRoomBase):
    id: int
