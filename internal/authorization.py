# Load environment variables.
import os
from datetime import datetime, timezone, timedelta

import jwt
from dotenv import load_dotenv
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext


# Load Environment Variables.
load_dotenv()

JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30                # 30 minutes
JWT_REFRESH_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7      # 7 days
JWT_ALGORITHM = "HS256"
JWT_ACCESS_SECRET_KEY = os.getenv('JWT_ACCESS_SECRET_KEY')
JWT_REFRESH_SECRET_KEY = os.getenv('JWT_REFRESH_SECRET_KEY')


# Create PassLib context to hash and verify passwords.
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# OAuth2 specifies that the client/user must send a username and password fields as form data.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/user/token", scheme_name="JWT")


# Authorization utility functions.
def get_hashed_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, hashed_pass: str) -> bool:
    return password_context.verify(password, hashed_pass)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_ACCESS_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(JWT_REFRESH_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_REFRESH_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt
