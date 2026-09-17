#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""稠密化实拍图板：从 materials/img 筛选课堂现场，拼成 3×3 / 3×2 合集。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MAT = ROOT / "materials" / "img"
OUT = ROOT / "figures"
DENSE = OUT / "dense"
FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
NAVY = "#1F4E79"


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


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


# 小语名师联盟封面/二维码/装饰，以及推文页眉碎片：无课堂互动信息
REJECT_FILES = {
    "即景/01.png", "即景/03.png", "即景/07.png",
    "古人谈读书/01.png", "古人谈读书/03.png", "古人谈读书/09.png",
    "我的植物朋友/01.png", "我的植物朋友/07.png", "我的植物朋友/08.png",
    "第一学段阅读研讨/01.png", "第一学段阅读研讨/02.png", "第一学段阅读研讨/03.png",
    "第一学段阅读研讨/04.png", "第一学段阅读研讨/05.png", "第一学段阅读研讨/06.png",
    "第一学段阅读研讨/07.png",  # 听课席，非课堂互动
    "赋能分层共生集备/01.png", "赋能分层共生集备/02.png", "赋能分层共生集备/03.png",
    "赋能分层共生集备/04.png", "赋能分层共生集备/05.png", "赋能分层共生集备/06.png",
    "赋能分层共生集备/07.png", "赋能分层共生集备/08.png",
    "五校语文集体备课/01.png", "五校语文集体备课/02.png", "五校语文集体备课/03.png",
    "五校语文集体备课/04.png", "五校语文集体备课/05.png", "五校语文集体备课/06.png",
    "五校语文集体备课/07.png", "五校语文集体备课/08.png", "五校语文集体备课/09.png",
    "五校语文集体备课/10.png",
    "地方课程三秀同台/01.png", "地方课程三秀同台/20.png",
}


def is_rejected(p: Path) -> bool:
    try:
        rel = str(p.resolve().relative_to(MAT.resolve())).replace("\\", "/")
    except Exception:
        rel = f"{p.parent.name}/{p.name}"
    if rel in REJECT_FILES:
        return True
    try:
        im = Image.open(p).convert("RGB")
    except Exception:
        return True
    w, h = im.size
    ar = w / max(h, 1)
    if ar > 2.2 or ar < 0.4:
        return True
    if w * h < 150000:
        return True
    # 近单色装饰块
    sample = im.resize((32, 32))
    colors = len({px for px in sample.getdata()})
    if colors < 18:
        return True
    return False


def score_path(p: Path) -> float:
    if is_rejected(p):
        return -1.0
    im = Image.open(p)
    w, h = im.size
    area = w * h
    ar = w / max(h, 1)
    score = float(area)
    if 1.1 <= ar <= 1.6:
        score *= 1.45
    return score


def pick(album: str, n: int = 6, prefer: list[str] | None = None) -> list[Path]:
    d = MAT / album
    files = [p for p in d.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"} and not is_rejected(p)]
    if prefer:
        ordered = []
        for name in prefer:
            p = d / name
            if p.exists() and not is_rejected(p):
                ordered.append(p)
        rest = sorted([p for p in files if p not in ordered], key=score_path, reverse=True)
        return (ordered + rest)[:n]
    return sorted(files, key=score_path, reverse=True)[:n]


def dense_grid(
    items: list[tuple[Path, str]],
    out_name: str,
    title: str,
    ncols: int = 3,
    cell: tuple[int, int] = (640, 430),
    fit: str = "cover",
) -> Path:
    DENSE.mkdir(parents=True, exist_ok=True)
    n = len(items)
    nrows = (n + ncols - 1) // ncols
    pad, cap_h, title_h, gap = 16, 56, 72, 12
    if ncols == 2 and n == 4:
        cell = (860, 560)
        cap_h, title_h, gap = 64, 78, 16
    W = ncols * cell[0] + (ncols + 1) * gap
    H = title_h + nrows * (cell[1] + cap_h) + (nrows + 1) * gap
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((W // 2, 20), title, fill=NAVY, font=_font(30 if ncols == 2 and n == 4 else 26), anchor="mt")
    for i, (path, caption) in enumerate(items):
        r, c = divmod(i, ncols)
        x = gap + c * (cell[0] + gap)
        y = title_h + gap + r * (cell[1] + cap_h + gap)
        img = _fit(path, cell[0], cell[1], mode=fit)
        canvas.paste(img, (x, y))
        draw.rectangle([x, y, x + cell[0] - 1, y + cell[1] - 1], outline=NAVY,
                       width=3 if ncols == 2 and n == 4 else 2)
        # wrap caption roughly
        draw.text((x + cell[0] // 2, y + cell[1] + 12), caption, fill="#2F2F2F",
                  font=_font(22 if ncols == 2 and n == 4 else 16), anchor="mt")
    dest = OUT / out_name
    canvas.save(dest, quality=92)
    # also keep a copy under dense/
    shutil.copy(dest, DENSE / out_name)
    print("wrote", dest, f"({n} photos)")
    return dest


def resolve_src(album: str, fname: str) -> Path | None:
    if album == "real":
        p = ROOT / "figures" / "real" / fname
    else:
        p = MAT / album / fname
    if p.exists() and (album == "real" or not is_rejected(p)):
        return p
    return None


def stage_copies() -> dict:
    """仅收录课堂实拍与真实材料，排除小语名师联盟封面/二维码/装饰图。"""
    DENSE.mkdir(parents=True, exist_ok=True)
    mapping = {
        "scene": [
            ("第一学段阅读研讨", "08.png", "cotton_screen"),
            ("第一学段阅读研讨", "09.jpeg", "cotton_class"),
            ("第一学段阅读研讨", "10.png", "elephant_hands"),
            ("第一学段阅读研讨", "11.png", "elephant_play"),
            ("即景", "02.jpeg", "jing_wide"),
            ("即景", "04.jpeg", "jing_board_scene"),
            ("我的植物朋友", "02.jpeg", "plant_wide"),
            ("我的植物朋友", "05.jpeg", "plant_share"),
            ("古人谈读书", "02.jpeg", "guren_wide"),
        ],
        "scaffold": [
            ("real", "jing_card.jpg", "jing_card"),
            ("real", "jing_essay.jpg", "jing_essay"),
            ("即景", "04.jpeg", "jing_board_live"),
            ("real", "plant_card.jpg", "plant_card"),
            ("real", "plant_board.jpg", "plant_board_live"),
            ("real", "plant_share.jpg", "plant_share"),
            ("real", "guren_text.jpg", "guren_text"),
            ("real", "guren_mic.jpg", "guren_mic"),
            ("real", "guren_peer.jpg", "guren_peer"),
        ],
        "break": [
            ("即景", "02.jpeg", "b1"),
            ("即景", "04.jpeg", "b2"),
            ("即景", "06.jpeg", "b3"),
            ("real", "jing_card.jpg", "b4"),
            ("real", "jing_essay.jpg", "b5"),
            ("real", "jing_req.jpg", "b6"),
        ],
        "write": [
            ("我的植物朋友", "02.jpeg", "w1"),
            ("我的植物朋友", "03.jpeg", "w2"),
            ("我的植物朋友", "05.jpeg", "w3"),
            ("我的植物朋友", "06.jpeg", "w4"),
            ("real", "plant_card.jpg", "w5"),
            ("real", "plant_board.jpg", "w6"),
            ("第一学段阅读研讨", "11.png", "w7"),
            ("第一学段阅读研讨", "12.png", "w8"),
            ("real", "plant_share.jpg", "w9"),
        ],
        "voice": [
            ("古人谈读书", "02.jpeg", "v1"),
            ("古人谈读书", "04.jpeg", "v2"),
            ("古人谈读书", "05.jpeg", "v3"),
            ("古人谈读书", "06.jpeg", "v4"),
            ("古人谈读书", "07.jpeg", "v5"),
            ("古人谈读书", "08.jpeg", "v6"),
            ("real", "guren_mic.jpg", "v7"),
            ("real", "guren_peer.jpg", "v8"),
            ("real", "here_beauty.jpg", "v9"),
        ],
        "prep": [
            ("赋能分层共生集备", "11.jpeg", "p1"),
            ("赋能分层共生集备", "12.jpeg", "p2"),
            ("赋能分层共生集备", "13.jpeg", "p3"),
            ("赋能分层共生集备", "14.jpeg", "p4"),
            ("赋能分层共生集备", "15.jpeg", "p5"),
            ("赋能分层共生集备", "16.jpeg", "p6"),
            ("五校语文集体备课", "11.jpeg", "p7"),
            ("五校语文集体备课", "12.jpeg", "p8"),
            ("五校语文集体备课", "14.jpeg", "p9"),
        ],
        "low": [
            ("第一学段阅读研讨", "08.png", "l1"),
            ("第一学段阅读研讨", "09.jpeg", "l2"),
            ("第一学段阅读研讨", "10.png", "l3"),
            ("第一学段阅读研讨", "11.png", "l4"),
        ],
    }
    staged = {}
    for group, specs in mapping.items():
        paths = []
        for album, fname, alias in specs:
            src = resolve_src(album, fname)
            if src is None:
                print("skip missing/rejected", album, fname)
                continue
            dest = DENSE / f"{group}_{alias}{src.suffix.lower()}"
            shutil.copy(src, dest)
            paths.append(dest)
        staged[group] = paths
    return staged


def compose_dense() -> None:
    staged = stage_copies()
    # 图2 课堂现场：9 联
    labels = [
        "（a）低段谜语／字卡投屏", "（b）低段课堂行列就座", "（c）举手应答，发起权在讲台",
        "（d）角色扮演前的座位朝向", "（e）《即景》展示课全景", "（f）《即景》板书与屏幕并置",
        "（g）《我的植物朋友》全景", "（h）记录卡进入公共视野", "（i）《古人谈读书》全景",
    ]
    dense_grid(list(zip(staged["scene"], labels)), "plate_scene.jpg",
               "课堂现场合集（稠密）：座位朝向、发言方向与公开课结构", ncols=3,
               cell=(620, 400))

    labels = [
        "（a）日落观察记录单", "（b）学生片段上屏评改", "（c）《即景》现场板书",
        "（d）植物记录卡细目", "（e）《我的植物朋友》现场板书", "（f）记录卡进入公共视野",
        "（g）语录与注释同屏", "（h）学生持麦解释", "（i）同桌互读互评",
    ]
    dense_grid(list(zip(staged["scaffold"], labels)), "plate_scaffold.jpg",
               "真实教学材料合集（稠密）：观察单、记录卡与现场板书", ncols=3,
               cell=(620, 380), fit="contain")

    labels = [
        "（a）现场全景", "（b）屏幕与真实板书并置", "（c）学生面向讲台写作",
        "（d）观察记录单物证", "（e）片段上屏对照评改", "（f）习作要求进入公共屏",
    ]
    dense_grid(list(zip(staged["break"], labels)), "plate_break.jpg",
               "《即景》破程合集（稠密）：观察所得进课堂，终稿仍由学生完成", ncols=3)

    labels = [
        "（a）课堂全景", "（b）教师组织分享", "（c）学生举卡可见",
        "（d）同伴交流瞬间", "（e）记录卡细节", "（f）现场板书支架",
        "（g）低段角色互动", "（h）低段横向问答预备", "（i）记录卡进入公共视野",
    ]
    dense_grid(list(zip(staged["write"], labels)), "plate_write.jpg",
               "化卡为文与低段横向通道合集（稠密）", ncols=3)

    labels = [
        "（a）课堂全景", "（b）同桌／小组活动", "（c）持麦解释",
        "（d）教师侧立组织", "（e）语录文本上屏", "（f）学生面向同伴表达",
        "（g）持麦表达特写", "（h）同桌互读", "（i）《这儿真美》按支架动笔",
    ]
    dense_grid(list(zip(staged["voice"], labels)), "plate_voice.jpg",
               "复权合集（稠密）：把问和写交还给学生", ncols=3)

    labels = [
        "（a）“赋能·分层·共生”课堂", "（b）学情支架展示", "（c）课堂互动组织",
        "（d）学生按任务表达", "（e）量规／评价可见", "（f）同伴互评瞬间",
        "（g）五校联研习作课", "（h）按支架动笔", "（i）同课异构现场",
    ]
    dense_grid(list(zip(staged["prep"], labels)), "plate_prep.jpg",
               "区域习作教研合集（稠密）：赋能·分层·共生", ncols=3)

    labels = [
        "（a）字卡／谜语投屏", "（b）低段课堂就座",
        "（c）举手应答", "（d）角色扮演",
    ]
    dense_grid(
        list(zip(staged["low"], labels)),
        "plate_low.jpg",
        "图13 低段阅读研讨合集（2×2）",
        ncols=2,
        cell=(860, 560),
        fit="cover",
    )

    meta = {k: [str(p.relative_to(ROOT)) for p in v] for k, v in staged.items()}
    (DENSE / "manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("manifest", DENSE / "manifest.json")


if __name__ == "__main__":
    compose_dense()
