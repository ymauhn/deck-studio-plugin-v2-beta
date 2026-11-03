"""create_app: the studio's FastAPI app, with security, core routes and every feature router."""
import asyncio
import importlib
import pkgutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from deck_studio import features
from deck_studio.server.api import ApiError
from deck_studio.server.routes import chats, core
from deck_studio.server.security import Security


def feature_modules():
    """Every module in deck_studio/features: each exports `router`, and optionally startup(state)/shutdown(state)."""
    return [importlib.import_module(f"{features.__name__}.{m.name}") for m in pkgutil.iter_modules(features.__path__)]


def create_app(state):
    modules = feature_modules()

    @asynccontextmanager
    async def lifespan(app):
        first_build = asyncio.ensure_future(state.builder.build_studio())  # runs while the server starts serving
        for m in modules:
            if hasattr(m, "startup"):
                await m.startup(state)
        yield
        for m in modules:
            if hasattr(m, "shutdown"):
                await m.shutdown(state)
        for chat in state.chats.values():
            if chat.session:
                await chat.session.close()
        first_build.cancel()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.studio = state
    app.add_middleware(Security, state=state)
    app.add_exception_handler(ApiError, lambda request, e: JSONResponse({"error": e.error, "message": e.message}, e.status))
    app.include_router(core.router)
    app.include_router(chats.router)
    for m in modules:
        app.include_router(m.router)
    return app
