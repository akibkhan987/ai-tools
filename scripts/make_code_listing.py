"""Create a PDF code listing of the back-end source for submission.

    pip install reportlab
    python scripts/make_code_listing.py      # writes TrailBlazer_code_listing.pdf
"""
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ["app.py", "requirements.txt", "trailblazer/*.py", "trailblazer/blueprints/*.py",
           "seed/*.py", "tests/*.py", "postman/build_collection.py", "scripts/*.py", "scripts/*.sh"]


def collect():
    files = []
    for pattern in SOURCES:
        files += sorted(p for p in ROOT.glob(pattern) if p.stat().st_size > 0)
    return files


def numbered(text):
    lines = text.splitlines()
    width = len(str(len(lines)))
    return "\n".join(f"{i:>{width}}  {line}" for i, line in enumerate(lines, 1))


def footer(canvas, doc):
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"TrailBlazer API – code listing – page {doc.page}")


def main():
    styles = getSampleStyleSheet()
    code = ParagraphStyle("code", fontName="Courier", fontSize=7, leading=8.5)
    files = collect()
    story = [Paragraph("TrailBlazer API – Complete Code Listing", styles["Title"]),
             Paragraph("COM661 Full Stack Strategies and Development – Coursework 1", styles["Normal"]),
             Spacer(1, 6 * mm), Paragraph("Files", styles["Heading2"])]
    story += [Paragraph(escape(str(f.relative_to(ROOT))), styles["Normal"]) for f in files]
    for f in files:
        story += [PageBreak(), Paragraph(escape(str(f.relative_to(ROOT))), styles["Heading2"]),
                  Preformatted(numbered(f.read_text(encoding="utf-8")), code, maxLineLength=130)]
    out = ROOT / "TrailBlazer_code_listing.pdf"
    SimpleDocTemplate(str(out), pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
                      topMargin=12 * mm, bottomMargin=15 * mm,
                      title="TrailBlazer API code listing").build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"Wrote {out} ({len(files)} files)")


if __name__ == "__main__":
    main()
