import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config import settings
from .base import Capability, ConversionContext


class LibreOfficeEngine:
    engine_id = "libreoffice"
    display_name = "LibreOffice"
    sources = ["doc", "docx", "odt", "rtf", "txt", "html", "xls", "xlsx", "ods", "csv", "ppt", "pptx", "odp"]

    def available(self) -> bool:
        return shutil.which("soffice") is not None

    def version(self) -> str:
        if not self.available():
            return "unavailable"
        return subprocess.run(
            ["soffice", "--version"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()

    def capabilities(self) -> list[Capability]:
        if not self.available():
            return []
        limits = [
            "Unavailable server fonts may be substituted.",
            "Macros and document scripts are never executed.",
            "Complex layouts, embedded objects, formulas, and animations may shift or be omitted.",
        ]
        return [
            Capability("office.convert", ["doc", "docx", "odt", "rtf", "txt", "html"],
                       ["pdf", "docx", "odt", "rtf", "txt", "html"], self.engine_id,
                       approximate=True, limitations=limits),
            Capability("office.convert", ["xls", "xlsx", "ods", "csv"],
                       ["pdf", "xlsx", "ods", "csv", "html"], self.engine_id,
                       approximate=True, limitations=limits),
            Capability("office.convert", ["ppt", "pptx", "odp"], ["pdf", "pptx", "odp"],
                       self.engine_id, approximate=True, limitations=limits),
        ]

    def convert(self, context: ConversionContext) -> list[Path]:
        with tempfile.TemporaryDirectory(prefix="lo-profile-") as profile:
            profile_path = Path(profile)
            user_path = profile_path / "user"
            user_path.mkdir(parents=True)
            (user_path / "registrymodifications.xcu").write_text(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
                '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
                '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
                '</item></oor:items>',
                encoding="utf-8",
            )
            command = [
                "soffice", "--headless", "--invisible", "--nologo", "--nodefault", "--nolockcheck",
                "--norestore", f"-env:UserInstallation=file:///{profile_path.as_posix()}",
                "--convert-to", context.target_extension, "--outdir", str(context.destination.parent),
                str(context.source),
            ]
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=settings.job_timeout_office, check=False)
            if result.returncode != 0:
                reason = (result.stderr or result.stdout or "unknown engine error").strip()[-500:]
                raise RuntimeError(f"LibreOffice conversion failed: {reason}")
            generated = context.destination.parent / f"{context.source.stem}.{context.target_extension}"
            if not generated.exists() or generated.stat().st_size == 0:
                raise RuntimeError("LibreOffice did not produce a valid output file")
            generated.replace(context.destination)
        return [context.destination]


class PandocEngine:
    engine_id = "pandoc"
    display_name = "Pandoc"

    def available(self) -> bool:
        return shutil.which("pandoc") is not None

    def version(self) -> str:
        if not self.available():
            return "unavailable"
        return subprocess.run(
            ["pandoc", "--version"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.splitlines()[0]

    def capabilities(self) -> list[Capability]:
        if not self.available():
            return []
        limits = ["Complex source layouts may not round-trip exactly.", "Remote resources are disabled."]
        markup_targets = ["html", "docx", "odt", "rtf", "txt", "epub", "md"]
        if shutil.which("weasyprint"):
            markup_targets.append("pdf")
        options = {
            "table_of_contents": {"type": "boolean", "default": False},
            "numbered_headings": {"type": "boolean", "default": False},
            "page_size": {"type": "string", "enum": ["A4", "Letter", "Legal"], "default": "A4"},
            "orientation": {"type": "string", "enum": ["portrait", "landscape"], "default": "portrait"},
            "margin_mm": {"type": "integer", "minimum": 5, "maximum": 50, "default": 20},
            "font_family": {"type": "string", "default": "DejaVu Sans"},
            "font_size": {"type": "integer", "minimum": 7, "maximum": 32, "default": 11},
        }
        return [
            Capability("markup.convert", ["md", "markdown", "html", "txt"], markup_targets,
                       self.engine_id, approximate=True, options=options, limitations=limits),
            Capability("markup.convert", ["docx", "odt", "rtf"], ["md", "html", "txt"],
                       self.engine_id, approximate=True, limitations=limits),
            Capability("markup.convert", ["epub"], ["html", "txt"], self.engine_id,
                       approximate=True, limitations=limits),
        ]

    def convert(self, context: ConversionContext) -> list[Path]:
        source_text = ""
        if context.source_extension in {"md", "markdown", "html", "txt"}:
            source_text = context.source.read_text(encoding="utf-8", errors="replace")
            if re.search(r"(?:src|href)\s*=\s*['\"]https?://|!\[[^]]*]\(https?://", source_text, re.I):
                raise ValueError("Remote resource references are disabled for private conversion")
        command = ["pandoc", "--sandbox", "--standalone", str(context.source), "--output", str(context.destination)]
        if context.options.get("table_of_contents"):
            command.append("--toc")
        if context.options.get("numbered_headings"):
            command.append("--number-sections")
        if context.target_extension == "pdf":
            if not shutil.which("weasyprint"):
                raise RuntimeError("PDF output is unavailable because WeasyPrint is not installed")
            page_size = context.options.get("page_size", "A4")
            orientation = context.options.get("orientation", "portrait")
            margin = max(5, min(50, int(context.options.get("margin_mm", 20))))
            font = re.sub(r"[^\w .,-]", "", str(context.options.get("font_family", "DejaVu Sans")))[:80]
            font_size = max(7, min(32, int(context.options.get("font_size", 11))))
            css = context.destination.parent / "document-theme.css"
            css.write_text(
                f"@page {{ size: {page_size} {orientation}; margin: {margin}mm; }} "
                f"body {{ font-family: '{font}', sans-serif; font-size: {font_size}pt; line-height: 1.5; }} "
                "img { max-width: 100%; } pre { white-space: pre-wrap; } table { border-collapse: collapse; } "
                "th, td { border: 1px solid #bbb; padding: 4px 6px; }",
                encoding="utf-8",
            )
            command.extend(["--pdf-engine=weasyprint", "--css", str(css)])
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=settings.job_timeout_general, check=False, cwd=context.source.parent)
        if result.returncode != 0:
            reason = (result.stderr or result.stdout or "unknown engine error").strip()[-500:]
            raise RuntimeError(f"Pandoc conversion failed: {reason}")
        if not context.destination.exists() or context.destination.stat().st_size == 0:
            raise RuntimeError("Pandoc did not produce a valid output file")
        return [context.destination]
