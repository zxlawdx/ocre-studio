"""Inference routines adapted from the Kokentau Studio V8.2 reference."""

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

HALO = 9


def rgb01(a):
    return (
        np.asarray(a, dtype=np.float32) / 255
        if np.asarray(a).dtype == np.uint8
        else np.asarray(a, dtype=np.float32)
    )


def opp(a):
    r, g, b = a.transpose(2, 0, 1)
    return np.stack((r - g, (r + g) * 0.5 - b), -1)


def blur(a, s):
    return cv2.GaussianBlur(a, (0, 0), max(0.5, float(s)), borderType=cv2.BORDER_REFLECT_101)


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -20, 20)))


def palette(a, z):
    y = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    red = sigmoid((z[..., 0] - 1.35) * 2.2)
    cyan = sigmoid((z[..., 1] - 0.65) * 2.0) * (1 - red)
    mag = sigmoid((-z[..., 1] - 0.65) * 1.25) * (1 - red) * (1 - cyan) * 0.55
    rock = np.array([0.24, 0.18, 0.75], np.float32)
    c = rock + (np.array([0.045, 0.88, 0.94], np.float32) - rock) * cyan[..., None]
    c = c + (np.array([0.7, 0.12, 0.8], np.float32) - rock) * mag[..., None]
    c = c * (1 - red[..., None]) + np.array([0.94, 0.12, 0.24], np.float32) * red[..., None]
    return np.clip(c * (0.52 + 0.78 * y[..., None]), 0, 1).astype(np.float32)


def _stats(o):
    q = o[:: max(1, o.shape[0] // 256), :: max(1, o.shape[1] // 256)].reshape(-1, 2)
    med = np.median(q, axis=0)
    v = q - med
    lo, hi = np.quantile(v, [0.02, 0.98], axis=0)
    v = np.clip(v, lo, hi)
    cov = v.T @ v / max(1, len(v) - 1)
    e, u = np.linalg.eigh(cov + np.eye(2) * 0.00035)
    w = (u / e**0.5 @ u.T).astype(np.float32)
    s = np.maximum(np.median(np.abs(v), axis=0) * 1.4826, 0.022).astype(np.float32)
    return (med.astype(np.float32), w, s)


def experts7(a, legacy):
    x = rgb01(a)
    b = rgb01(legacy)
    o = opp(x)
    med, w, s = _stats(o)
    sm = blur(o, 0.65)
    zg = (sm - med) @ w
    h, w = x.shape[:2]
    scale = min(1.0, 512 / max(h, w))
    ws, hs = (max(2, round(w * scale)), max(2, round(h * scale)))
    small_o = cv2.resize(sm, (ws, hs), interpolation=cv2.INTER_AREA)
    sigma = max(3, min(hs, ws) * 0.045)
    local = cv2.resize(blur(small_o, sigma), (w, h), interpolation=cv2.INTER_LINEAR)
    second = cv2.resize(blur(small_o * small_o, sigma), (w, h), interpolation=cv2.INTER_LINEAR)
    variance = np.maximum(second - local * local, 0)
    zl = 0.55 * zg + 0.45 * (sm - local) / np.sqrt(variance + 0.00035)
    zr = (sm - med) / s
    es = np.stack([palette(x, zg), palette(x, zl), palette(x, zr), b], 0).astype(np.float32)
    q = x[:: max(1, x.shape[0] // 256), :: max(1, x.shape[1] // 256)].reshape(-1, 3)
    ctx = np.concatenate(
        [
            q.mean(0),
            q.std(0),
            med,
            s,
            np.array([np.mean(np.abs(o - sm)), np.mean(np.abs(sm - local))]),
        ]
    ).astype(np.float32)

    def small(im):
        h, w = im.shape[:2]
        f = min(1, 256 / max(h, w))
        return cv2.resize(
            im, (max(2, round(w * f)), max(2, round(h * f))), interpolation=cv2.INTER_AREA
        )

    orig = small(o)
    mag = np.zeros(orig.shape[:2], np.float32)
    for ch in range(2):
        mag += np.abs(cv2.Sobel(orig[..., ch], cv2.CV_32F, 1, 0, ksize=3)) + np.abs(
            cv2.Sobel(orig[..., ch], cv2.CV_32F, 0, 1, ksize=3)
        )
    support = mag / (mag + max(float(np.quantile(mag, 0.65)), 0.012))
    logits = []
    for i, im in enumerate(es):
        c = opp(small(im))
        g = sum(
            (
                np.abs(cv2.Sobel(c[..., ch], cv2.CV_32F, dx, dy, ksize=3))
                for ch in range(2)
                for dx, dy in [(1, 0), (0, 1)]
            )
        )
        useful = float((g * support).sum() / (g.sum() + 1e-06))
        excessive = float(np.maximum(g - 1.8, 0).mean())
        logits.append(3 * useful - 1.5 * excessive + [0.2, 0.1, 0.0, -0.8][i])
    prob = np.exp(np.array(logits, np.float32) - max(logits))
    prob /= prob.sum()
    prob[:3] *= (1 - min(float(prob[3]), 0.15)) / prob[:3].sum()
    prob[3] = min(float(prob[3]), 0.15)
    anchor = np.einsum("e,ehwc->hwc", prob, es).astype(np.float32)
    luminance = x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    high = luminance - blur(luminance, 1.15)
    ch = np.linalg.norm(o - blur(o, 1.15), axis=2)
    support_native = ch / (ch + 0.018)
    detail = np.clip(high * (0.22 + 0.48 * support_native), -0.035, 0.035)
    t = np.clip(anchor + detail[..., None], 0, 1).astype(np.float32)
    return (es, ctx, prob, t)


class AdaptiveV7(nn.Module):
    def __init__(self):
        super().__init__()
        self.router = nn.Sequential(nn.Linear(12, 32), nn.SiLU(), nn.Linear(32, 4))
        self.stem = nn.Conv2d(8, 40, 3, padding=1)
        self.blocks = nn.ModuleList(
            [nn.Conv2d(40, 40, 3, padding=d, dilation=d) for d in (1, 2, 3)]
        )
        self.att = nn.Sequential(nn.Linear(12, 40), nn.Sigmoid())
        self.out = nn.Conv2d(40, 3, 3, padding=1)
        nn.init.zeros_(self.router[-1].weight)
        nn.init.zeros_(self.router[-1].bias)
        nn.init.zeros_(self.out.weight)
        nn.init.zeros_(self.out.bias)

    def weights(self, ctx, prior):
        w = torch.softmax(prior.clamp_min(1e-06).log() + 0.6 * torch.tanh(self.router(ctx)), dim=1)
        leg = w[:, 3:4].clamp(max=0.2)
        return torch.cat(
            (w[:, :3] * (1 - leg) / w[:, :3].sum(1, keepdim=True).clamp_min(1e-06), leg), 1
        )

    def forward(self, a, es, ctx, prior, strength=1.0):
        w = self.weights(ctx, prior)
        base = (es * w[:, :, None, None, None]).sum(1)
        r, g, b = a.unbind(1)
        op = torch.stack((r - g, (r + g) * 0.5 - b), 1)
        f = F.silu(self.stem(torch.cat((a, base, op), 1)))
        att = 0.5 + self.att(ctx)[:, :, None, None]
        for layer in self.blocks:
            f = f + 0.4 * F.silu(layer(f)) * att
        p = base + 0.06 * torch.tanh(self.out(f))
        return (a + float(strength) * (p - a), w)


def _to(im, device):
    return torch.from_numpy(np.ascontiguousarray(im)).float().to(device)


@torch.inference_mode()
def infer7(model, a, legacy, block=384, strength=1.0, return_experts=False):
    device = next(model.parameters()).device
    model.eval()
    es, ctx, prior, t = experts7(a, legacy)
    x = rgb01(a)
    H, W = x.shape[:2]
    result = np.empty((H, W, 3), np.uint8)
    c = _to(ctx, device)[None]
    pr = _to(prior, device)[None]
    weights = model.weights(c, pr)[0].cpu().numpy()
    for y in range(0, H, block):
        for z in range(0, W, block):
            y1, z1 = (min(y + block, H), min(z + block, W))
            y0, z0 = (max(0, y - HALO), max(0, z - HALO))
            yy, zz = (min(H, y1 + HALO), min(W, z1 + HALO))
            aa = _to(x[y0:yy, z0:zz].transpose(2, 0, 1), device)[None]
            ee = _to(es[:, y0:yy, z0:zz].transpose(0, 3, 1, 2), device)[None]
            p, _ = model(aa, ee, c, pr, strength)
            p = p[0, :, y - y0 : y1 - y0, z - z0 : z1 - z0]
            result[y:y1, z:z1] = (p.clamp(0, 1) * 255).round().byte().permute(1, 2, 0).cpu().numpy()
    if return_experts:
        return (
            result,
            weights,
            [(v * 255).round().astype(np.uint8) for v in es],
            (t * 255).round().astype(np.uint8),
        )
    return result
