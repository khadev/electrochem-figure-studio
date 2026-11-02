"""Asset-library helpers (Qt-free): folder scanning, path portability, drag payloads.

Layout of the ``assets/`` folder (next to ``main.py``)::

    assets/backgrounds/   full base images (3D renders, scenes)
    assets/components/    individual items (Nickel Foam, PPY, nanorods ... ; PNG with alpha)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
COMPONENTS_DIR = ASSETS_DIR / "components"
BACKGROUNDS_DIR = ASSETS_DIR / "backgrounds"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")

KIND_COMPONENT = "component"
KIND_BACKGROUND = "background"
ASSET_MIME = "application/x-chem-asset"


def ensure_asset_dirs() -> None:
    """Create the default asset folders if they do not exist yet."""
    for folder in (COMPONENTS_DIR, BACKGROUNDS_DIR):
        Path(folder).mkdir(parents=True, exist_ok=True)


def is_image_file(path) -> bool:
    return Path(str(path)).suffix.lower() in IMAGE_EXTENSIONS


def display_name(path) -> str:
    """'nickel_foam.png' -> 'nickel foam' (human friendly label)."""
    stem = Path(str(path)).stem
    return re.sub(r"[_\-]+", " ", stem).strip() or stem


def scan_folder(folder) -> list[tuple[str, str]]:
    """Return ``[(display_name, absolute_path), ...]`` for every PNG/JPG below
    `folder` (recursive, hidden files skipped), sorted by name."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in files:
            if name.startswith(".") or not is_image_file(name):
                continue
            found.append((display_name(name), os.path.abspath(os.path.join(root, name))))
    found.sort(key=lambda t: (t[0].lower(), t[1].lower()))
    return found


def asset_relative_path(path) -> str | None:
    """Path relative to the assets folder ('components/foam.png') or None if outside it."""
    try:
        rel = Path(os.path.abspath(str(path))).relative_to(Path(os.path.abspath(ASSETS_DIR)))
    except ValueError:
        return None
    return rel.as_posix()


def resolve_asset_path(rel: str) -> str | None:
    """Inverse of asset_relative_path(); refuses paths that escape the assets folder."""
    base = os.path.abspath(ASSETS_DIR)
    cand = os.path.abspath(os.path.join(base, str(rel)))
    try:
        if os.path.commonpath([base, cand]) != base:
            return None
    except ValueError:
        return None
    return cand


def unique_destination(folder, filename: str) -> str:
    """A non-existing path inside `folder` for `filename` (adds _2, _3 ... if needed)."""
    folder = Path(folder)
    stem, suffix = Path(filename).stem, Path(filename).suffix
    candidate = folder / f"{stem}{suffix}"
    n = 2
    while candidate.exists():
        candidate = folder / f"{stem}_{n}{suffix}"
        n += 1
    return str(candidate)


# ------------------------------------------------------- drag & drop payload
def encode_assets(entries) -> bytes:
    """entries: iterable of (kind, path) -> bytes for the ASSET_MIME payload."""
    return json.dumps([{"kind": k, "path": p} for k, p in entries]).encode("utf-8")


def decode_assets(data: bytes) -> list[tuple[str, str]]:
    """Parse an ASSET_MIME payload; invalid / non-image / missing entries are dropped."""
    try:
        raw = json.loads(bytes(data).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return []
    out = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        kind, path = entry.get("kind"), entry.get("path")
        if kind in (KIND_COMPONENT, KIND_BACKGROUND) and isinstance(path, str) \
                and is_image_file(path) and os.path.isfile(path):
            out.append((kind, path))
    return out
