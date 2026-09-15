# -*- coding: utf-8 -*-
"""征稿格式规格（唯一来源）。改这里即可统一所有生成结果。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WordFormatSpec:
    """教学论文 Word 征稿格式。"""

    # 页面
    page_width_cm: float = 21.0
    page_height_cm: float = 29.7
    margin_cm: float = 2.54

    # 字体：中文用 eastAsia，西文用 ascii
    font_cn_song: str = "宋体"
    font_cn_hei: str = "黑体"
    font_en: str = "Times New Roman"

    # 字号：三号=16磅，小四=12磅
    title_pt: float = 16.0
    body_pt: float = 12.0

    # 行距
    line_spacing: float = 1.5

    # 正文首行缩进（小四两字符 = 24磅）
    first_line_indent_pt: float = 24.0

    # 插图宽度（A4 左右边距 2.54cm 后的可用宽度）
    image_width_cm: float = 15.6

    # 文中一律不署单位和姓名
    omit_author: bool = True
    blocked_signatures: tuple = ("王安娜", "杭州市余杭区", "作者", "单位")

    # 正文顺序：题目 → 摘要 → 关键词 → 正文 → 参考文献
    order: tuple = ("title", "abstract", "keywords", "body", "references")


SPEC = WordFormatSpec()
