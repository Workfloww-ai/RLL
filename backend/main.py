import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure root project directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.core.config import settings
from backend.auth.router import router as auth_router
from backend.users.router import router as users_router
from backend.master_data.router import router as master_data_router
from backend.uploads.router import router as uploads_router
from backend.dashboard.router import router as dashboard_router
from backend.analytics.router import router as analytics_router
from backend.reports.router import router as reports_router
from backend.mobile.router import router as mobile_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API Server for Rajasthan Liquor Limited (RLL) Sales Analytics Platform. Processes government daily Excel uploads, master data, real-time dashboards, and analytics.",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)