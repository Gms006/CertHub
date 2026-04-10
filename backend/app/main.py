import logging
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.api import api_router
from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Auth crypto versions: passlib=%s bcrypt=%s",
        version("passlib"),
        version("bcrypt"),
    )
    yield


app = FastAPI(
    title="CertHub API",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

redoc_assets_dir = static_dir / "redoc"


@app.get("/redoc", response_class=HTMLResponse, include_in_schema=False)
async def redoc_html():
    local_redoc = redoc_assets_dir / "redoc.standalone.js"

    if local_redoc.exists():
        script_src = "/static/redoc/redoc.standalone.js"
    else:
        script_src = "https://cdn.jsdelivr.net/npm/redoc@2.1.5/bundles/redoc.standalone.js"

    return f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>CertHub API - ReDoc</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          body {{
            margin: 0;
            padding: 0;
          }}
        </style>
      </head>
      <body>
        <noscript>
          ReDoc requires Javascript to function. Please enable it to browse the documentation.
        </noscript>
        <redoc spec-url="/openapi.json"></redoc>
        <script src="{script_src}"></script>
      </body>
    </html>
    """


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_v1_prefix)