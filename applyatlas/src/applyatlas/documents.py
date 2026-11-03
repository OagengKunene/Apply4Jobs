from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def resume_pdf(packet):
    stream = BytesIO()
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor("#143b33")
    resume = packet["resume"]
    story = [Paragraph(escape(resume["name"]), styles["Title"]),
             Paragraph(escape(" | ".join(x for x in [resume["email"], resume["phone"], resume["location"]] if x)),
                       styles["Normal"]), Spacer(1, .25 * inch),
             Paragraph(escape(resume["headline"]), styles["Heading2"]),
             Paragraph(escape(", ".join(resume["skills"])), styles["Normal"]), Spacer(1, .15 * inch),
             Paragraph("Selected experience and projects", styles["Heading2"])]
    for claim in resume["evidence"]:
        story.extend([Paragraph(escape(claim["text"]), styles["Normal"]), Spacer(1, .14 * inch)])
    SimpleDocTemplate(stream, title="Application resume", rightMargin=48, leftMargin=48).build(story)
    return stream.getvalue()
