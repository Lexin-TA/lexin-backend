from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session

from internal.authorization import oauth2_scheme
from internal.database import get_session
from models.TokenModel import Token, RefreshTokenCreate
from models.UserModel import UserRead, UserCreate
from services import UserService, UserGoogleService

router = APIRouter(prefix="/user")


@router.post("/register", response_model=UserRead)
def register(*, session: Session = Depends(get_session), user_create: UserCreate):
    db_user_create = UserService.create_user(session, user_create)

    return db_user_create


@router.get("/me", response_model=UserRead)
def read_users_me(*, session: Session = Depends(get_session),
                  token: Annotated[str, Depends(oauth2_scheme)]):
    current_user = UserService.get_current_user(session, token)

    return current_user


@router.post("/token", response_model=Token)
def login(*, session: Session = Depends(get_session),
          form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    result = UserService.login_for_access_token(session, form_data)

    return result


@router.post("/refresh", response_model=Token)
def refresh_access_token(*, session: Session = Depends(get_session),
                         refresh_token_create: RefreshTokenCreate):
    result = UserService.get_access_token_with_refresh_token(session, refresh_token_create)

    return result


@router.get("/google")
async def login_google(request: Request):
    result = await UserGoogleService.get_login_google(request)

    return result


@router.get("/auth/google")
async def auth_google(*, session: Session = Depends(get_session), request: Request):
    result = await UserGoogleService.get_auth_google(session, request)

    return result

