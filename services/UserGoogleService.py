from authlib.integrations.base_client import OAuthError
from authlib.oauth2.rfc6749 import OAuth2Token
from fastapi import Request, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from starlette.responses import RedirectResponse

from internal.authorization import create_access_token, create_refresh_token
from internal.authorization_google import oauth, GOOGLE_REDIRECT_URI, FRONTEND_URL
from models.UserGoogleModel import UserGoogle
from models.UserModel import User


# Get User object by google sub.
def get_user_by_google_sub(session: Session, google_sub: int) -> User:
    try:
        statement = select(User).where(User.google_sub == str(google_sub))
        result = session.exec(statement)
        db_user = result.first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_user


# Create User object from Google's userinfo.
def create_user_from_google_info(session: Session, user_google: UserGoogle) -> User:
    google_sub = str(user_google.sub)
    email = user_google.email
    name = user_google.name

    # Query user based on email if exists.
    statement = select(User).where(User.email == email)
    result = session.exec(statement)
    db_user = result.first()

    try:
        # If user is found, update google_sub attribute on User model
        if db_user:
            db_user.google_sub = google_sub
            session.commit()
            return db_user

        # If user is not found, create a new User.
        else:
            new_user = User(fullname=name,
                            email=email,
                            google_sub=google_sub)

            session.add(new_user)
            session.commit()
            session.refresh(new_user)
            return new_user
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))


# Redirect to Google's login page.
async def get_login_google(request: Request):
    # Request Google authorization page.
    result = await oauth.google.authorize_redirect(request, GOOGLE_REDIRECT_URI)

    # After successful login, go to GOOGLE_REDIRECT_URI (specifically, go to get_auth_google function).
    return result


# Validate the request's Google access token to get user information, then create user access and refresh token.
async def get_auth_google(session: Session, request: Request):
    # Get user information from Google access token.
    try:
        user_response: OAuth2Token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    # Extract userinfo from the response.
    user_info = user_response.get("userinfo")

    # Map userinfo to UserGoogle class then use it to find the corresponding User class.
    google_user = UserGoogle(**user_info)
    db_user = get_user_by_google_sub(session=session, google_sub=google_user.sub)

    if not db_user:
        db_user = create_user_from_google_info(session=session, user_google=google_user)

    # Create access and refresh tokens.
    token_data = {"sub": db_user.id}

    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return RedirectResponse(f"{FRONTEND_URL}/auth?access_token={access_token}&refresh_token={refresh_token}")
