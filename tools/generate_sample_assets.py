"""Generate the small procedural sample assets shipped in assets/.

Run:  python tools/generate_sample_assets.py
Replace/extend them with your own transparent PNG renders at any time.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
COMP = ROOT / "assets" / "components"
BACK = ROOT / "assets" / "backgrounds"
rng = np.random.default_rng(7)


def cylinder_rgb(w, h, base, spec=0.5):
    x = np.tile(np.linspace(-1, 1, w)[None, :], (h, 1))
    shade = 0.36 + 0.64 * np.sqrt(np.clip(1 - x ** 2, 0, 1))
    hl = np.exp(-((x + 0.38) / 0.16) ** 2) * spec
    grain = rng.normal(0, 4, (h, w))
    rgb = np.stack([np.clip(base[k] * shade + 150 * hl + grain, 0, 255) for k in range(3)], -1)
    return Image.fromarray(rgb.astype("uint8"), "RGB")


def with_alpha(rgb: Image.Image, mask: Image.Image) -> Image.Image:
    out = rgb.convert("RGBA")
    out.putalpha(mask)
    return out


def rod(w, h, base, bumpy=False):
    S = 3
    mask = Image.new("L", (w * S, h * S), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=int(w * S * 0.28), fill=255)
    if bumpy:
        for _ in range(70):
            y = int(rng.uniform(0.04, 0.96) * h * S)
            side = rng.choice([0, 1])
            r = int(rng.uniform(5, 9) * S)
            x = int(w * S * 0.04) if side == 0 else int(w * S * 0.96)
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)
    return with_alpha(cylinder_rgb(w, h, base), mask)


def foam(w=380, h=260):
    S = 2
    img = Image.new("RGB", (w * S, h * S), (150, 152, 156))
    d = ImageDraw.Draw(img)
    for _ in range(95):
        x, y = rng.uniform(0, w * S), rng.uniform(0, h * S)
        r = rng.uniform(11, 24) * S
        d.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], fill=(196, 198, 202))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(38, 40, 44))
        d.ellipse([x - r * .6, y - r * .5, x + r * .6, y + r * .7], fill=(22, 23, 26))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    shade = np.linspace(1.12, 0.78, h * S)[:, None, None]
    arr = np.clip(np.asarray(img, float) * shade, 0, 255).astype("uint8")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=40 * S, fill=255)
    out = with_alpha(Image.fromarray(arr), mask)
    return out.resize((w, h), Image.LANCZOS)


def swoosh(w=320, h=140):
    """Asymmetric curved arrow: handy for testing Flip H/V."""
    S = 3
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p0, p1, p2 = np.array([20, 112]), np.array([140, -10]), np.array([262, 50])
    ts = np.linspace(0, 1, 160)
    pts = [((1 - t) ** 2) * p0 + 2 * (1 - t) * t * p1 + t * t * p2 for t in ts]
    for t, p in zip(ts, pts):
        r = (3 + 11 * t) * S
        c = (int(60 - 20 * t), int(190 - 50 * t), int(70 - 10 * t), 255)
        d.ellipse([p[0] * S - r, p[1] * S - r, p[0] * S + r, p[1] * S + r], fill=c)
    tan = p2 - pts[-6]
    tan = tan / np.linalg.norm(tan)
    nrm = np.array([-tan[1], tan[0]])
    tip, base = p2 + tan * 38, p2 - tan * 4
    poly = [tuple((tip) * S), tuple((base + nrm * 26) * S), tuple((base - nrm * 26) * S)]
    d.polygon(poly, fill=(30, 130, 50, 255))
    return img.resize((w, h), Image.LANCZOS)


def sphere(n=130, base=(205, 207, 210)):
    y, x = np.mgrid[-1:1:complex(n), -1:1:complex(n)]
    r2 = x ** 2 + y ** 2
    z = np.sqrt(np.clip(1 - r2, 0, 1))
    light = np.clip(-0.4 * x - 0.5 * y + 0.75 * z, 0, 1)
    spec = np.clip(light, 0, 1) ** 24 * 0.8
    rgb = np.stack([np.clip(base[k] * (0.3 + 0.7 * light) + 255 * spec, 0, 255) for k in range(3)], -1)
    a = np.clip((1 - np.sqrt(r2)) * n * 0.5, 0, 1) * 255
    return Image.fromarray(np.dstack([rgb, a]).astype("uint8"), "RGBA")


def gradient_bg(path, top, bottom, size=(1200, 800), vignette=False):
    w, h = size
    t = np.linspace(0, 1, h)[:, None, None]
    arr = (1 - t) * np.array(top) + t * np.array(bottom)
    arr = np.repeat(arr, w, axis=1)
    if vignette:
        yy, xx = np.mgrid[-1:1:complex(h), -1:1:complex(w)]
        arr *= (1 - 0.18 * np.clip(xx ** 2 + yy ** 2, 0, 1.6))[..., None]
    Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "RGB").save(path)


if __name__ == "__main__":
    COMP.mkdir(parents=True, exist_ok=True)
    BACK.mkdir(parents=True, exist_ok=True)
    foam().save(COMP / "nickel_foam.png")
    rod(90, 420, (118, 134, 152)).save(COMP / "nimoo4_nanorod.png")
    rod(124, 420, (46, 150, 52), bumpy=True).save(COMP / "ppy_coated_rod.png")
    swoosh().save(COMP / "reaction_arrow_green.png")
    sphere().save(COMP / "hydrogen_sphere.png")
    gradient_bg(BACK / "soft_gradient.png", (246, 249, 253), (205, 216, 230))
    gradient_bg(BACK / "studio_vignette.png", (250, 250, 250), (222, 224, 228), vignette=True)
    print("sample assets written to", ROOT / "assets")
