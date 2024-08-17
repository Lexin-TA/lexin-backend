from sqlmodel import SQLModel


# Data model used for requests/responses in the application.
# Token model for JWT authentication
class Token(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str


class RefreshTokenCreate(SQLModel):
    refresh_token: str
