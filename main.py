import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from internal.database import create_db_and_tables
from routers import HealthCheckRouter, UserRouter

# Load Environment Variables.
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")


# Database Setup.
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


# FastAPI Application.
class LexinBackendMicroservice(FastAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__ws_connections = dict()


app = LexinBackendMicroservice(lifespan=lifespan)


# Middleware Setup.
origins = ["*"]

app.add_middleware(CORSMiddleware,
                   allow_origins=origins,
                   allow_credentials=True,
                   allow_methods=["*"],
                   allow_headers=["*"])

app.add_middleware(SessionMiddleware,
                   secret_key=SECRET_KEY)


# Router Setup.
default_router = APIRouter(prefix="/api/v1")
default_router.include_router(HealthCheckRouter.router)
default_router.include_router(UserRouter.router, tags=['user'])

app.include_router(default_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app="main:app", host="127.0.0.1", port=80, reload=True)
