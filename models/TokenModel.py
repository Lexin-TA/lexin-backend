from datetime import datetime

from sqlmodel import SQLModel, Field


# Token model for JWT authentication
class Token(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str


class RefreshTokenCreate(SQLModel):
    refresh_token: str
