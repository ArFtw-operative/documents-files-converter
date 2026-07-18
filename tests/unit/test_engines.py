from pathlib import Path
import pytest
from convertvault.engines.pdf import parse_pages
from convertvault.engines.registry import resolve
from convertvault.storage import safe_name

def test_filename_sanitization_blocks_traversal():
    assert safe_name("../../private/evil<script>.png") == "evil_script_.png"
    assert "/" not in safe_name("..\\..\\secret.txt")

def test_page_ranges_are_zero_based_and_sorted():
    assert parse_pages("3, 1-2", 4) == [0, 1, 2]

def test_page_range_rejects_missing_page():
    with pytest.raises(ValueError): parse_pages("5", 4)

def test_registry_resolves_real_image_conversion():
    engine, capability = resolve("image.convert", "png", "jpg")
    assert engine.engine_id == "pillow"
    assert "jpg" in capability.target_extensions

def test_registry_rejects_unsupported_pair():
    with pytest.raises(ValueError): resolve("image.convert", "exe", "jpg")

