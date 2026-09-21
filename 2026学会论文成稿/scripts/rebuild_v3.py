#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild 学会教育论文 v3 from 正文_v3.md + 图源/表图源.

Keeps cover + TOC content control from v2; replaces body.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
SRC_DOCX = ROOT / "王安娜-学会教育论文_v2.docx"
MD = ROOT / "正文_v3.md"
OUT_DOCX = ROOT / "王安娜-学会教育论文_v3.docx"
OUT_PREVIEW_NOTE = ROOT / "王安娜-学会教育论文_v3-预览说明.txt"
COVER_IMG = ROOT / "封面" / "封面_简洁版.png"

FIG = {
    1: ROOT / "图源" / "fig1_课堂现场_排版用.png",
    2: ROOT / "图源" / "fig3_三类失衡合集.png",
    3: ROOT / "图源" / "fig3_交互层次与三元校准综合模型.png",
    4: ROOT / "图源" / "fig5_三元校准与技术边界.png",
    5: ROOT / "图源" / "fig7_人机分工.png",
    6: ROOT / "图源" / "fig8_课例流程合集.png",
}
# Prefer extracted classroom plate if present and smaller/cleaner
TAB = {
    1: ROOT / "表图源" / "表1.png",
    2: ROOT / "表图源" / "表2.png",
    3: ROOT / "表图源" / "表3.png",
    4: ROOT / "表图源" / "表5.png",  # 课型适配矩阵；删旧表4/表6后重编号
}

# Display widths per AGENTS.md
FIG_WIDTH_CM = {
    1: 14.0,  # wide classroom
    2: 12.0,  # near square
    3: 14.0,  # wide merged
    4: 12.0,
    5: 12.0,
    6: 14.0,
}
TAB_WIDTH_CM = 14.66


def set_run_font(run, *, east: str, ascii_font: str = "Times New Roman", size_pt: float, bold: bool = False):
    run.font.name = ascii_font
    run.font.size = Pt(size_pt)
    run.bold = bold
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:ascii"), ascii_font)
    rFonts.set(qn("w:hAnsi"), ascii_font)
    rFonts.set(qn("w:eastAsia"), east)
    rFonts.set(qn("w:cs"), ascii_font)


def set_paragraph_format(p, *, first_indent_chars: float | None = 2.0, align=None, space_before=0, space_after=0, keep_next=False):
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    if align is not None:
        p.alignment = align
    if first_indent_chars is None:
        pf.first_line_indent = None
    else:
        # 小四 12pt → 1 字符 ≈ 12pt；首行缩进 2 字符
        pf.first_line_indent = Pt(12 * first_indent_chars)
    if keep_next:
        pf.keep_with_next = True


def add_page_break(paragraph):
    run = paragraph.add_run()
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    run._element.append(br)


def clear_after_toc(doc: Document):
    body = doc.element.body
    children = list(body)
    # Find TOC sdt index
    toc_idx = None
    for i, child in enumerate(children):
        xml = etree.tostring(child, encoding="unicode")
        if child.tag.endswith("sdt") and "Table of Contents" in xml:
            toc_idx = i
            break
    if toc_idx is None:
        raise RuntimeError("TOC sdt not found")
    # remove old text cover (everything before TOC)
    for child in children[:toc_idx]:
        body.remove(child)
    # re-find toc after removals
    children = list(body)
    toc_idx = 0
    for i, child in enumerate(children):
        xml = etree.tostring(child, encoding="unicode")
        if child.tag.endswith("sdt") and "Table of Contents" in xml:
            toc_idx = i
            break
    # delete from toc_idx+1 to before sectPr
    for child in children[toc_idx + 1 :]:
        if child.tag.endswith("sectPr"):
            break
        body.remove(child)
    return toc_idx


def insert_cover_before_toc(doc: Document):
    """Insert full-page concise cover image before TOC, with page break after."""
    if not COVER_IMG.exists():
        raise FileNotFoundError(COVER_IMG)
    body = doc.element.body
    toc = None
    for child in list(body):
        xml = etree.tostring(child, encoding="unicode")
        if child.tag.endswith("sdt") and "Table of Contents" in xml:
            toc = child
            break
    if toc is None:
        raise RuntimeError("TOC sdt not found")

    # Build cover paragraph + page break paragraph as XML elements via temporary paras
    p_cover = doc.add_paragraph(style="Normal")
    set_paragraph_format(p_cover, first_indent_chars=None, align=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=0)
    run = p_cover.add_run()
    # content width ≈ 14.66 cm; cover designed as A4 so scales to one page
    run.add_picture(str(COVER_IMG), width=Cm(14.66))

    p_break = doc.add_paragraph(style="Normal")
    set_paragraph_format(p_break, first_indent_chars=None, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_page_break(p_break)

    # Move the two newly appended paras to before TOC
    body.remove(p_cover._element)
    body.remove(p_break._element)
    toc.addprevious(p_cover._element)
    toc.addprevious(p_break._element)


def replace_toc_cached_text(doc: Document, entries: list[tuple[int, str]]):
    """Replace visible TOC entries (level, title) while keeping TOC field."""
    body = doc.element.body
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    sdt = None
    for child in list(body):
        xml = etree.tostring(child, encoding="unicode")
        if child.tag.endswith("sdt") and "Table of Contents" in xml:
            sdt = child
            break
    if sdt is None:
        return
    content = sdt.find(f"{W}sdtContent")
    if content is None:
        return
    # Keep title paragraph + field begin/instr/separate structure of first TOC1,
    # then rebuild simple TOC lines for readability before F9 refresh.
    # Simpler approach: clear all paragraphs after the "目录" title and write static TOC.
    paras = [c for c in list(content) if c.tag.endswith("p")]
    # Find title
    title_p = paras[0] if paras else None
    # Remove all existing content children
    for c in list(content):
        content.remove(c)

    def make_p(text: str, style: str, indent_cm: float = 0.0):
        p = OxmlElement("w:p")
        pPr = OxmlElement("w:pPr")
        pStyle = OxmlElement("w:pStyle")
        pStyle.set(qn("w:val"), style)
        pPr.append(pStyle)
        if indent_cm:
            ind = OxmlElement("w:ind")
            # twips: 1cm ≈ 567
            ind.set(qn("w:left"), str(int(indent_cm * 567)))
            pPr.append(ind)
        spacing = OxmlElement("w:spacing")
        spacing.set(qn("w:line"), "360")
        spacing.set(qn("w:lineRule"), "auto")
        pPr.append(spacing)
        p.append(pPr)
        r = OxmlElement("w:r")
        rPr = OxmlElement("w:rPr")
        rFonts = OxmlElement("w:rFonts")
        rFonts.set(qn("w:ascii"), "Times New Roman")
        rFonts.set(qn("w:hAnsi"), "Times New Roman")
        rFonts.set(qn("w:eastAsia"), "宋体")
        rPr.append(rFonts)
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), "24")
        rPr.append(sz)
        r.append(rPr)
        t = OxmlElement("w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = text
        r.append(t)
        p.append(r)
        return p

    content.append(make_p("目录", "TOC"))
    for level, title in entries:
        style = {1: "TOC1", 2: "TOC2", 3: "TOC3"}.get(level, "TOC1")
        indent = {1: 0.0, 2: 0.42, 3: 0.84}.get(level, 0.0)
        content.append(make_p(title, style, indent))
    # note
    content.append(make_p("（打开文档后请按 F9 更新目录页码）", "TOC"))


def add_title(doc, text: str):
    p = doc.add_paragraph(style="Title")
    set_paragraph_format(p, first_indent_chars=None, align=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=0)
    run = p.add_run(text)
    set_run_font(run, east="黑体", size_pt=16, bold=True)
    return p


def add_heading(doc, text: str, level: int):
    style = f"Heading {level}"
    p = doc.add_paragraph(style=style)
    set_paragraph_format(p, first_indent_chars=None, align=WD_ALIGN_PARAGRAPH.LEFT if level > 1 else WD_ALIGN_PARAGRAPH.LEFT, space_before=6, space_after=6)
    # AGENTS: all heading levels 三号黑体
    run = p.add_run(text)
    set_run_font(run, east="黑体", size_pt=16, bold=True)
    # ensure outline level via style; also force eastAsia on style run
    return p


def add_body(doc, text: str):
    p = doc.add_paragraph(style="Normal")
    set_paragraph_format(p, first_indent_chars=2.0, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    run = p.add_run(text)
    set_run_font(run, east="宋体", size_pt=12, bold=False)
    return p


def add_caption(doc, text: str, *, keep_with_prev_image: bool = False):
    p = doc.add_paragraph(style="Normal")
    set_paragraph_format(p, first_indent_chars=None, align=WD_ALIGN_PARAGRAPH.CENTER, space_before=3, space_after=6)
    run = p.add_run(text)
    set_run_font(run, east="宋体", size_pt=12, bold=False)
    return p


def add_image(doc, path: Path, width_cm: float, *, keep_next: bool = True):
    p = doc.add_paragraph(style="Normal")
    set_paragraph_format(p, first_indent_chars=None, align=WD_ALIGN_PARAGRAPH.CENTER, space_before=6, space_after=0, keep_next=keep_next)
    run = p.add_run()
    run.add_picture(str(path), width=Cm(width_cm))
    return p


def ensure_header(doc: Document):
    section = doc.sections[0]
    header = section.header
    header.is_linked_to_previous = False
    # Clear existing paragraphs
    for p in list(header.paragraphs):
        p._element.getparent().remove(p._element)
    p = header.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("余杭区2026年教育学会论文语文学科")
    set_run_font(run, east="宋体", size_pt=10.5, bold=False)


def parse_md(md_text: str):
    lines = md_text.strip().splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("【摘要】"):
            blocks.append(("abstract", line[len("【摘要】"):].strip()))
        elif line.startswith("【关键词】"):
            blocks.append(("keywords", line[len("【关键词】"):].strip()))
        elif line.startswith("# "):
            blocks.append(("h1", line[2:].strip()))
        elif line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
        elif line.startswith("### "):
            blocks.append(("h3", line[4:].strip()))
        elif line.startswith("（图"):
            m = re.match(r"（图\s*(\d+)\s*(.*)）", line.strip())
            if m:
                blocks.append(("fig", int(m.group(1)), m.group(2).strip()))
        elif line.startswith("（表"):
            m = re.match(r"（表\s*(\d+)\s*(.*)）", line.strip())
            if m:
                blocks.append(("tab", int(m.group(1)), m.group(2).strip()))
        else:
            blocks.append(("p", line.strip()))
        i += 1
    return blocks


def build():
    md = MD.read_text(encoding="utf-8")
    blocks = parse_md(md)

    doc = Document(str(SRC_DOCX))
    clear_after_toc(doc)
    insert_cover_before_toc(doc)
    ensure_header(doc)
    # Different first page: hide header on cover
    section = doc.sections[0]
    section.different_first_page_header_footer = True
    # ensure first-page header empty
    fp = section.first_page_header
    for p in list(fp.paragraphs):
        p._element.getparent().remove(p._element)
    fp.add_paragraph()

    toc_entries: list[tuple[int, str]] = []

    # Titles after TOC
    add_title(doc, "失衡·校准·均衡")
    add_title(doc, "——AI赋能下小学语文三元协同师生互动优化策略")

    for b in blocks:
        kind = b[0]
        if kind == "abstract":
            add_body(doc, "【摘要】" + b[1])
        elif kind == "keywords":
            add_body(doc, "【关键词】" + b[1])
        elif kind == "h1":
            add_heading(doc, b[1], 1)
            if not b[1].startswith("参考文献"):
                toc_entries.append((1, b[1]))
        elif kind == "h2":
            add_heading(doc, b[1], 2)
            toc_entries.append((2, b[1]))
        elif kind == "h3":
            add_heading(doc, b[1], 3)
            toc_entries.append((3, b[1]))
        elif kind == "p":
            add_body(doc, b[1])
        elif kind == "fig":
            num, caption = b[1], b[2]
            path = FIG[num]
            if not path.exists():
                raise FileNotFoundError(path)
            add_image(doc, path, FIG_WIDTH_CM[num], keep_next=True)
            add_caption(doc, f"图 {num} {caption}")
        elif kind == "tab":
            num, caption = b[1], b[2]
            path = TAB[num]
            if not path.exists():
                raise FileNotFoundError(path)
            # 表题在上
            p = add_caption(doc, f"表{num} {caption}")
            p.paragraph_format.keep_with_next = True
            add_image(doc, path, TAB_WIDTH_CM, keep_next=False)

    replace_toc_cached_text(doc, toc_entries)

    # Page margins already set in template; enforce AGENTS values
    for sec in doc.sections:
        sec.page_width = Cm(21.0)
        sec.page_height = Cm(29.7)
        sec.top_margin = Cm(2.54)
        sec.bottom_margin = Cm(2.54)
        sec.left_margin = Cm(3.17)
        sec.right_margin = Cm(3.17)

    doc.save(str(OUT_DOCX))
    OUT_PREVIEW_NOTE.write_text(
        "本环境未安装 LibreOffice/poppler，未自动生成 PDF 预览。\n"
        f"请本地下载后打开：{OUT_DOCX.name}\n"
        "打开后按 F9 更新目录页码。\n",
        encoding="utf-8",
    )
    print("wrote", OUT_DOCX)


if __name__ == "__main__":
    build()
