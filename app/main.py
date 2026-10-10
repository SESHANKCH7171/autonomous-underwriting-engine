"""Main FastAPI Application Entrypoint for Autonomous Underwriting Engine."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from app.api.routes import router as underwriting_router
# pyrefly: ignore [missing-import]
from app.core.config import settings
# pyrefly: ignore [missing-import]
from app.telemetry.logfire_setup import configure_logfire


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: configure telemetry
    configure_logfire(app)
    yield
    # Shutdown: cleanup


app = FastAPI(
    title="Autonomous Financial Risk & Underwriting Engine",
    description="Sub-180ms GCC Underwriting & Compliance State Machine (UAE FTA & KSA SAMA)",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(underwriting_router)

from fastapi.responses import RedirectResponse

@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to interactive Swagger API documentation."""
    return RedirectResponse(url="/docs")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
