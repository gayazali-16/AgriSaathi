from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.api import router
from backend.config import ROOT
from backend.database import init_database
from backend.observability import REQUEST_ID

FRONTEND_DIST = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgriSaathi API",
        version="0.1.0",
        description="Evidence-aware agricultural support prototype API.",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.middleware("http")
    async def request_observability(request, call_next):
        request_id = uuid.uuid4().hex
        token = REQUEST_ID.set(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            logging.getLogger("agrisathi.request").info(
                "request_complete",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            REQUEST_ID.reset(token)

    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def frontend_home():
        index = FRONTEND_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse(
            "<!doctype html><html lang='en'><meta charset='utf-8'><title>AgriSaathi API</title>"
            "<main style='font:16px system-ui;max-width:42rem;margin:4rem auto;padding:1rem'>"
            "<h1>AgriSaathi API is running</h1><p>Build and run the React app from <code>frontend/</code> "
            "to use the interface.</p><p><a href='/docs'>Open API documentation</a></p></main></html>"
        )

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend_route(path: str):
        if path == "api" or path.startswith("api/") or path == "docs" or path.startswith("docs/"):
            raise HTTPException(status_code=404, detail="Not found.")
        root = FRONTEND_DIST.resolve()
        candidate = (root / Path(path)).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        index = root / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend build is not available.")

    return app


app = create_app()
