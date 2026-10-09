"""Uvicorn entrypoint: uvicorn main:app --reload"""

from app.main import app, create_app

__all__ = ["app", "create_app"]
