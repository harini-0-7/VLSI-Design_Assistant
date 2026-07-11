from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

NAVY = colors.HexColor("#0a1628")
CYAN = colors.HexColor("#00a8ff")
RED = colors.HexColor("#ff4d6d")
YELLOW = colors.HexColor("#ffc107")
GREEN = colors.HexColor("#00e676")
MUTED = colors.HexColor("#4a6b8a")
TEXT_DARK = colors.HexColor("#0a1628")


def build_pdf_report(record: dict, output_path: str) -> str:
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )

    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        "TitleVLSI", parent=styles["Title"], textColor=NAVY,
        fontSize=22, spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"], textColor=CYAN,
        fontSize=11, spaceAfter=14,
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"], textColor=NAVY,
        fontSize=14, spaceBefore=16, spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontSize=10, textColor=TEXT_DARK,
        leading=14,
    )
    meta_style = ParagraphStyle(
        "Meta", parent=styles["Normal"], fontSize=9, textColor=MUTED,
    )

    # ── Header ──
    story.append(Paragraph("VLSI Design Assistant", title_style))
    story.append(Paragraph("AI-Powered Verilog HDL Analysis Report", subtitle_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#dbe7f5"), thickness=1))
    story.append(Spacer(1, 10))

    meta_table = Table(
        [
            ["File", record["filename"]],
            ["Size", f"{record['size_kb']} KB"],
            ["Analyzed", record["uploaded_at"].replace("T", " ").replace("Z", " UTC")],
            ["Report ID", record["id"]],
        ],
        colWidths=[35 * mm, 120 * mm],
    )
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), TEXT_DARK),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 16))

    # ── Overall score ──
    analysis = record["analysis"]
    score = analysis["score"]
    score_color = GREEN if score >= 80 else (YELLOW if score >= 50 else RED)

    story.append(Paragraph("Overall Score", h2_style))
    score_table = Table(
        [[
            Paragraph(f'<font color="{score_color.hexval()}" size="28"><b>{score}</b></font>'
                      f'<font color="{MUTED.hexval()}" size="11">/100</font>', body_style),
            Paragraph(
                f'<font color="{RED.hexval()}"><b>{analysis["counts"]["errors"]}</b></font> Errors &nbsp;&nbsp;'
                f'<font color="{YELLOW.hexval()}"><b>{analysis["counts"]["warnings"]}</b></font> Warnings &nbsp;&nbsp;'
                f'<font color="{CYAN.hexval()}"><b>{analysis["counts"]["infos"]}</b></font> Infos',
                body_style,
            ),
        ]],
        colWidths=[60 * mm, 95 * mm],
    )
    score_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbe7f5")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f8fc")),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(score_table)

    # ── Issues table ──
    story.append(Paragraph("Issues Found", h2_style))
    if analysis["issues"]:
        rows = [["Severity", "Line", "Message"]]
        for issue in analysis["issues"][:40]:  # cap for sane page count
            rows.append([issue["severity"].capitalize(), str(issue["line"]), issue["message"]])

        issues_table = Table(rows, colWidths=[22 * mm, 16 * mm, 117 * mm], repeatRows=1)
        style_cmds = [
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dbe7f5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f8fc")]),
        ]
        for i, issue in enumerate(analysis["issues"][:40], start=1):
            color = RED if issue["severity"] == "error" else (YELLOW if issue["severity"] == "warning" else CYAN)
            style_cmds.append(("TEXTCOLOR", (0, i), (0, i), color))
            style_cmds.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))
        issues_table.setStyle(TableStyle(style_cmds))
        story.append(issues_table)
    else:
        story.append(Paragraph("No issues detected.", body_style))

    # ── Optimizations ──
    story.append(Paragraph("AI Optimization Suggestions", h2_style))
    impact_color = {"high": GREEN, "medium": YELLOW, "low": CYAN}
    for opt in record["optimizations"]:
        c = impact_color.get(opt["impact"], MUTED)
        story.append(Paragraph(
            f'<b>{opt["title"]}</b> &nbsp; '
            f'<font color="{c.hexval()}" size="8"><b>{opt["impact"].upper()} IMPACT</b></font>',
            body_style,
        ))
        story.append(Paragraph(opt["description"], meta_style))
        story.append(Spacer(1, 8))

    if not record["optimizations"]:
        story.append(Paragraph("No optimization suggestions for this file.", body_style))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#dbe7f5"), thickness=1))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Generated by VLSI Design Assistant — AI-Powered Verilog HDL Analysis",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=MUTED, alignment=TA_CENTER),
    ))

    doc.build(story)
    return output_path