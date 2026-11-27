
from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.database.connection import engine

app = FastAPI(
    title="Project Backend API",
    version="1.0.0"
)


@app.get("/")
def home():
    return {
        "message": "Project Marketplace API is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/health/database")
def database_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "database": "connected",
            "status": "healthy"
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed"
        )
