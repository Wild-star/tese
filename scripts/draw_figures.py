#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""绘制学位论文用原创结构图（灰度学术风格，非宣传示意图）。"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, RegularPolygon
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)

FONT = "WenQuanYi Micro Hei"
plt.rcParams.update({
    "font.family": FONT,
    "font.size": 10,
    "axes.unicode_minus": False,
    "savefig.dpi": 200,
    "savefig.facecolor": "white",
    "figure.facecolor": "white",
})

NAVY = "#1F4E79"
BLUE = "#2E75B6"
LIGHT = "#D6E3F0"
PALE = "#F4F7FA"
GRAY = "#595959"
LINE = "#2F2F2F"
ACCENT = "#C45911"
GREEN = "#548235"


def save(fig, name: str) -> None:
    path = OUT / name
    fig.savefig(path, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    print("wrote", path)


def box(ax, x, y, w, h, text, fc=PALE, ec=NAVY, fs=10, fw="normal", radius=0.08):
    p = FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                       boxstyle=f"round,pad=0.02,rounding_size={radius}",
                       facecolor=fc, edgecolor=ec, linewidth=1.2, zorder=2)
    ax.add_patch(p)
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, color=LINE,
            fontweight=fw, zorder=3, wrap=True)


def arrow(ax, x1, y1, x2, y2, color=NAVY):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.3),
                zorder=1)


def fig01_layers():
    fig, ax = plt.subplots(figsize=(8.6, 5.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis("off")
    layers = [
        (5, 1.1, 8.2, 1.3, "操作交互\n媒体操作、点选投屏、朗读测评等可重复行为", LIGHT, "基础层"),
        (5, 2.9, 6.6, 1.3, "信息交互\n关键词交换、资料归集、观点呈现", "#BDD7EE", "中间层"),
        (5, 4.7, 5.0, 1.3, "概念交互\n新旧观念碰撞、文本证据上的意义重构", BLUE, "目标层"),
    ]
    for x, y, w, h, t, c, tag in layers:
        fc = c if c != BLUE else "#9DC3E6"
        box(ax, x, y, w, h, t, fc=fc, fs=10)
        ax.text(x - w / 2 - 0.15, y, tag, ha="right", va="center", color=NAVY, fontsize=9)
    box(ax, 5, 6.35, 4.2, 0.7, "情意共鸣（不可外包给算法）", fc="#F8CBAD", ec=ACCENT, fs=10, fw="bold")
    arrow(ax, 5, 1.75, 5, 2.25)
    arrow(ax, 5, 3.55, 5, 4.05)
    arrow(ax, 5, 5.35, 5, 5.95)
    ax.text(8.7, 3.4, "拾级而上", rotation=90, va="center", color=NAVY, fontsize=11)
    save(fig, "fig01.jpg")


def fig02_model():
    fig, ax = plt.subplots(figsize=(9.2, 10.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")
    ax.set_title("三层互动 × 三元主体 × 三阶校准", fontsize=12, color=NAVY, pad=8)
    rows = [
        (11.2, "课堂问题", ["形式失衡", "关系失衡", "技术失衡"], LIGHT),
        (9.4, "三阶校准", ["破程之阶", "复权之阶", "守界之阶"], "#C5E0B4"),
        (7.6, "互动升级", ["操作交互", "信息交互", "概念交互 → 情意共鸣"], "#BDD7EE"),
        (5.8, "主体变化", ["教师组织", "师生协同", "学生主体"], "#F8CBAD"),
        (4.0, "AI角色", ["工具支撑", "过程支架", "受控介入（不替代人）"], "#FFE699"),
        (2.2, "实践结果", ["覆盖扩大", "层次提升", "边界清晰 / 关系温度"], PALE),
    ]
    for y, lab, items, fc in rows:
        ax.text(0.35, y, lab, ha="left", va="center", fontsize=10, color=NAVY, fontweight="bold")
        w = 2.6 if len(items) == 3 else 2.6
        xs = [2.5, 5.5, 8.5]
        for x, t in zip(xs, items):
            box(ax, x, y, 2.7, 1.05, t, fc=fc, fs=9)
        if y != 2.2:
            arrow(ax, 5.5, y - 0.58, 5.5, y - 1.15)
    box(ax, 5.5, 0.7, 8.4, 0.7, "指向：AI为支架 · 教师为引领 · 学生为意义建构者", fc=NAVY, ec=NAVY, fs=10)
    ax.texts[-1].set_color("white") if False else None
    # redo last box text color
    ax.patches[-1].set_facecolor(NAVY)
    ax.texts[-1].set_color("white")
    ax.texts[-1].set_fontweight("bold")
    save(fig, "fig02.jpg")


def fig03_boundary():
    fig, ax = plt.subplots(figsize=(9.0, 6.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.axis("off")
    box(ax, 5, 7.2, 3.2, 0.8, "教师\n育人判断 · 教学调控", fc="#1F4E79", fs=10)
    ax.texts[-1].set_color("white")
    arrow(ax, 5, 6.75, 5, 5.85)
    box(ax, 5, 5.15, 6.6, 1.5, "学生主体\n思考 · 表达 · 质疑 · 创造", fc="#C5E0B4", fs=12, fw="bold")
    arrow(ax, 5, 2.55, 5, 4.35)
    box(ax, 5, 1.7, 6.8, 1.4, "AI（支架，非主体）\n生成材料 · 归集观点 · 提供提示 · 即时反馈", fc="#FFF2CC", fs=10)
    ax.text(5, 0.55, "不可替代：价值判断、情感回应、终结性判断、真实表达",
            ha="center", fontsize=10, color=ACCENT, fontweight="bold")
    box(ax, 1.5, 3.5, 2.2, 1.1, "监督指导\n内容甄别", fc=LIGHT, fs=9)
    box(ax, 8.5, 3.5, 2.2, 1.1, "小学限制\n独自开放生成", fc=LIGHT, fs=9)
    save(fig, "fig03.jpg")


def fig04_chain():
    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 5)
    ax.axis("off")
    items = [
        (2, 3.4, "形式失衡\n怎么互动", "通道单一\n参与不均\n生成受限"),
        (6, 3.4, "关系失衡\n谁拥有互动权", "发起单向\n表达垄断\n权责模糊"),
        (10, 3.4, "技术失衡\n什么可交给AI", "替答\n替评\n替演\n替证"),
    ]
    for x, y, t, d in items:
        box(ax, x, y, 3.2, 1.6, t, fc=LIGHT, fs=11, fw="bold")
        box(ax, x, 1.3, 3.2, 1.4, d, fc=PALE, fs=9)
        arrow(ax, x, 2.55, x, 2.05)
    arrow(ax, 3.7, 3.4, 4.3, 3.4)
    arrow(ax, 7.7, 3.4, 8.3, 3.4)
    ax.text(6, 4.7, "层层加码：形式收窄 → 权责偏移 → 技术越位", ha="center", color=NAVY, fontsize=11)
    save(fig, "fig04.jpg")


def _network(ax, title, mode):
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title(title, fontsize=11, color=NAVY)
    def node(x, y, t, r=0.55, fc=LIGHT):
        c = Circle((x, y), r, facecolor=fc, edgecolor=NAVY, lw=1.2, zorder=3)
        ax.add_patch(c)
        ax.text(x, y, t, ha="center", va="center", fontsize=8, zorder=4)
    if mode == "old":
        node(5, 6.4, "教师", 0.7, "#1F4E79")
        ax.texts[-1].set_color("white")
        xs = [1.8, 3.6, 5.4, 7.2, 8.6]
        for x in xs:
            node(x, 2.2, "学生", 0.5)
            ax.annotate("", xy=(x, 2.75), xytext=(5, 5.7),
                        arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.0))
        ax.text(5, 0.7, "结构性示意：放射状路径为主，横向联系薄弱\n（供观察记录，不填写虚构边数）",
                ha="center", fontsize=9, color=GRAY)
    else:
        node(5, 7.0, "教师", 0.65, "#1F4E79")
        ax.texts[-1].set_color("white")
        node(2.2, 4.6, "小组", 0.55, "#C5E0B4")
        node(7.8, 4.6, "小组", 0.55, "#C5E0B4")
        node(5, 4.6, "AI", 0.5, "#FFE699")
        for x in [1.3, 3.1, 5.0, 6.9, 8.7]:
            node(x, 2.0, "学生", 0.42)
        # links
        for a, b in [((5, 6.35), (2.2, 5.15)), ((5, 6.35), (7.8, 5.15)), ((5, 6.35), (5, 5.15)),
                     ((2.2, 4.05), (1.3, 2.45)), ((2.2, 4.05), (3.1, 2.45)),
                     ((7.8, 4.05), (6.9, 2.45)), ((7.8, 4.05), (8.7, 2.45)),
                     ((5, 4.1), (5, 2.45))]:
            ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="-", color=BLUE, lw=1.0))
        ax.plot([1.3, 3.1, 5.0, 6.9, 8.7], [2.0]*5, color=GREEN, lw=1.2, zorder=1)
        ax.text(5, 0.55, "观察指标（结构性，非本文统计值）：互动节点 · 互动路径 · 学生横向互动比例",
                ha="center", fontsize=9, color=GRAY)


def fig05_net_old():
    fig, ax = plt.subplots(figsize=(8.4, 6.2))
    _network(ax, "传统课堂互动网络（放射状）", "old")
    save(fig, "fig05.jpg")


def fig06_net_new():
    fig, ax = plt.subplots(figsize=(8.4, 6.6))
    _network(ax, "三元协同课堂互动网络（多回路）", "new")
    save(fig, "fig06.jpg")


def fig07_overreach():
    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 5)
    ax.axis("off")
    items = [("替答", "直接给出本课终答\n跳过探究与试错"),
             ("替评", "当众出示机器分数\n替代情感回应"),
             ("替演", "人机问答充当交往\n过程无真实生成"),
             ("替证", "以工具出场证明先进\n忽略育人质量")]
    for i, (t, d) in enumerate(items):
        x = 1.5 + i * 3.0
        box(ax, x, 3.3, 2.6, 1.3, t, fc="#F8CBAD", fs=14, fw="bold")
        box(ax, x, 1.5, 2.6, 1.5, d, fc=PALE, fs=9)
    ax.text(6, 4.6, "技术越位的四种可观察表现", ha="center", color=NAVY, fontsize=12)
    save(fig, "fig07.jpg")


def fig08_ladder():
    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    steps = [
        (1.8, "破程之阶", "打开通道\n对应形式失衡"),
        (5.0, "复权之阶", "归还互动权\n对应关系失衡"),
        (8.2, "守界之阶", "限制技术越位\n对应技术失衡"),
    ]
    for i, (x, t, d) in enumerate(steps):
        y = 1.6 + i * 0.15
        box(ax, x, 3.4, 2.7, 2.2, t + "\n\n" + d, fc=[LIGHT, "#C5E0B4", "#FFE699"][i], fs=11, fw="bold")
        if i < 2:
            arrow(ax, x + 1.4, 3.4, steps[i+1][0] - 1.4, 3.4)
    ax.text(5, 5.4, "必须拾级而上：通道不开则复权空转；权责不准则守界落空", ha="center", color=NAVY, fontsize=10)
    ax.text(5, 0.7, "课前一分钟诊断：先看通道 → 再看权责 → 后看边界", ha="center", fontsize=10)
    save(fig, "fig08.jpg")


def fig09_questions():
    fig, ax = plt.subplots(figsize=(8.8, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    qs = [
        (5.2, "L1 提取：课文写了哪些颜色/动作？"),
        (4.0, "L2 比较：哪一处动态变化最明显？依据？"),
        (2.8, "L3 评价：删掉这句话，画面还完整吗？"),
        (1.6, "L4 创造：用自己的三句话写“我的火烧云”"),
    ]
    for y, t in qs:
        box(ax, 5.2, y, 8.2, 0.9, t, fc=PALE, fs=11)
    ax.text(5.2, 5.5, "梯度问题链（AI供问，教师守门，学生先写后比）", ha="center", color=NAVY, fontsize=11)
    save(fig, "fig09.jpg")


def fig10_loop():
    fig, ax = plt.subplots(figsize=(8.8, 6.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.axis("off")
    box(ax, 5, 7.1, 4.4, 0.9, "课前预学：AI辅助诊断与任务分发", fc=LIGHT, fs=10)
    box(ax, 5, 5.3, 4.4, 0.9, "学情归集（教师甄别）", fc=PALE, fs=10)
    box(ax, 5, 3.5, 4.4, 1.1, "课中互学：教师调控 + AI支架\n学生思考—表达—质疑", fc="#C5E0B4", fs=10)
    box(ax, 5, 1.5, 4.4, 1.0, "课后辩学：对照课文校验AI输出\n任务迭代与复盘", fc="#FFE699", fs=10)
    arrow(ax, 5, 6.6, 5, 5.8)
    arrow(ax, 5, 4.8, 5, 4.1)
    arrow(ax, 5, 2.9, 5, 2.05)
    ax.annotate("", xy=(2.6, 7.1), xytext=(2.6, 1.5),
                arrowprops=dict(arrowstyle="-|>", connectionstyle="arc3,rad=0.35", color=NAVY, lw=1.2))
    ax.text(1.15, 4.3, "复盘\n回流", ha="center", color=NAVY, fontsize=9)
    ax.text(5, 0.45, "教师：设计—判断—调控　　AI：生成—归集—提示　　学生：思考—表达—质疑",
            ha="center", fontsize=9)
    save(fig, "fig10.jpg")


def fig11_ask():
    fig, ax = plt.subplots(figsize=(9.0, 5.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    rows = [
        (4.8, "不建议", "帮我写一段赏析 / 这篇课文讲了什么"),
        (3.2, "建议", "这句话如果删掉，意思会有什么不同？"),
        (1.6, "校验", "你的依据在课文哪一句？能否找到反例？"),
    ]
    cols = [("#F8CBAD", 4.8), ("#C5E0B4", 3.2), ("#BDD7EE", 1.6)]
    for (y, lab, t), (fc, _) in zip(rows, cols):
        box(ax, 1.5, y, 2.0, 1.1, lab, fc=fc, fs=11, fw="bold")
        box(ax, 6.3, y, 6.4, 1.1, t, fc=PALE, fs=10)
    ax.text(5, 5.6, "学生向生成式人工智能提问的支架转向", ha="center", color=NAVY, fontsize=12)
    save(fig, "fig11.jpg")


def fig12_ai_role():
    fig, ax = plt.subplots(figsize=(9.0, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.5)
    ax.axis("off")
    box(ax, 3, 3.4, 4.2, 3.0, "AI宜做\n生成问题梯度\n归集小组观点\n观察记录卡模板\n即时朗读反馈\n情境图辅助识字", fc="#E2EFDA", fs=11)
    box(ax, 7.2, 3.4, 4.2, 3.0, "AI慎做/禁做\n直接给出中心思想\n当众惩戒式评分\n直接生成成篇习作\n充当价值判断者\n小学生独自开放生成", fc="#FCE4D6", fs=11)
    ax.text(5, 0.7, "原则：育人为本、技术为用；增强而非替代", ha="center", color=NAVY, fontsize=11, fontweight="bold")
    save(fig, "fig12.jpg")


def fig13_intensity():
    fig, ax = plt.subplots(figsize=(8.2, 5.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xlabel("生成式AI介入强度 →")
    ax.set_ylabel("学生主体性（思考—表达—质疑）")
    ax.set_xticks([])
    ax.set_yticks([])
    xs = np.linspace(0.8, 9.2, 80)
    ys = 1.4 + 6.6 * np.exp(-((xs - 4.6) ** 2) / 6.8)
    ax.plot(xs, ys, color=NAVY, lw=2)
    ax.fill_between(xs, 0, ys, where=(xs > 3.2) & (xs < 6.2), color="#C5E0B4", alpha=0.5)
    ax.text(1.4, 2.6, "工具型", fontsize=10)
    ax.text(3.7, 8.4, "支架型（最佳区域）", fontsize=10, color=GREEN)
    ax.text(7.5, 2.3, "替代型", fontsize=10, color=ACCENT)
    ax.set_title("AI介入强度与学生主体性：中等介入、高主体性为适切区间", fontsize=11, color=NAVY)
    save(fig, "fig13.jpg")


def fig14_radar():
    labels = ["问题开放度", "参与覆盖面", "交互层次", "人机边界", "情意回应", "倾听质疑"]
    n = len(labels)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    fig, ax = plt.subplots(figsize=(6.6, 6.6), subplot_kw=dict(polar=True))
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_thetagrids(np.degrees(ang), labels)
    ax.set_ylim(0, 3)
    ax.set_yticks([1, 2, 3])
    ax.set_yticklabels(["1", "2", "3"], fontsize=8, color=GRAY)
    ax.set_title("课堂互动质量六维观察工具（示意，非实测分数）", fontsize=11, color=NAVY, pad=18)
    ring = np.ones(n) * 3
    ax.plot(np.append(ang, ang[0]), np.append(ring, ring[0]), color=LIGHT, lw=1)
    ax.fill(np.append(ang, ang[0]), np.append(np.ones(n)*2, 2), color=BLUE, alpha=0.08)
    save(fig, "fig14.jpg")


def fig15_code():
    fig, ax = plt.subplots(figsize=(9.2, 6.2))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis("off")
    cols = [
        (2, "T 教师行为", "T1 提问\nT2 追问\nT3 反馈\nT4 情感支持\nT5 价值判断", LIGHT),
        (6, "S 学生行为", "S1 回答  S2 提问\nS3 补充  S4 质疑\nS5 合作  S6 创造", "#C5E0B4"),
        (10, "AI 技术行为", "AI1 生成\nAI2 归集\nAI3 提示\nAI4 反馈\nAI5 可视化", "#FFE699"),
    ]
    for x, t, d, fc in cols:
        box(ax, x, 5.6, 3.4, 0.8, t, fc=fc, fs=11, fw="bold")
        box(ax, x, 3.4, 3.4, 2.6, d, fc=PALE, fs=10)
    box(ax, 6, 1.2, 10.4, 1.2, "可观察互动链：T→S　T→AI→S　S→AI→S　S→S　T→S→T", fc=NAVY, fs=11)
    ax.texts[-1].set_color("white")
    ax.text(6, 7.4, "课堂互动行为编码体系（供录像编码与课后复盘）", ha="center", color=NAVY, fontsize=12)
    save(fig, "fig15.jpg")


def fig16_huoshaoyun():
    fig, ax = plt.subplots(figsize=(9.0, 3.6))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4)
    ax.axis("off")
    steps = ["课前观察\n写下三句", "AI供四层问\n教师筛选", "先写后比\n折叠终答", "情意护航\n评分课后看"]
    for i, t in enumerate(steps):
        box(ax, 1.6 + i * 3.0, 2.1, 2.5, 1.6, t, fc=LIGHT, fs=10)
        if i < 3:
            arrow(ax, 2.85 + i * 3.0, 2.1, 3.35 + i * 3.0, 2.1)
    ax.text(6, 3.5, "《火烧云》破程流程：问题引擎 + 先思后比", ha="center", color=NAVY, fontsize=11)
    save(fig, "fig16.jpg")


def fig17_shouzhu():
    fig, ax = plt.subplots(figsize=(9.0, 3.6))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4)
    ax.axis("off")
    steps = ["学生口述\n留住悬念", "AI扮守株人\n学生追问", "接住意外\n正反用证据", "投屏争议句\n据文证伪"]
    for i, t in enumerate(steps):
        box(ax, 1.6 + i * 3.0, 2.1, 2.5, 1.6, t, fc="#F8CBAD", fs=10)
        if i < 3:
            arrow(ax, 2.85 + i * 3.0, 2.1, 3.35 + i * 3.0, 2.1)
    ax.text(6, 3.5, "《守株待兔》复权—守界流程：角色陪练 + 文本证伪", ha="center", color=NAVY, fontsize=11)
    save(fig, "fig17.jpg")


def fig18_shouzhi():
    fig, ax = plt.subplots(figsize=(9.0, 3.6))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4)
    ax.axis("off")
    steps = ["小组讨论\n五指特点", "关键词输入\nAI归集投屏", "组际追问\n找课文依据", "边缘声音\n进入公共屏幕"]
    for i, t in enumerate(steps):
        box(ax, 1.6 + i * 3.0, 2.1, 2.5, 1.6, t, fc="#C5E0B4", fs=10)
        if i < 3:
            arrow(ax, 2.85 + i * 3.0, 2.1, 3.35 + i * 3.0, 2.1)
    ax.text(6, 3.5, "《手指》全员可见流程：归集是支架，追问才是互动", ha="center", color=NAVY, fontsize=11)
    save(fig, "fig18.jpg")


def fig19_public():
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.bar(["应用前", "应用后"], [82, 94], color=["#A6A6A6", NAVY], width=0.45)
    ax.set_ylim(70, 100)
    ax.set_ylabel("班级平均发音准确率（%）")
    ax.set_title("公开案例中的AI朗读反馈效果（非本文实验数据）", fontsize=11, color=NAVY)
    for i, v in enumerate([82, 94]):
        ax.text(i, v + 0.8, f"{v}%", ha="center", fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    save(fig, "fig19.jpg")


def fig24_card_to_text():
    fig, ax = plt.subplots(figsize=(9.2, 3.4))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4)
    ax.axis("off")
    steps = ["课前观察\n完成记录卡", "课中分享\n补充观察角度", "化卡为文\n写清楚+有感受", "互评修改\n同伴交流分享"]
    for i, t in enumerate(steps):
        box(ax, 1.6 + i * 3.0, 2.0, 2.5, 1.6, t, fc="#D6E3F0", fs=10)
        if i < 3:
            arrow(ax, 2.85 + i * 3.0, 2.0, 3.35 + i * 3.0, 2.0)
    ax.text(6, 3.45, "习作互动链：观察记录卡 → 化卡为文 → 分享修改", ha="center", color="#1F4E79", fontsize=11)
    save(fig, "fig24.jpg")


def _desk(ax, x, y, w=0.55, h=0.32, fc="#D6E3F0"):
    r = FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.01,rounding_size=0.04",
                       facecolor=fc, edgecolor=NAVY, linewidth=0.9, zorder=2)
    ax.add_patch(r)
    ax.add_patch(Circle((x, y + h / 2 + 0.12), 0.09, facecolor="#F4F7FA", edgecolor=NAVY, lw=0.8, zorder=3))


def fig25_desks():
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 5.4))
    for ax in axes:
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 8)
        ax.axis("off")
        ax.set_aspect("equal")
    ax = axes[0]
    ax.set_title("（a）行列式：发言朝向讲台", color=NAVY, fontsize=11)
    box(ax, 5, 7.2, 2.4, 0.7, "教师 / 屏幕", fc=NAVY, fs=9)
    ax.texts[-1].set_color("white")
    for r in range(4):
        for c in range(5):
            _desk(ax, 1.5 + c * 1.7, 5.4 - r * 1.15)
            ax.annotate("", xy=(5, 6.75), xytext=(1.5 + c * 1.7, 5.55 - r * 1.15),
                        arrowprops=dict(arrowstyle="-", color="#A6A6A6", lw=0.6))
    ax.text(5, 0.45, "身体在场 ≠ 话语在场", ha="center", color=ACCENT, fontsize=10)
    ax = axes[1]
    ax.set_title("（b）多向通道：组内互说 + 组际可见", color=NAVY, fontsize=11)
    box(ax, 5, 7.2, 2.2, 0.65, "教师侧立", fc=NAVY, fs=9)
    ax.texts[-1].set_color("white")
    box(ax, 8.6, 7.2, 1.8, 0.65, "AI投屏", fc="#FFE699", fs=9)
    clusters = [(2.4, 4.6), (7.4, 4.6), (5.0, 2.0)]
    for cx, cy in clusters:
        for dx, dy in [(-0.7, 0.45), (0.7, 0.45), (-0.7, -0.45), (0.7, -0.45)]:
            _desk(ax, cx + dx, cy + dy, fc="#C5E0B4")
        ax.add_patch(Circle((cx, cy), 0.22, facecolor="#FFF2CC", edgecolor=GREEN, lw=1.0, zorder=4))
        ax.text(cx, cy, "说", ha="center", va="center", fontsize=8, zorder=5)
    ax.annotate("", xy=(7.4, 5.3), xytext=(2.4, 5.3), arrowprops=dict(arrowstyle="<->", color=BLUE, lw=1.2))
    ax.annotate("", xy=(8.6, 6.8), xytext=(7.4, 5.2), arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=1.0))
    ax.text(5, 0.45, "关键词上屏，追问仍在组际发生", ha="center", color=GREEN, fontsize=10)
    fig.suptitle("座位朝向决定通道：秧田收束发言，围坐打开横向互动", color=NAVY, fontsize=12, y=0.98)
    fig.tight_layout()
    save(fig, "fig25.jpg")


def fig26_traffic():
    fig, ax = plt.subplots(figsize=(10.2, 5.0))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6)
    ax.axis("off")
    lights = [
        (2.0, "#548235", "#E2EFDA", "绿灯·宜做", "问题梯度\n观点归集\n观察卡模板\n朗读即时反馈\n情境图助识字"),
        (6.0, "#C45911", "#FFF2CC", "黄灯·慎做", "角色扮演陪练\n争议句投屏\n学情标签提示\n须教师当场守门"),
        (10.0, "#C00000", "#FCE4D6", "红灯·禁做", "本课终答/中心思想\n成篇习作代写\n当众惩戒式评分\n小学生独自开放生成"),
    ]
    for x, ec, fc, title, body in lights:
        ax.add_patch(Circle((x, 5.15), 0.38, facecolor=ec, edgecolor=ec, zorder=3))
        box(ax, x, 2.6, 3.4, 3.2, title + "\n\n" + body, fc=fc, ec=ec, fs=10)
    ax.text(6, 0.45, "小学语文课堂：绿灯给支架，黄灯须守门，红灯不越位", ha="center", color=NAVY, fontsize=11)
    save(fig, "fig26.jpg")


def fig27_dialogue():
    fig, ax = plt.subplots(figsize=(10.4, 5.2))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6.2)
    ax.axis("off")
    box(ax, 2.4, 4.6, 3.6, 2.0, "屏幕生成句\n“等待也是一种策略”", fc="#FFE699", fs=11)
    box(ax, 6.2, 2.4, 3.2, 1.6, "学生\n课文里有这一句吗？", fc="#C5E0B4", fs=11)
    box(ax, 9.6, 4.4, 3.2, 1.6, "教师\n回到第几自然段？", fc=LIGHT, fs=11)
    arrow(ax, 4.3, 4.2, 5.0, 3.2)
    arrow(ax, 8.0, 4.0, 7.6, 3.2)
    box(ax, 6.2, 0.85, 8.8, 0.9, "概念交互发生在“据文校验”，而不是发生在生成句上屏的瞬间", fc=PALE, fs=10)
    ax.text(6, 5.9, "《守株待兔》现场示意：人机输出必须被追问", ha="center", color=NAVY, fontsize=12)
    save(fig, "fig27.jpg")


def fig28_ketype():
    fig, ax = plt.subplots(figsize=(10.6, 5.6))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7)
    ax.axis("off")
    cols = [
        (1.5, "识字写字", "宜：情境图、音形提示", "禁：替学生识记"),
        (3.9, "阅读鉴赏", "宜：问题链、观点归集", "禁：给中心思想"),
        (6.3, "口语交际", "宜：情境陪练", "禁：替学生发言"),
        (8.7, "习作", "宜：角度/提纲/病句", "禁：生成成篇范文"),
        (11.1, "综合实践", "宜：资料聚类", "禁：替代真实调查"),
    ]
    for x, t, ok, no in cols:
        box(ax, x, 5.6, 2.2, 1.1, t, fc=NAVY, fs=10, fw="bold")
        ax.texts[-1].set_color("white")
        box(ax, x, 3.6, 2.2, 1.8, ok, fc="#E2EFDA", fs=9)
        box(ax, x, 1.5, 2.2, 1.6, no, fc="#FCE4D6", fs=9)
    ax.text(6, 0.4, "课型不同，支架不同；终答、范写、价值判断一律留在人这边", ha="center", color=NAVY, fontsize=11)
    save(fig, "fig28.jpg")


def main():
    fig01_layers()
    fig02_model()
    fig03_boundary()
    fig04_chain()
    fig05_net_old()
    fig06_net_new()
    fig07_overreach()
    fig08_ladder()
    fig09_questions()
    fig10_loop()
    fig11_ask()
    fig12_ai_role()
    fig13_intensity()
    fig14_radar()
    fig15_code()
    fig16_huoshaoyun()
    fig17_shouzhu()
    fig18_shouzhi()
    fig19_public()
    fig24_card_to_text()
    fig25_desks()
    fig26_traffic()
    fig27_dialogue()
    fig28_ketype()
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from compose_plates import compose_all
    compose_all()


if __name__ == "__main__":
    main()
