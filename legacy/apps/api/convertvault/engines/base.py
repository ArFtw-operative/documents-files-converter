from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Capability:
    operation: str
    source_extensions: list[str]
    target_extensions: list[str]
    engine_id: str
    lossless_targets: list[str] = field(default_factory=list)
    approximate: bool = False
    options: dict = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    def json(self) -> dict:
        return asdict(self)


@dataclass
class ConversionContext:
    source: Path
    destination: Path
    source_extension: str
    target_extension: str
    options: dict
    additional_sources: list[Path] = field(default_factory=list)


class ConversionEngine(Protocol):
    engine_id: str
    display_name: str

    def available(self) -> bool: ...
    def version(self) -> str: ...
    def capabilities(self) -> list[Capability]: ...
    def convert(self, context: ConversionContext) -> list[Path]: ...
