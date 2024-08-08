from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session

from internal.authorization import oauth2_scheme
from internal.database import get_session
from models.TokenModel import Token
from models.UserModel import UserRead, UserCreate
from services import UserService

router = APIRouter(prefix="/user")


@router.post("/register", response_model=UserRead)
def register(*, session: Session = Depends(get_session), user_create: UserCreate):
    db_user_create = UserService.create_user(session, user_create)

    return db_user_create


@router.get("/me", response_model=UserRead)
def read_users_me(*, session: Session = Depends(get_session),
                  token: Annotated[str, Depends(oauth2_scheme)]):
    # email is stored as form_data.username to comply with OAuth2 specification of needing username and password fields.
    current_user = UserService.get_current_user(session, token)

    return current_user


@router.post("/token", response_model=Token)
def login(*, session: Session = Depends(get_session), form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    result = UserService.login_for_access_token(session, form_data)

    return result
