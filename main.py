from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter

from internal.database import create_db_and_tables
from routers import HealthCheckRouter, UserRouter

# Load Environment Variables.
load_dotenv()


# FastAPI Application.
class LexinBackendMicroservice(FastAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__ws_connections = dict()


app = LexinBackendMicroservice()


# Database Setup.
@app.on_event("startup")
def on_startup():
    create_db_and_tables()


# Router Setup.
default_router = APIRouter(prefix="/api/v1")
default_router.include_router(HealthCheckRouter.router)
default_router.include_router(UserRouter.router, tags=['user'])

app.include_router(default_router)
