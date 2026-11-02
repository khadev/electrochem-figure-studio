"""Cyclic-voltammetry curve generation and publication-style plotting.

Pure Python / NumPy / Matplotlib - no Qt imports.
"""
from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

CURVE_TYPES = ("Reversible", "Irreversible", "Catalytic Wave")

E_START = -0.20   # V, start / end of the scan window
E_SWITCH = 0.90   # V, switching potential
LINE_COLOR = "#1a47d6"


def _unit_peak(s: np.ndarray, s_peak: float, width: float, decay: float) -> np.ndarray:
    """Diffusion-controlled peak shape (sigmoid rise x 1/sqrt tail), max = 1.

    `s` is the distance travelled along the scan direction (V).
    """
    grid = np.linspace(0.0, 3.0, 6001)

    def shape(x):
        rise = 1.0 / (1.0 + np.exp(-(x - s_peak) / width))
        soft = 0.03 * np.logaddexp(0.0, (x - s_peak) / 0.03)   # smooth max(x - s_peak, 0)
        tail = 1.0 / np.sqrt(1.0 + soft / decay)
        return rise * tail

    return shape(s) / shape(grid).max()


def generate_cv_data(cv_type: str = "Reversible",
                     peak_height: float = 0.6,
                     peak_position: float = 0.5,
                     n_points: int = 600):
    """Return (E, I) NumPy arrays for one full cycle.

    peak_height   : anodic peak current in mA
    peak_position : anodic peak potential in V (vs. Ag/AgCl)
    """
    if cv_type not in CURVE_TYPES:
        raise ValueError(f"Unknown CV type: {cv_type!r}")

    h = float(peak_height)
    ep = float(peak_position)
    s = np.linspace(0.0, E_SWITCH - E_START, n_points)
    e_fwd = E_START + s
    e_rev = E_SWITCH - s

    # smooth capacitive background (+ on forward scan, - on reverse scan)
    cap_f = 0.04 * h * np.tanh(s / 0.03)
    cap_r = -0.04 * h * np.tanh((s - 0.06) / 0.03)

    if cv_type in ("Reversible", "Irreversible"):
        if cv_type == "Reversible":
            w_f, d_f, w_r, d_r, h_r, d_ep = 0.035, 0.10, 0.035, 0.10, 0.95 * h, 0.15
        else:
            w_f, d_f, w_r, d_r, h_r, d_ep = 0.050, 0.12, 0.070, 0.12, 0.08 * h, 0.28

        sp_f = (ep - E_START) - 0.03
        sp_r = (E_SWITCH - (ep - d_ep)) - 0.03

        fwd_main = h * _unit_peak(s, sp_f, w_f, d_f)
        cont = fwd_main[-1] * np.exp(-s / 0.15)          # decay of the anodic tail
        i_rev = cont + cap_r - h_r * _unit_peak(s, sp_r, w_r, d_r)
        i_fwd = fwd_main + cap_f + i_rev[-1] * np.exp(-s / 0.08)   # close the loop

    else:  # Catalytic Wave: sigmoidal plateau, hysteresis, weak return peak
        def sig(e):
            return 1.0 / (1.0 + np.exp(-(e - ep) / 0.05))

        sp_r = (E_SWITCH - (ep - 0.25)) - 0.03
        i_fwd = h * sig(e_fwd) + 0.1 * h * np.clip(e_fwd - ep, 0, None) + cap_f
        i_rev = (0.97 * h * sig(e_rev + 0.04) + 0.1 * h * np.clip(e_rev - ep, 0, None)
                 + cap_r - 0.15 * h * _unit_peak(s, sp_r, 0.04, 0.10))

    return np.concatenate([e_fwd, e_rev]), np.concatenate([i_fwd, i_rev])


def draw_cv(fig: Figure, cv_type: str = "Reversible",
            peak_height: float = 0.6, peak_position: float = 0.5) -> Figure:
    """(Re)draw a publication-styled CV onto an existing Figure."""
    fig.clear()
    ax = fig.add_subplot(111)
    E, I = generate_cv_data(cv_type, peak_height, peak_position)

    ax.plot(E, I, color=LINE_COLOR, lw=2.6, label="CV curve", solid_capstyle="round")
    ax.axhline(0, color="#b0b0b0", ls="--", lw=1.1, zorder=0)

    ax.set_xlabel("Potential (V vs. Ag/AgCl)", fontsize=13, fontweight="bold")
    ax.set_ylabel("Current (mA)", fontsize=13, fontweight="bold")
    ax.set_title("Cyclic Voltammetry (CV)", fontsize=15, fontweight="bold", pad=10)
    ax.tick_params(labelsize=11, width=1.3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_linewidth(1.5)

    lo, hi = min(I.min(), 0.0), max(I.max(), 0.0)
    span = hi - lo
    ax.set_xlim(-0.3, 1.0)
    ax.set_ylim(lo - 0.40 * span, hi + 0.50 * span)

    # peak annotations
    n = len(E) // 2
    ia = int(np.argmax(I[:n]))
    ic = int(np.argmin(I[n:])) + n
    arrow = dict(arrowstyle="-|>", color=LINE_COLOR, lw=1.2)
    kw = dict(color=LINE_COLOR, fontsize=10.5, textcoords="offset points", arrowprops=arrow)
    label_ox = "Catalytic current\n(Forward scan)" if cv_type == "Catalytic Wave" \
        else "Oxidation peak\n(Forward scan)"
    ax.annotate(label_ox, xy=(E[ia], I[ia]), xytext=(-45, 18), ha="right", va="bottom", **kw)
    if abs(I[ic]) > 0.2 * max(I[ia], 1e-9):
        ax.annotate("Reduction peak\n(Reverse scan)", xy=(E[ic], I[ic]),
                    xytext=(45, -18), ha="left", va="top", **kw)

    ax.legend(loc="lower right" if cv_type == "Catalytic Wave" else "upper right",
              frameon=False, fontsize=11)
    return fig


def create_cv_figure(cv_type: str = "Reversible", peak_height: float = 0.6,
                     peak_position: float = 0.5, figsize=(8, 4), dpi: int = 100) -> Figure:
    """Create and return a new publication-styled Matplotlib Figure."""
    fig = Figure(figsize=figsize, dpi=dpi, facecolor="white", layout="constrained")
    return draw_cv(fig, cv_type, peak_height, peak_position)
