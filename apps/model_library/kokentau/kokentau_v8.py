"""Inference routines adapted from the Kokentau Studio V8.2 reference."""

import cv2
import numpy as np
import torch
from scipy.ndimage import binary_fill_holes, distance_transform_edt

from .kokentau_v7_core import infer7, opp, palette


def u8(x):
    return np.round(np.clip(x, 0, 1) * 255).astype(np.uint8)


def rgb(x):
    return (
        np.asarray(x, dtype=np.float32) / 255
        if x.dtype == np.uint8
        else np.asarray(x, dtype=np.float32)
    )


def ten(a, device="cpu"):
    return torch.from_numpy(np.ascontiguousarray(rgb(a).transpose(2, 0, 1)))[None].to(device)


@torch.inference_mode()
def grade_img(m, a, block=384):
    device = next(m.parameters()).device
    h, w = a.shape[:2]
    g = m.grade(ten(cv2.resize(a, (256, 256), interpolation=cv2.INTER_LINEAR), device))
    out = np.empty_like(a)
    for y in range(0, h, block):
        for x in range(0, w, block):
            sl = np.s_[y : y + block, x : x + block]
            q = m.aplicar(g, ten(a[sl], device), torch.tensor([[y, x, h, w]], device=device))
            out[sl] = u8(q[0].permute(1, 2, 0).cpu().numpy())
    return out


def rectmask(shape, box):
    h, w = shape[:2]
    x0, y0, x1, y1 = map(int, box)
    x0, x1 = np.clip([x0, x1], 0, w)
    y0, y1 = np.clip([y0, y1], 0, h)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("ROI vazia")
    m = np.zeros((h, w), bool)
    m[y0:y1, x0:x1] = True
    return m


def auto_roi(a):
    """Conservative heuristic proposal, not a learned rock classifier. May fail on light rock."""
    h, w = a.shape[:2]
    scale = min(1.0, 640 / max(h, w))
    H, W = (max(8, round(h * scale)), max(8, round(w * scale)))
    small = cv2.resize(a, (W, H), interpolation=cv2.INTER_AREA)
    L = cv2.cvtColor(small, cv2.COLOR_RGB2LAB)[..., 0]
    L = cv2.GaussianBlur(L, (5, 5), 0)
    cut, _ = cv2.threshold(L, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    base = (L < cut).astype(np.uint8)
    K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    base = cv2.morphologyEx(base, cv2.MORPH_CLOSE, K)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(base)
    if n <= 1:
        return (None, {"reason": "sem componente contrastante"})
    Y, X = np.ogrid[:H, :W]
    center = ((Y - H * 0.5) / (H * 0.46)) ** 2 + ((X - W * 0.5) / (W * 0.46)) ** 2 < 1
    choices = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA] / (H * W)
        if 0.1 <= area <= 0.92:
            overlap = np.count_nonzero((labels == i) & center) / max(1, np.count_nonzero(center))
            choices.append((area * (0.3 + overlap), i))
    if not choices:
        return (None, {"reason": "área contrastante não conclusiva"})
    _, i = max(choices)
    seed = (labels == i).astype(np.uint8)
    sure_fg = cv2.erode(seed, K) > 0
    sure_bg = cv2.dilate(seed, K) == 0
    if not sure_fg.any() or not sure_bg.any():
        return (None, {"reason": "sementes insuficientes"})
    gc = np.where(seed > 0, cv2.GC_PR_FGD, cv2.GC_PR_BGD).astype(np.uint8)
    gc[sure_fg] = cv2.GC_FGD
    gc[sure_bg] = cv2.GC_BGD
    try:
        cv2.grabCut(
            small,
            gc,
            None,
            np.zeros((1, 65), np.float64),
            np.zeros((1, 65), np.float64),
            3,
            cv2.GC_INIT_WITH_MASK,
        )
    except cv2.error:
        return (None, {"reason": "GrabCut indisponível para esta foto"})
    m = np.isin(gc, [cv2.GC_FGD, cv2.GC_PR_FGD])
    m = binary_fill_holes(m)
    frac = float(m.mean())
    contrast = float(np.median(L[~m]) - np.median(L[m])) if m.any() and (~m).any() else 0.0
    if not 0.12 <= frac <= 0.9 or contrast < 15:
        return (
            None,
            {"reason": "contraste/área insuficiente", "area": frac, "contraste_L": contrast},
        )
    full = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
    return (
        full,
        {
            "reason": "GrabCut/contraste — sugestão não revisada",
            "area": frac,
            "contraste_L": contrast,
        },
    )


def roi_crop(a, m):
    ys, xs = np.nonzero(m)
    if len(ys) < 32:
        raise ValueError("ROI muito pequena")
    sl = np.s_[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    b = a[sl].copy()
    k = m[sl]
    if not k.all():
        idx = distance_transform_edt(~k, return_distances=False, return_indices=True)
        b[~k] = b[idx[0][~k], idx[1][~k]]
    return (sl, b, k)


def masked_color(a, m):
    x = rgb(a)
    o = opp(x)
    q = o[m]
    q = q[:: max(1, len(q) // 100000)]
    med = np.median(q, 0)
    v = q - med
    lo, hi = np.quantile(v, [0.02, 0.98], axis=0)
    v = np.clip(v, lo, hi)
    cov = v.T @ v / max(1, len(v) - 1)
    eig, U = np.linalg.eigh(cov + np.eye(2) * 0.00035)
    W = U * eig ** (-0.5) @ U.T
    z = (cv2.GaussianBlur(o, (0, 0), 0.65) - med) @ W
    return palette(x, z)


def guided(guide, target, radius=5, eps=0.002):
    def mean(values):
        size = 2 * radius + 1
        return cv2.boxFilter(
            values, -1, (size, size), normalize=True, borderType=cv2.BORDER_REFLECT
        )

    mean_guide, mean_target = mean(guide), mean(target)
    variance = np.maximum(mean(guide * guide) - mean_guide * mean_guide, 0)
    slope = (mean(guide * target) - mean_guide * mean_target) / (variance + eps)
    offset = mean_target - slope * mean_guide
    return mean(slope) * guide + mean(offset)


def norm_map(x, m, floor=0.015):
    d = max(float(np.quantile(x[m], 0.99)), floor)
    return np.clip(x / d, 0, 1).astype(np.float32)


def structure(a, m=None):
    """Apparent structure: source luminance, morphology, signed Hessian and oriented Gabor. NOT depth."""
    x = rgb(a)
    L = cv2.cvtColor(x, cv2.COLOR_RGB2GRAY)
    m = np.ones(L.shape, bool) if m is None else m
    sm = guided(L, L, 3, 0.0007)
    black = np.zeros_like(L)
    white = black.copy()
    dark = black.copy()
    bright = black.copy()
    gab = black.copy()
    detail = black.copy()
    for k in (3, 5, 9, 15, 31):
        K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        black = np.maximum(black, cv2.morphologyEx(sm, cv2.MORPH_BLACKHAT, K))
        white = np.maximum(white, cv2.morphologyEx(sm, cv2.MORPH_TOPHAT, K))
    for s in (1.0, 2.0, 4.0, 8.0):
        g = cv2.GaussianBlur(sm, (0, 0), s)
        dxx = cv2.Sobel(g, cv2.CV_32F, 2, 0, ksize=3) * s * s / 4
        dyy = cv2.Sobel(g, cv2.CV_32F, 0, 2, ksize=3) * s * s / 4
        dxy = cv2.Sobel(g, cv2.CV_32F, 1, 1, ksize=3) * s * s / 4
        root = np.sqrt((dxx - dyy) ** 2 + 4 * dxy * dxy)
        a1 = (dxx + dyy - root) / 2
        a2 = (dxx + dyy + root) / 2
        small = np.where(abs(a1) < abs(a2), a1, a2)
        large = np.where(abs(a1) < abs(a2), a2, a1)
        ratio = abs(small) / (abs(large) + 1e-06)
        val = np.exp(-(ratio**2) / 0.5) * (1 - np.exp(-(small**2 + large**2) / (2 * 0.018**2)))
        dark = np.maximum(dark, val * (large > 0))
        bright = np.maximum(bright, val * (large < 0))
        detail = np.maximum(detail, abs(sm - g))
    for th in np.arange(6) * np.pi / 6:
        K = cv2.getGaborKernel((15, 15), 2.5, float(th), 7.0, 0.6, 0, ktype=cv2.CV_32F)
        K -= K.mean()
        K /= max(np.abs(K).sum(), 1e-06)
        gab = np.maximum(gab, abs(cv2.filter2D(sm, -1, K)))
    B, T, D, R, G, P = [norm_map(i, m) for i in (black, white, dark, bright, gab, detail)]
    cla = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8)).apply(u8(L)).astype(np.float32) / 255
    support = np.clip(0.55 * np.maximum(B, T) * np.maximum(D, R) + 0.25 * G + 0.2 * P, 0, 1)
    signed = np.clip(0.65 * (L - guided(L, L, 9, 0.003)) + 0.2 * (white - black), -0.09, 0.09)
    lum = np.clip(0.65 * L + 0.35 * cla + signed, 0, 1)
    features = np.stack([L, B, T, D, R, G, P, support], -1).astype(np.float32)
    return (features, lum, signed)


def enhance(a, mask=None, grade=None, v7=None, block=384, forca=0.85):
    if not 0 <= forca <= 1:
        raise ValueError("forca deve estar entre 0 e 1")
    m = np.ones(a.shape[:2], bool) if mask is None else np.asarray(mask, bool)
    if m.shape != a.shape[:2]:
        raise ValueError("dimensão da máscara incompatível")
    sl, c, k = roi_crop(a, m)
    chrom = masked_color(c, k)
    maps, L, d = structure(c, k)
    if grade is not None and v7 is not None:
        v = infer7(v7, c, grade_img(grade, c, block), block=block)
        chrom = 0.6 * rgb(v) + 0.4 * chrom
    x = rgb(c)
    col = x + forca * (chrom - x)
    comb = np.clip(col + forca * (d * (0.3 + 0.7 * maps[..., 7]))[..., None], 0, 1)

    def paste(q):
        out = a.copy()
        target = out[sl]
        target[k] = u8(q)[k]
        return out

    def map_full(q):
        out = np.zeros(a.shape[:2], np.uint8)
        out[sl][k] = u8(q)[k]
        return out

    out = {
        "original": a,
        "roi": m.astype(np.uint8) * 255,
        "cromatico": paste(col),
        "estrutural": paste(np.repeat(L[..., None], 3, 2)),
        "combinado": paste(comb),
        "blackhat": map_full(maps[..., 1]),
        "tophat": map_full(maps[..., 2]),
        "hessiana_escura": map_full(maps[..., 3]),
        "hessiana_clara": map_full(maps[..., 4]),
        "gabor": map_full(maps[..., 5]),
        "suporte_estrutural": map_full(maps[..., 7]),
    }
    return out
