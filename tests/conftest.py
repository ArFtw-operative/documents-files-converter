import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "apps" / "api", ROOT / "services", ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import tempfile  # noqa: E402

_RUNTIME = Path(tempfile.mkdtemp(prefix="folio-test-"))
os.environ.setdefault("FOLIO_ENV", "test")
os.environ.setdefault("FOLIO_DATABASE_URL", f"sqlite:///{_RUNTIME / 'folio.db'}")
os.environ.setdefault("FOLIO_DATA_DIR", str(_RUNTIME / "storage"))
os.environ.setdefault("FOLIO_ENGINE_MODE", "inline")

import pytest  # noqa: E402

from tests.golden.generate import build_all  # noqa: E402


@pytest.fixture(scope="session")
def golden(tmp_path_factory) -> dict[str, Path]:
    return build_all(tmp_path_factory.mktemp("golden"))
