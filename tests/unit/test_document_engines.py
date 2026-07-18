from types import SimpleNamespace

import pytest

from convertvault.engines.base import ConversionContext
from convertvault.engines.subprocess_engine import LibreOfficeEngine, PandocEngine


def test_pandoc_rejects_remote_document_resources(monkeypatch, tmp_path):
    source, output = tmp_path / "input.md", tmp_path / "output.pdf"
    source.write_text("![private](https://remote.example/image.png)", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    with pytest.raises(ValueError, match="Remote resource"):
        PandocEngine().convert(ConversionContext(source, output, "md", "pdf", {}))


def test_pandoc_pdf_uses_sandbox_and_controlled_css(monkeypatch, tmp_path):
    source, output = tmp_path / "input.md", tmp_path / "output.pdf"
    source.write_text("# Safe document", encoding="utf-8")
    observed = {}
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")

    def run(command, **kwargs):
        observed["command"] = command
        output.write_bytes(b"%PDF-safe")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    PandocEngine().convert(ConversionContext(source, output, "md", "pdf", {
        "table_of_contents": True, "page_size": "A4", "margin_mm": 15,
    }))
    assert "--sandbox" in observed["command"]
    assert "--pdf-engine=weasyprint" in observed["command"]
    assert "--toc" in observed["command"]
    assert (tmp_path / "document-theme.css").exists()


def test_libreoffice_uses_isolated_macro_locked_profile(monkeypatch, tmp_path):
    source, output = tmp_path / "input.docx", tmp_path / "result.pdf"
    source.write_bytes(b"synthetic-docx")
    observed = {}

    def run(command, **kwargs):
        observed["command"] = command
        profile_arg = next(value for value in command if value.startswith("-env:UserInstallation="))
        profile = profile_arg.split("file:///", 1)[1]
        registry = __import__("pathlib").Path(profile) / "user" / "registrymodifications.xcu"
        observed["profile"] = registry.read_text(encoding="utf-8")
        (tmp_path / "input.pdf").write_bytes(b"%PDF-office")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    LibreOfficeEngine().convert(ConversionContext(source, output, "docx", "pdf", {}))
    assert "MacroSecurityLevel" in observed["profile"] and "<value>3</value>" in observed["profile"]
    assert "--headless" in observed["command"] and output.read_bytes().startswith(b"%PDF")
