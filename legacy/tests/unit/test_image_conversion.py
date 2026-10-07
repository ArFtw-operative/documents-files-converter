from PIL import Image
from pypdf import PdfReader
import zipfile
from convertvault.engines.base import ConversionContext
from convertvault.engines.image import PillowEngine

def test_png_to_jpeg_is_real_conversion(tmp_path):
    source, output = tmp_path / "input.png", tmp_path / "output.jpg"
    Image.new("RGBA", (40, 30), (20, 120, 80, 128)).save(source)
    PillowEngine().convert(ConversionContext(source, output, "png", "jpg", {"quality": 80}))
    with Image.open(output) as image:
        assert image.format == "JPEG"
        assert image.size == (40, 30)


def test_resize_crop_flip_watermark_and_target_size(tmp_path):
    source, output = tmp_path / "large.png", tmp_path / "small.jpg"
    Image.new("RGB", (800, 600), (20, 120, 80)).save(source)
    PillowEngine().convert(ConversionContext(source, output, "png", "jpg", {
        "_operation": "image.compress", "crop": [100, 100, 700, 500], "width": 240, "height": 160,
        "resize_mode": "fill", "flip": "horizontal", "watermark_text": "Private", "target_size_kb": 25,
    }))
    with Image.open(output) as image:
        assert image.format == "JPEG" and image.size == (240, 160)
    assert output.stat().st_size <= 30 * 1024


def test_batch_images_to_pdf_and_gif_frame_extraction(tmp_path):
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    Image.new("RGB", (30, 20), "red").save(first); Image.new("RGB", (30, 20), "blue").save(second)
    pdf = tmp_path / "images.pdf"
    PillowEngine().convert(ConversionContext(first, pdf, "png", "pdf", {"_operation": "image.to_pdf"}, [second]))
    assert len(PdfReader(pdf).pages) == 2
    gif = tmp_path / "animation.gif"
    PillowEngine().convert(ConversionContext(first, gif, "png", "gif", {"_operation": "image.create_gif", "duration_ms": 100}, [second]))
    frames = tmp_path / "frames.zip"
    PillowEngine().convert(ConversionContext(gif, frames, "gif", "zip", {"_operation": "image.extract_frames", "format": "png"}))
    with zipfile.ZipFile(frames) as archive:
        assert archive.namelist() == ["frame-0001.png", "frame-0002.png"]
