import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT
from app.main import create_app

(ROOT / "backend/openapi.json").write_text(
    json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
