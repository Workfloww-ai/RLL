import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import uvicorn

# Ensure root project directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.core.logging_config import setup_logging

# Setup application logging
setup_logging()

import logging
logger = logging.getLogger("main")

from backend.core.config import settings
from backend.auth.router import router as auth_router
from backend.users.router import router as users_router
from backend.master_data.router import router as master_data_router
from backend.uploads.router import router as uploads_router
from backend.dashboard.router import router as dashboard_router
from backend.analytics.router import router as analytics_router
from backend.reports.router import router as reports_router
from backend.mobile.router import router as mobile_router

from contextlib import asynccontextmanager
from backend.db.redis_client import init_redis, close_redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Redis connection pool...")
    await init_redis()
    
    # Pre-warm master lookup cache asynchronously in background on startup
    try:
        import asyncio
        from backend.mobile.router import warm_master_cache
        asyncio.create_task(warm_master_cache())
    except Exception as e:
        logger.warning(f"Master cache warming initiation notice: {e}")

    yield
    logger.info("Closing Redis connection pool...")
    await close_redis()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API Server for Rajasthan Liquor Limited (RLL) Sales Analytics Platform. Processes government daily Excel uploads, master data, real-time dashboards, and analytics.",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import time
from fastapi import Request

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(
        f"API Call - Method: {request.method} | Path: {request.url.path} | "
        f"Status: {response.status_code} | Duration: {duration:.4f}s"
    )
    return response

# Register v1 API Routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(mobile_router, prefix=settings.API_V1_STR)
app.include_router(users_router, prefix=settings.API_V1_STR)
app.include_router(master_data_router, prefix=settings.API_V1_STR)
app.include_router(uploads_router, prefix=settings.API_V1_STR)
# Backwards compatibility for /uploads/ root path
app.include_router(uploads_router)
app.include_router(dashboard_router, prefix=settings.API_V1_STR)
app.include_router(analytics_router, prefix=settings.API_V1_STR)
app.include_router(reports_router, prefix=settings.API_V1_STR)

@app.get("/")
def read_root():
    return {
        "title": settings.PROJECT_NAME,
        "status": "running",
        "version": settings.VERSION,
        "docs": "/docs"
    }

if __name__ == "__main__":

    port = int(os.environ.get("PORT", settings.PORT))
    host = os.environ.get("HOST", "0.0.0.0")
    is_dev = os.environ.get("ENVIRONMENT", "development") == "development"
    
    uvicorn.run("main:app", host=host, port=port, reload=is_dev)