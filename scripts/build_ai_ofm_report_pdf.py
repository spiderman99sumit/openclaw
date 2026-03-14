#!/usr/bin/env python3
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_LEFT
from reportlab.lib import colors
import html

workspace = Path('/kaggle/working/.openclaw/workspace')
md_path = workspace / 'reports' / 'ai_ofm_market_report_2026-03-14.md'
pdf_path = workspace / 'reports' / 'ai_ofm_market_report_2026-03-14.pdf'
text = md_path.read_text()

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodySmall', parent=styles['BodyText'], fontName='Helvetica', fontSize=10.2, leading=14, alignment=TA_LEFT, spaceAfter=6))
styles.add(ParagraphStyle(name='H1X', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=colors.HexColor('#111827'), spaceAfter=10))
styles.add(ParagraphStyle(name='H2X', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, leading=17, textColor=colors.HexColor('#111827'), spaceBefore=8, spaceAfter=6))

def p(txt):
    return Paragraph(html.escape(txt).replace('\n', '<br/>'), styles['BodySmall'])

story = []
for raw in text.splitlines():
    line = raw.rstrip()
    if not line:
        story.append(Spacer(1, 4))
        continue
    if line.startswith('# '):
        story.append(Paragraph(html.escape(line[2:]), styles['H1X']))
    elif line.startswith('## '):
        story.append(Paragraph(html.escape(line[3:]), styles['H2X']))
    elif line.startswith('### '):
        story.append(Paragraph('<b>%s</b>' % html.escape(line[4:]), styles['BodySmall']))
    elif line.startswith('- '):
        story.append(Paragraph('&bull; ' + html.escape(line[2:]), styles['BodySmall']))
    elif line[:2].isdigit() and line[1] == '.':
        story.append(p(line))
    else:
        story.append(p(line))

doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=16*mm, rightMargin=16*mm, topMargin=14*mm, bottomMargin=14*mm, title='AI OFM Business Report')
doc.build(story)
print(pdf_path)
