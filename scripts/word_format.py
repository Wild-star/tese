# -*- coding: utf-8 -*-
"""学位论文/征稿格式规格（唯一来源）。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WordFormatSpec:
    """教学论文 Word 格式。"""

    page_width_cm: float = 21.0
    page_height_cm: float = 29.7
    margin_top_cm: float = 2.54
    margin_bottom_cm: float = 2.54
    margin_left_cm: float = 3.17
    margin_right_cm: float = 3.17
    # 兼容旧字段
    margin_cm: float = 2.54

    font_cn_song: str = "宋体"
    font_cn_hei: str = "黑体"
    font_en: str = "Times New Roman"

    title_pt: float = 16.0       # 题目：三号
    h1_pt: float = 16.0          # 一级：三号
    h2_pt: float = 14.0          # 二级：四号
    body_pt: float = 12.0        # 小四（正文／三级）
    caption_pt: float = 10.5     # 五号
    table_pt: float = 10.5       # 五号
    ref_pt: float = 10.5         # 参考文献：五号

    line_spacing: float = 1.5
    first_line_indent_pt: float = 24.0
    image_width_cm: float = 15.0

    omit_author: bool = True
    blocked_signatures: tuple = ("王安娜", "杭州市余杭区", "作者", "单位", "基金")
    order: tuple = ("toc", "title", "abstract", "keywords", "body", "references")


SPEC = WordFormatSpec()
