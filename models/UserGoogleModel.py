from sqlmodel import SQLModel


class UserGoogle(SQLModel):
    sub: int
    email: str
    name: str
    picture: str
