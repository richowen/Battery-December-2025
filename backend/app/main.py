"""
Battery Optimization Service - FastAPI Application
"""
import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app import __version__
from app.config import settings
from app.database import init_db, get_db, get_db_session
from app.api import router as api_router
from app.models import ManualOverride

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# Background task for expiring manual overrides
async def expire_manual_overrides_task():
    """
    Background task to auto-expire manual overrides
    Runs every 5 minutes
    """
    logger.info("Starting manual override expiry background task")
    
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            
            with get_db_session() as db:
                now = datetime.now()
                
                # Find expired overrides that are still active
                expired_overrides = db.query(ManualOverride).filter(
                    and_(
                        ManualOverride.is_active == True,
                        ManualOverride.expires_at <= now
                    )
                ).all()
                
                if expired_overrides:
                    for override in expired_overrides:
                        override.is_active = False
                        override.cleared_at = now
                        override.cleared_by = 'system_expiry'
                        logger.info(
                            f"Auto-expired manual override: {override.immersion_name} "
                            f"(id={override.id}, was {override.desired_state})"
                        )
                    
                    db.commit()
                    logger.info(f"Expired {len(expired_overrides)} manual override(s)")
                
        except Exception as e:
            logger.error(f"Error in manual override expiry task: {e}", exc_info=True)
            await asyncio.sleep(60)  # Wait 1 minute before retrying


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown events"""
    # Startup
    logger.info(f"Starting Battery Optimization Service v{__version__}")
    logger.info(f"Environment: {settings.log_level}")
    
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    
    # Start background task for expiring manual overrides
    expiry_task = asyncio.create_task(expire_manual_overrides_task())
    logger.info("Manual override expiry task started")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Battery Optimization Service")
    expiry_task.cancel()
    try:
        await expiry_task
    except asyncio.CancelledError:
        logger.info("Manual override expiry task cancelled")


# Create FastAPI app
app = FastAPI(
    title="Battery Optimization Service",
    description="Optimizes solar battery charge/discharge using Linear Programming",
    version=__version__,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Battery Optimization Service",
        "version": __version__,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": __version__
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=True
    )