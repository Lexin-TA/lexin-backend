from datetime import datetime, timezone

from sqlmodel import SQLModel, Field, Relationship

from models.ChatRoomModel import ChatRoom


# Base model.
class ChatMessageBase(SQLModel):
    question: str
    answer: str


# Database model used for tables in the db.
class ChatMessage(ChatMessageBase, table=True):
    __tablename__ = "chat_message"

    # Attributes.
    id: int | None = Field(default=None, primary_key=True)
    creation_time: datetime = Field(default=datetime.now(timezone.utc))
    chat_room_id: int = Field(foreign_key='chat_room.id')

    # Relationships.
    chat_room: ChatRoom = Relationship(back_populates='chat_messages')


# Data model used for requests/responses in the application.
class ChatMessageCreate(ChatMessageBase):
    pass


class ChatMessageRead(ChatMessageBase):
    creation_time: datetime
