"""Application configuration, read from environment variables with safe defaults."""
import os


class Config:
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017")
    MONGO_DB = os.environ.get("MONGO_DB", "trailblazer")
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    TOKEN_LIFETIME_MINUTES = int(os.environ.get("TOKEN_LIFETIME_MINUTES", "60"))
    DEFAULT_PAGE_SIZE = 10
    MAX_PAGE_SIZE = 50
