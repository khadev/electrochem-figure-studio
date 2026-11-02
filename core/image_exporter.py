"""PIL-based vertical stitching of the canvas render and CV graph."""
from __future__ import annotations

from PIL import Image


def _flatten_and_resize(img: Image.Image, width: int) -> Image.Image:
    """Flatten any transparency onto white and scale to `width`, keeping aspect."""
    rgba = img.convert("RGBA")
    flat = Image.new("RGB", rgba.size, "white")
    flat.paste(rgba, mask=rgba.split()[3])
    height = max(1, round(flat.height * width / flat.width))
    return flat.resize((width, height), Image.Resampling.LANCZOS)


def stitch_and_export(canvas_image: Image.Image, graph_image: Image.Image,
                      filepath: str, width: int = 1200, gap: int = 0,
                      dpi: int = 300) -> Image.Image:
    """Stack canvas (top) and graph (bottom) on white at a unified width; save PNG.

    Returns the combined PIL image as well.
    """
    top = _flatten_and_resize(canvas_image, width)
    bottom = _flatten_and_resize(graph_image, width)

    combined = Image.new("RGB", (width, top.height + gap + bottom.height), "white")
    combined.paste(top, (0, 0))
    combined.paste(bottom, (0, top.height + gap))
    combined.save(filepath, format="PNG", dpi=(dpi, dpi))
    return combined
