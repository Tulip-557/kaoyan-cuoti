#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作台渲染器 v4：按"轻重缓急"分三个视图的单文件 HTML 仪表盘。

信息架构：
  今日（行动层）——今天该重做的题（按 逾期>高频>到期 排序）、警报摘要、
                  未来 7 天负载、状态环；打开页面默认落在这一页。
  复盘（分析层）——掌握率、科目构成、热力图、周趋势、错因/书籍/知识点分布。
  题库（记录层）——高频错题榜、最近录入。

视觉：Linear/Vercel 式高级暗色 + 玻璃拟态 + 极光背景；零依赖、零 CDN。
数据由 库维护.py 的 dashboard 子命令准备；本模块只负责"长什么样"。
"""
import datetime as dt
import html

SUBJ_COLORS = {"数学": "#0A84FF", "英语": "#30D158", "政治": "#FF9F0A", "专业课": "#BF5AF2"}
SUBJ_ORDER = ["数学", "英语", "政治", "专业课", "其它"]
STATUS_COLORS = {"未掌握": "#FF453A", "复习中": "#0A84FF", "已掌握": "#30D158"}
_ERROR_COLORS = {"概念不清": "#0A84FF", "条件误用": "#30D158", "公式记错": "#FF9F0A",
                 "计算失误": "#BF5AF2", "思路不会": "#FF453A", "审题失误": "#64D2FF",
                 "知识盲区": "#FF9F0A", "表达问题": "#5E5CE6", "时间不够": "#8E8E93",
                 "待确认": "#8E8E93", "（空）": "#8E8E93"}

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
    "flame": '<path d="M12 3s5 4.5 5 9a5 5 0 0 1-10 0c0-2 1-3.5 2-4.5 0 1.5 1 2.5 2 2.5-1-2.5 0-5.5 1-7Z"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13l3.5 7v5a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-5Z"/>',
    "ring": '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 9 9"/><circle cx="12" cy="12" r="4"/>',
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


def _ring(dist, colors, total, cap):
    """通用环形图：dist=[(label,count)]，colors={label:hex}。"""
    if not dist or not total:
        return '<div class="muted">暂无数据</div>'
    segs, acc = [], 0.0
    gap = 1.0
    for label, count in dist:
        pct = count / total * 100
        color = colors.get(label, "#8a94a6")
        segs.append(
            f'<circle cx="21" cy="21" r="15.9155" fill="none" stroke="{color}" stroke-width="7" '
            f'pathLength="100" stroke-linecap="round" '
            f'stroke-dasharray="{max(0.5, pct - gap):.2f} {100 - max(0.5, pct - gap):.2f}" '
            f'stroke-dashoffset="{-acc - gap / 2:.2f}" transform="rotate(-90 21 21)">'
            f'<title>{html.escape(str(label))} · {count}</title></circle>')
        acc += pct
    legend = "".join(
        f'<span class="lg"><i style="background:{colors.get(l, "#8a94a6")}"></i>'
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
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="var(--card-solid)" stroke="var(--accent)" stroke-width="2"/>'
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
        for dd in range(7):
            day = week_start + dt.timedelta(days=dd)
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


def _priority_due(due):
    """轻重缓急排序：逾期最久 > 错过次数多 > 到期早。"""
    return sorted(due, key=lambda x: (-x["overdue"], -x["wrong_count"], x["due"]))


def _due_items(due, top=False):
    """生成清单条目；top=True 时仅组内第一题加"最优先"高亮。"""
    items = []
    for i, x in enumerate(due):
        color = SUBJ_COLORS.get(x["subject"], "#8a94a6")
        if x["overdue"] > 0:
            due_tag = f'<span class="due-tag over">逾期 {x["overdue"]} 天</span>'
        else:
            due_tag = '<span class="due-tag">今天</span>'
        wc = (f'<span class="wc" title="累计做错 {x["wrong_count"]} 次">×{x["wrong_count"]}</span>'
              if x["wrong_count"] else "")
        hot = '<span class="wc hot" title="高频错题（错 ≥3 次）">高频</span>' if x["wrong_count"] >= 3 else ""
        over_cls = " is-over" if x["overdue"] > 0 else ""
        top_cls = " top1" if (top and i == 0) else ""
        items.append(
            f'<div class="due{over_cls}{top_cls}" data-subject="{html.escape(x["subject"])}" style="--sc:{color}">'
            f'<span class="rank-mini">{i + 1}</span>'
            f'<span class="due-main">{_obsidian(x["file"], x["stem"])}'
            f'<em class="tp">{html.escape(x["topic"])}</em></span>'
            f'{hot}{wc}{due_tag}</div>')
    return "".join(items)


def _due_panel(due):
    """今日该重做：逾期/今天 分组 + 优先级排序 + 科目筛选。"""
    due = _priority_due(due)
    chips = ['<button class="chip on" data-f="all">全部 ' + str(len(due)) + "</button>"]
    counts = {}
    for x in due:
        counts[x["subject"]] = counts.get(x["subject"], 0) + 1
    for subj, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        color = SUBJ_COLORS.get(subj, "#8a94a6")
        chips.append(f'<button class="chip" data-f="{html.escape(subj)}">'
                     f'<i style="background:{color}"></i>{html.escape(subj)} {c}</button>')
    overs = [x for x in due if x["overdue"] > 0]
    today = [x for x in due if x["overdue"] == 0]
    body = ""
    if overs:
        body += f'<div class="grp g-over">{_icon("alert")}逾期 · {len(overs)} 道，先清这些</div>' + _due_items(overs, top=True)
    if today:
        body += f'<div class="grp">{_icon("clock")}今天到期 · {len(today)} 道</div>' + _due_items(today)
    if not overs and not today:
        body = ""
    if due:
        return f'<div class="chips">{"".join(chips)}</div><div class="due-list">{body}</div>'
    return ""


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


def _stat_chip(icon, num, label, tone=""):
    tone_cls = f" t-{tone}" if tone else ""
    return (f'<div class="schip"><div class="schip-n count{tone_cls}" data-n="{num}">0</div>'
            f'<div class="schip-l">{icon}{html.escape(label)}</div></div>')


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
/* ───────── Apple 风格 · 玻璃质感 ───────── */
:root{
  --card:rgba(30,30,34,.55); --card-solid:#1e1e22; --card2:rgba(44,44,48,.55);
  --ink:#f5f5f7; --sub:#98989f;
  --line:rgba(255,255,255,.12); --line2:rgba(255,255,255,.07);
  --accent:#0A84FF; --violet:#BF5AF2; --warn:#FF9F0A; --danger:#FF453A; --ok:#30D158;
  --track:rgba(120,120,128,.26);
  --blur:blur(40px) saturate(180%);
  --shadow:0 .5px 0 rgba(255,255,255,.14) inset, 0 2px 8px rgba(0,0,0,.26), 0 24px 48px rgba(0,0,0,.38);
  --h0:rgba(120,120,128,.16); --h1:rgba(10,132,255,.30); --h2:rgba(10,132,255,.55);
  --h3:#0A84FF; --h4:#BF5AF2;
  --r:22px;
}
html[data-theme="light"]{
  --card:rgba(255,255,255,.60); --card-solid:#ffffff; --card2:rgba(255,255,255,.75);
  --ink:#1d1d1f; --sub:#86868b;
  --line:rgba(0,0,0,.09); --line2:rgba(0,0,0,.05);
  --accent:#007AFF; --violet:#AF52DE; --warn:#FF9500; --danger:#FF3B30; --ok:#34C759;
  --track:rgba(120,120,128,.18);
  --blur:blur(40px) saturate(160%);
  --shadow:0 .5px 0 rgba(255,255,255,.9) inset, 0 2px 6px rgba(29,29,31,.06), 0 22px 44px rgba(29,29,31,.13);
  --h0:rgba(120,120,128,.12); --h1:rgba(0,122,255,.22); --h2:rgba(0,122,255,.42);
  --h3:#007AFF; --h4:#AF52DE;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","PingFang SC","Segoe UI","Microsoft YaHei",sans-serif;
  color:var(--ink);padding:0 18px 60px;line-height:1.5;background:#0d0d12;min-height:100vh;overflow-x:hidden;
  transition:color .3s ease;
  font-feature-settings:"tnum";
}
/* 壁纸 + 极光 + 颗粒 */
.wallpaper{position:fixed;inset:0;z-index:-3;background:linear-gradient(155deg,#101b3c 0%,#242050 28%,#472063 54%,#2a1a46 78%,#16122a 100%);transition:background .4s ease}
html[data-theme="light"] .wallpaper{background:linear-gradient(155deg,#cfe3ff 0%,#e4d9f8 30%,#f7dfe9 56%,#dde8ff 100%)}
.aurora{position:fixed;inset:0;z-index:-2;overflow:hidden;pointer-events:none}
.aurora i{position:absolute;border-radius:50%;filter:blur(100px);opacity:.42}
html[data-theme="light"] .aurora i{opacity:.5;filter:blur(90px)}
.aurora .a1{width:680px;height:680px;left:-200px;top:-240px;background:radial-gradient(circle,rgba(10,132,255,.5),transparent 65%);animation:drift1 28s ease-in-out infinite alternate}
.aurora .a2{width:600px;height:600px;right:-180px;top:-140px;background:radial-gradient(circle,rgba(191,90,242,.42),transparent 65%);animation:drift2 34s ease-in-out infinite alternate}
.aurora .a3{width:640px;height:640px;left:33%;bottom:-320px;background:radial-gradient(circle,rgba(255,159,10,.28),transparent 62%);animation:drift1 40s ease-in-out infinite alternate-reverse}
.grain{position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.05;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.55'/%3E%3C/svg%3E")}
@keyframes drift1{from{transform:translate(0,0) scale(1)}to{transform:translate(70px,50px) scale(1.12)}}
@keyframes drift2{from{transform:translate(0,0) scale(1.05)}to{transform:translate(-60px,70px) scale(.95)}}
@media (prefers-reduced-motion: reduce){.aurora i{animation:none}}

.wrap{max-width:1160px;margin:0 auto}

/* ── macOS 工具栏 ── */
.topbar{
  position:sticky;top:10px;z-index:50;margin:14px -6px 18px;padding:10px 16px;
  display:flex;align-items:center;gap:12px;border-radius:20px;
  background:var(--card);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);
  border:.5px solid var(--line);box-shadow:var(--shadow);
}
.lights{display:flex;gap:8px;margin-right:2px;flex:none}
.lights i{width:12.5px;height:12.5px;border-radius:50%;box-shadow:inset 0 0 0 .5px rgba(0,0,0,.18)}
.l-r{background:#FF5F57}.l-y{background:#FEBC2E}.l-g{background:#28C840}
.brand{display:flex;align-items:center;gap:9px;font-size:15px;font-weight:700;letter-spacing:.2px;white-space:nowrap}
.brand svg{width:23px;height:23px;flex:none}
.tchips{display:flex;gap:7px;margin-left:4px}
.tchip{
  display:inline-flex;align-items:center;gap:5px;font-size:12px;padding:5px 12px;border-radius:999px;
  border:.5px solid var(--line);background:var(--card2);color:var(--sub);white-space:nowrap;font-weight:500;
}
.tchip b{color:var(--ink);font-variant-numeric:tabular-nums}
.tchip.fire{color:var(--ink)}
/* 分段控件 */
.seg{
  position:relative;display:flex;gap:2px;margin-left:auto;padding:2.5px;border-radius:13px;
  background:var(--track);backdrop-filter:blur(6px);flex:none;
}
.seg .thumb{
  position:absolute;top:2.5px;bottom:2.5px;left:0;width:60px;border-radius:10.5px;
  background:var(--card-solid);
  box-shadow:0 2px 8px rgba(0,0,0,.22), 0 .5px 0 rgba(255,255,255,.22) inset;
  transition:left .28s cubic-bezier(.32,.72,.24,1), width .28s cubic-bezier(.32,.72,.24,1);
}
html[data-theme="light"] .seg .thumb{box-shadow:0 2px 8px rgba(29,29,31,.14), 0 .5px 0 rgba(255,255,255,.9) inset}
.tab{
  position:relative;z-index:1;border:none;background:transparent;color:var(--sub);font-size:13px;font-weight:600;
  padding:6px 16px;border-radius:10.5px;cursor:pointer;transition:color .2s ease;white-space:nowrap;
  font-family:inherit;
}
.tab:hover{color:var(--ink)}
.tab.on{color:var(--accent)}
.tab .badge{
  display:inline-block;margin-left:5px;min-width:17px;padding:0 5px;border-radius:9px;
  background:var(--danger);color:#fff;font-size:10px;line-height:15px;text-align:center;font-weight:700;
}
.tbtn{
  border:.5px solid var(--line);background:var(--card2);color:var(--ink);border-radius:12px;
  padding:7px 11px;cursor:pointer;display:flex;align-items:center;gap:6px;flex:none;
  transition:transform .15s ease,background .2s ease;white-space:nowrap;
}
.tbtn:hover{background:var(--card-solid)}
.tbtn:active{transform:scale(.94)}
.tbtn svg{width:15px;height:15px}
html[data-theme="dark"] .icon-sun{display:none}
html[data-theme="light"] .icon-moon{display:none}

/* ── 视图 ── */
.view{display:none}
.view.on{display:block;animation:rise .45s cubic-bezier(.25,.8,.25,1)}
@media (prefers-reduced-motion: reduce){.view.on{animation:none}}

/* ── 玻璃卡片 ── */
.panel,.schip,.hero-card{
  background:var(--card);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);
  border:.5px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);
  animation:rise .5s cubic-bezier(.25,.8,.25,1) backwards;
}
.panel{padding:18px 20px;min-width:0}
@keyframes rise{from{opacity:0;transform:translateY(16px) scale(.99)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion: reduce){.panel,.schip,.hero-card,.flip{animation:none}}
.panel h2{
  font-size:13px;font-weight:700;letter-spacing:.2px;margin-bottom:14px;
  display:flex;align-items:center;gap:8px;color:var(--sub);
}
.panel h2 .picon{width:17px;height:17px;stroke:var(--accent);fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;flex:none}
.panel h2 .hint{font-size:11px;font-weight:500;margin-left:auto;opacity:.8}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.muted{color:var(--sub);font-size:13px}
.grad-t{background:linear-gradient(120deg,var(--accent),var(--violet));-webkit-background-clip:text;background-clip:text;color:transparent}

/* ── 版式 ── */
.grid{display:grid;gap:16px;margin-bottom:16px}
.g21{grid-template-columns:2fr 1fr}
.g35{grid-template-columns:3fr 5fr}
.g73{grid-template-columns:7fr 5fr}
.g3{grid-template-columns:1fr 1fr 1fr}

/* ── 倒计时横幅（iOS 渐变小组件） ── */
.cd-banner{
  position:relative;border-radius:var(--r);margin-bottom:16px;padding:24px 30px 20px;overflow:hidden;
  background:linear-gradient(135deg,#0A84FF 0%,#5E5CE6 55%,#BF5AF2 100%);
  color:#fff;box-shadow:0 24px 55px rgba(94,92,230,.42);
}
.cd-banner::before{content:"";position:absolute;right:-60px;top:-80px;width:260px;height:260px;border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.2),transparent 60%)}
.cd-banner::after{content:"";position:absolute;left:-70px;bottom:-110px;width:240px;height:240px;border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.12),transparent 62%)}
.cd-row{display:flex;align-items:center;gap:30px;flex-wrap:wrap;position:relative;z-index:1}
.cd-kicker{font-size:10.5px;letter-spacing:3px;opacity:.85;margin-bottom:8px;font-weight:700}
.cd-digits{display:flex;align-items:center;gap:7px}
.flip{
  display:inline-flex;align-items:center;justify-content:center;
  width:.64em;height:1.06em;font-size:80px;font-weight:800;
  background:linear-gradient(180deg,#3a3a3e 0%,#2a2a2e 47%,#242428 53%,#1c1c20 100%);
  border-radius:.09em;position:relative;font-variant-numeric:tabular-nums;color:#fff;
  box-shadow:0 8px 22px rgba(0,0,0,.4), 0 .5px 0 rgba(255,255,255,.22) inset;
  animation:flipin .65s cubic-bezier(.25,.8,.25,1) backwards;
}
.flip::before{content:"";position:absolute;left:5%;right:5%;top:calc(50% - 1px);height:2px;background:rgba(0,0,0,.5);z-index:1}
@keyframes flipin{from{transform:rotateX(-92deg);opacity:0}62%{transform:rotateX(14deg);opacity:1}to{transform:none}}
.cd-unit{font-size:22px;font-weight:700;opacity:.95;margin-left:4px}
.cd-info{margin-left:auto;text-align:right}
.cd-date{font-size:17px;font-weight:800;letter-spacing:.3px}
.cd-wd{font-size:12px;font-weight:600;opacity:.95;margin-left:8px;padding:2px 10px;border-radius:999px;background:rgba(255,255,255,.22)}
.cd-sub{font-size:11.5px;opacity:.8;margin-top:5px}
.cd-equiv{font-size:13px;opacity:.96;margin-top:8px}
.cd-equiv b{font-size:16px;font-weight:800}
.ms-track{display:flex;gap:8px;margin-top:18px;flex-wrap:wrap;position:relative;z-index:1}
.ms{font-size:11.5px;padding:4.5px 12px;border-radius:999px;background:rgba(255,255,255,.16);font-variant-numeric:tabular-nums;font-weight:500}
.ms.past{opacity:.5}
.ms.fut{opacity:.8}
.ms.on{background:rgba(255,255,255,.96);color:#0A84FF;font-weight:800;box-shadow:0 4px 16px rgba(0,0,0,.25)}
.ms-gap{margin-left:7px;opacity:.75;font-weight:600}
.cd-empty{font-size:14px;text-align:center;padding:16px 0;opacity:.92}

/* ── 今日：行动卡 ── */
.hero-card{padding:20px 24px;margin-bottom:16px;display:flex;align-items:center;gap:22px;flex-wrap:wrap}
.hero-num b{font-size:42px;font-weight:800;line-height:1;font-variant-numeric:tabular-nums;color:var(--accent)}
.hero-num span{font-size:12px;color:var(--sub);margin-top:4px}
.hero-mid{display:flex;gap:22px;flex-wrap:wrap;flex:1}
.hero-item{display:flex;flex-direction:column;gap:2px}
.hero-item b{font-size:21px;font-weight:800;font-variant-numeric:tabular-nums}
.hero-item span{font-size:11.5px;color:var(--sub)}
.hero-item.warn b{color:var(--danger)}
.hero-item.ok b{color:var(--ok)}
.hero-tip{font-size:12px;color:var(--sub);border-left:2px solid var(--line);padding-left:14px;max-width:270px;line-height:1.7}
.hero-tip b{color:var(--ink)}

/* ── 清单 ── */
.chips{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:12px}
.chip{
  display:inline-flex;align-items:center;gap:6px;border:.5px solid var(--line);background:var(--card2);
  color:var(--sub);border-radius:999px;padding:4.5px 13px;font-size:12px;cursor:pointer;
  transition:all .16s ease;font-family:inherit;font-weight:500;
}
.chip i{width:7px;height:7px;border-radius:50%;display:inline-block}
.chip:hover{color:var(--ink)}
.chip.on{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.due-list{display:flex;flex-direction:column;max-height:520px;overflow-y:auto;padding-right:6px;scrollbar-width:thin}
.due-list::-webkit-scrollbar{width:7px}
.due-list::-webkit-scrollbar-thumb{background:var(--track);border-radius:4px}
.grp{display:flex;align-items:center;gap:7px;font-size:11.5px;font-weight:700;color:var(--sub);margin:10px 0 6px}
.grp:first-child{margin-top:0}
.grp .picon{width:14px;height:14px;stroke:var(--sub);fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.grp.g-over{color:var(--danger)}
.grp.g-over .picon{stroke:var(--danger)}
.due{
  display:flex;align-items:center;gap:10px;padding:10px 12px;margin:3px 0;border-radius:14px;
  font-size:13.5px;border-left:3px solid var(--sc);background:var(--card2);
  transition:background .15s ease, transform .15s ease;
}
.due:hover{transform:translateX(2px)}
.due.is-over{border-left-color:var(--danger)}
.due.top1{box-shadow:0 0 0 1.5px color-mix(in srgb,var(--accent) 60%,transparent)}
.rank-mini{flex:none;width:22px;height:22px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;background:var(--track);color:var(--sub);font-size:11px;font-weight:800}
.due.top1 .rank-mini{background:linear-gradient(135deg,var(--accent),var(--violet));color:#fff}
.due-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}
.due-main .note{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.tp{font-style:normal;font-size:11.5px;color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wc{font-size:11px;color:var(--warn);border:1px solid var(--warn);border-radius:999px;padding:1px 8px;white-space:nowrap;font-weight:600}
.wc.hot{background:var(--danger);color:#fff;border-color:var(--danger)}
.due-tag{font-size:11.5px;color:var(--sub);white-space:nowrap}
.due-tag.over{color:var(--danger);font-weight:700}
.zero-state{color:var(--sub);font-size:13.5px;padding:34px 0;text-align:center}

/* ── 侧栏 ── */
.side{display:flex;flex-direction:column;gap:16px}
.mini-stats{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.schip{padding:13px 15px;border-radius:16px}
.schip-n{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums}
.schip-n.t-warn{color:var(--warn)}
.schip-n.t-ok{color:var(--ok)}
.schip-l{font-size:11.5px;color:var(--sub);margin-top:2px;display:flex;align-items:center;gap:5px}
.schip-l .picon{width:13px;height:13px;stroke:var(--sub);fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}

/* ── 图表 ── */
.donut-wrap{position:relative;width:158px;height:158px;margin:6px auto 8px}
.donut{width:100%;height:100%;filter:drop-shadow(0 8px 20px rgba(10,132,255,.28))}
.donut-cap{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none}
.donut-cap b{font-size:28px;font-weight:800;font-variant-numeric:tabular-nums}
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
.btrack i{display:block;height:100%;border-radius:6px;width:0;transition:width .8s cubic-bezier(.25,.8,.25,1)}
.ready .btrack i{width:var(--w)}
.bnum{flex:0 0 46px;text-align:right;font-weight:700;font-variant-numeric:tabular-nums}
.bnum small{font-size:10.5px;margin-left:3px;color:var(--sub);font-weight:500}
.cols{display:flex;align-items:flex-end;gap:7px;height:136px;padding-top:16px}
.col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:3px}
.col i{
  display:block;width:64%;height:0;border-radius:6px 6px 4px 4px;min-height:4px;
  background:linear-gradient(180deg,#409CFF,var(--accent));
  transition:height .8s cubic-bezier(.25,.8,.25,1);
}
.ready .col i{height:var(--h)}
.col.today i{background:linear-gradient(180deg,#FFB340,var(--warn))}
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
.stat-strip{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:16px}

/* ── 热力图 ── */
.heat-wrap{display:flex;gap:8px}
.hweeks{display:flex;flex-direction:column;gap:3px;font-size:9.5px;color:var(--sub);padding-top:20px}
.hweeks span{height:13px;line-height:13px;display:block}
.heat-main{flex:1;min-width:0}
.hlabels{display:flex;gap:3px;font-size:9.5px;color:var(--sub);margin-bottom:5px;font-weight:600}
.hlabels span{flex:1;text-align:left;white-space:nowrap;overflow:hidden}
.hgrid{display:flex;gap:3px}
.hcol{display:flex;flex-direction:column;gap:3px;flex:1}
.hcell{display:block;height:13px;border-radius:4.5px;background:var(--h0);transition:transform .12s ease}
.hcell:hover{transform:scale(1.3)}
.hcell.fut{background:transparent}
.hcell.lv0{background:var(--h0)}
.hcell.lv1{background:var(--h1)}
.hcell.lv2{background:var(--h2)}
.hcell.lv3{background:var(--h3)}
.hcell.lv4{background:var(--h4);box-shadow:0 0 10px rgba(191,90,242,.45)}
.hlegend{display:flex;align-items:center;gap:3px;justify-content:flex-end;margin-top:8px;font-size:10.5px;color:var(--sub)}
.hlegend .hcell{width:13px;height:13px}
.hlegend span{margin:0 3px}

/* ── 表格 ── */
.tbl{width:100%;border-collapse:collapse;font-size:12.8px}
.tbl th{text-align:left;color:var(--sub);font-weight:600;padding:6px 8px;border-bottom:.5px solid var(--line);white-space:nowrap;font-size:11px}
.tbl td{padding:8px;border-bottom:.5px solid var(--line2);vertical-align:middle}
.tbl tr:last-child td{border-bottom:none}
.tbl tbody tr{transition:background .15s ease}
.tbl tbody tr:hover{background:var(--card2)}
.td-note{max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.td-tp{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--sub)}
.td-date{color:var(--sub);white-space:nowrap;font-variant-numeric:tabular-nums}
.rank{display:inline-flex;width:21px;height:21px;align-items:center;justify-content:center;border-radius:7px;background:var(--track);color:var(--sub);font-size:11px;font-weight:800}
.rank.gold{background:linear-gradient(135deg,#FFD60A,#FF9F0A);color:#4a3300}
.rank.silver{background:linear-gradient(135deg,#e5e7ee,#b9c1d4);color:#2a3446}
.rank.bronze{background:linear-gradient(135deg,#f0c393,#d29a63);color:#4a2f14}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
.wcbig{font-size:14px;color:var(--danger);font-weight:800}
.pill{font-size:11px;padding:2.5px 11px;border-radius:999px;white-space:nowrap;font-weight:600}
.p-未掌握{color:#FF6B60;background:rgba(255,69,58,.15)}
.p-复习中{color:#4A9EFF;background:rgba(10,132,255,.15)}
.p-已掌握{color:#3BDD73;background:rgba(48,209,88,.15)}
html[data-theme="light"] .p-未掌握{color:#E0342A;background:rgba(255,59,48,.10)}
html[data-theme="light"] .p-复习中{color:#0071E3;background:rgba(0,122,255,.10)}
html[data-theme="light"] .p-已掌握{color:#248A3D;background:rgba(52,199,89,.12)}

/* ── 空状态 ── */
.empty-big{text-align:center;padding:60px 20px}
.empty-svg{width:120px;height:120px;margin-bottom:16px}
.empty-big h2{display:block;font-size:17.5px;margin-bottom:8px;letter-spacing:.2px}
.steps{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;margin-top:18px}
.step{background:var(--card2);border:.5px solid var(--line);border-radius:16px;padding:15px 17px;font-size:12.5px;min-width:190px;text-align:left}
.step b{display:inline-flex;width:23px;height:23px;border-radius:8px;background:linear-gradient(135deg,var(--accent),var(--violet));color:#fff;align-items:center;justify-content:center;font-size:12px;margin-right:7px}
.step small{color:var(--sub)}

.foot{color:var(--sub);font-size:11.5px;text-align:center;margin-top:28px;line-height:1.9;opacity:.9}
@media (max-width:1000px){
  .g21,.g35,.g73,.g3{grid-template-columns:1fr}
  .stat-strip{grid-template-columns:repeat(3,1fr)}
  .tchips{display:none}
  .hero-tip{display:none}
}
@media (max-width:620px){
  body{padding:0 10px 40px}
  .stat-strip{grid-template-columns:repeat(2,1fr)}
  .brand{font-size:13px}
  .lights{display:none}
  .tab{padding:6px 11px;font-size:12px}
  .hero-num b{font-size:34px}
  .seg{margin-left:8px}
  .flip{font-size:54px}
  .cd-info{margin-left:0;text-align:left}
  .cd-row{gap:16px}
}
@media print{
  .wallpaper,.aurora,.grain,.topbar,.chips{display:none}
  .view{display:none!important}
  .view.on{display:block!important}
  body{background:#fff;color:#000;padding-top:16px}
  .panel,.schip,.hero-card,.cd-banner{box-shadow:none;border:1px solid #ddd;background:#fff;animation:none;color:#000}
  .grad-t,.donut-cap b{color:inherit;-webkit-text-fill-color:inherit}
}
@supports not (backdrop-filter: blur(1px)){
  .panel,.schip,.hero-card,.topbar,.seg{background:var(--card-solid)}
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
  /* 分段控件（iOS 风格滑块） */
  var thumb=document.querySelector('.seg .thumb');
  function moveThumb(){
    var on=document.querySelector('.seg .tab.on');
    if(!on||!thumb)return;
    thumb.style.left=on.offsetLeft+'px';
    thumb.style.width=on.offsetWidth+'px';
  }
  var tabs=document.querySelectorAll('.seg .tab');
  function show(v){
    tabs.forEach(function(t){t.classList.toggle('on',t.dataset.v===v)});
    document.querySelectorAll('.view').forEach(function(x){x.classList.toggle('on',x.id==='v-'+v)});
    try{history.replaceState(null,'','#'+v)}catch(e){}
    moveThumb();
    window.scrollTo({top:0});
  }
  tabs.forEach(function(t){t.addEventListener('click',function(){show(t.dataset.v)})});
  var h=(location.hash||'').replace('#','');
  show(document.getElementById('v-'+h)?h:'today');
  window.addEventListener('resize',moveThumb);
  setTimeout(moveThumb,120);
  /* 清单按科目筛选 */
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


def _countdown_banner(d):
    """今日视图顶部：大号翻牌钟倒计时 + 里程碑轨道。"""
    days, exam = d["days_left"], d["exam_date"]
    if days is None or exam is None:
        return ('<div class="cd-banner"><div class="cd-empty">⏳ 去 个人配置.md 填一行「初试日期」——'
                "这里会变成大号倒计时翻牌钟</div></div>")
    days = max(0, days)
    wd = "一二三四五六日"[dt.date.fromisoformat(exam).weekday()]
    digits = "".join(
        f'<span class="flip" style="animation-delay:{0.1 + 0.12 * i:.2f}s">{ch}</span>'
        for i, ch in enumerate(str(days)))
    weeks, rdays = divmod(days, 7)
    months = round(days / 30.44)
    ms = [500, 400, 300, 200, 100, 50, 30]
    nxt = max((m for m in ms if m <= days), default=None)
    chips = []
    for m in ms:
        if m > days:
            chips.append(f'<span class="ms past">✓ {m}</span>')
        elif m == nxt:
            gap = days - m
            chips.append(f'<span class="ms on">● {m} 天<span class="ms-gap">'
                         f'{"今天！" if gap == 0 else f"还有 {gap} 天"}</span></span>')
        else:
            chips.append(f'<span class="ms fut">{m}</span>')
    return (
        '<div class="cd-banner">'
        '<div class="cd-row">'
        '<div class="cd-left"><div class="cd-kicker">DISTANCE TO GOAL · 距初试</div>'
        f'<div class="cd-digits">{digits}<span class="cd-unit">天</span></div></div>'
        '<div class="cd-info">'
        f'<div class="cd-date">{exam}<span class="cd-wd">周{wd}</span></div>'
        '<div class="cd-sub">暂按往年规律估算 · 官方公布后改 个人配置.md 一行即可</div>'
        f'<div class="cd-equiv">≈ <b>{months}</b> 个月 · <b>{weeks}</b> 周 <b>+{rdays}</b> 天</div>'
        "</div></div>"
        f'<div class="ms-track">{"".join(chips)}</div>'
        "</div>")


def _view_today(d):
    due = _priority_due(d["due"])
    st = d["status_counts"]
    total = d["total"]
    overdue = d["overdue"]
    inbox, pending = d["inbox"], d["pending"]

    # 行动头条
    if due:
        num_html = f'<b class="count" data-n="{len(due)}">0</b><span>今天该重做</span>'
        mid = [
            f'<div class="hero-item{" warn" if overdue else ""}"><b class="count" data-n="{overdue}">0</b><span>逾期</span></div>',
            f'<div class="hero-item{" warn" if inbox else " ok"}"><b class="count" data-n="{inbox}">0</b><span>收件箱待处理</span></div>',
            f'<div class="hero-item"><b class="count" data-n="{d["reviewed_today"]}">0</b><span>今日已复习</span></div>',
            f'<div class="hero-item"><b class="count" data-n="{d["streak"]}">0</b><span>连续学习（天）</span></div>',
        ]
        tip = ('<b>从 ① 号开始做</b>——清单已按"逾期最久 → 错过最多 → 到期最早"排好。'
               '做完把结果告诉 AI（或拍照回传），状态与下次日期自动更新。')
    else:
        nxt = next((f for f in d["future"] if f["count"] > 0), None)
        if nxt:
            num_html = f'<b class="grad-t">0</b><span>今天没有到期</span>'
            mid = [f'<div class="hero-item ok"><b>{nxt["label"]}</b><span>下一批到期</span></div>',
                   f'<div class="hero-item ok"><b class="count" data-n="{nxt["count"]}">0</b><span>届时需重做</span></div>',
                   f'<div class="hero-item"><b class="count" data-n="{d["streak"]}">0</b><span>连续学习（天）</span></div>']
            tip = f'下一批在 <b>{html.escape(nxt["label"])}</b>（{nxt["count"]} 道）。可以趁空档说「出重做单」打印一份，或让 AI 统计错因。'
        else:
            num_html = '<b class="grad-t">0</b><span>今天没有到期</span>'
            mid = [f'<div class="hero-item"><b class="count" data-n="{d["streak"]}">0</b><span>连续学习（天）</span></div>']
            tip = '未来两周暂无到期。新错题录入后 FSRS 会自动排期。'
        if inbox:
            mid.append(f'<div class="hero-item warn"><b class="count" data-n="{inbox}">0</b><span>收件箱待处理</span></div>')
            tip = f'收件箱还有 <b>{inbox} 张</b>待处理——说「处理收件箱」即可归档。' + tip
    hero = (f'<div class="hero-card"><div class="hero-num">{num_html}</div>'
            f'<div class="hero-mid">{"".join(mid)}</div>'
            f'<div class="hero-tip">{tip}</div></div>')
    banner = _countdown_banner(d)

    status_ring = _ring([(s, st[s]) for s in ("未掌握", "复习中", "已掌握") if st[s]],
                        STATUS_COLORS, total, "道错题")
    side = (
        '<div class="side">'
        '<div class="panel">' + _icon("load") + '<h2>未来 7 天负载</h2>' + _cols(d["future"][:7], today_idx=0) + "</div>"
        '<div class="panel">' + _icon("ring") + '<h2>学习状态</h2>' + status_ring + "</div>"
        '<div class="panel">' + _icon("inbox") + '<h2>今日打卡</h2><div class="mini-stats">'
        + _stat_chip(_icon("flame"), d["streak"], "连续学习（天）")
        + _stat_chip(_icon("target"), d["reviewed_today"], "已复习（道）")
        + _stat_chip(_icon("trend"), d["week_new"], "本周新增")
        + _stat_chip(_icon("brain"), d["knowledge_items"], "知识库条目")
        + "</div></div></div>")

    main = ('<div class="panel">' + _icon("due")
            + '<h2>今日该重做 <span class="hint">按轻重缓急排序 · 点题名跳转 Obsidian</span></h2>'
            + (_due_panel(d["due"]) if due else '<div class="zero-state">🎉 今天没有到期的错题</div>')
            + "</div>")
    return f'<div id="v-today" class="view on">{banner}{hero}<div class="grid g21">{main}{side}</div></div>'


def _view_review(d):
    st = d["status_counts"]
    total = d["total"]
    strip = (
        '<div class="stat-strip">'
        + _stat_chip(_icon("target"), total, "错题总数", "")
        + _stat_chip(_icon("ring"), f'{d["mastery"]:.0f}', "掌握率 %", "ok")
        + _stat_chip(_icon("trend"), d["week_new"], "本周新增")
        + _stat_chip(_icon("alert"), d["high3"], "高频错题", "warn" if d["high3"] else "")
        + _stat_chip(_icon("brain"), d["knowledge_items"], "知识库条目")
        + "</div>")
    body = (
        strip
        + '<div class="grid g35">'
        '<div class="panel">' + _icon("target") + "<h2>学习进度</h2>" + _funnel(st, total, d["mastery"]) + "</div>"
        '<div class="panel">' + _icon("pie") + '<h2>科目分布 <span class="hint">环形 + 状态构成</span></h2>'
        + _ring(d["subject_counts"], SUBJ_COLORS, total, "道错题")
        + '<div style="margin-top:14px">' + _stack_rows(d["subject_status"]) + "</div></div></div>"
        '<div class="grid g73">'
        '<div class="panel">' + _icon("heat") + '<h2>学习活动热力图 <span class="hint">近 16 周 · 每日新增错题</span></h2>'
        + _heatmap(d["heatmap"], d["today"]) + "</div>"
        '<div class="panel">' + _icon("trend") + '<h2>近 8 周新增 <span class="hint">每周错题量</span></h2>'
        + _sparkline(d["week_trend"]) + "</div></div>"
        '<div class="grid g3">'
        '<div class="panel">' + _icon("alert") + "<h2>错因分布</h2>" + _bars(d["error_counts"], _ERROR_COLORS) + "</div>"
        '<div class="panel">' + _icon("book") + "<h2>哪本书错得最多</h2>" + _bars(d["book_counts"]) + "</div>"
        '<div class="panel">' + _icon("brain") + "<h2>知识点 Top 10</h2>" + _bars(d["topic_counts"]) + "</div></div>")
    return f'<div id="v-review" class="view">{body}</div>'


def _view_bank(d):
    body = (
        '<div class="grid g21">'
        '<div class="panel">' + _icon("trophy") + '<h2>高频错题榜 <span class="hint">错过 ≥2 次 · 点击题名跳转</span></h2>'
        + _high_table(d["high"]) + "</div>"
        '<div class="panel">' + _icon("clock") + "<h2>最近录入</h2>" + _recent_table(d["recent"]) + "</div></div>")
    return f'<div id="v-bank" class="view">{body}</div>'


def render(d):
    total = d["total"]
    st = d["status_counts"]
    exam_line = d["exam_date"] or ""
    streak_chip = f'<span class="tchip fire">🔥 连续 <b>{d["streak"]}</b> 天</span>' if d["streak"] else ""

    due_badge = (f'<span class="badge">{len(d["due"])}</span>' if d["due"] else "")
    tabs = ('<div class="seg"><div class="thumb"></div>'
            f'<button class="tab" data-v="today">今日{due_badge}</button>'
            '<button class="tab" data-v="review">复盘</button>'
            '<button class="tab" data-v="bank">题库</button></div>')

    if total or d["inbox"]:
        body = _view_today(d) + _view_review(d) + _view_bank(d)
    else:
        tabs = ""
        body = _countdown_banner(d) + _empty_state()

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
            '<div class="wallpaper"></div>'
            '<div class="aurora"><i class="a1"></i><i class="a2"></i><i class="a3"></i></div>'
            '<div class="grain"></div>'
            '<div class="wrap">'
            '<nav class="topbar">'
            '<div class="lights" title="窗口装饰"><i class="l-r"></i><i class="l-y"></i><i class="l-g"></i></div>'
            f'<div class="brand">{brand_svg}考研错题工作台</div>'
            f'<div class="tchips">{streak_chip}</div>'
            f'{tabs}'
            f'<button class="tbtn" id="themeBtn" title="切换深浅色">{sun}{moon}</button></nav>'
            "<main>" + body + "</main>"
            f'<div class="foot">星期{d["weekday"]} · {d["today"]} · 生成于 {d["generated_at"]} · '
            "说「刷新工作台」重新生成 · F5 看最新 · 数据全部来自本地错题笔记</div>"
            "</div><script>" + _JS + "</script></body></html>")