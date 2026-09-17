#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同主题结构图与课堂照片拼成合集板，避免文中一张一张散放。"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.image import imread
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures"
FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
NAVY = "#1F4E79"


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def _cover(path: Path, w: int, h: int) -> Image.Image:
    im = Image.open(path).convert("RGB")
    scale = max(w / im.width, h / im.height)
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return im.crop((left, top, left + w, top + h))


def _fit(path: Path, w: int, h: int, mode: str = "cover") -> Image.Image:
    im = Image.open(path).convert("RGB")
    if mode == "contain":
        scale = min(w / im.width, h / im.height)
        nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (w, h), "white")
        canvas.paste(im, ((w - nw) // 2, (h - nh) // 2))
        return canvas
    scale = max(w / im.width, h / im.height)
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return im.crop((left, top, left + w, top + h))


def photo_grid(items: list[tuple[str, str]], out_name: str, title: str, cell=(920, 620), fit="cover") -> None:
    cols, rows = 2, 2
    pad, cap_h, title_h, gap = 18, 54, 70, 14
    W = cols * cell[0] + (cols + 1) * gap
    H = title_h + rows * (cell[1] + cap_h) + (rows + 1) * gap
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((W // 2, 18), title, fill=NAVY, font=_font(28), anchor="mt")
    for i, (fname, caption) in enumerate(items):
        r, c = divmod(i, cols)
        x = gap + c * (cell[0] + gap)
        y = title_h + gap + r * (cell[1] + cap_h + gap)
        img = _fit(OUT / fname, cell[0], cell[1], mode=fit)
        canvas.paste(img, (x, y))
        draw.rectangle([x, y, x + cell[0] - 1, y + cell[1] - 1], outline="#1F4E79", width=2)
        draw.text((x + cell[0] // 2, y + cell[1] + 10), caption, fill="#2F2F2F",
                  font=_font(20), anchor="mt")
    dest = OUT / out_name
    canvas.save(dest, quality=92)
    print("wrote", dest)


def mpl_grid(paths: list[str], labels: list[str], out_name: str, title: str, ncols=2, figsize=(11.2, 8.4)):
    plt.rcParams.update({"font.family": "WenQuanYi Micro Hei", "axes.unicode_minus": False})
    n = len(paths)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize)
    axes = [axes] if n == 1 else axes.flatten()
    for i, ax in enumerate(axes):
        ax.axis("off")
        if i >= n:
            continue
        img = imread(OUT / paths[i])
        ax.imshow(img)
        ax.set_title(labels[i], fontsize=11, color=NAVY, pad=6)
    fig.suptitle(title, fontsize=13, color=NAVY, y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    dest = OUT / out_name
    fig.savefig(dest, bbox_inches="tight", pad_inches=0.12, dpi=180, facecolor="white")
    plt.close(fig)
    print("wrote", dest)


def compose_all() -> None:
    photo_grid(
        [
            ("real/cotton.jpg", "（a）《棉花姑娘》：谜语投屏、出示字卡，座位仍为行列式"),
            ("real/elephant_hands.jpg", "（b）《大象的耳朵》：举手应答，发起权仍在教师"),
            ("real/jing_req.jpg", "（c）《即景》：习作要求上屏，学生一律朝向讲台"),
            ("real/plant_task.jpg", "（d）《我的植物朋友》：任务写清，课堂仍以听讲为主"),
        ],
        "plate_scene.jpg",
        "课堂现场合集：座位朝向与发言方向",
    )
    photo_grid(
        [
            ("real/jing_board_live.jpg", "（a）《即景》现场板书：一定顺序，写出动态变化"),
            ("real/jing_card.jpg", "（b）课前观察记录单：日落过程用图和词记下变化"),
            ("real/plant_card.jpg", "（c）植物记录卡：看、闻、摸分开写，感受写进卡里"),
            ("real/guren_board_live.jpg", "（d）《古人谈读书》现场板书：态度与方法，落在熟读深思"),
        ],
        "plate_scaffold.jpg",
        "真实教学材料合集：板书、观察记录单与记录卡",
        cell=(920, 560),
        fit="contain",
    )
    photo_grid(
        [
            ("real/jing_card.jpg", "（a）观察记录单先完成：眼前的、当下的景"),
            ("real/jing_req.jpg", "（b）教材要求上屏：按顺序写，写出动态变化"),
            ("real/jing_essay.jpg", "（c）学生片段上屏，对照板书评改变化是否写出"),
            ("real/jing_scene.jpg", "（d）现场板书与观察材料进入公共视野"),
        ],
        "plate_break.jpg",
        "《即景》破程合集：观察所得进入课堂，终稿仍由学生完成",
    )
    photo_grid(
        [
            ("real/plant_card.jpg", "（a）记录卡已有观察，课上要连成连贯表达"),
            ("real/plant_board.jpg", "（b）板书：写清楚、多角度、有感受"),
            ("real/plant_share.jpg", "（c）学生举起记录卡/习作，同伴开始被看见"),
            ("real/elephant_play.jpg", "（d）《大象的耳朵》：角色扮演，学生之间开始问答"),
        ],
        "plate_write.jpg",
        "化卡为文与低段横向通道合集",
    )
    photo_grid(
        [
            ("real/guren_peer.jpg", "（a）学习活动一：同桌互读互评，读准字音、读好停顿"),
            ("real/guren_mic.jpg", "（b）学生持麦解释语录，教师侧立组织"),
            ("real/guren_text.jpg", "（c）语录与注释同屏，理解仍须学生自己说"),
            ("real/here_beauty.jpg", "（d）《这儿真美》：例文上屏，学生按支架动笔"),
        ],
        "plate_voice.jpg",
        "复权合集：把问和写交还给学生",
    )
    mpl_grid(
        ["fig04.jpg", "fig07.jpg", "fig05.jpg", "fig25.jpg"],
        ["（a）三类失衡层层加码", "（b）替答·替评·替演·替证", "（c）放射状问答网络", "（d）秧田座位如何收束发言"],
        "plate02.jpg",
        "图集：形式—关系—技术三类失衡如何叠在一起",
        ncols=2, figsize=(11.4, 9.2),
    )
    mpl_grid(
        ["fig16.jpg", "fig17.jpg", "fig18.jpg", "fig10.jpg"],
        ["（a）《火烧云》：先观察、先写后比",
         "（b）《守株待兔》：角色陪练与文本证伪",
         "（c）《手指》：归集上屏、组际追问",
         "（d）课前预学—课中互学—课后辩学闭环"],
        "plate_flow.jpg",
        "课例流程合集：破程、守界与全员可见的操作链",
        ncols=2, figsize=(11.2, 9.0),
    )
    mpl_grid(
        ["fig08.jpg", "fig03.jpg", "fig12.jpg", "fig13.jpg", "fig26.jpg"],
        ["（a）破程→复权→守界", "（b）教师引领 / 学生建构 / AI支架",
         "（c）宜做与慎做", "（d）介入强度与主体性", "（e）绿灯·黄灯·红灯"],
        "plate05.jpg",
        "图集：三元权责与技术边界",
        ncols=2, figsize=(11.4, 12.6),
    )
    mpl_grid(
        ["fig09.jpg", "fig16.jpg"],
        ["（a）四层问题链：提取—比较—评价—创造",
         "（b）《火烧云》：先观察、先写后比"],
        "plate06.jpg",
        "图集：破程课例——把封闭问答改成可选择的通道",
        ncols=1, figsize=(8.8, 8.8),
    )
    mpl_grid(
        ["fig10.jpg", "fig24.jpg", "fig28.jpg"],
        ["（a）课前预学—课中互学—课后辩学",
         "（b）化卡为文：记录卡连成有感受的表达",
         "（c）五类课型的宜做与禁做"],
        "plate07.jpg",
        "图集：分层任务、习作通道与课型边界",
        ncols=1, figsize=(8.8, 12.8),
    )
    mpl_grid(
        ["fig11.jpg", "fig18.jpg", "fig06.jpg"],
        ["（a）提问支架：不索要终答，要指向课文",
         "（b）《手指》：归集上屏，组际追问",
         "（c）多回路互动网络（结构性示意）"],
        "plate08.jpg",
        "图集：复权——让问、让看见、让论证",
        ncols=1, figsize=(8.8, 12.6),
    )
    mpl_grid(
        ["fig17.jpg", "fig27.jpg"],
        ["（a）《守株待兔》：角色陪练 + 文本证伪", "（b）生成句上屏之后必须被追问"],
        "plate09.jpg",
        "图集：守界——终答不给机器，判断回到课文",
        ncols=1, figsize=(8.8, 8.6),
    )
    mpl_grid(
        ["fig19.jpg", "fig14.jpg", "fig15.jpg"],
        ["（a）公开报道中的朗读反馈（非本文实验数据）",
         "（b）六维观察工具（示意，不填虚构分数）",
         "（c）T / S / AI 行为编码，供课后摘记"],
        "plate10.jpg",
        "图集：成效侧面与循证观察工具",
        ncols=1, figsize=(8.4, 14.2),
    )


if __name__ == "__main__":
    compose_all()
