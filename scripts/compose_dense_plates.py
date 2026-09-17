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


def score_path(p: Path) -> float:
    im = Image.open(p)
    w, h = im.size
    area = w * h
    ar = w / max(h, 1)
    score = float(area)
    if ar > 2.8 or ar < 0.35:
        score *= 0.12
    if area < 120000:
        score *= 0.1
    if 1.1 <= ar <= 1.6:
        score *= 1.45
    return score


def pick(album: str, n: int = 6, prefer: list[str] | None = None) -> list[Path]:
    d = MAT / album
    files = [p for p in d.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
    if prefer:
        ordered = []
        for name in prefer:
            p = d / name
            if p.exists():
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
    pad, cap_h, title_h, gap = 14, 48, 64, 10
    W = ncols * cell[0] + (ncols + 1) * gap
    H = title_h + nrows * (cell[1] + cap_h) + (nrows + 1) * gap
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((W // 2, 16), title, fill=NAVY, font=_font(26), anchor="mt")
    for i, (path, caption) in enumerate(items):
        r, c = divmod(i, ncols)
        x = gap + c * (cell[0] + gap)
        y = title_h + gap + r * (cell[1] + cap_h + gap)
        img = _fit(path, cell[0], cell[1], mode=fit)
        canvas.paste(img, (x, y))
        draw.rectangle([x, y, x + cell[0] - 1, y + cell[1] - 1], outline=NAVY, width=2)
        # wrap caption roughly
        draw.text((x + cell[0] // 2, y + cell[1] + 8), caption, fill="#2F2F2F",
                  font=_font(16), anchor="mt")
    dest = OUT / out_name
    canvas.save(dest, quality=92)
    # also keep a copy under dense/
    shutil.copy(dest, DENSE / out_name)
    print("wrote", dest, f"({n} photos)")
    return dest


def stage_copies() -> dict:
    """Copy selected materials into figures/dense with stable names."""
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
            ("即景", "01.png", "jing_title"),
            ("即景", "03.png", "jing_board"),
            ("即景", "05.jpeg", "jing_card"),
            ("即景", "07.png", "jing_req"),
            ("我的植物朋友", "01.png", "plant_title"),
            ("我的植物朋友", "07.png", "plant_board"),
            ("我的植物朋友", "08.png", "plant_card"),
            ("古人谈读书", "01.png", "guren_title"),
            ("古人谈读书", "03.png", "guren_board"),
        ],
        "break": [
            ("即景", "02.jpeg", "b1"),
            ("即景", "04.jpeg", "b2"),
            ("即景", "06.jpeg", "b3"),
            ("即景", "05.jpeg", "b4"),
            ("即景", "03.png", "b5"),
            ("即景", "07.png", "b6"),
            ("即景", "01.png", "b7"),
            ("赋能分层共生集备", "12.jpeg", "b8"),
            ("赋能分层共生集备", "13.jpeg", "b9"),
        ],
        "write": [
            ("我的植物朋友", "02.jpeg", "w1"),
            ("我的植物朋友", "03.jpeg", "w2"),
            ("我的植物朋友", "05.jpeg", "w3"),
            ("我的植物朋友", "06.jpeg", "w4"),
            ("我的植物朋友", "07.png", "w5"),
            ("我的植物朋友", "08.png", "w6"),
            ("第一学段阅读研讨", "11.png", "w7"),
            ("第一学段阅读研讨", "12.png", "w8"),
            ("赋能分层共生集备", "14.jpeg", "w9"),
        ],
        "voice": [
            ("古人谈读书", "02.jpeg", "v1"),
            ("古人谈读书", "04.jpeg", "v2"),
            ("古人谈读书", "05.jpeg", "v3"),
            ("古人谈读书", "06.jpeg", "v4"),
            ("古人谈读书", "07.jpeg", "v5"),
            ("古人谈读书", "08.jpeg", "v6"),
            ("五校语文集体备课", "11.jpeg", "v7"),
            ("五校语文集体备课", "12.jpeg", "v8"),
            ("五校语文集体备课", "14.jpeg", "v9"),
        ],
        "prep": [
            ("赋能分层共生集备", "11.jpeg", "p1"),
            ("赋能分层共生集备", "12.jpeg", "p2"),
            ("赋能分层共生集备", "13.jpeg", "p3"),
            ("赋能分层共生集备", "15.jpeg", "p4"),
            ("赋能分层共生集备", "16.jpeg", "p5"),
            ("赋能分层共生集备", "18.jpeg", "p6"),
            ("五校语文集体备课", "13.jpeg", "p7"),
            ("五校语文集体备课", "15.jpeg", "p8"),
            ("五校语文集体备课", "16.jpeg", "p9"),
        ],
        "low": [
            ("第一学段阅读研讨", "08.png", "l1"),
            ("第一学段阅读研讨", "09.jpeg", "l2"),
            ("第一学段阅读研讨", "10.png", "l3"),
            ("第一学段阅读研讨", "11.png", "l4"),
            ("第一学段阅读研讨", "12.png", "l5"),
            ("第一学段阅读研讨", "07.png", "l6"),
            ("第一学段阅读研讨", "01.png", "l7"),
            ("地方课程三秀同台", "15.jpeg", "l8"),
            ("地方课程三秀同台", "16.jpeg", "l9"),
        ],
    }
    staged = {}
    for group, specs in mapping.items():
        paths = []
        for album, fname, alias in specs:
            src = MAT / album / fname
            if not src.exists():
                # fallback to best scored
                alts = pick(album, 1)
                if not alts:
                    continue
                src = alts[0]
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
        "（a）《即景》课题页", "（b）《即景》板书支架", "（c）日落观察记录单",
        "（d）教材要求上屏", "（e）《我的植物朋友》课题", "（f）板书：写清楚／有感受",
        "（g）植物记录卡细目", "（h）《古人谈读书》课题", "（i）“熟读深思”板书",
    ]
    dense_grid(list(zip(staged["scaffold"], labels)), "plate_scaffold.jpg",
               "真实教学材料合集（稠密）：板书、记录单与记录卡", ncols=3,
               cell=(620, 380), fit="contain")

    labels = [
        "（a）现场：屏幕与板书并置", "（b）学生面向讲台写作", "（c）片段交流／评改",
        "（d）观察记录单物证", "（e）板书“顺序／变化”", "（f）要求页可见支架",
        "（g）课题导入页", "（h）分层任务进入公共屏", "（i）习作支架课堂流转",
    ]
    dense_grid(list(zip(staged["break"], labels)), "plate_break.jpg",
               "《即景》破程合集（稠密）：观察所得进课堂，终稿仍由学生完成", ncols=3)

    labels = [
        "（a）课堂全景", "（b）教师组织分享", "（c）学生举卡可见",
        "（d）同伴交流瞬间", "（e）板书支架", "（f）记录卡细节",
        "（g）低段角色互动", "（h）低段横向问答预备", "（i）分层习作任务屏",
    ]
    dense_grid(list(zip(staged["write"], labels)), "plate_write.jpg",
               "化卡为文与低段横向通道合集（稠密）", ncols=3)

    labels = [
        "（a）课堂全景", "（b）同桌／小组活动", "（c）持麦解释",
        "（d）教师侧立组织", "（e）语录文本上屏", "（f）学生面向同伴表达",
        "（g）例文／支架上屏", "（h）按支架动笔", "（i）习作同课异构现场",
    ]
    dense_grid(list(zip(staged["voice"], labels)), "plate_voice.jpg",
               "复权合集（稠密）：把问和写交还给学生", ncols=3)

    labels = [
        "（a）“赋能·分层·共生”主题屏", "（b）学情支架展示", "（c）课堂互动组织",
        "（d）学生按任务表达", "（e）量规／评价可见", "（f）同伴互评瞬间",
        "（g）五校联研现场", "（h）同课异构听课", "（i）集备成果交流",
    ]
    dense_grid(list(zip(staged["prep"], labels)), "plate_prep.jpg",
               "区域习作教研合集（稠密）：赋能·分层·共生", ncols=3)

    labels = [
        "（a）字卡／谜语投屏", "（b）低段课堂就座", "（c）举手应答",
        "（d）角色扮演", "（e）学生互问预备", "（f）研讨听课席",
        "（g）课例文本页", "（h）地方课程展示互动", "（i）公开课互动侧面",
    ]
    dense_grid(list(zip(staged["low"], labels)), "plate_low.jpg",
               "低段阅读研讨合集（稠密）：情境打开与通道仍偏放射", ncols=3)

    meta = {k: [str(p.relative_to(ROOT)) for p in v] for k, v in staged.items()}
    (DENSE / "manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("manifest", DENSE / "manifest.json")


if __name__ == "__main__":
    compose_dense()
