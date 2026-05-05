"""Generate banner.png using Pillow — no native C dependencies needed."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 400
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "banner.png")

img = Image.new("RGB", (W, H), color=(15, 23, 42))  # #0f172a
draw = ImageDraw.Draw(img)

# Background gradient (simulate with horizontal bands)
for y in range(H):
    t = y / H
    r = int(15 + t * (30 - 15))
    g = int(23 + t * (27 - 23))
    b = int(42 + t * (75 - 42))
    draw.line([(0, y), (W, y)], fill=(r, g, b))

# Accent bar left
for y in range(H):
    t = y / H
    r = int(99 + t * (168 - 99))
    g = int(102 + t * (85 - 102))
    b = int(241 + t * (247 - 241))
    draw.line([(0, y), (5, y)], fill=(r, g, b))

# Subtle grid
grid_color = (255, 255, 255, 15)
for gy in [100, 200, 300]:
    draw.line([(0, gy), (W, gy)], fill=(255, 255, 255), width=1)
for gx in [300, 600, 900]:
    draw.line([(gx, 0), (gx, H)], fill=(255, 255, 255), width=1)

# Try to load a nice font, fall back to default
def get_font(size, bold=False):
    attempts = [
        "C:/Windows/Fonts/segoeui.ttf" if not bold else "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arial.ttf" if not bold else "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibri.ttf" if not bold else "C:/Windows/Fonts/calibrib.ttf",
    ]
    for path in attempts:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

# Title
draw.text((60, 60), "Tenacious Judge", font=get_font(58, bold=True), fill=(248, 250, 252))

# Subtitle
draw.text((62, 130), "B2B Sales Outreach Pre-Send Judge  ·  ORPO  ·  LoRA", font=get_font(22), fill=(148, 163, 184))

# Divider
for x in range(60, 540):
    t = (x - 60) / 480
    r = int(99 + t * (168 - 99))
    g = int(102 + t * (85 - 102))
    b = int(241 + t * (247 - 241))
    draw.line([(x, 168), (x, 170)], fill=(r, g, b))

def badge(x, y, w, h, color_hex, label, value):
    r2 = int(color_hex[1:3], 16)
    g2 = int(color_hex[3:5], 16)
    b2 = int(color_hex[5:7], 16)
    draw.rounded_rectangle([x, y, x+w, y+h], radius=10, fill=(r2, g2, b2))
    lf = get_font(13)
    lb = draw.textlength(label, font=lf)
    draw.text((x + w//2 - lb//2, y + 8), label, font=lf, fill=(220, 240, 220))
    vf = get_font(24, bold=True)
    vb = draw.textlength(value, font=vf)
    draw.text((x + w//2 - vb//2, y + 26), value, font=vf, fill=(255, 255, 255))

badge(60,  185, 200, 58, "#16a34a", "Held-out Accuracy", "85.2%")
badge(276, 185, 200, 58, "#0ea5e9", "Compute",           "Colab T4 Free")
badge(492, 185, 200, 58, "#7c3aed", "Preference Pairs",  "323")

def pill(x, y, w, h, color_hex, text):
    r2 = int(color_hex[1:3], 16)
    g2 = int(color_hex[3:5], 16)
    b2 = int(color_hex[5:7], 16)
    draw.rounded_rectangle([x, y, x+w, y+h], radius=h//2, fill=(r2, g2, b2))
    pf = get_font(16, bold=True)
    pb = draw.textlength(text, font=pf)
    draw.text((x + w//2 - pb//2, y + 8), text, font=pf, fill=(255, 255, 255))

pill(780,  68, 148, 36, "#dc2626", "SUPPRESS")
pill(944,  68, 148, 36, "#d97706", "ESCALATE")
pill(780, 118, 120, 36, "#7c3aed", "BLOCK")
pill(916, 118, 148, 36, "#b45309", "PENALISE")
pill(780, 168, 110, 36, "#16a34a", "PASS")

draw.text((60, 308), "Base model: Qwen2.5-1.5B-Instruct  ·  ORPO  ·  Colab T4  ·  10 probes  ·  Cohen's κ = 1.000",
          font=get_font(14), fill=(100, 116, 139))
draw.text((60, 338), "bethelhem21/tenacious-judge-lora  ·  bethelhem21/tenacious-bench  ·  10 Academy TRP1  ·  2026",
          font=get_font(13), fill=(71, 85, 105))

img.save(OUT, "PNG")
print(f"Saved: {OUT}")
