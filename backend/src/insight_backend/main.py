import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.database import init_database, session_scope
from .api.routes.v1.health import router as health_router
from .api.routes.v1.chat import router as chat_router
from .api.routes.v1.data import router as data_router
from .api.routes.v1.mcp import router as mcp_router
from .api.routes.v1.mindsdb import router as mindsdb_router
from .api.routes.v1.auth import router as auth_router
from .repositories.user_repository import UserRepository
from .services.auth_service import AuthService


log = logging.getLogger("insight.main")


def create_app() -> FastAPI:
    app = FastAPI(title="20_insightv2 API", version="0.1.0")

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers v1
    app.include_router(health_router, prefix=f"{settings.api_prefix}/v1", tags=["health"]) 
    app.include_router(chat_router, prefix=f"{settings.api_prefix}/v1", tags=["chat"]) 
    app.include_router(data_router, prefix=f"{settings.api_prefix}/v1", tags=["data"]) 
    app.include_router(mcp_router, prefix=f"{settings.api_prefix}/v1", tags=["mcp"]) 
    app.include_router(mindsdb_router, prefix=f"{settings.api_prefix}/v1", tags=["mindsdb"]) 
    app.include_router(auth_router, prefix=f"{settings.api_prefix}/v1", tags=["auth"])

    @app.on_event("startup")
    def _startup() -> None:
        init_database()
        with session_scope() as session:
            created = AuthService(UserRepository(session)).ensure_admin_user(
                settings.admin_username,
                settings.admin_password,
            )
            if created:
                log.info("Default admin user created: %s", settings.admin_username)

    return app


app = create_app()
