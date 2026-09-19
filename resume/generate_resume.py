#!/usr/bin/env python3
"""Generate Sharad Pratap Singh resume PDF tailored for CoinDCX Analytics Intern."""

from pathlib import Path

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT_DIR = Path(__file__).resolve().parent
ARTIFACTS = Path("/opt/cursor/artifacts")

INK = HexColor("#1a1a1a")
MUTED = HexColor("#444444")
LINE = HexColor("#222222")
ACCENT = HexColor("#0f172a")


def styles():
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle(
            "Name",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=19,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=2,
        ),
        "contact": ParagraphStyle(
            "Contact",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=11,
            textColor=ACCENT,
            spaceBefore=5,
            spaceAfter=1,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=10.4,
            textColor=INK,
            alignment=TA_JUSTIFY,
            spaceAfter=2,
        ),
        "role_left": ParagraphStyle(
            "RoleLeft",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.8,
            leading=10.5,
            textColor=INK,
        ),
        "role_right": ParagraphStyle(
            "RoleRight",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=MUTED,
            alignment=TA_RIGHT,
        ),
        "sub_left": ParagraphStyle(
            "SubLeft",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=10,
            textColor=MUTED,
        ),
        "sub_right": ParagraphStyle(
            "SubRight",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=MUTED,
            alignment=TA_RIGHT,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.1,
            leading=10.2,
            textColor=INK,
            leftIndent=9,
            firstLineIndent=-8,
            spaceAfter=0.8,
        ),
        "skill": ParagraphStyle(
            "Skill",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10.2,
            textColor=INK,
            leftIndent=9,
            firstLineIndent=-8,
            spaceAfter=0.6,
        ),
        "proj_title": ParagraphStyle(
            "ProjTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=INK,
            spaceBefore=2,
            spaceAfter=0.5,
        ),
        "proj_tools": ParagraphStyle(
            "ProjTools",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            leading=9,
            textColor=MUTED,
            spaceAfter=0.5,
        ),
    }


def section_rule():
    return HRFlowable(
        width="100%",
        thickness=0.8,
        color=LINE,
        spaceBefore=0,
        spaceAfter=4,
    )


def two_col(left, right, s, left_style="role_left", right_style="role_right"):
    data = [[Paragraph(left, s[left_style]), Paragraph(right, s[right_style])]]
    t = Table(data, colWidths=[5.1 * inch, 2.0 * inch])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return t


def bullet(text, s):
    return Paragraph(f"• {text}", s["bullet"])


def build(path: Path):
    s = styles()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.32 * inch,
        bottomMargin=0.32 * inch,
        title="Sharad Pratap Singh — Resume",
        author="Sharad Pratap Singh",
    )

    story = []
    story.append(Paragraph("Sharad Pratap Singh", s["name"]))
    story.append(
        Paragraph(
            'sharadxsinghh@gmail.com &nbsp;|&nbsp; '
            '<link href="https://github.com/sharaddsingh">GitHub</link> &nbsp;|&nbsp; '
            "LinkedIn &nbsp;|&nbsp; Tableau",
            s["contact"],
        )
    )

    # Profile
    story.append(Paragraph("PROFILE SUMMARY", s["section"]))
    story.append(section_rule())
    story.append(
        Paragraph(
            "Aspiring Business and Data Analyst pursuing a B.S. in Computer Science at BITS Pilani "
            "with hands-on experience in Python, SQL, Excel, and Tableau. Skilled at translating "
            "business requirements into analytical plans and delivering actionable insights via "
            "dashboards and stakeholder reporting. Analytics internship at OZi supporting growth, "
            "product, and operations with KPI tracking, anomaly monitoring, and cross-functional "
            "analytics. Interested in Web3, fintech, and data-driven decision-making.",
            s["body"],
        )
    )

    # Experience — OZi (written for CoinDCX JD alignment)
    story.append(Paragraph("EXPERIENCE", s["section"]))
    story.append(section_rule())
    story.append(two_col("Analytics Intern", "May 2026 – Aug 2026", s))
    story.append(
        two_col(
            "OZi (Quick Commerce for Parents) — Gurugram",
            "On-site",
            s,
            "sub_left",
            "sub_right",
        )
    )
    story.append(Spacer(1, 1))
    for b in [
        "Collaborated with product, growth, and operations stakeholders to gather, analyze, and "
        "document business requirements for KPI reporting, funnel tracking, and performance reviews.",
        "Assisted in data collection and analysis across orders, retention, and category performance "
        "using SQL and Excel; generated actionable reports that informed weekly business reviews.",
        "Supported Tableau and Excel dashboards for business performance tracking — conversion, "
        "repeat rates, delivery SLAs, and regional trends — used in stakeholder reviews.",
        "Conducted market research and competitive analysis on quick-commerce benchmarks to surface "
        "growth opportunities and inform strategy discussions.",
        "Supported cross-functional data requests from growth, category, and operations; helped set "
        "up data-quality checks and anomaly alerts for faster incident prioritization.",
        "Used Python (Pandas) for EDA and report automation; validated schema and data-model "
        "assumptions before publishing stakeholder deliverables.",
    ]:
        story.append(bullet(b, s))

    # Education
    story.append(Paragraph("EDUCATION", s["section"]))
    story.append(section_rule())
    story.append(two_col("BITS Pilani", "2025 – 2029", s))
    story.append(
        two_col(
            "Bachelor of Science (B.S.) in Computer Science",
            "CGPA: 8.8",
            s,
            "sub_left",
            "sub_right",
        )
    )

    # Skills
    story.append(Paragraph("TECHNICAL & BUSINESS SKILLS", s["section"]))
    story.append(section_rule())
    for line in [
        "<b>Programming &amp; Databases:</b> Python, SQL, MySQL",
        "<b>Data Analysis:</b> Pandas, NumPy, Exploratory Data Analysis (EDA), Statistical Analysis, "
        "Data Cleaning, Data Validation, Anomaly Detection",
        "<b>Business Analysis:</b> Business Requirements Analysis, KPI Reporting, Business Intelligence, "
        "Product Analytics, Market &amp; Competitive Research, Actionable Insights",
        "<b>Visualization &amp; Reporting:</b> Tableau, Matplotlib, Dashboard Development, Data Storytelling",
        "<b>Tools:</b> Microsoft Excel (Pivot Tables, XLOOKUP, VLOOKUP), PowerPoint, Git, GitHub, Jupyter Notebook",
        "<b>Professional Skills:</b> Cross-Functional Collaboration, Stakeholder Communication, "
        "Problem Solving, Teamwork, Leadership, Presentation",
    ]:
        story.append(Paragraph(f"• {line}", s["skill"]))

    # Projects
    story.append(Paragraph("PROJECTS", s["section"]))
    story.append(section_rule())

    projects = [
        (
            "Supply Chain Cost Analysis and Business Intelligence",
            "Python, SQL, Tableau, Excel",
            [
                "Analyzed 180,000+ supply chain records to identify shipping cost drivers, delivery delays, "
                "and regional trends; built a Tableau KPI dashboard for stakeholder reporting.",
                "Translated operational questions into an analytical plan and produced data-driven "
                "recommendations on inefficiencies.",
            ],
        ),
        (
            "Retail Sales Analysis",
            "Python, SQL, Tableau, Excel",
            [
                "Evaluated retail performance across regions, categories, and segments; built a Tableau "
                "dashboard with KPIs and filters to support stakeholder decision-making.",
            ],
        ),
        (
            "Telecom Customer Churn Analysis",
            "Python, SQL, Tableau",
            [
                "Identified churn drivers and segmentation patterns; designed a Tableau dashboard of "
                "churn KPIs to support retention initiatives.",
            ],
        ),
    ]
    for title, tools, bullets in projects:
        story.append(Paragraph(title, s["proj_title"]))
        story.append(Paragraph(tools, s["proj_tools"]))
        for b in bullets:
            story.append(bullet(b, s))

    # Achievements
    story.append(Paragraph("ACHIEVEMENTS & LEADERSHIP", s["section"]))
    story.append(section_rule())
    for b in [
        "<b>Certificate of Excellence – Best End Semester Project</b> — Recognized for delivering a "
        "high-quality team project at PW Institute of Innovation.",
        "<b>Runner-Up – Startup Resurrection: The Revival Challenge</b> — Collaborated in a team-based "
        "business challenge focused on analyzing problems, developing strategic solutions, and presenting recommendations.",
        "<b>Qualified AWS Hackathon</b> — Demonstrated collaborative problem-solving, adaptability, and "
        "execution in a competitive project environment at PW Institute of Innovation.",
    ]:
        story.append(bullet(b, s))

    doc.build(story)
    return path


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    primary = OUT_DIR / "Sharad_Pratap_Singh_Resume.pdf"
    build(primary)
    artifact = ARTIFACTS / "Sharad_Pratap_Singh_Resume_CoinDCX.pdf"
    build(artifact)
    print(f"Wrote {primary}")
    print(f"Wrote {artifact}")


if __name__ == "__main__":
    main()
