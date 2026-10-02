"""Run from any working directory; data paths remain rooted at the repository."""

import uvicorn

from app.config import Settings
from app.main import create_app

if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, workers=1)
