"""Project persistence for the Scientific Schematic Editor (``.chem`` files).

A ``.chem`` file is UTF-8 JSON.  This module is deliberately Qt-free: the GUI
converts its scene to/from plain dictionaries and this module takes care of
validation, path handling and safe file I/O.

Schema (version 2; version-1 files, which lack "components", still load)::

    {
      "format": "chem-project", "version": 2,
      "canvas":     {"width": 1200, "height": 800},
      "background": {"path": "<relative or absolute>", "absolute_path": "..."} | null,
      "grid":       {"visible": false, "size": 25, "snap": true},
      "graph":      {"type": "Reversible", "peak_height": 0.6, "peak_position": 0.5},
      "molecules":  [{"kind", "x", "y", "scale", "rotation", "z", "locked"}],
      "texts":      [{"text", "x", "y", "scale", "rotation", "z", "locked",
                      "color", "font_family", "font_size", "bold", "italic"}],
      "arrows":     [{"x1", "y1", "x2", "y2", "x", "y", "color", "width",
                      "z", "locked"}],
      "components": [{"path": "<relative to the .chem file>", "absolute_path",
                      "asset": "components/foam.png" | null,
                      "x", "y", "scale", "rotation", "opacity",
                      "flip_h", "flip_v", "z", "locked"}]
    }

Image paths (background and components) are written relative to the project
file, with the absolute path (and, for library assets, the path inside the
``assets/`` folder) kept as fallbacks when loading.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile

from . import asset_library

FORMAT = "chem-project"
VERSION = 2
EXTENSION = ".chem"


class ProjectError(Exception):
    """Raised when a project file cannot be read or is not a valid project."""


# --------------------------------------------------------------------- helpers
def new_project() -> dict:
    """Return an empty, valid project dictionary."""
    return {
        "format": FORMAT,
        "version": VERSION,
        "canvas": {"width": 1200.0, "height": 800.0},
        "background": None,
        "grid": {"visible": False, "size": 25, "snap": True},
        "graph": {"type": "Reversible", "peak_height": 0.6, "peak_position": 0.5},
        "molecules": [],
        "texts": [],
        "arrows": [],
        "components": [],
    }


def _f(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _common(d: dict, index: int) -> dict:
    return {
        "x": _f(d.get("x")), "y": _f(d.get("y")),
        "z": _f(d.get("z"), 10 + index),
        "locked": bool(d.get("locked", False)),
    }


def _norm_molecule(d: dict, i: int) -> dict:
    if not isinstance(d.get("kind"), str):
        raise ValueError("molecule without a 'kind'")
    out = _common(d, i)
    out.update(kind=d["kind"], scale=_f(d.get("scale"), 1.0) or 1.0,
               rotation=_f(d.get("rotation")))
    return out


def _norm_text(d: dict, i: int) -> dict:
    out = _common(d, i)
    out.update(
        text=str(d.get("text", "")),
        scale=_f(d.get("scale"), 1.0) or 1.0,
        rotation=_f(d.get("rotation")),
        color=str(d.get("color", "#111111")),
        font_family=str(d.get("font_family", "Arial")),
        font_size=max(1, int(_f(d.get("font_size"), 24))),
        bold=bool(d.get("bold", True)),
        italic=bool(d.get("italic", False)),
    )
    return out


def _norm_arrow(d: dict, i: int) -> dict:
    for key in ("x1", "y1", "x2", "y2"):
        if key not in d:
            raise ValueError(f"arrow missing '{key}'")
    out = _common(d, i)
    out.update(x1=_f(d["x1"]), y1=_f(d["y1"]), x2=_f(d["x2"]), y2=_f(d["y2"]),
               color=str(d.get("color", "#1f55d6")),
               width=max(0.5, _f(d.get("width"), 4.0)))
    return out


def _norm_component(d: dict, i: int) -> dict:
    path, absolute, asset = d.get("path"), d.get("absolute_path"), d.get("asset")
    if not any(isinstance(v, str) and v for v in (path, absolute, asset)):
        raise ValueError("component without an image path")
    out = _common(d, i)
    out.update(
        path=path if isinstance(path, str) and path else None,
        absolute_path=absolute if isinstance(absolute, str) and absolute else None,
        asset=asset if isinstance(asset, str) and asset else None,
        scale=_f(d.get("scale"), 1.0) or 1.0,
        rotation=_f(d.get("rotation")),
        opacity=max(0.0, min(1.0, _f(d.get("opacity"), 1.0))),
        flip_h=bool(d.get("flip_h", False)),
        flip_v=bool(d.get("flip_v", False)),
    )
    return out


def normalize_project(raw) -> tuple[dict, list[str]]:
    """Validate ``raw`` and return ``(clean_project, warnings)``.

    Unknown / malformed entries are skipped (with a warning) rather than
    aborting the whole load, so a partly damaged file still opens.
    """
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise ProjectError("This file is not a Scientific Schematic Editor project.")

    warnings: list[str] = []
    version = raw.get("version", 1)
    if isinstance(version, (int, float)) and version > VERSION:
        warnings.append(f"Project was saved by a newer version (v{version}); "
                        "some data may be ignored.")

    data = new_project()
    canvas = raw.get("canvas") if isinstance(raw.get("canvas"), dict) else {}
    data["canvas"] = {"width": _f(canvas.get("width"), 1200.0) or 1200.0,
                      "height": _f(canvas.get("height"), 800.0) or 800.0}

    bg = raw.get("background")
    if isinstance(bg, dict) and (bg.get("path") or bg.get("absolute_path")):
        data["background"] = {"path": bg.get("path"),
                              "absolute_path": bg.get("absolute_path")}

    grid = raw.get("grid") if isinstance(raw.get("grid"), dict) else {}
    data["grid"] = {"visible": bool(grid.get("visible", False)),
                    "size": max(2, int(_f(grid.get("size"), 25))),
                    "snap": bool(grid.get("snap", True))}

    graph = raw.get("graph") if isinstance(raw.get("graph"), dict) else {}
    data["graph"] = {"type": str(graph.get("type", "Reversible")),
                     "peak_height": _f(graph.get("peak_height"), 0.6),
                     "peak_position": _f(graph.get("peak_position"), 0.5)}

    for key, fn, label in (("molecules", _norm_molecule, "molecule"),
                           ("texts", _norm_text, "text"),
                           ("arrows", _norm_arrow, "arrow"),
                           ("components", _norm_component, "component")):
        entries = raw.get(key, [])
        if not isinstance(entries, list):
            warnings.append(f"'{key}' is not a list - ignored.")
            continue
        for i, entry in enumerate(entries):
            try:
                data[key].append(fn(entry, i))
            except (ValueError, TypeError, AttributeError) as exc:
                warnings.append(f"Skipped invalid {label} #{i + 1}: {exc}")
    return data, warnings


# ------------------------------------------------------------------- file I/O
def _relativize(path_like: str, project_dir: str) -> tuple[str, str]:
    """Return (path relative to project_dir if possible, absolute path)."""
    absolute = os.path.abspath(path_like)
    try:
        rel = os.path.relpath(absolute, project_dir)
    except ValueError:          # different drive on Windows
        rel = absolute
    return rel.replace("\\", "/"), absolute


def save_project(data: dict, filepath: str) -> str:
    """Write ``data`` to ``filepath`` (``.chem`` is appended if missing).

    Image paths (background + components) are stored relative to the project
    file when possible (so a project folder can be moved), with the absolute
    path kept as a fallback.  The write is atomic.  Returns the final path.
    """
    if not filepath.lower().endswith(EXTENSION):
        filepath += EXTENSION
    filepath = os.path.abspath(filepath)
    project_dir = os.path.dirname(filepath)

    out = copy.deepcopy(data)
    out["format"], out["version"] = FORMAT, VERSION

    bg = out.get("background")
    if bg and (bg.get("path") or bg.get("absolute_path")):
        rel, absolute = _relativize(bg.get("absolute_path") or bg["path"], project_dir)
        out["background"] = {"path": rel, "absolute_path": absolute}
    else:
        out["background"] = None

    for comp in out.get("components", []):
        source = comp.get("absolute_path") or comp.get("path")
        if source:
            comp["path"], comp["absolute_path"] = _relativize(source, project_dir)
            if not comp.get("asset"):
                comp["asset"] = asset_library.asset_relative_path(comp["absolute_path"])
        comp.pop("resolved_path", None)
        comp.pop("fallback_path", None)
    out.pop("_warnings", None)

    os.makedirs(project_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=project_dir, prefix=".chem_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, filepath)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return filepath


def _candidates(entry: dict, project_dir: str) -> list[str]:
    """Possible locations of an image, most specific first."""
    out = []
    rel = entry.get("path")
    if rel:
        out.append(rel if os.path.isabs(rel) else os.path.join(project_dir, rel))
    if entry.get("absolute_path"):
        out.append(entry["absolute_path"])
    if entry.get("asset"):
        resolved = asset_library.resolve_asset_path(entry["asset"])
        if resolved:
            out.append(resolved)
    return [os.path.normpath(c) for c in out]


def load_project(filepath: str) -> tuple[dict, list[str]]:
    """Read a ``.chem`` file. Returns ``(project, warnings)``.

    For the background and every component, ``resolved_path`` is the first
    existing image (relative-to-project, then absolute, then assets-folder) or
    ``None`` when it cannot be found; ``fallback_path`` is the best guess of the
    intended location so a placeholder can keep the link.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, UnicodeDecodeError) as exc:
        raise ProjectError(f"Could not read file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectError(f"File is not valid JSON: {exc}") from exc

    data, warnings = normalize_project(raw)
    project_dir = os.path.dirname(os.path.abspath(filepath))

    bg = data.get("background")
    if bg:
        cands = _candidates(bg, project_dir)
        bg["resolved_path"] = next((c for c in cands if os.path.isfile(c)), None)
        if bg["resolved_path"] is None:
            warnings.append("Background image not found: "
                            f"{bg.get('path') or bg.get('absolute_path')}")

    for comp in data["components"]:
        cands = _candidates(comp, project_dir)
        comp["resolved_path"] = next((c for c in cands if os.path.isfile(c)), None)
        comp["fallback_path"] = cands[0] if cands else None
        if comp["resolved_path"] is None:
            warnings.append("Component image not found: "
                            f"{comp.get('path') or comp.get('absolute_path') or comp.get('asset')}")
    return data, warnings
