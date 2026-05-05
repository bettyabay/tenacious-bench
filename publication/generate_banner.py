"""Generate banner.png using reportlab — no native C dependencies needed."""
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader
import io, os

W, H = 1200, 400
OUT = os.path.join(os.path.dirname(__file__), "banner.pdf")
PNG = os.path.join(os.path.dirname(__file__), "banner.png")

c = canvas.Canvas(OUT, pagesize=(W, H))

# Background gradient approximation (dark navy)
c.setFillColor(HexColor("#0f172a"))
c.rect(0, 0, W, H, fill=1, stroke=0)

# Accent bar left
c.linearGradient(0, 0, 0, H,
    [HexColor("#6366f1"), HexColor("#a855f7")],
    [0, 1], extend=False)
# fallback solid accent
c.setFillColor(HexColor("#6366f1"))
c.rect(0, 0, 6, H, fill=1, stroke=0)

# Subtle grid
c.setStrokeColor(HexColor("#ffffff"))
c.setStrokeAlpha(0.05)
for y in [100, 200, 300]:
    c.line(0, y, W, y)
for x in [300, 600, 900]:
    c.line(x, 0, x, H)

# Title
c.setFillColor(HexColor("#f8fafc"))
c.setFont("Helvetica-Bold", 52)
c.drawString(60, H - 120, "Tenacious Judge")

# Subtitle
c.setFillColor(HexColor("#94a3b8"))
c.setFont("Helvetica", 22)
c.drawString(62, H - 165, "B2B Sales Outreach Pre-Send Judge  ·  ORPO  ·  LoRA")

# Divider
c.setFillColor(HexColor("#6366f1"))
c.rect(60, H - 195, 480, 3, fill=1, stroke=0)

# --- Badges ---
def badge(x, y, w, h, color, label, value):
    c.setFillColor(HexColor(color))
    c.roundRect(x, y, w, h, 10, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica", 13)
    c.drawCentredString(x + w/2, y + h - 20, label)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(x + w/2, y + 8, value)

badge(60,  H - 280, 200, 52, "#16a34a", "Held-out Accuracy", "85.2%")
badge(276, H - 280, 200, 52, "#0ea5e9", "Training Cost",     "$0.00")
badge(492, H - 280, 200, 52, "#7c3aed", "Preference Pairs",  "323")

# --- Decision pills ---
def pill(x, y, w, h, color, text):
    c.setFillColor(HexColor(color))
    c.roundRect(x, y, w, h, h//2, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(x + w/2, y + 10, text)

pill(780, H - 120, 145, 36, "#dc2626", "SUPPRESS")
pill(940, H - 120, 145, 36, "#d97706", "ESCALATE")
pill(780, H - 170, 120, 36, "#7c3aed", "BLOCK")
pill(916, H - 170, 145, 36, "#b45309", "PENALISE")
pill(780, H - 220, 110, 36, "#16a34a", "PASS")

# Bottom info
c.setFillColor(HexColor("#64748b"))
c.setFont("Helvetica", 14)
c.drawString(60, 68, "Base model: Qwen2.5-1.5B-Instruct  ·  ORPO  ·  Colab T4  ·  10 probes  ·  Cohen's κ = 1.000")
c.setFillColor(HexColor("#475569"))
c.setFont("Helvetica", 13)
c.drawString(60, 42, "bethelhem21/tenacious-judge-lora  ·  bethelhem21/tenacious-bench  ·  10 Academy TRP1  ·  2026")

c.save()
print(f"PDF saved: {OUT}")

# Convert PDF page to PNG via reportlab's renderPM if available
try:
    from reportlab.graphics import renderPM
    from reportlab.graphics.shapes import Drawing
    print("renderPM available but PDF->PNG conversion not straightforward via reportlab alone.")
except ImportError:
    pass

# Use pdf2image if available
try:
    from pdf2image import convert_from_path
    pages = convert_from_path(OUT, dpi=150, size=(1200, 400))
    pages[0].save(PNG)
    print(f"PNG saved: {PNG}")
except Exception as e:
    print(f"pdf2image not available ({e}) — upload SVG directly to HuggingFace instead.")
