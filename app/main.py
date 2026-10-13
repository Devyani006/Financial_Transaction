import logging
import sys
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on sys.path when running via uvicorn
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.routes import router
from app.db.connection import check_connectivity
from app.config import settings, ConfigError

# Logging setup
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# App instance
app = FastAPI(
    title="Financial Transaction Intelligence API",
    description=(
        "SQL-first fintech analytics API for transaction monitoring, "
        "anomaly detection, and business intelligence."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
# Allow the Streamlit dashboard (running on a different port) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Exception handlers

@app.exception_handler(ConfigError)
async def config_error_handler(request: Request, exc: ConfigError):
    logger.error("Configuration error: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"error": "Service misconfigured", "detail": str(exc)}
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    # Log the full traceback internally but return a safe message externally
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


# Startup event

@app.on_event("startup")
async def startup_event():
    logger.info("FTI API starting up…")
    health = check_connectivity()
    if health["status"] == "ok":
        logger.info("Database connected: MySQL %s", health.get("mysql_version", ""))
    else:
        logger.warning("Database connectivity issue at startup: %s", health.get("detail", ""))


# Router

app.include_router(router, prefix="/api/v1")


# Root

@app.get("/", tags=["System"])
def root():
    return {
        "name": "Financial Transaction Intelligence API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
