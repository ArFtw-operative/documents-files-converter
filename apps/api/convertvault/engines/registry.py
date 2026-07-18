from .base import Capability, ConversionEngine
from .image import PillowEngine
from .pdf import OcrEngine, PdfEngine
from .pdf_editor import PdfEditorEngine
from .subprocess_engine import LibreOfficeEngine, PandocEngine
from .text import TextExtractionEngine

ENGINES: list[ConversionEngine] = [PillowEngine(), PdfEngine(), PdfEditorEngine(), OcrEngine(), TextExtractionEngine(), LibreOfficeEngine(), PandocEngine()]


def capabilities() -> list[dict]:
    return [cap.json() for engine in ENGINES for cap in engine.capabilities()]


def health() -> list[dict]:
    result = []
    for engine in ENGINES:
        available = engine.available()
        try: version = engine.version()
        except Exception: version = "unknown"
        result.append({"engine_id": engine.engine_id, "display_name": engine.display_name, "available": available, "version": version})
    return result


def resolve(operation: str, source: str, target: str) -> tuple[ConversionEngine, Capability]:
    source, target = source.lower().lstrip("."), target.lower().lstrip(".")
    for engine in ENGINES:
        for cap in engine.capabilities():
            if cap.operation == operation and source in cap.source_extensions and target in cap.target_extensions:
                return engine, cap
    raise ValueError(f"No installed engine supports {operation}: {source} to {target}")
