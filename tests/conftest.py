import os
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test-convertvault.db")
os.environ.setdefault("STORAGE_PROVIDER", "local")
os.environ.setdefault("LOCAL_STORAGE_PATH", "./data/test-files")

database = Path("data/test-convertvault.db")
database.parent.mkdir(exist_ok=True)
database.unlink(missing_ok=True)

