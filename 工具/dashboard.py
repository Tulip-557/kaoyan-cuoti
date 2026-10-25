#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作台渲染器 v3：把 库维护.py 扫描好的统计数据渲染成单文件 HTML 仪表盘。

设计语言（参考 Linear / Vercel / Raycast 的"高级暗色"+ Bento + 玻璃拟态）：
近黑底色上叠极光径向光晕；毛玻璃卡片（backdrop-blur + 发丝边框）；
渐变文字大数字；克制的入场微动效。纯标准库、零 CDN、离线可用。
数据由 库维护.py 的 dashboard 子命令准备，本模块只负责"长什么样"。
"""
import datetime as dt
import html

SUBJ_COLORS = {"数学": "#6e8bff", "英语": "#2bd4a0", "政治": "#f0b04d", "专业课": "#b487ff"}
SUBJ_ORDER = ["数学", "英语", "政治", "专业课", "其它"]
STATUS_COLORS = {"未掌握": "#ff7849", "复习中": "#6e8bff", "已掌握": "#2bd4a0"}
_ERROR_COLORS = {"概念不清": "#6e8bff", "条件误用": "#2bd4a0", "公式记错": "#f0b04d",
                 "计算失误": "#b487ff", "思路不会": "#ff7849", "审题失误": "#31c9a8",
                 "知识盲区": "#ffa02e", "表达问题": "#8aa0ff", "时间不够": "#8a94a6",
                 "待确认": "#adb5bd", "（空）": "#adb5bd"}

_ICONS = {
    "due": '<path d="M8 2v4M16 2v4M3 9h18M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"/>',
    "load": '<path d="M3 20h18M6 20v-6M11 20V8M16 20v-9M21 20V5"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/>',
    "pie": '<circle cx="12" cy="12" r="9"/><path d="M12 3v9l7.8 4.5"/>',
    "heat": '<rect x="3" y="4" width="5" height="5" rx="1.5"/><rect x="10" y="4" width="5" height="5" rx="1.5"/><rect x="17" y="4" width="4" height="5" rx="1.5"/><rect x="3" y="11" width="5" height="5" rx="1.5"/><rect x="10" y="11" width="5" height="5" rx="1.5"/><rect x="17" y="11" width="4" height="9" rx="1.5"/><rect x="3" y="18" width="12" height="2" rx="1"/>',
    "trend": '<path d="M3 17l5-6 4 3 6-8"/><circle cx="18" cy="6" r="1.6" fill="currentColor"/>',
    "alert": '<path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 10v4M12 17.5v.3"/>',
    "book": '<path d="M4 5a2 2 0 0 1 2-2h14v18H6a2 2 0 0 0-2 2V5Z"/><path d="M4 19a2 2 0 0 1 2-2h14"/>',
    "brain": '<path d="M9.5 3A3.5 3.5 0 0 0 6 6.5 3 3 0 0 0 4 9.3a3 3 0 0 0 1.6 2.7A3 3 0 0 0 6 15a3 3 0 0 0 3 3 3 3 0 0 0 3-3V6.5A3.5 3.5 0 0 0 9.5 3Z"/><path d="M14.5 3A3.5 3.5 0 0 1 18 6.5a3 3 0 0 1 2 2.8 3 3 0 0 1-1.6 2.7A3 3 0 0 1 18 15a3 3 0 0 1-3 3 3 3 0 0 1-3-3"/>',
    "trophy": '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4Z"/><path d="M7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
}


def _icon(name):
    return f'<svg class="picon" viewBox="0 0 24 24" aria-hidden="true">{_ICONS[name]}</svg>'


def _rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _obsidian(file_rel, stem):
    from urllib.parse import quote
    href = "obsidian://open?vault=%E8%80%83%E7%A0%94&file=" + quote(file_rel)
    return f'<a class="note" href="{href}">{html.escape(stem)}</a>'


def _kpi(num, label, sub="", tone=""):
    tone_cls = f" t-{tone}" if tone else ""
    sub_html = f'<div class="kpi-s">{sub}</div>' if sub else ""
    return (f'<div class="kpi"><div class="kpi-n count{tone_cls}" data-n="{num}">0</div>'
            f'<div class="kpi-l">{html.escape(label)}</div>{sub_html}</div>')


def _donut(dist, total, cap):
    if not dist or not total:
        return '<div class="muted">暂无科目数据</div>'
    segs, acc = [], 0.0
    gap = 1.0
    for label, count in dist:
        pct = count / total * 100
        color = SUBJ_COLORS.get(label, "#8a94a6")
        segs.append(
            f'<circle cx="21" cy="21" r="15.9155" fill="none" stroke="{color}" stroke-width="7" '
            f'pathLength="100" stroke-linecap="round" '
            f'stroke-dasharray="{max(0.5, pct - gap):.2f} {100 - max(0.5, pct - gap):.2f}" '
            f'stroke-dashoffset="{-acc - gap / 2:.2f}" transform="rotate(-90 21 21)">'
            f'<title>{html.escape(str(label))} · {count} 道</title></circle>')
        acc += pct
    legend = "".join(
        f'<span class="lg"><i style="background:{SUBJ_COLORS.get(l, "#8a94a6")}"></i>'
        f'{html.escape(str(l))}<b>{c}</b></span>' for l, c in dist)
    return (f'<div class="donut-wrap"><svg viewBox="0 0 42 42" class="donut">'
            f'<circle cx="21" cy="21" r="15.9155" fill="none" stroke="var(--track)" stroke-width="7"/>'
            f'{"".join(segs)}</svg>'
            f'<div class="donut-cap"><b class="grad-t">{total}</b><small>{html.escape(cap)}</small></div></div>'
            f'<div class="legend">{legend}</div>')


def _stack_rows(subject_status):
    rows = []
    order = [s for s in SUBJ_ORDER if s in subject_status]
    order += [s for s in subject_status if s not in order]
    for subj in order:
        counts = subject_status[subj]
        tot = sum(counts.values())
        color = SUBJ_COLORS.get(subj, "#8a94a6")
        if tot == 0:
            segs = '<i class="empty-seg"></i>'
        else:
            segs = "".join(
                f'<i style="flex:{c};background:{STATUS_COLORS[st]}" '
                f'title="{html.escape(subj)} · {st} {c}"></i>'
                for st, c in counts.items() if c)
        rows.append(f'<div class="srow"><span class="slb" style="color:{color}">{html.escape(subj)}</span>'
                    f'<span class="stack">{segs}</span><b class="snum">{tot}</b></div>')
    legend = "".join(f'<span class="lg"><i style="background:{STATUS_COLORS[s]}"></i>{s}</span>'
                     for s in ("未掌握", "复习中", "已掌握"))
    return "".join(rows) + f'<div class="legend">{legend}</div>'


def _bars(dist, colors=None, empty="暂无数据"):
    if not dist:
        return f'<div class="muted">{empty}</div>'
    maxc = max(c for _l, c in dist) or 1
    total = sum(c for _l, c in dist) or 1
    out = []
    for label, count in dist:
        color = (colors or {}).get(label, "#748ffc")
        w = count / maxc * 100
        pct = count / total * 100
        out.append(
            f'<div class="brow"><span class="blb" title="{html.escape(str(label))}">{html.escape(str(label))}</span>'
            f'<span class="btrack"><i style="--w:{w:.1f}%;background:linear-gradient(90deg,{_rgba(color, 0.55)},{color})"></i></span>'
            f'<span class="bnum">{count}<small>{pct:.0f}%</small></span></div>')
    return "".join(out)


def _smooth(pts):
    if len(pts) < 2:
        return ""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def _sparkline(pairs):
    """近 8 周新增：平滑面积折线（SVG）。"""
    vals = [p["count"] for p in pairs]
    n = len(vals)
    if n < 2:
        return '<div class="muted">数据不足</div>'
    W, H, top, bottom = 560, 168, 30, 34
    maxv = max(vals) or 1
    pts = []
    for i, v in enumerate(vals):
        x = 14 + i * ((W - 28) / (n - 1))
        y = top + (1 - v / maxv) * (H - top - bottom)
        pts.append((x, y))
    line = _smooth(pts)
    area = line + f"L{pts[-1][0]:.1f},{H - bottom + 2} L{pts[0][0]:.1f},{H - bottom + 2} Z"
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="var(--card)" stroke="var(--accent)" stroke-width="2"/>'
        f'<text x="{x:.1f}" y="{y - 10:.1f}" text-anchor="middle" class="sv">{v}</text>'
        for (x, y), v in zip(pts, vals) if v)
    labels = "".join(
        f'<text x="{x:.1f}" y="{H - 12}" text-anchor="middle" class="sl">{html.escape(pairs[i]["label"])}</text>'
        for i, (x, _y) in enumerate(pts))
    last_x, last_y = pts[-1]
    return (
        '<svg viewBox="0 0 560 168" class="spark" preserveAspectRatio="none">'
        '<defs><linearGradient id="areaG" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="var(--accent)" stop-opacity=".38"/>'
        '<stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs>'
        f'<path d="{area}" fill="url(#areaG)"/>'
        f'<path d="{line}" fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linecap="round"/>'
        f'{dots}{labels}'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="5.5" fill="var(--accent)" opacity=".28"/>'
        "</svg>")


def _cols(pairs, unit="道", today_idx=None):
    maxc = max((p["count"] for p in pairs), default=0) or 1
    cells = []
    for i, p in enumerate(pairs):
        c = p["count"]
        h = 8 + c / maxc * 86
        cls = " today" if (today_idx is not None and i == today_idx) else ""
        val = f"{c}" if c else ""
        cells.append(
            f'<div class="col{cls}" title="{html.escape(p["label"])} · {c} {unit}">'
            f'<span class="cv">{val}</span>'
            f'<i style="--h:{h:.0f}px"></i>'
            f'<em>{html.escape(p["label"])}</em></div>')
    return f'<div class="cols">{"".join(cells)}</div>'


def _heatmap(note_days, today_iso):
    t = dt.date.fromisoformat(today_iso)
    monday = t - dt.timedelta(days=t.weekday())
    start = monday - dt.timedelta(weeks=15)
    cols, labels = [], []
    prev_month = None
    for w in range(16):
        week_start = start + dt.timedelta(weeks=w)
        labels.append(f"<span>{week_start.month}月</span>" if week_start.month != prev_month else "<span></span>")
        prev_month = week_start.month
        cells = []
        for d in range(7):
            day = week_start + dt.timedelta(days=d)
            if day > t:
                cells.append('<i class="hcell fut"></i>')
                continue
            c = note_days.get(day.isoformat(), 0)
            lv = 0 if c == 0 else 1 if c == 1 else 2 if c == 2 else 3 if c <= 4 else 4
            title = f"{day.month}/{day.day} · " + (f"{c} 道新错题" if c else "无")
            cells.append(f'<i class="hcell lv{lv}" title="{title}"></i>')
        cols.append(f'<span class="hcol">{"".join(cells)}</span>')
    legend = ('<div class="hlegend"><span>少</span><i class="hcell lv0"></i><i class="hcell lv1"></i>'
              '<i class="hcell lv2"></i><i class="hcell lv3"></i><i class="hcell lv4"></i><span>多</span></div>')
    weekday_lbs = '<div class="hweeks"><span>一</span><span></span><span>三</span><span></span><span>五</span><span></span><span>日</span></div>'
    return ('<div class="heat-wrap">' + weekday_lbs +
            '<div class="heat-main"><div class="hlabels">' + "".join(labels) + "</div>"
            f'<div class="hgrid">{"".join(cols)}</div></div></div>' + legend)


def _due_panel(due):
    if not due:
        return '<div class="zero-state">🎉 今天没有到期的错题</div>'
    chips = ['<button class="chip on" data-f="all">全部 ' + str(len(due)) + "</button>"]
    counts = {}
    for x in due:
        counts[x["subject"]] = counts.get(x["subject"], 0) + 1
    for subj, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        color = SUBJ_COLORS.get(subj, "#8a94a6")
        chips.append(f'<button class="chip" data-f="{html.escape(subj)}">'
                     f'<i style="background:{color}"></i>{html.escape(subj)} {c}</button>')
    items = []
    for x in due:
        color = SUBJ_COLORS.get(x["subject"], "#8a94a6")
        if x["overdue"] > 0:
            due_tag = f'<span class="due-tag over">逾期 {x["overdue"]} 天</span>'
        else:
            due_tag = '<span class="due-tag">今天</span>'
        wc = (f'<span class="wc" title="累计做错 {x["wrong_count"]} 次">×{x["wrong_count"]}</span>'
              if x["wrong_count"] else "")
        over_cls = " is-over" if x["overdue"] > 0 else ""
        items.append(
            f'<div class="due{over_cls}" data-subject="{html.escape(x["subject"])}" style="--sc:{color}">'
            f'<span class="due-main">{_obsidian(x["file"], x["stem"])}'
            f'<em class="tp">{html.escape(x["topic"])}</em></span>'
            f'{wc}{due_tag}</div>')
    return f'<div class="chips">{"".join(chips)}</div><div class="due-list">{"".join(items)}</div>'


def _high_table(high):
    if not high:
        return '<div class="muted">还没有错过 2 次以上的题——保持住。</div>'
    rows = []
    for i, x in enumerate(high, 1):
        color = SUBJ_COLORS.get(x["subject"], "#8a94a6")
        rank_cls = " gold" if i == 1 else " silver" if i == 2 else " bronze" if i == 3 else ""
        rows.append(
            f'<tr><td><span class="rank{rank_cls}">{i}</span></td>'
            f'<td class="td-note">{_obsidian(x["file"], x["stem"])}</td>'
            f'<td><span class="dot" style="background:{color}"></span>{html.escape(x["subject"])}</td>'
            f'<td class="td-tp">{html.escape(x["topic"])}</td>'
            f'<td><b class="wcbig">{x["wrong_count"]}</b> 次</td>'
            f'<td><span class="pill p-{x["status"]}">{html.escape(x["status"])}</span></td></tr>')
    return ('<table class="tbl"><thead><tr><th>#</th><th>题目</th><th>科目</th><th>知识点</th>'
            f'<th>错过</th><th>状态</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')


def _recent_table(recent):
    if not recent:
        return '<div class="muted">暂无记录</div>'
    rows = []
    for x in recent:
        color = SUBJ_COLORS.get(x["subject"], "#8a94a6")
        rows.append(
            f'<tr><td class="td-date">{x["date"][5:]}</td>'
            f'<td class="td-note">{_obsidian(x["file"], x["stem"])}</td>'
            f'<td><span class="dot" style="background:{color}"></span>{html.escape(x["subject"])}</td>'
            f'<td><span class="pill p-{x["status"]}">{html.escape(x["status"])}</span></td></tr>')
    return ('<table class="tbl"><thead><tr><th>录入</th><th>题目</th><th>科目</th><th>状态</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def _funnel(status_counts, total, mastery):
    if not total:
        return '<div class="muted">暂无数据</div>'
    segs = "".join(
        f'<i style="flex:{status_counts[s]};background:{STATUS_COLORS[s]}" '
        f'title="{s} {status_counts[s]} 道"></i>' for s in ("未掌握", "复习中", "已掌握") if status_counts[s])
    rows = "".join(
        f'<div class="f-row"><span class="lg"><i style="background:{STATUS_COLORS[s]}"></i>{s}</span>'
        f'<b>{status_counts[s]}</b><small>{status_counts[s] / total * 100:.0f}%</small></div>'
        for s in ("未掌握", "复习中", "已掌握"))
    return (f'<div class="mastery"><b class="grad-t">{mastery:.0f}%</b><span>掌握率</span></div>'
            f'<div class="stack big">{segs}</div><div class="f-rows">{rows}</div>')


def _empty_state():
    return (
        '<div class="panel empty-big">'
        '<svg viewBox="0 0 120 120" class="empty-svg" aria-hidden="true">'
        '<defs><linearGradient id="eg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#6e8bff"/><stop offset="1" stop-color="#b487ff"/></linearGradient></defs>'
        '<rect x="22" y="18" width="66" height="84" rx="10" fill="none" stroke="url(#eg)" stroke-width="4"/>'
        '<path d="M36 42h38M36 56h38M36 70h22" stroke="url(#eg)" stroke-width="4" stroke-linecap="round"/>'
        '<circle cx="84" cy="82" r="19" fill="none" stroke="url(#eg)" stroke-width="4"/>'
        '<path d="M75 82l6 6 12-13" fill="none" stroke="url(#eg)" stroke-width="4.4" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
        '<h2>还没有错题数据——面板在等你的第一张照片</h2>'
        '<p class="muted">流程只有三步：</p>'
        '<div class="steps">'
        '<div class="step"><b>1</b>拍照发给 AI 工具<br><small>或丢进 收件箱/</small></div>'
        '<div class="step"><b>2</b>AI 转写、判类、查重后归档<br><small>附一行判断依据，你只纠错</small></div>'
        '<div class="step"><b>3</b>面板自动亮起<br><small>到期提醒、构成分析、复习负载</small></div>'
        "</div>"
        '<p class="muted" style="margin-top:14px">说一句「刷新工作台」可随时重新生成本页面。</p>'
        "</div>")


_CSS = """
:root{
  --bg:#0b0d13; --bg2:#0f1219; --card:rgba(22,26,37,.66); --card-solid:#161b26;
  --ink:#e9edf6; --sub:#9aa3b8; --line:rgba(148,163,199,.16); --line2:rgba(148,163,199,.10);
  --accent:#7c93ff; --accent2:#5b7cfa; --violet:#b487ff; --warn:#ff8a5c; --ok:#2bd4a0;
  --track:rgba(148,163,199,.14);
  --glass-blur:blur(18px) saturate(1.5);
  --shadow:0 1px 0 rgba(255,255,255,.05) inset, 0 18px 44px rgba(2,6,18,.5);
  --h0:rgba(148,163,199,.10); --h1:rgba(124,147,255,.30); --h2:rgba(124,147,255,.55);
  --h3:#5b7cfa; --h4:#8fa6ff;
  --gold:#ffd257;
  --r:18px;
}
html[data-theme="light"]{
  --bg:#eef0f7; --bg2:#ffffff; --card:rgba(255,255,255,.72); --card-solid:#ffffff;
  --ink:#1a2133; --sub:#5f6a83; --line:rgba(30,41,72,.12); --line2:rgba(30,41,72,.07);
  --accent:#4c6ef5; --accent2:#4263eb; --violet:#8f5cf0; --warn:#e8590c; --ok:#0ca678;
  --track:rgba(30,41,72,.09);
  --glass-blur:blur(18px) saturate(1.3);
  --shadow:0 1px 0 rgba(255,255,255,.8) inset, 0 16px 40px rgba(30,41,72,.12);
  --h0:rgba(30,41,72,.07); --h1:rgba(76,110,245,.22); --h2:rgba(76,110,245,.42);
  --h3:#5b7cfa; --h4:#3b52d9;
  --gold:#f5b301;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{
  font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  color:var(--ink);padding:0 18px 60px;line-height:1.5;
  background:var(--bg);min-height:100vh;overflow-x:hidden;
  transition:background .3s ease,color .3s ease;
}
/* ── 极光背景 ── */
.aurora{position:fixed;inset:0;z-index:-1;overflow:hidden;pointer-events:none}
.aurora i{position:absolute;border-radius:50%;filter:blur(90px);opacity:.5}
html[data-theme="light"] .aurora i{opacity:.30;filter:blur(80px)}
.aurora .a1{width:640px;height:640px;left:-180px;top:-220px;background:radial-gradient(circle,rgba(91,124,250,.55),transparent 65%);animation:drift1 26s ease-in-out infinite alternate}
.aurora .a2{width:560px;height:560px;right:-160px;top:-120px;background:radial-gradient(circle,rgba(180,135,255,.45),transparent 65%);animation:drift2 32s ease-in-out infinite alternate}
.aurora .a3{width:620px;height:620px;left:34%;bottom:-300px;background:radial-gradient(circle,rgba(43,212,160,.32),transparent 65%);animation:drift1 38s ease-in-out infinite alternate-reverse}
@keyframes drift1{from{transform:translate(0,0) scale(1)}to{transform:translate(70px,50px) scale(1.12)}}
@keyframes drift2{from{transform:translate(0,0) scale(1.05)}to{transform:translate(-60px,70px) scale(.95)}}
@media (prefers-reduced-motion: reduce){.aurora i{animation:none}}

.wrap{max-width:1160px;margin:0 auto}

/* ── 顶栏 ── */
.topbar{
  position:sticky;top:10px;z-index:50;margin:14px -6px 20px;padding:10px 16px;
  display:flex;align-items:center;gap:14px;border-radius:16px;
  background:var(--card);backdrop-filter:var(--glass-blur);-webkit-backdrop-filter:var(--glass-blur);
  border:1px solid var(--line);box-shadow:var(--shadow);
}
.brand{display:flex;align-items:center;gap:10px;font-size:16.5px;font-weight:700;letter-spacing:.3px}
.brand svg{width:26px;height:26px}
.snap{color:var(--sub);font-size:12px;margin-left:auto;text-align:right;line-height:1.5}
.tbtn{
  border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:12px;
  padding:8px 13px;font-size:12.5px;cursor:pointer;display:flex;align-items:center;gap:7px;
  transition:border-color .2s ease,transform .15s ease;
}
.tbtn:hover{border-color:var(--accent);transform:translateY(-1px)}
.tbtn svg{width:15px;height:15px}
html[data-theme="dark"] .icon-sun{display:none}
html[data-theme="light"] .icon-moon{display:none}

/* ── 头部：倒计时 + KPI ── */
.hero-grid{display:grid;grid-template-columns:300px 1fr;gap:16px;margin-bottom:16px}
.cd-card{
  position:relative;overflow:hidden;border-radius:var(--r);padding:20px 22px;
  background:linear-gradient(140deg,#4353d9 0%,#6d5df0 48%,#a45cf0 100%);
  color:#fff;display:flex;flex-direction:column;gap:6px;box-shadow:0 24px 60px rgba(80,70,220,.35);
}
.cd-card::before{
  content:"";position:absolute;right:-70px;top:-70px;width:220px;height:220px;border-radius:50%;
  background:radial-gradient(circle,rgba(255,255,255,.25),transparent 60%);
}
.cd-card::after{
  content:"";position:absolute;left:-50px;bottom:-90px;width:200px;height:200px;border-radius:50%;
  background:radial-gradient(circle,rgba(255,255,255,.14),transparent 62%);
}
.cd-label{font-size:11px;letter-spacing:4px;opacity:.85}
.cd-num{font-size:52px;font-weight:800;line-height:1.02;font-variant-numeric:tabular-nums;text-shadow:0 4px 24px rgba(0,0,0,.25)}
.cd-num small{font-size:16px;font-weight:500;margin-left:5px;opacity:.85}
.cd-date{font-size:12px;opacity:.82}
.cd-foot{margin-top:auto;padding-top:12px;border-top:1px solid rgba(255,255,255,.28);font-size:12.5px}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}

/* ── 卡片通用（玻璃 + 入场） ── */
.panel,.kpi{
  background:var(--card);backdrop-filter:var(--glass-blur);-webkit-backdrop-filter:var(--glass-blur);
  border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);
  animation:rise .5s cubic-bezier(.2,.7,.2,1) backwards;
}
.panel{padding:18px 20px;min-width:0;transition:border-color .2s ease,transform .2s ease}
.panel:hover{border-color:var(--line)}
.kpi{padding:14px 16px;transition:transform .18s ease,border-color .18s ease}
.kpi:hover{transform:translateY(-2px);border-color:var(--accent)}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion: reduce){.panel,.kpi{animation:none}}
.panel:nth-of-type(1){animation-delay:.02s}.panel:nth-of-type(2){animation-delay:.06s}
.panel:nth-of-type(3){animation-delay:.10s}.panel:nth-of-type(4){animation-delay:.14s}
.panel:nth-of-type(5){animation-delay:.18s}.panel:nth-of-type(6){animation-delay:.22s}
.panel h2{
  font-size:13px;font-weight:700;letter-spacing:.6px;margin-bottom:14px;
  display:flex;align-items:center;gap:9px;color:var(--sub);text-transform:none;
}
.panel h2 .picon{width:17px;height:17px;stroke:var(--accent);fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;flex:none}
.panel h2 .hint{font-size:11px;font-weight:400;margin-left:auto;opacity:.75}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.muted{color:var(--sub);font-size:13px}
.grad-t{
  background:linear-gradient(120deg,var(--accent),var(--violet));
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
.zero-state{color:var(--sub);font-size:13.5px;padding:30px 0;text-align:center}

/* ── 版式 ── */
.grid{display:grid;gap:16px;margin-bottom:16px}
.g53{grid-template-columns:5fr 3fr}
.g35{grid-template-columns:3fr 5fr}
.g73{grid-template-columns:7fr 5fr}
.g3{grid-template-columns:1fr 1fr 1fr}

/* ── 到期清单 ── */
.chips{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:12px}
.chip{
  display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:transparent;
  color:var(--sub);border-radius:999px;padding:4.5px 12px;font-size:12px;cursor:pointer;
  transition:all .16s ease;
}
.chip i{width:7px;height:7px;border-radius:50%;display:inline-block}
.chip:hover{border-color:var(--accent);color:var(--ink)}
.chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.due-list{display:flex;flex-direction:column;max-height:432px;overflow-y:auto;padding-right:6px;scrollbar-width:thin}
.due-list::-webkit-scrollbar{width:7px}
.due-list::-webkit-scrollbar-thumb{background:var(--line);border-radius:4px}
.due{
  display:flex;align-items:center;gap:10px;padding:10px 12px;margin:3px 0;border-radius:12px;
  border-bottom:1px dashed var(--line2);font-size:13.5px;position:relative;
  border-left:3px solid var(--sc);
  background:linear-gradient(90deg,color-mix(in srgb,var(--sc) 7%,transparent),transparent 55%);
  transition:background .15s ease;
}
.due:hover{background:color-mix(in srgb,var(--sc) 12%,transparent)}
.due:last-child{border-bottom:none}
.due.is-over{border-left-color:var(--warn)}
.due-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}
.due-main .note{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.tp{font-style:normal;font-size:11.5px;color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wc{font-size:11px;color:var(--warn);border:1px solid var(--warn);border-radius:8px;padding:1px 7px;white-space:nowrap;opacity:.9}
.due-tag{font-size:11.5px;color:var(--sub);white-space:nowrap}
.due-tag.over{color:var(--warn);font-weight:700}

/* ── 图表 ── */
.donut-wrap{position:relative;width:172px;height:172px;margin:6px auto 8px}
.donut{width:100%;height:100%;filter:drop-shadow(0 6px 18px rgba(91,124,250,.25))}
.donut-cap{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none}
.donut-cap b{font-size:30px;font-weight:800;font-variant-numeric:tabular-nums}
.donut-cap small{font-size:11px;color:var(--sub)}
.legend{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;font-size:12px;color:var(--sub);margin-top:8px}
.legend .lg{display:inline-flex;align-items:center;gap:5px}
.legend .lg b{color:var(--ink);margin-left:2px}
.legend i{width:9px;height:9px;border-radius:3px;display:inline-block}
.srow{display:flex;align-items:center;gap:10px;margin:9px 0;font-size:12.5px}
.slb{flex:0 0 46px;font-weight:700}
.stack{flex:1;height:13px;border-radius:7px;overflow:hidden;display:flex;gap:2px;background:var(--track)}
.stack i{display:block}
.stack.big{height:18px;border-radius:9px;margin:12px 0 16px}
.empty-seg{flex:1;background:var(--track)}
.snum{flex:0 0 26px;text-align:right;color:var(--sub);font-weight:700}
.brow{display:flex;align-items:center;gap:9px;margin:8px 0;font-size:12.5px}
.blb{flex:0 0 106px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--sub)}
.btrack{flex:1;height:11px;background:var(--track);border-radius:6px;overflow:hidden}
.btrack i{display:block;height:100%;border-radius:6px;width:0;transition:width .8s cubic-bezier(.2,.7,.2,1)}
.ready .btrack i{width:var(--w)}
.bnum{flex:0 0 46px;text-align:right;color:var(--ink);font-weight:700;font-variant-numeric:tabular-nums}
.bnum small{font-size:10.5px;margin-left:3px;color:var(--sub);font-weight:400}
.cols{display:flex;align-items:flex-end;gap:7px;height:136px;padding-top:16px}
.col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:3px}
.col i{
  display:block;width:64%;height:0;border-radius:6px 6px 3px 3px;min-height:4px;
  background:linear-gradient(180deg,var(--accent),color-mix(in srgb,var(--accent2) 70%,transparent));
  box-shadow:0 0 14px color-mix(in srgb,var(--accent) 45%,transparent);
  transition:height .8s cubic-bezier(.2,.7,.2,1);
}
.ready .col i{height:var(--h)}
.col.today i{background:linear-gradient(180deg,#ffab7a,var(--warn));box-shadow:0 0 18px color-mix(in srgb,var(--warn) 55%,transparent)}
.col .cv{font-size:10.5px;color:var(--sub);height:14px;font-variant-numeric:tabular-nums}
.col em{font-style:normal;font-size:10px;color:var(--sub);white-space:nowrap}
.col.today em{color:var(--warn);font-weight:700}
.spark{width:100%;height:auto}
.spark .sv{font-size:11px;fill:var(--sub);font-weight:700}
.spark .sl{font-size:10px;fill:var(--sub)}
.mastery{display:flex;align-items:baseline;gap:9px;margin-bottom:2px}
.mastery b{font-size:44px;font-weight:800;font-variant-numeric:tabular-nums}
.mastery span{color:var(--sub);font-size:12.5px}
.f-rows{display:flex;flex-direction:column;gap:7px;font-size:12.5px}
.f-row{display:flex;align-items:center;gap:8px}
.f-row b{margin-left:auto;font-variant-numeric:tabular-nums}
.f-row small{color:var(--sub);flex:0 0 42px;text-align:right;font-variant-numeric:tabular-nums}

/* ── 热力图 ── */
.heat-wrap{display:flex;gap:8px}
.hweeks{display:flex;flex-direction:column;gap:3px;font-size:9.5px;color:var(--sub);padding-top:20px}
.hweeks span{height:13px;line-height:13px;display:block}
.heat-main{flex:1;min-width:0}
.hlabels{display:flex;gap:3px;font-size:9.5px;color:var(--sub);margin-bottom:5px;font-weight:600}
.hlabels span{flex:1;text-align:left;white-space:nowrap;overflow:hidden}
.hgrid{display:flex;gap:3px}
.hcol{display:flex;flex-direction:column;gap:3px;flex:1}
.hcell{display:block;height:13px;border-radius:4px;background:var(--h0);transition:transform .12s ease}
.hcell:hover{transform:scale(1.28)}
.hcell.fut{background:transparent}
.hcell.lv0{background:var(--h0)}
.hcell.lv1{background:var(--h1)}
.hcell.lv2{background:var(--h2)}
.hcell.lv3{background:var(--h3)}
.hcell.lv4{background:var(--h4);box-shadow:0 0 10px color-mix(in srgb,var(--accent) 60%,transparent)}
.hlegend{display:flex;align-items:center;gap:3px;justify-content:flex-end;margin-top:8px;font-size:10.5px;color:var(--sub)}
.hlegend .hcell{width:13px;height:13px}
.hlegend span{margin:0 3px}

/* ── 表格 ── */
.tbl{width:100%;border-collapse:collapse;font-size:12.8px}
.tbl th{text-align:left;color:var(--sub);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap;font-size:11px;letter-spacing:.5px}
.tbl td{padding:8px;border-bottom:1px solid var(--line2);vertical-align:middle}
.tbl tr:last-child td{border-bottom:none}
.tbl tbody tr{transition:background .15s ease}
.tbl tbody tr:hover{background:color-mix(in srgb,var(--accent) 6%,transparent)}
.td-note{max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.td-tp{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--sub)}
.td-date{color:var(--sub);white-space:nowrap;font-variant-numeric:tabular-nums}
.rank{
  display:inline-flex;width:21px;height:21px;align-items:center;justify-content:center;
  border-radius:7px;background:var(--track);color:var(--sub);font-size:11px;font-weight:800;
}
.rank.gold{background:linear-gradient(135deg,#ffd257,#f5a623);color:#4a3300}
.rank.silver{background:linear-gradient(135deg,#dfe6f2,#aab8d0);color:#2a3446}
.rank.bronze{background:linear-gradient(135deg,#eab789,#cf8a52);color:#4a2f14}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
.wcbig{font-size:14px;color:var(--warn)}
.pill{font-size:11px;padding:2.5px 10px;border-radius:999px;white-space:nowrap;font-weight:600}
.p-未掌握{color:#ff8a5c;background:rgba(255,122,69,.14)}
.p-复习中{color:#7c93ff;background:rgba(124,147,255,.15)}
.p-已掌握{color:#2bd4a0;background:rgba(43,212,160,.14)}
html[data-theme="light"] .p-未掌握{color:#d9480f;background:rgba(232,89,12,.10)}
html[data-theme="light"] .p-复习中{color:#4263eb;background:rgba(76,110,245,.10)}
html[data-theme="light"] .p-已掌握{color:#087f5b;background:rgba(12,166,120,.10)}

/* ── 空状态 ── */
.empty-big{text-align:center;padding:60px 20px}
.empty-svg{width:120px;height:120px;margin-bottom:16px}
.empty-big h2{display:block;font-size:17.5px;margin-bottom:8px;color:var(--ink);letter-spacing:.2px}
.steps{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;margin-top:18px}
.step{
  background:color-mix(in srgb,var(--accent) 7%,transparent);border:1px solid var(--line);
  border-radius:14px;padding:15px 17px;font-size:12.5px;min-width:190px;text-align:left;
}
.step b{
  display:inline-flex;width:23px;height:23px;border-radius:8px;
  background:linear-gradient(135deg,var(--accent),var(--violet));color:#fff;
  align-items:center;justify-content:center;font-size:12px;margin-right:7px;
}
.step small{color:var(--sub)}

/* ── 页脚与响应式 ── */
.foot{color:var(--sub);font-size:11.5px;text-align:center;margin-top:28px;line-height:1.9;opacity:.85}
@media (max-width:1000px){
  .hero-grid{grid-template-columns:1fr}
  .kpis{grid-template-columns:repeat(3,1fr)}
  .g53,.g35,.g73,.g3{grid-template-columns:1fr}
  .snap{display:none}
}
@media (max-width:560px){
  body{padding:0 10px 40px}
  .kpis{grid-template-columns:repeat(2,1fr)}
  .brand{font-size:14.5px}
  .cd-num{font-size:42px}
}
@media print{
  .aurora,.topbar,.chips{display:none}
  body{background:#fff;color:#000;padding-top:16px}
  .panel,.kpi,.cd-card{box-shadow:none;border:1px solid #ddd;background:#fff;animation:none}
  .cd-num,.grad-t,.donut-cap b{color:inherit;-webkit-text-fill-color:inherit}
}
@supports not (backdrop-filter: blur(1px)){
  .panel,.kpi,.topbar{background:var(--card-solid)}
}
"""

_JS = """
(function(){
  var root=document.documentElement;
  var btn=document.getElementById('themeBtn');
  if(btn){btn.addEventListener('click',function(){
    var d=root.dataset.theme==='dark'?'light':'dark';
    root.dataset.theme=d;
    try{localStorage.setItem('ky-theme',d)}catch(e){}
  });}
  document.querySelectorAll('.chip').forEach(function(c){
    c.addEventListener('click',function(){
      document.querySelectorAll('.chip').forEach(function(x){x.classList.remove('on')});
      c.classList.add('on');
      var f=c.dataset.f;
      document.querySelectorAll('.due').forEach(function(it){
        it.style.display=(f==='all'||it.dataset.subject===f)?'':'none';
      });
    });
  });
  requestAnimationFrame(function(){requestAnimationFrame(function(){
    document.body.classList.add('ready');
  });});
  var els=document.querySelectorAll('.count');
  els.forEach(function(el){
    var n=parseInt(el.dataset.n||'0',10);
    if(!isFinite(n)||n>100000){el.textContent=n;return;}
    var s=null,dur=700;
    function tick(t){
      if(s===null)s=t;
      var p=Math.min(1,(t-s)/dur);
      el.textContent=Math.round(n*(1-Math.pow(1-p,3)));
      if(p<1)requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });
})();
"""


def render(d):
    total = d["total"]
    st = d["status_counts"]
    due = d["due"]
    exam_line = (f'{d["exam_date"]}（估算日期，改 个人配置.md 可更新）' if d["exam_date"]
                 else "初试日期未配置 · 去 个人配置.md 填一行")
    days_left = d["days_left"]
    if days_left is None:
        cd_num = "—"
        cd_unit = ""
    else:
        cd_num = f'<span class="count" data-n="{max(0, days_left)}">0</span>'
        cd_unit = "<small>天</small>"
    streak_txt = f"🔥 连续学习 {d['streak']} 天" if d["streak"] else "今天还没记录 · 从第一张错题开始"

    kpis = "".join([
        _kpi(total, "错题总数", f"掌握率 {d['mastery']:.0f}%"),
        _kpi(len(due), "今日到期", f"其中逾期 {d['overdue']} 道" if d["overdue"] else "都还没过期",
             "warn" if due else "ok"),
        _kpi(st["未掌握"], "未掌握", "等重做"),
        _kpi(st["复习中"], "复习中", f"今日已复习 {d['reviewed_today']} 道"),
        _kpi(st["已掌握"], "已掌握", f"平均复习 {d['avg_reviews']:.1f} 轮"),
        _kpi(d["week_new"], "本周新增", "周一起算"),
        _kpi(d["high3"], "高频错题", "错 ≥3 次"),
        _kpi(d["inbox"], "收件箱积压",
             f"待确认 {d['pending']} 张" if d["pending"] else ("待 AI 归档" if d["inbox"] else "干净"),
             "warn" if d["inbox"] else "ok"),
        _kpi(d["knowledge_items"], "知识库条目", "手册/速记累计"),
    ])

    if total:
        body = (
            '<div class="grid g53">'
            '<div class="panel">' + _icon("due") + '<h2>今日该重做 <span class="hint">点题名跳转 Obsidian</span></h2>'
            + _due_panel(due) + "</div>"
            '<div class="panel">' + _icon("load") + '<h2>未来两周复习负载 <span class="hint">每天到期数</span></h2>'
            + _cols(d["future"], today_idx=0) + "</div></div>"
            '<div class="grid g35">'
            '<div class="panel">' + _icon("target") + "<h2>学习进度</h2>" + _funnel(st, total, d["mastery"]) + "</div>"
            '<div class="panel">' + _icon("pie") + '<h2>科目分布 <span class="hint">环形 + 状态构成</span></h2>'
            + _donut(d["subject_counts"], total, "道错题")
            + '<div style="margin-top:14px">' + _stack_rows(d["subject_status"]) + "</div></div></div>"
            '<div class="grid g73">'
            '<div class="panel">' + _icon("heat") + '<h2>学习活动热力图 <span class="hint">近 16 周 · 每日新增错题</span></h2>'
            + _heatmap(d["heatmap"], d["today"]) + "</div>"
            '<div class="panel">' + _icon("trend") + '<h2>近 8 周新增 <span class="hint">每周错题量</span></h2>'
            + _sparkline(d["week_trend"]) + "</div></div>"
            '<div class="grid g3">'
            '<div class="panel">' + _icon("alert") + "<h2>错因分布</h2>" + _bars(d["error_counts"], _ERROR_COLORS) + "</div>"
            '<div class="panel">' + _icon("book") + "<h2>哪本书错得最多</h2>" + _bars(d["book_counts"]) + "</div>"
            '<div class="panel">' + _icon("brain") + "<h2>知识点 Top 10</h2>" + _bars(d["topic_counts"]) + "</div></div>"
            '<div class="grid g53">'
            '<div class="panel">' + _icon("trophy") + '<h2>高频错题榜 <span class="hint">点击题名跳转</span></h2>'
            + _high_table(d["high"]) + "</div>"
            '<div class="panel">' + _icon("clock") + "<h2>最近录入</h2>" + _recent_table(d["recent"]) + "</div></div>")
    else:
        body = _empty_state()

    head_theme = (
        "<script>(function(){try{var t=localStorage.getItem('ky-theme')||"
        "(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');"
        "document.documentElement.dataset.theme=t}catch(e){}})();</script>"
    )
    brand_svg = (
        '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
        '<defs><linearGradient id="bg1" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#6e8bff"/><stop offset="1" stop-color="#b487ff"/></linearGradient></defs>'
        '<rect x="3" y="4" width="13" height="17" rx="2.5" stroke="url(#bg1)" stroke-width="1.8"/>'
        '<path d="M7 8.5h5M7 12h5M7 15.5h3" stroke="url(#bg1)" stroke-width="1.8" stroke-linecap="round"/>'
        '<circle cx="16.5" cy="16.5" r="4.5" stroke="url(#bg1)" stroke-width="1.8"/>'
        '<path d="M14.6 16.5l1.4 1.4 2.6-2.9" stroke="url(#bg1)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )
    sun = '<svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4.4"/><path d="M12 2.5v2.4M12 19.1v2.4M2.5 12h2.4M19.1 12h2.4M5 5l1.7 1.7M17.3 17.3 19 19M19 5l-1.7 1.7M6.7 17.3 5 19"/></svg>'
    moon = '<svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13.5A8.5 8.5 0 1 1 10.5 4 6.8 6.8 0 0 0 20 13.5Z"/></svg>'
    return ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light dark">'
            "<title>考研错题工作台</title>" + head_theme +
            "<style>" + _CSS + "</style></head><body>"
            '<div class="aurora"><i class="a1"></i><i class="a2"></i><i class="a3"></i></div>'
            '<div class="wrap">'
            '<nav class="topbar">'
            f'<div class="brand">{brand_svg}考研错题工作台</div>'
            f'<div class="snap">星期{d["weekday"]} · {d["today"]} · 数据快照 {d["generated_at"]}<br>'
            "库维护.py dashboard 生成 · 归档后自动更新</div>"
            f'<button class="tbtn" id="themeBtn" title="切换深浅色">{sun}{moon} 主题</button></nav>'
            '<section class="hero-grid">'
            '<div class="cd-card">'
            '<div class="cd-label">距 初 试</div>'
            f'<div class="cd-num">{cd_num}{cd_unit}</div>'
            f'<div class="cd-date">{html.escape(exam_line)}</div>'
            f'<div class="cd-foot">{streak_txt}</div></div>'
            f'<div class="kpis">{kpis}</div></section>'
            "<main>" + body + "</main>"
            '<div class="foot">数据全部来自本地错题笔记（错题/ 目录）· 说「刷新工作台」重新生成 · F5 看最新<br>'
            "复习间隔由 FSRS-4.5 按各题历史计算 · 状态以笔记文件现值为准</div>"
            "</div><script>" + _JS + "</script></body></html>")