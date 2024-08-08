from sqlmodel import SQLModel, Field


# Token model for JWT authentication and payload.
class Token(SQLModel, table=True):
    __tablename__ = "token"

    # Attributes
    access_token: str | None = Field(default=None, primary_key=True)
    token_type: str
