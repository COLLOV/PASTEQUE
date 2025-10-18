from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .api.routes.v1.health import router as health_router
from .api.routes.v1.chat import router as chat_router
from .api.routes.v1.data import router as data_router
from .api.routes.v1.mcp import router as mcp_router
from .api.routes.v1.mindsdb import router as mindsdb_router


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

    return app


app = create_app()
