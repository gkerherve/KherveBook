"""Peak lineshapes for KherveFitting ``.kfit`` projects.

A ``.kfit`` stores each fitted peak as parameters (position, height,
FWHM, L/G, area, sigma, gamma, skew) plus the name of the model that
produced it — never the fitted curve itself. To draw the fit, the
lineshapes have to be evaluated again here.

These are ported from KherveFitting's ``Peak_Functions`` and wired up the
way its ``update_overall_fit_and_residuals`` does, so the peaks and the
envelope KherveBook draws are the ones KherveFitting draws. The stored
Area is used where the model is area-based (rather than re-deriving it
from the height), because that is what builds the envelope there.

``peak_curve()`` returns ``None`` for a model this module does not
implement — the derived non-spectral fits (D-parameter, Curie-Weiss,
equivalent circuit, VBM, cut-off) which are not lineshapes at all, and
the three CasaXPS convolution shapes DL, TLA and LA*G's cousins. The
caller reports those rather than drawing something plausible and wrong.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import numpy as np

_SQRT_2LN2 = np.sqrt(2.0 * np.log(2.0))
#: FWHM -> Gaussian sigma.
_FWHM_TO_SIGMA = 1.0 / (2.0 * _SQRT_2LN2)


# ---------------------------------------------------------------------------
#  Primitives
# ---------------------------------------------------------------------------
def _gaussian(x, center, fwhm, m):
    return np.exp(-4 * np.log(2) * (1 - m / 100) * ((x - center) / fwhm) ** 2)


def _lorentzian(x, center, fwhm, m):
    return 1 / (1 + 4 * m / 100 * ((x - center) / fwhm) ** 2)


def _voigt_fwhm_split(fwhm, fraction):
    """Split a total Voigt FWHM into its Gaussian and Lorentzian parts.

    Olivero-Longbothum, accurate to ~0.02%: the L/G column sets the
    Lorentzian share of the *total* width rather than a separate width.
    """
    r = np.clip(float(fraction), 0.0, 100.0) / 100.0
    k = 0.5346 * r + np.sqrt(0.2166 * r * r + (1.0 - r) ** 2)
    scale = float(fwhm) / k if k else 0.0
    return (1.0 - r) * scale, r * scale


def _skewed_voigt_apex_offset(sigma, gamma, skew):
    """Distance from lmfit's skewed_voigt ``center`` to its true maximum.

    SkewedVoigt multiplies a Voigt by ``1 + erf(skew (x-c) / (sigma √2))``,
    which drags the apex away from ``center`` whenever skew != 0; the
    profiles below re-anchor by this offset so ``Position`` really is where
    the peak is.
    """
    from lmfit.lineshapes import skewed_voigt

    if sigma <= 0 or abs(skew) < 1e-9:
        return 0.0
    span = 4.0 * (sigma + abs(gamma)) * (1.0 + abs(skew))
    x = np.linspace(-span, span, 801)
    y = skewed_voigt(x, amplitude=1.0, center=0.0, sigma=sigma, gamma=gamma,
                     skew=skew)
    i = int(np.argmax(y))
    step = x[1] - x[0]
    x_fine = np.linspace(x[i] - step, x[i] + step, 41)
    y_fine = skewed_voigt(x_fine, amplitude=1.0, center=0.0, sigma=sigma,
                          gamma=gamma, skew=skew)
    j = int(np.argmax(y_fine))
    if 0 < j < len(x_fine) - 1:
        denom = y_fine[j - 1] - 2.0 * y_fine[j] + y_fine[j + 1]
        if denom < 0:
            fine = x_fine[1] - x_fine[0]
            return float(x_fine[j]
                         + 0.5 * fine * (y_fine[j - 1] - y_fine[j + 1]) / denom)
    return float(x_fine[j])


def _skewed_voigt_profile(x, center, amplitude, sigma, gamma, skew):
    from lmfit.lineshapes import skewed_voigt

    offset = _skewed_voigt_apex_offset(float(sigma), float(gamma), float(skew))
    return skewed_voigt(x, amplitude=amplitude, center=center - offset,
                        sigma=sigma, gamma=gamma, skew=skew)


def _area_normalised(x, shape, area):
    """Scale a unit-amplitude *shape* so its integral over *x* is *area*.

    The asymmetric shapes have no closed-form area, so KherveFitting
    normalises them numerically over the spectrum's own x range — do the
    same here or the heights come out different.
    """
    order = np.argsort(x)
    unit = abs(np.trapz(shape[order], x[order]))
    return (area / unit) * shape if unit else np.zeros_like(shape)


# ---------------------------------------------------------------------------
#  Lineshapes
# ---------------------------------------------------------------------------
def _gl_height(x, p):
    return p.height * (_gaussian(x, p.center, p.fwhm, p.lg)
                       * _lorentzian(x, p.center, p.fwhm, p.lg))


def _sgl_height(x, p):
    return p.height * ((1 - p.lg / 100) * _gaussian(x, p.center, p.fwhm, 0)
                       + p.lg / 100 * _lorentzian(x, p.center, p.fwhm, 100))


def _gl_area(x, p):
    sigma = p.fwhm * _FWHM_TO_SIGMA
    height = p.area / (sigma * np.sqrt(2 * np.pi)) if sigma else 0.0
    return height * (_gaussian(x, p.center, p.fwhm, p.lg)
                     * _lorentzian(x, p.center, p.fwhm, p.lg))


def _sgl_area(x, p):
    sigma = p.fwhm * _FWHM_TO_SIGMA
    gamma = p.fwhm / 2
    norm = ((1 - p.lg / 100) * sigma * np.sqrt(2 * np.pi)
            + (p.lg / 100) * np.pi * gamma)
    height = p.area / norm if norm else 0.0
    return height * ((1 - p.lg / 100) * _gaussian(x, p.center, p.fwhm, 0)
                     + p.lg / 100 * _lorentzian(x, p.center, p.fwhm, 100))


def _voigt_area(x, p):
    from lmfit.lineshapes import voigt

    f_g, f_l = _voigt_fwhm_split(p.fwhm, p.lg)
    return voigt(x, amplitude=p.area, center=p.center,
                 sigma=max(f_g * _FWHM_TO_SIGMA, 1e-4), gamma=f_l / 2.0)


def _voigt_area_skew(x, p):
    f_g, f_l = _voigt_fwhm_split(p.fwhm, p.lg)
    return _skewed_voigt_profile(x, p.center, p.area,
                                 max(f_g * _FWHM_TO_SIGMA, 1e-4),
                                 f_l / 2.0, p.skew)


def _voigt_sigma_gamma(x, p):
    """Voigt driven by separate widths: the sigma and gamma columns.

    The stored Area is not the lmfit amplitude for this variant — it is
    scaled from the height, exactly as KherveFitting does.
    """
    import lmfit

    model = lmfit.models.VoigtModel()
    sigma = max(p.sigma / 2.355, 1e-4)
    gamma = max(p.gamma / 2.0, 1e-6)
    unit = model.eval(center=0, amplitude=1, sigma=sigma, gamma=gamma, x=0)
    amplitude = p.height / unit if unit else 0.0
    return model.eval(x=x, center=p.center, amplitude=amplitude,
                      sigma=sigma, gamma=gamma)


def _voigt_sigma_gamma_skew(x, p):
    return _skewed_voigt_profile(x, p.center, p.area,
                                 max(p.sigma / 2.355, 1e-4),
                                 max(p.gamma / 2.0, 1e-6), p.skew)


def _pseudo_voigt_area(x, p):
    import lmfit

    model = lmfit.models.PseudoVoigtModel()
    sigma = p.fwhm / 2
    unit = model.eval(center=0, amplitude=1, sigma=sigma,
                      fraction=p.lg / 100, x=0)
    amplitude = p.height / unit if unit else 0.0
    return model.eval(x=x, center=p.center, amplitude=amplitude, sigma=sigma,
                      fraction=p.lg / 100)


def _expgauss_area(x, p):
    import lmfit

    return lmfit.models.ExponentialGaussianModel().eval(
        x=x, center=p.center, amplitude=p.area,
        sigma=max(p.sigma, 1e-6), gamma=max(p.gamma, 1e-6))


def _doniach(x, p):
    import lmfit

    model = lmfit.models.DoniachModel()
    sigma = max(p.sigma, 1e-6)
    probe = np.linspace(-10 * sigma, 10 * sigma, 1000)
    unit = np.max(model.eval(x=probe, center=0, amplitude=1, sigma=sigma,
                             gamma=p.gamma, asymmetry=p.skew))
    amplitude = p.height / unit if unit else 0.0
    return model.eval(x=x, center=p.center, amplitude=amplitude, sigma=sigma,
                      gamma=p.gamma, asymmetry=p.skew)


def _doniach_gauss(x, p):
    """Doniach-Sunjic convolved with a Gaussian (the DS*G model)."""
    from scipy.signal import convolve

    sigma = max(p.sigma, 1e-6)          # Gaussian FWHM
    gamma = max(p.gamma, 1e-6)          # DS width
    skew = float(np.clip(p.skew, 0.001, 0.999))

    span = max(x.max() - x.min(), 4 * (gamma + sigma))
    grid = np.linspace(-span / 2, span / 2, max(len(x), 64) * 4)
    t = -grid
    ds = (np.cos(np.pi * skew / 2 + (1 - skew) * np.arctan2(t, gamma))
          / (gamma ** 2 + t ** 2) ** ((1 - skew) / 2))
    gauss = np.exp(-4 * np.log(2) * (grid / sigma) ** 2)
    gauss = gauss / np.sum(gauss)
    shape = np.interp(x - p.center, grid, convolve(ds, gauss, mode="same"))
    return _area_normalised(x, shape, p.area)


def _la(x, p):
    """LA: two Lorentzian exponents, one per side of the peak."""
    sigma, gamma = max(p.sigma, 1e-6), max(p.gamma, 1e-6)
    width = 2 * p.fwhm / (np.sqrt(2 ** (1 / sigma) - 1)
                          + np.sqrt(2 ** (1 / gamma) - 1))
    t = x - p.center
    base = 1 / (1 + 4 * (t / width) ** 2)
    shape = np.where(t <= 0, base ** gamma, base ** sigma)
    return _area_normalised(x, shape, p.area)


def _lf(x, p):
    """LF (finite Lorentzian): LA whose exponents ramp to 3 in the tails,
    which drives them to the baseline and makes the area finite."""
    sigma, gamma = max(p.sigma, 1e-6), max(p.gamma, 1e-6)
    width = 2 * p.fwhm / (np.sqrt(2 ** (1 / sigma) - 1)
                          + np.sqrt(2 ** (1 / gamma) - 1))
    t = x - p.center
    base = 1 / (1 + 4 * (t / width) ** 2)
    ramp = 1.0 / (1.0 + 4.0 * (t / max(p.damping, 1e-3)) ** 2)
    expo = np.where(t <= 0, gamma, sigma)
    shape = base ** (3.0 - (3.0 - expo) * ramp)
    return _area_normalised(x, shape, p.area)


def _la_gauss(x, p):
    """LA convolved with a Gaussian of FWHM ``fwhm_g``."""
    from scipy.signal import convolve

    sigma, gamma = max(p.sigma, 1e-6), max(p.gamma, 1e-6)
    width = 2 * p.fwhm / (np.sqrt(2 ** (1 / sigma) - 1)
                          + np.sqrt(2 ** (1 / gamma) - 1))
    span = max(x.max() - x.min(), 4 * p.fwhm)
    grid = np.linspace(-span / 2, span / 2, max(len(x), 64) * 4)
    base = 1 / (1 + 4 * (grid / width) ** 2)
    la = np.where(grid <= 0, base ** gamma, base ** sigma)
    gauss = np.exp(-4 * np.log(2) * (grid / max(p.fwhm_g, 1e-6)) ** 2)
    shape = np.interp(x - p.center, grid,
                      convolve(la, gauss, mode="same") / np.sum(gauss))
    return _area_normalised(x, shape, p.area)


def _gelius_tail(t, fwhm, a, b):
    """The CasaXPS Gelius asymmetric tail, added on the high-BE side.

    Zero in both value and slope at the centre, so ``Position`` stays the
    true maximum and the height column still means the apex height.
    """
    w = b * (0.7 + 0.3 / (a + 0.01))
    u = 2.0 * np.sqrt(np.log(2.0)) * np.where(t > 0, t, 0.0)
    aw = np.exp(-(u / (fwhm + a * u)) ** 2)
    g0 = np.exp(-(u / fwhm) ** 2)
    return np.where(t > 0, w * (aw - g0), 0.0)


def _a_gl(x, p):
    m = np.clip(p.lg, 0.0, 100.0) / 100.0
    t = x - p.center
    gl = (np.exp(-4 * np.log(2) * (1 - m) * t ** 2 / p.fwhm ** 2)
          / (1 + 4 * m * t ** 2 / p.fwhm ** 2))
    return p.height * (gl + _gelius_tail(t, p.fwhm, p.sigma, p.gamma))


def _a_sgl(x, p):
    m = np.clip(p.lg, 0.0, 100.0) / 100.0
    t = x - p.center
    sgl = ((1 - m) * np.exp(-4 * np.log(2) * t ** 2 / p.fwhm ** 2)
           + m / (1 + 4 * t ** 2 / p.fwhm ** 2))
    return p.height * (sgl + _gelius_tail(t, p.fwhm, p.sigma, p.gamma))


def _sb_height(x, p):
    """SB(0)V — the sigmoid response of a Voigt bell, used as an
    optimisable background step under a photoelectron peak."""
    fwhm = max(p.fwhm, 1e-3)
    t = x - p.center
    span = max(20.0 * fwhm, (np.max(np.abs(t)) if t.size else 0.0) + 10 * fwhm)
    grid = np.linspace(-span, span, 4001)
    f_g, f_l = _voigt_fwhm_split(fwhm, p.lg)
    from lmfit.lineshapes import voigt
    bell = voigt(grid, amplitude=1.0, center=0.0,
                 sigma=max(f_g * _FWHM_TO_SIGMA, 1e-4), gamma=f_l / 2.0)
    cdf = np.cumsum(bell)
    return p.height * np.interp(t, grid, cdf / cdf[-1])


# ---------------------------------------------------------------------------
#  Dispatch
# ---------------------------------------------------------------------------
#: Model name (as stored in the .kfit) -> evaluator.
_MODELS = {
    "GL (Height)": _gl_height,
    "SGL (Height)": _sgl_height,
    "GL (Area)": _gl_area,
    "SGL (Area)": _sgl_area,
    "Voigt (Area)": _voigt_area,
    "Voigt (Area, L/G, S)": _voigt_area_skew,
    "Voigt (Area, L/G, σ)": _voigt_sigma_gamma,
    "Voigt (Area, σ, γ)": _voigt_sigma_gamma,
    "Voigt (Area, L/G, σ, S)": _voigt_sigma_gamma_skew,
    "Pseudo-Voigt (Area)": _pseudo_voigt_area,
    "ExpGauss.(Area, σ, γ)": _expgauss_area,
    "DS (A, σ, γ)": _doniach,
    "DS*G (A, σ, γ, S)": _doniach_gauss,
    "LA (Area, σ, γ)": _la,
    "LA (Area, σ/γ, γ)": _la,
    "LA*G (Area, σ/γ, γ)": _la_gauss,
    "LF (Area, σ, γ, w)": _lf,
    "A*GL (Area, a, b)": _a_gl,
    "A*SGL (Area, a, b)": _a_sgl,
    "SB (Height)": _sb_height,
}

#: Entries that are fits but not lineshapes — a D-parameter derivative, a
#: Curie-Weiss law, an equivalent circuit. They have no curve to add to a
#: spectrum, so they are skipped silently rather than reported as gaps.
NON_SPECTRAL = {"Unfitted", "SurveyID", "D-parameter", "Curie-Weiss",
                "Equivalent Circuit", "Fermi", "VBM", "Cut-Off",
                "SingleEntity", "SingleEntity_OLD"}


class _Params:
    """The stored peak parameters, named the way the lineshapes want them."""

    __slots__ = ("center", "height", "fwhm", "lg", "area", "sigma", "gamma",
                 "skew", "fwhm_g", "damping")

    def __init__(self, peak):
        self.center = _num(peak.get("Position"))
        self.height = _num(peak.get("Height"))
        self.fwhm = _num(peak.get("FWHM"), 1.0) or 1.0
        self.lg = _num(peak.get("L/G"), 30.0)
        self.area = _num(peak.get("Area"))
        self.sigma = _num(peak.get("Sigma"))
        self.gamma = _num(peak.get("Gamma"))
        self.skew = _num(peak.get("Skew"))
        # LA*G keeps its Gaussian width in its own key, but older projects
        # parked it in the skew column, which is unused for that model.
        self.fwhm_g = _num(peak.get("fwhm_g")) or self.skew or 1.0
        self.damping = _num(peak.get("Skew"), 30.0) or 30.0   # LF's w


def _num(value, default=0.0):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if np.isfinite(out) else default


def model_name(peak: dict) -> str:
    return str(peak.get("Fitting Model") or "").strip()


def is_supported(peak: dict) -> bool:
    return model_name(peak) in _MODELS


def peak_curve(x, peak: dict):
    """Evaluate one stored peak over *x*, above the background.

    Returns ``None`` when the model is not a lineshape this module can
    draw, so the caller can say so instead of showing a wrong fit.
    """
    fn = _MODELS.get(model_name(peak))
    if fn is None:
        return None
    x = np.asarray(x, dtype=float)
    try:
        curve = np.asarray(fn(x, _Params(peak)), dtype=float)
    except Exception:
        return None
    if curve.shape != x.shape:
        return None
    return np.nan_to_num(curve, nan=0.0, posinf=0.0, neginf=0.0)
