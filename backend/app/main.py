import logging
from importlib.metadata import version

from fastapi import FastAPI

from app.api.v1.api import api_router
from app.core.config import settings

app = FastAPI(title="CertHub API")
logger = logging.getLogger(__name__)


@app.on_event("startup")
def log_crypto_versions() -> None:
    logger.info(
        "Auth crypto versions: passlib=%s bcrypt=%s",
        version("passlib"),
        version("bcrypt"),
    )


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_v1_prefix)
