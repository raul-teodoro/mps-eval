"""Gera o ícone do MPS-Eval (squircle estilo iOS): PNGs e .ico multi-resolução.

Uso: python tools/gerar_icone.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[1] / "mpseval" / "assets" / "icon"
S = 4096                       # superamostragem
TOP, BOTTOM = (90, 170, 255), (0, 86, 220)     # azul de sistema, claro → profundo


def squircle_mask(size: int, n: float = 5.0, margin: float = 0.0) -> Image.Image:
    """Superelipse |x|^n + |y|^n = 1 — a forma contínua dos ícones iOS."""
    m = Image.new("L", (size, size), 0)
    r = size / 2 * (1 - margin)
    c = size / 2
    pts = []
    for i in range(2048):
        t = 2 * math.pi * i / 2048
        ct, st = math.cos(t), math.sin(t)
        x = c + r * math.copysign(abs(ct) ** (2 / n), ct)
        y = c + r * math.copysign(abs(st) ** (2 / n), st)
        pts.append((x, y))
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def gradient(size: int) -> Image.Image:
    g = Image.new("RGB", (1, size))
    for y in range(size):
        k = y / (size - 1)
        g.putpixel((0, y), tuple(round(a + (b - a) * k) for a, b in zip(TOP, BOTTOM)))
    return g.resize((size, size))


def thick_polyline(d: ImageDraw.ImageDraw, pts, w, fill):
    for a, b in zip(pts, pts[1:]):
        d.line([a, b], fill=fill, width=w)
    for x, y in pts:
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=fill)


def glyph(size: int, ring_w: float, check_w: float, mode: str = "full") -> Image.Image:
    """Anel de progresso (~80%) com ponta arredondada + check central, em branco.

    mode: "full" (com trilho translúcido), "bold" (sem trilho) ou "check" (só o check, ampliado).
    """
    g = Image.new("L", (size, size), 0)
    if mode == "check":
        d = ImageDraw.Draw(g)
        c, k = size / 2, size * 0.0019
        pts = [(c - 105 * k, c + 8 * k), (c - 30 * k, c + 80 * k), (c + 115 * k, c - 75 * k)]
        thick_polyline(d, pts, int(size * check_w), 255)
        return g
    d = ImageDraw.Draw(g)
    c = size / 2
    R = size * 0.285
    w = int(size * ring_w)
    # trilho do anel (translúcido)
    track = Image.new("L", (size, size), 0)
    ImageDraw.Draw(track).ellipse([c - R, c - R, c + R, c + R], outline=255, width=w)
    if mode == "full":
        g = ImageChops.lighter(g, track.point(lambda v: int(v * 0.32)))
    d = ImageDraw.Draw(g)
    # arco de progresso: começa no topo, sentido horário, 290°
    start, sweep = -90, 290
    d.arc([c - R, c - R, c + R, c + R], start, start + sweep, fill=255, width=w)
    for ang in (start, start + sweep):
        a = math.radians(ang)
        rr = R - w / 2
        x, y = c + rr * math.cos(a), c + rr * math.sin(a)
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=255)
    # check
    k = size * 0.001
    pts = [(c - 105 * k * 1.0, c + 8 * k), (c - 30 * k, c + 80 * k), (c + 115 * k, c - 75 * k)]
    thick_polyline(d, pts, int(size * check_w), 255)
    return g


def render(px: int) -> Image.Image:
    """Desenha em alta resolução e reduz. Tamanhos pequenos usam versões simplificadas."""
    if px <= 20:
        mode, ring_w, check_w = "check", 0, 0.17
    elif px <= 32:
        mode, ring_w, check_w = "bold", 0.12, 0.11
    else:
        mode, ring_w, check_w = "full", 0.085, 0.080
    base = gradient(S).convert("RGBA")
    # sombra suave sob o glifo, para profundidade
    gl = glyph(S, ring_w, check_w, mode)
    shadow = gl.filter(ImageFilter.GaussianBlur(S * 0.012)).point(lambda v: int(v * 0.28))
    shadow = ImageChops.offset(shadow, 0, int(S * 0.008))
    base = Image.composite(Image.new("RGBA", (S, S), (0, 30, 90, 255)), base, shadow)
    base = Image.composite(Image.new("RGBA", (S, S), (255, 255, 255, 255)), base, gl)
    mask = squircle_mask(S, margin=0.0 if px <= 32 else 0.02)
    base.putalpha(mask)
    return base.resize((px, px), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256, 512, 1024]
    imgs = {s: render(s) for s in sizes}
    for s in (16, 32, 64, 128, 256, 512, 1024):
        imgs[s].save(OUT / f"mpseval_{s}.png")
    ico_sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    imgs[256].save(OUT / "mpseval.ico", sizes=[(s, s) for s in ico_sizes],
                   append_images=[imgs[s] for s in ico_sizes if s != 256])
    print("ícones gerados em", OUT)


if __name__ == "__main__":
    main()
