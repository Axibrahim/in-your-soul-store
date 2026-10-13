"""
Generate every PWA image (home-screen icons, favicon, iPhone splash screens) from the brand star in
app/static/images/logo.png.

    pip install pillow
    python tools/generate_pwa_assets.py

Output:  app/static/icons/*   app/static/splash/*
The star is composited ADDITIVELY on the brand background (#040804), so its glow blends in with no
visible box. The wordmark on the splash screens uses tools/space-mono-700.woff (Space Mono Bold, SIL OFL);
if that file is missing the splash screens are generated without the wordmark.
"""
import os
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(ROOT, "app", "static", "images", "logo.png")
FONT = os.path.join(ROOT, "tools", "space-mono-700.woff")
ICONS = os.path.join(ROOT, "app", "static", "icons")
SPLASH = os.path.join(ROOT, "app", "static", "splash")

BG = (4, 8, 4)            # --bg
ACCENT = (118, 255, 3)    # --accent

# (css px width, css px height, device pixel ratio) for portrait iPhones -> image is (w*dpr, h*dpr)
IPHONES = [
    (440, 956, 3),  # 16 Pro Max
    (402, 874, 3),  # 16 Pro
    (430, 932, 3),  # 14 Pro Max, 15 Plus, 15 Pro Max, 16 Plus
    (393, 852, 3),  # 14 Pro, 15, 15 Pro, 16
    (428, 926, 3),  # 12/13 Pro Max, 14 Plus
    (390, 844, 3),  # 12/13/14, 12/13 Pro
    (375, 812, 3),  # X, XS, 11 Pro, 12/13 mini
    (414, 896, 3),  # XS Max, 11 Pro Max
    (414, 896, 2),  # XR, 11
    (414, 736, 3),  # 6/7/8 Plus
    (375, 667, 2),  # 6/7/8, SE 2/3
    (320, 568, 2),  # SE 1
]


def load_star():
    src = Image.open(LOGO).convert("RGB")
    mask = src.convert("L").point(lambda v: 255 if v > 40 else 0)
    l, t, r, b = mask.getbbox()
    pad = 28                       # keep the soft glow
    box = (max(l - pad, 0), max(t - pad, 0), min(r + pad, src.width), min(b + pad, src.height))
    star = src.crop(box)
    side = max(star.size)          # square it so it centres exactly on the star
    sq = Image.new("RGB", (side, side), (0, 0, 0))
    sq.paste(star, ((side - star.width) // 2, (side - star.height) // 2))
    return sq


STAR = load_star()


def paste_star(canvas, width, cx, cy):
    width = int(width)
    star = STAR.resize((width, width), Image.LANCZOS)
    x, y = int(cx - width / 2), int(cy - width / 2)
    region = canvas.crop((x, y, x + width, y + width))
    canvas.paste(ImageChops.add(region, star), (x, y))


def square_icon(size, star_frac):
    img = Image.new("RGB", (size, size), BG)
    paste_star(img, size * star_frac, size / 2, size / 2)
    return img


def save(img, folder, name):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    img.save(path, optimize=True)
    print(f"  {os.path.relpath(path, ROOT)}  {img.size[0]}x{img.size[1]}")


def wordmark(canvas, text, cx, top, font_px):
    if not os.path.exists(FONT):
        return
    font = ImageFont.truetype(FONT, font_px)
    track = font_px * 0.34
    widths = [font.getlength(c) for c in text]
    total = sum(widths) + track * (len(text) - 1)
    layer = Image.new("RGB", canvas.size, (0, 0, 0))
    d = ImageDraw.Draw(layer)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        d.text((x, top), ch, font=font, fill=ACCENT)
        x += w + track
    glow = layer.filter(ImageFilter.GaussianBlur(font_px * 0.35)).point(lambda v: int(v * 0.55))
    out = ImageChops.add(canvas, glow)
    out.paste(ImageChops.add(out, layer))
    canvas.paste(out)


def splash(w, h):
    img = Image.new("RGB", (w, h), BG)
    star_w = min(w * 0.36, 640)
    cy = h * 0.44
    paste_star(img, star_w, w / 2, cy)
    wordmark(img, "IN YOUR SOUL", w / 2, cy + star_w / 2 + h * 0.035, max(int(w * 0.047), 14))
    return img


def main():
    print("icons:")
    save(square_icon(1024, 0.66), ICONS, "icon-master-1024.png")   # open this one in Figma to tweak
    save(square_icon(512, 0.66), ICONS, "icon-512.png")
    save(square_icon(192, 0.66), ICONS, "icon-192.png")
    # maskable: the OS may crop to a circle/squircle, so keep the star inside the central 80% safe zone
    save(square_icon(512, 0.56), ICONS, "icon-maskable-512.png")
    save(square_icon(192, 0.56), ICONS, "icon-maskable-192.png")
    save(square_icon(180, 0.64), ICONS, "apple-touch-icon.png")    # iOS: opaque square, iOS rounds the corners
    save(square_icon(96, 0.70), ICONS, "shortcut-96.png")
    fav = {s: square_icon(s, 0.86) for s in (16, 32, 48)}
    save(fav[32], ICONS, "favicon-32.png")
    fav[48].save(os.path.join(ICONS, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
    print("  app/static/icons/favicon.ico  16/32/48")
    print("splash:")
    for cw, ch, dpr in IPHONES:
        save(splash(cw * dpr, ch * dpr), SPLASH, f"iphone-{cw * dpr}x{ch * dpr}.png")


if __name__ == "__main__":
    main()