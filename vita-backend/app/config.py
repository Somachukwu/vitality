from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings

# ── Centralized Filesystem Paths ──────────────────────────────────────────────
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
UPLOADS_DIR = BACKEND_DIR / "uploads"
MEALS_UPLOAD_DIR = UPLOADS_DIR / "meals"

# Guarantee that upload directories exist safely on startup
MEALS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "vita_db"

    JWT_SECRET_KEY: str = "change-this-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    APP_ENV: str = "development"
    CORS_ORIGINS: str = "https://somachukwu.github.io,http://localhost:8080,http://localhost:5173,http://localhost:3000,http://localhost:5500,http://127.0.0.1:8080"

    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str

    # Fernet key for encrypting OAuth tokens at rest (generate with: Fernet.generate_key())
    FERNET_SECRET_KEY: str

    # Separate secret for session middleware — must NOT be the same as JWT_SECRET_KEY
    SESSION_SECRET_KEY: str

    # Cloudinary Cloud Storage URL (e.g. cloudinary://API_KEY:API_SECRET@CLOUD_NAME)
    CLOUDINARY_URL: str | None = None

    # Render / Cloud Keep-Alive Settings (prevents free-tier idle spin-down)
    KEEP_ALIVE_URL: str | None = None
    RENDER_EXTERNAL_URL: str | None = None

    @property
    def database_url(self) -> str:
        password = quote_plus(self.DB_PASSWORD)
        return (
            f"mysql+pymysql://{self.DB_USER}:{password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def uploads_dir(self) -> Path:
        return UPLOADS_DIR

    @property
    def meals_upload_dir(self) -> Path:
        return MEALS_UPLOAD_DIR

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    class Config:
        env_file = ".env"


settings = Settings()
