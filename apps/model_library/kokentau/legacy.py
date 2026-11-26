"""Inference routines adapted from the Kokentau Studio V8.2 reference."""

import torch
import torch.nn.functional as F
from torch import nn


class Grade(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 16, 5, 4, 2),
            nn.SiLU(),
            nn.Conv2d(16, 24, 3, 2, 1),
            nn.SiLU(),
            nn.Conv2d(24, 32, 3, 2, 1),
            nn.SiLU(),
            nn.AdaptiveAvgPool2d((8, 8)),
        )
        self.global_fc = nn.Linear(32, 32)
        self.head = nn.Conv2d(32, 12 * 8, 1)
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)
        self.register_buffer("identity", torch.eye(3, 4).reshape(1, 12, 1, 1, 1))

    def grade(self, ctx):
        f = self.features(ctx)
        f = f + self.global_fc(f.mean((2, 3)))[:, :, None, None]
        grade = self.head(f).reshape(-1, 12, 8, 8, 8) + self.identity
        canais = self.oponentes(ctx).flatten(2)
        media = canais.mean(2, keepdim=True)
        centrado = canais - media
        cov = centrado @ centrado.transpose(1, 2) / (canais.shape[-1] - 1)
        e, u = torch.linalg.eigh(cov)
        w = u * (e.clamp_min(0) + 0.0004).rsqrt()[:, None, :] @ u.transpose(1, 2)
        return (grade, media, w)

    @staticmethod
    def oponentes(x):
        r, g, b = x.unbind(1)
        return torch.stack((r - g, (r + g) * 0.5 - b), 1)

    def aplicar(self, grade, x, geo):
        top, left, H, W = geo.float().unbind(1)
        h, w = x.shape[-2:]
        y = (
            2 * (top[:, None] + torch.arange(h, device=x.device)) / (H - 1).clamp_min(1)[:, None]
            - 1
        )
        u = (
            2 * (left[:, None] + torch.arange(w, device=x.device)) / (W - 1).clamp_min(1)[:, None]
            - 1
        )
        grade, media, w_zca = grade
        z = w_zca @ (self.oponentes(x).flatten(2) - media)
        amarelo, vermelho = (z[:, 1].clamp_min(0), z[:, 0].clamp_min(0))
        guia = (amarelo - 0.35).clamp_min(0) / 1.25 - (vermelho - 1.7).clamp_min(0) / 1.4
        guia = guia.clamp(-1, 1).reshape(-1, h, w)
        pontos = torch.stack(
            (u[:, None, :].expand_as(guia), y[:, :, None].expand_as(guia), guia), -1
        )
        afim = F.grid_sample(grade, pontos[:, None], padding_mode="border", align_corners=True)
        afim = afim.reshape(-1, 3, 4, h, w)
        return (afim[:, :, :3] * x[:, None]).sum(2) + afim[:, :, 3]

    def forward(self, ctx, x, geo):
        return self.aplicar(self.grade(ctx), x, geo)
