from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from core.config import REDIS_URL
from api.routes import landlord, property, tenant, payment, accounting, ussd, integration
from core.database import engine, Base

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create database tables (no-op if they already exist)
Base.metadata.create_all(bind=engine)

# Some changes to the models may not be reflected by create_all; for example
# adding a column to an existing table won't alter the table automatically.
# On deployment we historically added `metadata_data` to the properties table
# but older databases may still be missing that column, leading to 500 errors
# whenever the ORM queries the table.  Ensure the column exists at startup
# so the app remains backwards compatible with existing deployments.
from sqlalchemy import text
with engine.connect() as conn:
    try:
        # Postgres syntax that safely adds the column if it doesn't exist.
        conn.execute(
            text(
                "ALTER TABLE properties "
                "ADD COLUMN IF NOT EXISTS metadata_data JSON DEFAULT '{}'::jsonb"
            )
        )
        conn.commit()
    except Exception as exc:
        # if we are running on a different backend (e.g. SQLite) or the
        # column already exists, the operation may raise.  We log and move
        # on since the ORM will still work with or without the migration.
        logging.info(f"metadata_data migration skipped: {exc}")

app = FastAPI(
    title="Landlord254 API",
    description="Property Management API with SMS and USSD integration",
    version="1.0.0"
)

# Configure CORS for local development and Vercel deployment
# allow_origins is intentionally narrow during development, but in production
# we permit any Vercel preview domain using a regex.  We also maintain the
# local origins for convenience.  If you want to open the API to all
# origins you can simply use `allow_origins=["*"]` instead.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",           # Local development
        "http://localhost:8000",           # Local API
    ],
    # permit any subdomain of vercel.app (preview deployments, aliases, etc)
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(landlord.router)
app.include_router(property.router)
app.include_router(tenant.router)
app.include_router(payment.router)
app.include_router(accounting.router)
app.include_router(ussd.router)
# Integration endpoints used by n8n and other automation
app.include_router(integration.router)

@app.get("/")
async def root():
    return {
        "message": "Welcome to Landlord254 API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logging.error(f"Global exception: {str(exc)}")
    # include CORS headers for error responses if we received an Origin
    origin = request.headers.get("origin")
    resp = JSONResponse(
        status_code=500,
        content={"message": "Internal server error", "detail": str(exc)}
    )
    if origin:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Vary"] = "Origin"
    return resp

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
