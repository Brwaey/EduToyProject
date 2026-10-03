from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EDUTOY_", env_file=ROOT / ".env", extra="ignore")
    db_path: str = "data/edutoy.sqlite3"
    host: str = "127.0.0.1"
    port: int = 8000
    secure_cookie: bool = False
    ai_key_path: str = "data/ai-master.key"
    ai_timeout: float = 120
    ai_worker_enabled: bool = True
    origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173"
    )

    @property
    def database_path(self) -> Path:
        path = Path(self.db_path).expanduser()
        return (path if path.is_absolute() else ROOT / path).resolve()

    @property
    def allowed_origins(self) -> set[str]:
        return {origin.strip().rstrip("/") for origin in self.origins.split(",") if origin.strip()}

    @property
    def ai_key_file(self) -> Path:
        path = Path(self.ai_key_path).expanduser()
        return (path if path.is_absolute() else ROOT / path).resolve()
