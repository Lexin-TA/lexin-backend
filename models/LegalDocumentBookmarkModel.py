from sqlmodel import SQLModel, Field, Relationship

from models.UserModel import User


# Base model.
class LegalDocumentBookmarkBase(SQLModel):
    document_id: str


# Database model used for tables in the db.
# Legal document bookmark model for saving user's bookmarked legal documents
class LegalDocumentBookmark(LegalDocumentBookmarkBase, table=True):
    __tablename__ = "legal_document_bookmark"

    # Attributes.
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key='users.id')
    document_id: str

    # Relationships.
    user: User = Relationship(back_populates='legal_document_bookmarks')


# Data model used for requests/responses in the application.
class LegalDocumentBookmarkCreate(LegalDocumentBookmarkBase):
    pass


class LegalDocumentBookmarkRead(LegalDocumentBookmarkBase):
    pass
