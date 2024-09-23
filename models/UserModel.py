from pydantic import EmailStr
from sqlmodel import SQLModel, Field, Relationship


# Base model.
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True)


# Database model used for tables in the db.
class User(UserBase, table=True):
    __tablename__ = "users"

    # Attributes.
    id: int | None = Field(default=None, primary_key=True)
    fullname: str
    password: str | None = Field(default=None)
    google_sub: str | None = Field(default=None, unique=True)

    # Relationships.
    chat_rooms: list['ChatRoom'] = Relationship(
        back_populates='user',
        sa_relationship_kwargs={'cascade': 'all, delete, delete-orphan'}
    )
    legal_document_bookmarks: list['LegalDocumentBookmark'] = Relationship(
        back_populates='user',
        sa_relationship_kwargs={'cascade': 'all, delete, delete-orphan'}
    )


# Data model used for requests/responses in the application.
class UserCreate(UserBase):
    fullname: str
    password: str


class UserRead(UserBase):
    id: int
    fullname: str


class UserUpdate(UserBase):
    fullname: str | None = None
    password: str | None = None


class UserLogin(UserBase):
    password: str
