from sqlmodel import SQLModel


# Data model used for requests/responses in the application.
# GoogleUser model for capturing userinfo upon successful google authentication.
class UserGoogle(SQLModel):
    sub: int
    email: str
    name: str
    picture: str
