import io
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, ImageSequence

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF = True
except ImportError:
    HEIF = False

from .base import Capability, ConversionContext


class PillowEngine:
    engine_id = "pillow"
    display_name = "Pillow image engine"
    source_formats = ["jpg", "jpeg", "png", "webp", "gif", "tiff", "tif", "bmp", "ico"]
    targets = ["jpg", "jpeg", "png", "webp", "tiff", "bmp", "gif", "pdf"]

    def available(self) -> bool:
        return True

    def version(self) -> str:
        import PIL

        return PIL.__version__

    def capabilities(self) -> list[Capability]:
        sources = self.source_formats + (["heic", "heif"] if HEIF else [])
        common_options = {
            "quality": {"type": "integer", "minimum": 1, "maximum": 100, "default": 85},
            "width": {"type": "integer", "minimum": 1},
            "height": {"type": "integer", "minimum": 1},
            "resize_mode": {"type": "string", "enum": ["fit", "fill", "exact"], "default": "fit"},
            "percentage": {"type": "integer", "minimum": 1, "maximum": 1000},
            "crop": {"type": "array", "items": 4},
            "rotate": {"type": "integer", "enum": [0, 90, 180, 270], "default": 0},
            "flip": {"type": "string", "enum": ["none", "horizontal", "vertical"], "default": "none"},
            "auto_orient": {"type": "boolean", "default": True},
            "strip_metadata": {"type": "boolean", "default": False},
            "background": {"type": "string", "default": "#ffffff"},
            "dpi": {"type": "integer", "minimum": 36, "maximum": 1200},
            "color_mode": {"type": "string", "enum": ["unchanged", "RGB", "RGBA", "L"], "default": "unchanged"},
            "watermark_text": {"type": "string", "maximum_length": 200},
        }
        limits = ["HDR HEIC sources are tone-mapped to an 8-bit output where required."]
        return [
            Capability("image.convert", sources, self.targets, self.engine_id,
                       lossless_targets=["png", "tiff", "bmp"], options=common_options, limitations=limits),
            Capability("image.compress", sources, ["jpg", "jpeg", "png", "webp"], self.engine_id,
                       options={**common_options, "preset": {"type": "string", "enum": ["lossless", "balanced", "maximum", "custom"], "default": "balanced"},
                                "target_size_kb": {"type": "integer", "minimum": 10}}, limitations=limits),
            Capability("image.to_pdf", sources, ["pdf"], self.engine_id,
                       options={"input_file_ids": {"type": "array", "minimum_items": 1}}),
            Capability("image.extract_frames", ["gif", "webp", "tiff", "tif"], ["zip"], self.engine_id,
                       options={"format": {"type": "string", "enum": ["png", "jpg"], "default": "png"}}),
            Capability("image.create_gif", sources, ["gif"], self.engine_id,
                       options={"duration_ms": {"type": "integer", "minimum": 20, "maximum": 10000, "default": 250},
                                "loop": {"type": "integer", "minimum": 0, "default": 0}}),
        ]

    def convert(self, context: ConversionContext) -> list[Path]:
        operation = context.options.get("_operation", "image.convert")
        context.destination.parent.mkdir(parents=True, exist_ok=True)
        if operation == "image.to_pdf":
            return self._images_to_pdf(context)
        if operation == "image.extract_frames":
            return self._extract_frames(context)
        if operation == "image.create_gif":
            return self._create_gif(context)
        with Image.open(context.source) as opened:
            image = self._transform(opened, context.options)
            return self._save(image, opened, context)

    def _transform(self, opened: Image.Image, options: dict) -> Image.Image:
        image = ImageOps.exif_transpose(opened) if options.get("auto_orient", True) else opened.copy()
        crop = options.get("crop")
        if isinstance(crop, list) and len(crop) == 4:
            left, top, right, bottom = (int(value) for value in crop)
            if left < 0 or top < 0 or right > image.width or bottom > image.height or right <= left or bottom <= top:
                raise ValueError("Crop coordinates fall outside the image")
            image = image.crop((left, top, right, bottom))
        percentage = options.get("percentage")
        width, height = options.get("width"), options.get("height")
        if percentage:
            scale = max(1, min(1000, int(percentage))) / 100
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
        elif width or height:
            target_width = int(width or image.width * int(height) / image.height)
            target_height = int(height or image.height * int(width) / image.width)
            mode = options.get("resize_mode", "fit")
            if mode == "fill" and width and height:
                image = ImageOps.fit(image, (target_width, target_height), Image.Resampling.LANCZOS)
            elif mode == "exact" and width and height:
                image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            else:
                image.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
        rotation = int(options.get("rotate", 0))
        if rotation: image = image.rotate(-rotation, expand=True)
        if options.get("flip") == "horizontal": image = ImageOps.mirror(image)
        elif options.get("flip") == "vertical": image = ImageOps.flip(image)
        color_mode = options.get("color_mode", "unchanged")
        if color_mode != "unchanged": image = image.convert(color_mode)
        watermark = str(options.get("watermark_text", "")).strip()
        if watermark:
            if image.mode not in {"RGB", "RGBA"}: image = image.convert("RGBA")
            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0)); drawing = ImageDraw.Draw(overlay)
            box = drawing.textbbox((0, 0), watermark); text_width, text_height = box[2] - box[0], box[3] - box[1]
            position = (max(8, image.width - text_width - 16), max(8, image.height - text_height - 16))
            drawing.rectangle((position[0] - 5, position[1] - 4, position[0] + text_width + 5, position[1] + text_height + 4), fill=(0, 0, 0, 110))
            drawing.text(position, watermark, fill=(255, 255, 255, 210)); image = Image.alpha_composite(image.convert("RGBA"), overlay)
        return image

    def _save(self, image: Image.Image, opened: Image.Image, context: ConversionContext) -> list[Path]:
        options = context.options; target = context.target_extension.lower().replace("jpeg", "jpg")
        save_format = {"jpg": "JPEG", "tif": "TIFF"}.get(target, target.upper())
        if target in {"jpg", "bmp", "pdf"} and image.mode in {"RGBA", "LA", "P"}:
            rgba = image.convert("RGBA"); background = Image.new("RGB", rgba.size, options.get("background", "#ffffff"))
            background.paste(rgba, mask=rgba.getchannel("A")); image = background
        preset_quality = {"lossless": 100, "balanced": 82, "maximum": 55}.get(options.get("preset"), 85)
        quality = max(1, min(100, int(options.get("quality", preset_quality))))
        kwargs: dict = {}
        if target in {"jpg", "webp"}: kwargs.update(quality=quality, optimize=True)
        elif target == "png": kwargs.update(optimize=True, compress_level=9)
        if options.get("dpi"): kwargs["dpi"] = (int(options["dpi"]), int(options["dpi"]))
        if not options.get("strip_metadata") and "exif" in opened.info: kwargs["exif"] = opened.info["exif"]
        target_bytes = int(options.get("target_size_kb", 0)) * 1024
        if target_bytes and target in {"jpg", "webp"}:
            minimum_quality = max(10, int(options.get("minimum_quality", 25)))
            while quality >= minimum_quality:
                buffer = io.BytesIO(); image.save(buffer, save_format, **{**kwargs, "quality": quality})
                if buffer.tell() <= target_bytes or quality == minimum_quality:
                    context.destination.write_bytes(buffer.getvalue()); break
                quality = max(minimum_quality, quality - 5)
        else: image.save(context.destination, save_format, **kwargs)
        return [context.destination]

    def _images_to_pdf(self, context: ConversionContext) -> list[Path]:
        images: list[Image.Image] = []
        try:
            for source in [context.source, *context.additional_sources]:
                with Image.open(source) as opened:
                    for frame in ImageSequence.Iterator(opened): images.append(ImageOps.exif_transpose(frame).convert("RGB"))
            if not images: raise ValueError("No readable image pages were supplied")
            images[0].save(context.destination, "PDF", save_all=True, append_images=images[1:], resolution=int(context.options.get("dpi", 150)))
        finally:
            for image in images: image.close()
        return [context.destination]

    def _extract_frames(self, context: ConversionContext) -> list[Path]:
        image_format = context.options.get("format", "png").lower()
        with Image.open(context.source) as opened, zipfile.ZipFile(context.destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, frame in enumerate(ImageSequence.Iterator(opened), 1):
                buffer = io.BytesIO(); converted = frame.convert("RGB") if image_format == "jpg" else frame.convert("RGBA")
                converted.save(buffer, "JPEG" if image_format == "jpg" else "PNG")
                archive.writestr(f"frame-{index:04d}.{image_format}", buffer.getvalue())
        return [context.destination]

    def _create_gif(self, context: ConversionContext) -> list[Path]:
        frames: list[Image.Image] = []
        try:
            for source in [context.source, *context.additional_sources]:
                with Image.open(source) as opened: frames.append(ImageOps.exif_transpose(opened).convert("RGBA"))
            if not frames: raise ValueError("No readable frames were supplied")
            frames[0].save(context.destination, "GIF", save_all=True, append_images=frames[1:],
                           duration=int(context.options.get("duration_ms", 250)), loop=int(context.options.get("loop", 0)), disposal=2)
        finally:
            for frame in frames: frame.close()
        return [context.destination]
