"""Demo entrypoint that extends the existing OCEAN 3D FastAPI app."""
from .main import app
from .adaptive_api import router as adaptive_router

app.include_router(adaptive_router)
