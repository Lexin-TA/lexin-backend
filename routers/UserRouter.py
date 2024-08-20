from fastapi import APIRouter, Request

from internal.auth import JWTDecodeDep, OAuth2FormDep
from internal.database import SessionDep
from models.TokenModel import Token, RefreshTokenCreate
from models.UserModel import UserRead, UserCreate
from services import UserService, UserGoogleService

router = APIRouter(prefix="/user")


@router.post("/register", response_model=UserRead)
def register(*, session: SessionDep, user_create: UserCreate):
    db_user_create = UserService.create_user(session, user_create)

    return db_user_create


@router.get("/me", response_model=UserRead)
def read_users_me(*, session: SessionDep, token_payload: JWTDecodeDep):
    current_user = UserService.get_current_user(session, token_payload)

    return current_user


@router.post("/token", response_model=Token)
def login(*, session: SessionDep,
          form_data: OAuth2FormDep):
    token = UserService.login_for_access_token(session, form_data)

    return token


@router.post("/refresh", response_model=Token)
def refresh_access_token(*, session: SessionDep, refresh_token_create: RefreshTokenCreate):
    token = UserService.get_access_token_with_refresh_token(session, refresh_token_create)

    return token


@router.get("/google")
async def login_google(request: Request):
    redirect_to_google_auth_page = await UserGoogleService.get_login_google(request)

    return redirect_to_google_auth_page


@router.get("/auth/google")
async def auth_google(*, session: SessionDep, request: Request):
    redirect_to_frontend = await UserGoogleService.get_auth_google(session, request)

    return redirect_to_frontend
