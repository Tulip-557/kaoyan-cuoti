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


def _dual_spark(new_pairs, rev_pairs):
    """新增 vs 复习 两条平滑曲线。"""
    vals = [p["count"] for p in new_pairs] + [p["count"] for p in rev_pairs]
    n = len(new_pairs)
    if n < 2:
        return '<div class="muted">数据不足</div>'
    W, H, top, bottom = 560, 170, 28, 36
    maxv = max(vals) or 1

    def pts(pairs):
        out = []
        for i, p in enumerate(pairs):
            x = 14 + i * ((W - 28) / (n - 1))
            y = top + (1 - p["count"] / maxv) * (H - top - bottom)
            out.append((x, y))
        return out

    def path(pairs, color, ident):
        ps = pts(pairs)
        line = _smooth(ps)
        area = line + f"L{ps[-1][0]:.1f},{H - bottom + 2} L{ps[0][0]:.1f},{H - bottom + 2} Z"
        dots = "".join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="var(--card-solid)" stroke="{color}" stroke-width="1.8"/>'
            for x, y in ps)
        return (f'<defs><linearGradient id="{ident}" x1="0" y1="0" x2="0" y2="1">'
                f'<stop offset="0" stop-color="{color}" stop-opacity=".22"/>'
                f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
                f'<path d="{area}" fill="url(#{ident})"/>'
                f'<path d="{line}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>{dots}')

    labels = "".join(
        f'<text x="{x:.1f}" y="{H - 12}" text-anchor="middle" class="sl">{html.escape(new_pairs[i]["label"])}</text>'
        for i, (x, _y) in enumerate(pts(new_pairs)))
    return (
        f'<svg viewBox="0 0 560 170" class="spark" preserveAspectRatio="none">'
        + path(rev_pairs, "#b08cff", "revG")
        + path(new_pairs, "#8fb8ff", "newG")
        + labels + "</svg>"
        + '<div class="dual-legend"><span><i style="background:#8fb8ff"></i>新增错题</span>'
          '<span><i style="background:#b08cff"></i>复习次数</span></div>')


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
            f'<span class="due-rank">{i + 1:02d}</span>'
            f'<span class="due-bar"></span>'
            f'<span class="due-main">{_obsidian(x["file"], x["stem"])}'
            f'<em class="tp">{html.escape(x["topic"])}</em></span>'
            f'<span class="due-trail">{hot}{wc}{due_tag}</span></div>')
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
            f'<div class="ios-row" style="--sc:{color}"><span class="ios-when">'
            f'<span class="rank{rank_cls}">{i}</span></span>'
            f'<span class="ios-bar"></span>'
            f'<span class="ios-main">{_obsidian(x["file"], x["stem"])}'
            f'<em><span class="dot" style="background:{color}"></span>{html.escape(x["subject"])}'
            f' · {html.escape(x["topic"])}</em></span>'
            f'<span class="ios-trail"><span class="wcbig">{x["wrong_count"]} 次</span>'
            f'<span class="pill p-{x["status"]}">{html.escape(x["status"])}</span></span></div>')
    return '<div class="ios-list">' + "".join(rows) + "</div>"


def _recent_table(recent):
    if not recent:
        return '<div class="muted">暂无记录</div>'
    rows = []
    for x in recent:
        color = SUBJ_COLORS.get(x["subject"], "#8a94a6")
        rows.append(
            f'<div class="ios-row" style="--sc:{color}"><span class="ios-when">{x["date"][5:]}</span>'
            f'<span class="ios-bar"></span>'
            f'<span class="ios-main">{_obsidian(x["file"], x["stem"])}'
            f'<em><span class="dot" style="background:{color}"></span>{html.escape(x["subject"])}</em></span>'
            f'<span class="ios-trail"><span class="pill p-{x["status"]}">'
            f'{html.escape(x["status"])}</span></span></div>')
    return '<div class="ios-list">' + "".join(rows) + "</div>"


def _focus_ring(st, total, mastery):
    """参考图 Focus 组件的白色进度环：中心掌握率，尾端一枚旋钮。"""
    import math
    if not total:
        return '<div class="muted">暂无数据</div>'
    r = 42.0
    c = 2 * math.pi * r
    pct = max(0.0, min(100.0, mastery)) / 100
    off = c * (1 - pct)
    knob = ""
    if pct > 0.02:
        rad = math.radians(-90 + 360 * pct)
        knob = (f'<circle class="knob" cx="{50 + r * math.cos(rad):.2f}" '
                f'cy="{50 + r * math.sin(rad):.2f}" r="5.6"/>')
    svg = ('<svg viewBox="0 0 100 100" class="rings" aria-hidden="true">'
           f'<circle class="ring-track" cx="50" cy="50" r="{r}" stroke-width="9"/>'
           f'<circle class="prog" cx="50" cy="50" r="{r}" stroke-width="9" '
           f'stroke-dasharray="{c:.2f}" style="--c:{c:.2f};stroke-dashoffset:{off:.2f}">'
           f'<title>掌握率 {mastery:.0f}%</title></circle>{knob}</svg>')
    rows = "".join(
        f'<div class="ring-row"><i style="background:{STATUS_COLORS[s]}"></i>{s}'
        f'<small>{st[s] / total * 100:.0f}%</small><b>{st[s]}</b></div>'
        for s in ("未掌握", "复习中", "已掌握"))
    return (f'<div class="rings-wrap">{svg}'
            f'<div class="rings-cap"><b>{mastery:.0f}%</b><small>掌握率</small></div></div>'
            f'<div class="ring-legend">{rows}</div>')


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


def _insights_html(d):
    ins = []
    if d["worst_subject"]:
        w = d["worst_subject"]
        ins.append(("📌", f"最痛科目：<b>{w['subject']}</b>——未掌握 {w['open']} 道，掌握率仅 {w['pct']:.0f}%"))
    if d["weakest_topic"]:
        name, pain = d["weakest_topic"]
        ins.append(("🧠", f"最弱知识点：<b>{html.escape(str(name))}</b>——累计错 {pain} 次"))
    if d["top_error"]:
        name, cnt = d["top_error"]
        ins.append(("⚠️", f"最大错因：<b>{html.escape(str(name))}</b>（{cnt} 道）"))
    if d["review_ratio"] is not None:
        r = d["review_ratio"]
        tone = "复习跟得上录入 ✅" if r >= 1 else "复习追不上新错题 ⚠️"
        ins.append(("🔁", f"本周复习 {d['week_reviews']} 次 vs 新增 {d['week_new']} 道——<b>{tone}</b>"))
    if d["accuracy"] is not None:
        ins.append(("🎯", f"重做正确率：近 8 周 <b>{d['accuracy']:.0f}%</b>"
                          f"（对 {d['acc_ok']} / 错 {d['acc_bad']}）"))
    advice = []
    if d["overdue"]:
        advice.append(f"优先清掉 {d['overdue']} 道逾期题")
    if d["inbox"]:
        advice.append(f"收件箱还有 {d['inbox']} 张待归档")
    if d["worst_subject"]:
        advice.append(f"把 {d['worst_subject']['subject']} 的未掌握题排进下次重做单")
    ins.append(("💡", "建议：" + "；".join(advice) if advice else "保持节奏，暂无需要特别处理的事"))
    return "".join(
        f'<div class="insight-row"><span class="ib">{ic}</span><span>{txt}</span></div>'
        for ic, txt in ins)


def _msub_html(d):
    if not d["subj_mastery"]:
        return '<div class="muted">暂无数据</div>'
    return "".join(
        f'<div class="msub-row"><span class="lb">{html.escape(s["subject"])}</span>'
        f'<span class="tk"><i style="width:{s["pct"]:.0f}%;background:{SUBJ_COLORS.get(s["subject"], "#9d8cff")}"></i></span>'
        f'<b>{s["pct"]:.0f}%</b><small>{s["done"]}/{s["total"]}</small></div>'
        for s in d["subj_mastery"])


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
/* ═════════════ v7 Aura 液态玻璃 · 全屏极光 ═════════════ */
:root{
  --bg:#1a0f2e; --ink:#ffffff; --ink2:rgba(255,255,255,.72); --sub:rgba(255,255,255,.52);
  --card:rgba(255,255,255,.07); --card2:rgba(255,255,255,.10); --card-solid:#241436;
  --line:rgba(255,255,255,.15); --line2:rgba(255,255,255,.08);
  --accent:#9d8cff; --accent2:#7aa7ff; --violet:#e58cff; --warn:#ffb45c; --danger:#ff7a6e; --ok:#5fe3c0;
  --track:rgba(255,255,255,.10);
  --blur:blur(46px) saturate(170%);
  --shadow:0 1px 0 rgba(255,255,255,.10) inset, 0 24px 60px rgba(20,5,40,.38);
  --h0:rgba(255,255,255,.08); --h1:rgba(255,255,255,.22); --h2:rgba(255,255,255,.38);
  --h3:rgba(255,255,255,.58); --h4:#ffffff;
  --r:32px;
  --spring:cubic-bezier(.32,.72,.24,1);
}
html[data-theme="light"]{
  --ink:#241a3d; --ink2:rgba(36,26,61,.78); --sub:rgba(36,26,61,.55);
  --card:rgba(255,255,255,.48); --card2:rgba(255,255,255,.62); --card-solid:#ffffff;
  --line:rgba(255,255,255,.75); --line2:rgba(255,255,255,.45);
  --accent:#6b4edb; --accent2:#4c7df0; --violet:#b04fd8; --warn:#c96a00; --danger:#d64545; --ok:#0f9d76;
  --track:rgba(36,26,61,.10);
  --blur:blur(46px) saturate(160%);
  --shadow:0 1px 0 rgba(255,255,255,.9) inset, 0 20px 50px rgba(80,50,120,.16);
  --h0:rgba(36,26,61,.07); --h1:rgba(107,78,219,.18); --h2:rgba(107,78,219,.34);
  --h3:rgba(107,78,219,.55); --h4:#5b3fd0;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","PingFang SC","Segoe UI","Microsoft YaHei",sans-serif;
  color:var(--ink);padding:0 24px 64px;line-height:1.5;min-height:100vh;overflow-x:hidden;
  background:#1a0f2e;transition:color .3s ease,background .3s ease;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;font-feature-settings:"tnum";
}
/* ── 全屏极光壁纸（Aura 参考图的核心） ── */
.wallpaper{
  position:fixed;inset:0;z-index:-3;
  background:
    radial-gradient(64% 54% at 8% 2%, rgba(236,90,255,.55), transparent 62%),
    radial-gradient(52% 46% at 92% 6%, rgba(122,102,255,.55), transparent 64%),
    radial-gradient(58% 50% at 78% 88%, rgba(255,110,190,.35), transparent 66%),
    radial-gradient(72% 58% at 28% 100%, rgba(48,98,255,.55), transparent 68%),
    linear-gradient(150deg,#3a1550 0%,#241242 38%,#141132 68%,#101638 100%);
}
html[data-theme="light"] .wallpaper{
  background:
    radial-gradient(62% 52% at 6% 0%, rgba(255,168,236,.75), transparent 62%),
    radial-gradient(54% 46% at 94% 4%, rgba(168,158,255,.70), transparent 64%),
    radial-gradient(56% 46% at 80% 92%, rgba(255,190,214,.55), transparent 66%),
    radial-gradient(74% 58% at 22% 102%, rgba(150,205,255,.70), transparent 68%),
    linear-gradient(150deg,#fbe9fb 0%,#f0eaff 40%,#e8f0ff 72%,#eaf6ff 100%);
}
.aurora{display:none}
.grain{position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.030;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.6'/%3E%3C/svg%3E")}

.wrap{max-width:1200px;margin:0 auto}

/* ── 顶部胶囊导航 ── */
.topbar{
  position:sticky;top:12px;z-index:50;margin:18px 0 22px;padding:10px 14px;
  display:flex;align-items:center;gap:14px;border-radius:26px;
  background:var(--card);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);
  border:.5px solid var(--line);box-shadow:var(--shadow);
}
.brand{display:flex;align-items:center;gap:10px;white-space:nowrap;flex:none}
.appicon{
  width:34px;height:34px;border-radius:11px;flex:none;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(140deg,#ff8ad8 0%,#a06bff 45%,#5b8cff 100%);
  box-shadow:0 6px 16px rgba(150,90,255,.45), 0 1px 0 rgba(255,255,255,.45) inset;
}
.appicon svg{width:19px;height:19px}
.brand .bname{font-size:15px;font-weight:600;letter-spacing:-.01em}
.bver{
  font-size:9.5px;letter-spacing:.5px;color:var(--sub);border:.5px solid var(--line);
  padding:1.5px 7px;border-radius:999px;
}
/* 居中导航：玻璃胶囊里的文字导航 */
.seg{position:relative;display:flex;gap:2px;margin:0 auto;padding:3px;border-radius:999px;background:var(--track);flex:none}
.seg .thumb{
  position:absolute;top:3px;bottom:3px;left:0;width:64px;border-radius:999px;
  background:var(--card2);border:.5px solid var(--line);
  box-shadow:0 4px 14px rgba(0,0,0,.16);
  transition:left .34s var(--spring), width .34s var(--spring);
}
.tab{
  position:relative;z-index:1;border:none;background:transparent;color:var(--sub);font-size:13px;font-weight:500;
  padding:7px 18px;border-radius:999px;cursor:pointer;transition:color .25s ease;white-space:nowrap;font-family:inherit;
}
.tab:hover{color:var(--ink)}
.tab.on{color:var(--ink);font-weight:600}
.tab .badge{
  display:inline-block;margin-left:5px;min-width:17px;padding:0 5px;border-radius:9px;
  background:var(--danger);color:#fff;font-size:10px;line-height:15px;text-align:center;font-weight:700;
}
.tchips{display:flex;gap:8px;margin-left:auto;align-items:center;flex:none}
.tchip{
  display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:6px 13px;border-radius:999px;
  border:.5px solid var(--line);background:var(--card2);color:var(--ink2);white-space:nowrap;font-weight:500;
}
.tchip b{color:var(--ink);font-variant-numeric:tabular-nums;font-weight:600}
.tbtn{
  width:34px;height:34px;border-radius:50%;border:.5px solid var(--line);background:var(--card2);color:var(--ink);
  cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none;
  transition:transform .2s var(--spring),background .2s ease;
}
.tbtn:hover{background:var(--card-solid)}
.tbtn:active{transform:scale(.9)}
.tbtn svg{width:15px;height:15px}
html[data-theme="dark"] .icon-sun{display:none}
html[data-theme="light"] .icon-moon{display:none}

/* ── 视图 ── */
.view{display:none}
.view.on{display:block;animation:rise .5s var(--spring)}
@media (prefers-reduced-motion: reduce){.view.on{animation:none}}

/* ── 玻璃卡（Aura 式：强模糊、几乎无边框、大圆角） ── */
.panel,.schip{
  position:relative;
  background:var(--card);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);
  border:.5px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);
  animation:rise .55s var(--spring) backwards;
}
.panel::before{
  content:"";position:absolute;left:24px;right:24px;top:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.5) 22%,rgba(255,255,255,.08) 55%,transparent);
  opacity:.8;pointer-events:none;border-radius:1px;
}
html[data-theme="light"] .panel::before{background:linear-gradient(90deg,transparent,rgba(255,255,255,1) 22%,rgba(255,255,255,.3) 55%,transparent)}
.panel{padding:24px 26px;min-width:0}
@keyframes rise{from{opacity:0;transform:translateY(18px) scale(.985)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion: reduce){.panel,.schip,.flip{animation:none}}
.panel h2{
  font-size:15px;font-weight:600;letter-spacing:-.01em;margin-bottom:16px;
  display:flex;align-items:center;gap:9px;color:var(--ink);
}
.panel h2 .picon{width:17px;height:17px;stroke:currentColor;fill:none;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round;flex:none;opacity:.65}
.panel h2 .hint{font-size:11px;font-weight:400;margin-left:auto;color:var(--sub);opacity:.9}
a{color:var(--ink);text-decoration:none}
a:hover{text-decoration:underline;text-underline-offset:3px;text-decoration-color:var(--line)}
.muted{color:var(--sub);font-size:13px}
.grad-t{background:linear-gradient(120deg,#fff 20%,#e8c8ff 90%);-webkit-background-clip:text;background-clip:text;color:transparent}
html[data-theme="light"] .grad-t{background:linear-gradient(120deg,#3a2a66,#7a4fd0);-webkit-background-clip:text;background-clip:text;color:transparent}

/* ── 版式 ── */
.grid{display:grid;gap:20px;margin-bottom:20px}
.g21{grid-template-columns:2fr 1fr}
.g35{grid-template-columns:3fr 5fr}
.g73{grid-template-columns:7fr 5fr}
.g3{grid-template-columns:1fr 1fr 1fr}
.hero-grid{display:grid;grid-template-columns:1.05fr 1.95fr;gap:26px;margin-bottom:22px;align-items:stretch}

/* ── 问候区（无卡片，字直接浮在壁纸上，参考图左栏） ── */
.greet{display:flex;flex-direction:column;justify-content:center;padding:6px 2px 2px}
.greet-date{
  font-size:10.5px;letter-spacing:2.6px;color:var(--sub);font-weight:600;
  text-transform:uppercase;margin-bottom:14px;
}
.greet-h{
  font-size:clamp(34px,3.4vw,46px);font-weight:300;line-height:1.14;letter-spacing:-.025em;
  color:var(--ink);
}
.greet-h b{font-weight:500;font-variant-numeric:tabular-nums;letter-spacing:-.03em}
.greet-h .soft{color:var(--ink2)}
.greet-sub{font-size:13px;color:var(--sub);margin-top:14px;max-width:330px;line-height:1.75}
.greet-pills{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}
.hpill{
  display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--ink2);
  padding:7px 13px;border-radius:999px;background:var(--card2);border:.5px solid var(--line);font-weight:500;
  backdrop-filter:blur(10px);
}
.hpill b{font-size:13px;font-weight:600;font-variant-numeric:tabular-nums;color:var(--ink)}
.hpill.danger b{color:var(--danger)}
.hpill.ok b{color:var(--ok)}
.hpill.warn b{color:var(--warn)}

/* ── 倒计时（参考图中栏的"Now Playing"大卡） ── */
.cd-banner{
  position:relative;border-radius:var(--r);padding:28px 32px 24px;overflow:hidden;
  background:
    radial-gradient(120% 120% at 10% 0%, rgba(255,255,255,.22), transparent 55%),
    linear-gradient(135deg,#c25bff 0%,#7a5cff 46%,#3f6dff 100%);
  color:#fff;box-shadow:0 30px 70px rgba(90,50,200,.45), 0 1px 0 rgba(255,255,255,.4) inset;
  border:.5px solid rgba(255,255,255,.35);
  display:flex;flex-direction:column;justify-content:space-between;
}
/* 唱片式同心光环（参考图专辑封面） */
.cd-banner::before{
  content:"";position:absolute;left:50%;top:50%;width:420px;height:420px;margin:-210px 0 0 -210px;
  border-radius:50%;border:1px solid rgba(255,255,255,.22);
  box-shadow:0 0 0 34px rgba(255,255,255,.05), 0 0 0 68px rgba(255,255,255,.035), 0 0 0 104px rgba(255,255,255,.02);
  pointer-events:none;
}
.cd-banner::after{
  content:"";position:absolute;right:-70px;top:-90px;width:260px;height:260px;border-radius:50%;
  background:radial-gradient(circle,rgba(255,255,255,.25),transparent 62%);pointer-events:none;
}
.sheen{
  position:absolute;top:-40%;bottom:-40%;left:-30%;width:34%;
  background:linear-gradient(102deg,transparent 18%,rgba(255,255,255,.14) 46%,rgba(255,255,255,.30) 50%,rgba(255,255,255,.12) 54%,transparent 80%);
  transform:rotate(8deg);animation:sheen 7.5s ease-in-out 1.2s infinite;pointer-events:none;
}
@keyframes sheen{0%{left:-40%}45%{left:120%}100%{left:120%}}
@media (prefers-reduced-motion: reduce){.sheen{display:none}}
.cd-top{display:flex;align-items:flex-start;justify-content:space-between;position:relative;z-index:1;gap:16px}
.cd-kicker{font-size:10px;letter-spacing:3px;opacity:.9;font-weight:700}
.cd-date{font-size:14px;font-weight:500;opacity:.95;text-align:right}
.cd-wd{font-size:10.5px;font-weight:600;margin-left:6px;padding:1px 8px;border-radius:999px;background:rgba(255,255,255,.22)}
.cd-mid{display:flex;align-items:center;justify-content:center;gap:8px;padding:22px 0 18px;position:relative;z-index:1}
.flip{
  display:inline-flex;align-items:center;justify-content:center;
  width:.66em;height:1.08em;font-size:78px;font-weight:300;letter-spacing:-.02em;
  background:rgba(255,255,255,.13);border:.5px solid rgba(255,255,255,.30);
  backdrop-filter:blur(20px) saturate(150%);
  border-radius:.16em;position:relative;color:#fff;font-variant-numeric:tabular-nums;
  box-shadow:0 1px 0 rgba(255,255,255,.45) inset, 0 18px 40px rgba(40,10,90,.35);
  animation:flipin .75s var(--spring) backwards;
}
.flip::before{content:"";position:absolute;left:6%;right:6%;top:calc(50% - 1px);height:1.5px;background:rgba(255,255,255,.16);z-index:1}
.flip::after{content:"";position:absolute;inset:0;border-radius:inherit;background:linear-gradient(180deg,rgba(255,255,255,.16),transparent 45%);pointer-events:none}
@keyframes flipin{from{transform:rotateX(-92deg);opacity:0}62%{transform:rotateX(14deg);opacity:1}to{transform:none}}
.cd-unit{font-size:22px;font-weight:300;opacity:.9;margin-left:4px;letter-spacing:-.02em}
.cd-bottom{display:flex;align-items:center;justify-content:space-between;gap:14px;position:relative;z-index:1;flex-wrap:wrap}
.cd-equiv{font-size:12.5px;opacity:.92;font-weight:300}
.cd-equiv b{font-size:15px;font-weight:600}
.ms-track{display:flex;gap:7px;flex-wrap:wrap}
.ms{font-size:11px;padding:4px 11px;border-radius:999px;background:rgba(255,255,255,.15);font-variant-numeric:tabular-nums;font-weight:400}
.ms.past{opacity:.45}
.ms.fut{opacity:.75}
.ms.on{background:rgba(255,255,255,.94);color:#6b3fd4;font-weight:700;box-shadow:0 4px 18px rgba(0,0,0,.22)}
.ms-gap{margin-left:6px;opacity:.75;font-weight:500}
.cd-empty{font-size:14px;text-align:center;padding:40px 0;opacity:.92}

/* ── 今日：清单（参考图 Tomorrow 列表） ── */
.chips{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:14px}
.chip{
  display:inline-flex;align-items:center;gap:6px;border:.5px solid var(--line);background:var(--card2);
  color:var(--sub);border-radius:999px;padding:5px 13px;font-size:12px;cursor:pointer;
  transition:all .18s var(--spring);font-family:inherit;font-weight:500;
}
.chip i{width:7px;height:7px;border-radius:50%;display:inline-block}
.chip:hover{color:var(--ink)}
.chip.on{background:rgba(255,255,255,.90);border-color:transparent;color:#3a2360;font-weight:600}
html[data-theme="light"] .chip.on{background:#3a2360;color:#fff}
.due-list{display:flex;flex-direction:column;max-height:560px;overflow-y:auto;padding-right:2px;scrollbar-width:thin}
.due-list::-webkit-scrollbar{width:6px}
.due-list::-webkit-scrollbar-thumb{background:var(--track);border-radius:3px}
.grp{display:flex;align-items:center;gap:7px;font-size:10.5px;letter-spacing:2px;font-weight:600;color:var(--sub);padding:16px 2px 8px;text-transform:uppercase}
.grp:first-child{padding-top:0}
.grp .picon{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.grp.g-over{color:var(--danger)}
.due{display:flex;align-items:center;gap:12px;padding:12px 2px;position:relative;font-size:13.5px;border-radius:12px;transition:background .18s ease}
.due:hover{background:var(--card2)}
.due::after{content:"";position:absolute;left:44px;right:0;bottom:0;height:.5px;background:var(--line2)}
.due:last-child::after{display:none}
.due-rank{
  flex:0 0 24px;text-align:center;font-size:12px;font-weight:600;color:var(--sub);
  font-variant-numeric:tabular-nums;
}
.due.top1 .due-rank{color:var(--ink)}
.due.top1 .due-bar{box-shadow:0 0 12px color-mix(in srgb,var(--sc) 80%,transparent)}
.due.is-over .due-rank{color:var(--danger)}
.due-bar{flex:none;width:3px;height:30px;border-radius:2px;background:var(--sc);opacity:.9}
.due-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}
.due-main .note{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500;color:var(--ink);font-size:14px}
.tp{font-style:normal;font-size:11.5px;color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.due-trail{display:flex;align-items:center;gap:6px;flex:none}
.wc{font-size:11px;color:var(--warn);background:color-mix(in srgb,var(--warn) 16%,transparent);border-radius:999px;padding:2px 9px;white-space:nowrap;font-weight:600}
.wc.hot{background:var(--danger);color:#fff}
.due-tag{font-size:11.5px;color:var(--sub);white-space:nowrap;font-weight:400;padding:2px 9px;border-radius:999px;background:var(--track)}
.due-tag.over{color:var(--danger);background:color-mix(in srgb,var(--danger) 16%,transparent);font-weight:600}
.chev{display:none}
.zero-state{color:var(--sub);font-size:13.5px;padding:40px 0;text-align:center}

/* ── Focus 环（参考图左下的圆形计时器） ── */
.rings-wrap{position:relative;width:196px;height:196px;margin:4px auto 10px}
.rings{width:100%;height:100%}
.rings .ring-track{fill:none;stroke:var(--track)}
.rings .prog{
  fill:none;stroke:#fff;stroke-linecap:round;transform:rotate(-90deg);transform-origin:50% 50%;
  filter:drop-shadow(0 0 10px rgba(255,255,255,.35));
  animation:ringdraw 1.25s var(--spring);
}
html[data-theme="light"] .rings .prog{stroke:#5b3fd0;filter:drop-shadow(0 0 8px rgba(91,63,208,.25))}
.rings .knob{fill:#fff;filter:drop-shadow(0 0 8px rgba(255,255,255,.55))}
html[data-theme="light"] .rings .knob{fill:#5b3fd0;filter:drop-shadow(0 0 6px rgba(91,63,208,.35))}
@keyframes ringdraw{from{stroke-dashoffset:var(--c)}}
@media (prefers-reduced-motion: reduce){.rings .prog{animation:none}}
.rings-cap{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none}
.rings-cap b{font-size:44px;font-weight:300;letter-spacing:-.03em;font-variant-numeric:tabular-nums;line-height:1}
.rings-cap small{font-size:10.5px;letter-spacing:2px;color:var(--sub);margin-top:6px;text-transform:uppercase}
.ring-legend{display:flex;flex-direction:column;gap:8px;font-size:12.5px}
.ring-row{display:flex;align-items:center;gap:8px;color:var(--ink2)}
.ring-row i{width:8px;height:8px;border-radius:50%;flex:none}
.ring-row small{margin-left:auto;color:var(--sub);font-variant-numeric:tabular-nums}
.ring-row b{flex:0 0 30px;text-align:right;color:var(--ink);font-variant-numeric:tabular-nums;font-weight:600}

/* ── 侧栏 / 小卡 ── */
.side{display:flex;flex-direction:column;gap:20px}
.mini-stats{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.schip{padding:14px 16px;border-radius:22px}
.schip-n{font-size:24px;font-weight:400;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.schip-n.t-warn{color:var(--warn)}
.schip-n.t-ok{color:var(--ok)}
.schip-l{font-size:11px;color:var(--sub);margin-top:3px;display:flex;align-items:center;gap:5px}
.schip-l .picon{width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}

/* ── 图表 ── */
.donut-wrap{position:relative;width:162px;height:162px;margin:6px auto 10px}
.donut{width:100%;height:100%;filter:drop-shadow(0 10px 26px rgba(120,80,255,.30))}
.donut-cap{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none}
.donut-cap b{font-size:34px;font-weight:300;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.donut-cap small{font-size:10.5px;color:var(--sub);letter-spacing:1px}
.legend{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;font-size:12px;color:var(--sub);margin-top:10px}
.legend .lg{display:inline-flex;align-items:center;gap:5px}
.legend .lg b{color:var(--ink);margin-left:2px;font-weight:600}
.legend i{width:8px;height:8px;border-radius:2.5px;display:inline-block}
.srow{display:flex;align-items:center;gap:10px;margin:10px 0;font-size:12.5px}
.slb{flex:0 0 46px;font-weight:600}
.stack{flex:1;height:12px;border-radius:6px;overflow:hidden;display:flex;gap:2px;background:var(--track)}
.stack i{display:block}
.stack.big{height:16px;border-radius:8px;margin:14px 0 18px}
.empty-seg{flex:1;background:var(--track)}
.snum{flex:0 0 26px;text-align:right;color:var(--sub);font-weight:500;font-variant-numeric:tabular-nums}
.brow{display:flex;align-items:center;gap:9px;margin:9px 0;font-size:12.5px}
.blb{flex:0 0 106px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--sub)}
.btrack{flex:1;height:9px;background:var(--track);border-radius:5px;overflow:hidden}
.btrack i{display:block;height:100%;border-radius:5px;width:0;transition:width .9s var(--spring)}
.ready .btrack i{width:var(--w)}
.bnum{flex:0 0 46px;text-align:right;font-weight:500;font-variant-numeric:tabular-nums}
.bnum small{font-size:10.5px;margin-left:3px;color:var(--sub);font-weight:400}
.cols{display:flex;align-items:flex-end;gap:7px;height:132px;padding-top:14px}
.col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:3px}
.col i{
  display:block;width:58%;height:0;border-radius:5px;min-height:4px;
  background:linear-gradient(180deg,rgba(255,255,255,.92),rgba(255,255,255,.42));
  transition:height .9s var(--spring);
}
html[data-theme="light"] .col i{background:linear-gradient(180deg,rgba(91,63,208,.85),rgba(91,63,208,.35))}
.ready .col i{height:var(--h)}
.col.today i{background:linear-gradient(180deg,#ffd9a8,#ff9f5c)}
.col .cv{font-size:10.5px;color:var(--sub);height:14px;font-variant-numeric:tabular-nums}
.col em{font-style:normal;font-size:10px;color:var(--sub);white-space:nowrap}
.col.today em{color:var(--warn);font-weight:600}
.spark{width:100%;height:auto}
.spark .sv{font-size:11px;fill:var(--ink2);font-weight:600}
.spark .sl{font-size:10px;fill:var(--sub)}
.mastery{display:flex;align-items:baseline;gap:10px;margin-bottom:4px}
.mastery b{font-size:48px;font-weight:300;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.mastery span{color:var(--sub);font-size:12px}
.f-rows{display:flex;flex-direction:column;gap:8px;font-size:12.5px}
.f-row{display:flex;align-items:center;gap:8px;color:var(--ink2)}
.f-row b{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:600;color:var(--ink)}
.f-row small{color:var(--sub);flex:0 0 42px;text-align:right;font-variant-numeric:tabular-nums}
.stat-strip{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;margin-bottom:20px}

/* ── 热力图 ── */
.heat-wrap{display:flex;gap:8px}
.hweeks{display:flex;flex-direction:column;gap:3px;font-size:9.5px;color:var(--sub);padding-top:20px}
.hweeks span{height:13px;line-height:13px;display:block}
.heat-main{flex:1;min-width:0}
.hlabels{display:flex;gap:3px;font-size:9.5px;color:var(--sub);margin-bottom:5px;font-weight:600}
.hlabels span{flex:1;text-align:left;white-space:nowrap;overflow:hidden}
.hgrid{display:flex;gap:3px}
.hcol{display:flex;flex-direction:column;gap:3px;flex:1}
.hcell{display:block;height:13px;border-radius:4px;background:var(--h0);transition:transform .15s var(--spring)}
.hcell:hover{transform:scale(1.3)}
.hcell.fut{background:transparent}
.hcell.lv0{background:var(--h0)}
.hcell.lv1{background:var(--h1)}
.hcell.lv2{background:var(--h2)}
.hcell.lv3{background:var(--h3)}
.hcell.lv4{background:var(--h4);box-shadow:0 0 12px rgba(255,255,255,.35)}
.hlegend{display:flex;align-items:center;gap:3px;justify-content:flex-end;margin-top:10px;font-size:10.5px;color:var(--sub)}
.hlegend .hcell{width:13px;height:13px}
.hlegend span{margin:0 3px}

/* ── 列表（题库） ── */
.ios-list{display:flex;flex-direction:column;margin:0 -2px}
.ios-row{display:flex;align-items:center;gap:12px;padding:12px 2px;position:relative;transition:background .15s ease;border-radius:12px}
.ios-row:hover{background:var(--card2)}
.ios-row::after{content:"";position:absolute;left:44px;right:0;bottom:0;height:.5px;background:var(--line2)}
.ios-row:last-child::after{display:none}
.ios-when{flex:0 0 30px;text-align:center;font-size:11.5px;color:var(--sub);font-variant-numeric:tabular-nums}
.ios-bar{flex:none;width:3px;height:30px;border-radius:2px;background:var(--sc,#9d8cff)}
.ios-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}
.ios-main .note{font-weight:500;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}
.ios-main em{font-style:normal;font-size:11.5px;color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ios-trail{display:flex;align-items:center;gap:7px;flex:none}
.rank{
  display:inline-flex;width:26px;height:26px;align-items:center;justify-content:center;border-radius:50%;
  background:var(--track);color:var(--sub);font-size:11px;font-weight:600;flex:none;
}
.rank.gold{background:linear-gradient(135deg,#ffd76e,#ff9f5c);color:#4a2d00}
.rank.silver{background:linear-gradient(135deg,#eef0f6,#c3cbe0);color:#2a3446}
.rank.bronze{background:linear-gradient(135deg,#f0c393,#d29a63);color:#4a2f14}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;vertical-align:1px}
.wcbig{font-size:12.5px;color:var(--danger);font-weight:600;font-variant-numeric:tabular-nums}
.pill{font-size:11px;padding:3px 11px;border-radius:999px;white-space:nowrap;font-weight:500}
.p-未掌握{color:#ffb4ab;background:rgba(255,122,110,.18)}
.p-复习中{color:#c4b5ff;background:rgba(157,140,255,.18)}
.p-已掌握{color:#9debd6;background:rgba(95,227,192,.16)}
html[data-theme="light"] .p-未掌握{color:#c0392b;background:rgba(214,69,69,.10)}
html[data-theme="light"] .p-复习中{color:#5b3fd0;background:rgba(107,78,219,.10)}
html[data-theme="light"] .p-已掌握{color:#0a7d5f;background:rgba(15,157,118,.10)}
.td-date{color:var(--sub);white-space:nowrap;font-variant-numeric:tabular-nums;font-size:11.5px;flex:none}

/* ── v8 实用组件 ── */
.goal-line{display:flex;align-items:baseline;gap:8px;font-size:12.5px;color:var(--sub)}
.goal-line b{font-size:24px;font-weight:400;color:var(--ink);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.goal-line i{font-style:normal;margin-left:auto;font-size:11px;color:var(--sub)}
.goal-track{height:8px;border-radius:4px;background:var(--track);margin-top:9px;overflow:hidden}
.goal-track i{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,#fff,rgba(255,255,255,.55))}
html[data-theme="light"] .goal-track i{background:linear-gradient(90deg,#5b3fd0,#8f6bff)}
.insight{display:grid;grid-template-columns:1.08fr .92fr;gap:30px}
.insight-list{display:flex;flex-direction:column;gap:11px}
.insight-row{display:flex;gap:10px;font-size:13px;line-height:1.6;color:var(--ink2)}
.insight-row .ib{flex:none;width:24px;height:24px;border-radius:8px;display:flex;align-items:center;justify-content:center;background:var(--card2);border:.5px solid var(--line);font-size:12px}
.insight-row b{color:var(--ink);font-weight:600}
.msub-row{display:flex;align-items:center;gap:10px;margin:10px 0;font-size:12.5px}
.msub-row .lb{flex:0 0 48px;font-weight:500;color:var(--ink2)}
.msub-row .tk{flex:1;height:8px;border-radius:4px;background:var(--track);overflow:hidden}
.msub-row .tk i{display:block;height:100%;border-radius:4px}
.msub-row b{flex:0 0 42px;text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.msub-row small{flex:0 0 52px;text-align:right;color:var(--sub);font-size:10.5px}
.ach-strip{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:8px}
.ach{display:flex;align-items:center;gap:7px;padding:8px 13px;border-radius:14px;background:var(--card2);border:.5px solid var(--line);font-size:12px;color:var(--sub)}
.ach.done{color:var(--ink)}
.ach .em{font-size:15px;filter:grayscale(1);opacity:.4}
.ach.done .em{filter:none;opacity:1}
.ach b{font-weight:600}
.pillbtn{border:.5px solid var(--line);background:var(--card2);color:var(--ink2);border-radius:999px;padding:4px 12px;font-size:11px;cursor:pointer;font-family:inherit;margin-left:8px}
.pillbtn:hover{color:var(--ink);background:var(--card-solid)}
.dual-legend{display:flex;gap:16px;font-size:11px;color:var(--sub);margin-top:8px}
.dual-legend i{display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:6px;vertical-align:2px}

/* ── 空状态 ── */
.empty-big{text-align:center;padding:70px 20px}
.empty-svg{width:110px;height:110px;margin-bottom:18px;opacity:.9}
.empty-big h2{display:block;font-size:18px;margin-bottom:8px;letter-spacing:-.01em}
.steps{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;margin-top:20px}
.step{background:var(--card2);border:.5px solid var(--line);border-radius:22px;padding:16px 18px;font-size:12.5px;min-width:190px;text-align:left;backdrop-filter:blur(14px)}
.step b{display:inline-flex;width:24px;height:24px;border-radius:50%;background:rgba(255,255,255,.92);color:#4a2a8a;align-items:center;justify-content:center;font-size:12px;margin-right:7px;font-weight:700}
html[data-theme="light"] .step b{background:#5b3fd0;color:#fff}
.step small{color:var(--sub)}

.foot{color:var(--sub);font-size:11.5px;text-align:center;margin-top:34px;line-height:1.9;opacity:.9}
@media (max-width:1050px){
  .hero-grid{grid-template-columns:1fr}
  .g21,.g35,.g73,.g3{grid-template-columns:1fr}
  .stat-strip{grid-template-columns:repeat(3,1fr)}
  .tchips .tchip:not(.keep){display:none}
}
@media (max-width:640px){
  body{padding:0 12px 44px}
  .topbar{padding:8px 10px;gap:8px;border-radius:22px}
  .brand .bname,.brand .bver{display:none}
  .stat-strip{grid-template-columns:repeat(2,1fr)}
  .tab{padding:6px 11px;font-size:12px}
  .greet-h{font-size:30px}
  .flip{font-size:52px}
  .cd-mid{padding:16px 0 12px}
  .cd-bottom{flex-direction:column;align-items:flex-start}
}
@media print{
  .wallpaper,.grain,.topbar,.chips,.sheen{display:none}
  .view{display:none!important}
  .view.on{display:block!important}
  body{background:#fff;color:#000;padding-top:16px}
  .panel,.schip,.cd-banner{box-shadow:none;border:1px solid #ddd;background:#fff;animation:none;color:#000}
  .panel::before{display:none}
  .greet-h,.grad-t,.rings-cap b,.donut-cap b{color:#000;-webkit-text-fill-color:#000}
}
@supports not (backdrop-filter: blur(1px)){
  .panel,.schip,.topbar,.seg,.step{background:var(--card-solid)}
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
  /* 问候语随时段变化 */
  var g=document.getElementById('greetWord');
  if(g){var h=new Date().getHours();
    g.textContent = h<5?'夜深了':h<11?'早上好':h<13?'中午好':h<18?'下午好':h<23?'晚上好':'夜深了';}
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
  /* 快捷键：1/2/3 切换视图，T 换主题 */
  document.addEventListener('keydown',function(e){
    if(e.target&&/input|textarea/i.test(e.target.tagName))return;
    var k=(e.key||'').toLowerCase();
    if(k==='1')show('today');
    else if(k==='2')show('review');
    else if(k==='3')show('bank');
    else if(k==='t'&&btn)btn.click();
  });
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
    var s=null,dur=750;
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
        '<div class="cd-banner"><span class="sheen"></span>'
        '<div class="cd-top"><div class="cd-kicker">COUNTDOWN · 距 初 试</div>'
        f'<div class="cd-date">{exam}<span class="cd-wd">周{wd}</span></div></div>'
        f'<div class="cd-mid">{digits}<span class="cd-unit">天</span></div>'
        '<div class="cd-bottom">'
        f'<div class="cd-equiv">≈ <b>{months}</b> 个月 · <b>{weeks}</b> 周 <b>+{rdays}</b> 天</div>'
        f'<div class="ms-track">{"".join(chips)}</div>'
        "</div></div>")


def _view_today(d):
    due = _priority_due(d["due"])
    st = d["status_counts"]
    total = d["total"]
    overdue = d["overdue"]
    inbox, pending = d["inbox"], d["pending"]

    # 行动头条
    pills = []
    if due:
        pills.append(f'<span class="hpill danger"><b class="count" data-n="{overdue}">0</b> 逾期</span>')
        if inbox:
            pills.append(f'<span class="hpill warn"><b class="count" data-n="{inbox}">0</b> 收件箱待处理</span>')
        pills.append(f'<span class="hpill ok"><b class="count" data-n="{d["reviewed_today"]}">0</b> 今日已复习</span>')
        pills.append(f'<span class="hpill"><b class="count" data-n="{d["streak"]}">0</b> 连续学习（天）</span>')
        tip = ('<b>从 ① 号开始做</b>——清单已按"逾期最久 → 错过最多 → 到期最早"排好。'
               '做完把结果告诉 AI（或拍照回传），状态与下次日期自动更新。')
    else:
        nxt = next((f for f in d["future"] if f["count"] > 0), None)
        if nxt:
            pills.append(f'<span class="hpill ok"><b>{html.escape(nxt["label"])}</b> 下一批到期</span>')
            pills.append(f'<span class="hpill ok"><b class="count" data-n="{nxt["count"]}">0</b> 届时需重做</span>')
            tip = f'下一批在 <b>{html.escape(nxt["label"])}</b>（{nxt["count"]} 道）。可以趁空档说「出重做单」打印一份，或让 AI 统计错因。'
        else:
            tip = '未来两周暂无到期。新错题录入后 FSRS 会自动排期。'
        pills.append(f'<span class="hpill"><b class="count" data-n="{d["streak"]}">0</b> 连续学习（天）</span>')
        if inbox:
            pills.append(f'<span class="hpill warn"><b class="count" data-n="{inbox}">0</b> 收件箱待处理</span>')
            tip = f'收件箱还有 <b>{inbox} 张</b>待处理——说「处理收件箱」即可归档。' + tip
    big_num = len(due) if due else 0
    wd = "一二三四五六日"[dt.date.fromisoformat(d["today"]).weekday()]
    month, dayn = int(d["today"][5:7]), int(d["today"][8:10])
    mint = f' · 距初试 {max(0, d["days_left"])} 天' if d["days_left"] is not None else ""
    if d["phase"]:
        mint += f' · {d["phase"]}阶段'
    em = d["est_minutes"]
    est_txt = f"{em} 分钟" if em < 60 else f"{em / 60:.1f} 小时"
    if due:
        pills.insert(1, f'<span class="hpill"><b>{est_txt}</b> 预计用时</span>')
    if due:
        greet_h = (f'<b class="count" data-n="{big_num}">0</b> 道题<br>'
                   '<span class="soft">等你重做</span>')
    elif d["future"] and next((f for f in d["future"] if f["count"] > 0), None):
        nxt = next(f for f in d["future"] if f["count"] > 0)
        greet_h = f'<span class="soft">今天没有到期</span><br>{html.escape(nxt["label"])} 再战'
    else:
        greet_h = '<span class="soft">今天没有到期</span>'
    greet = ('<section class="greet">'
             f'<div class="greet-date">星期{wd} · {month} 月 {dayn} 日{mint}</div>'
             f'<h1 class="greet-h"><span id="greetWord">下午好</span>，<br>{greet_h}</h1>'
             f'<p class="greet-sub">{tip}</p>'
             f'<div class="greet-pills">{"".join(pills)}</div></section>')
    banner = _countdown_banner(d)

    status_ring = _focus_ring(st, total, d["mastery"])
    goal = d["weekly_goal"]
    gpct = min(100, d["week_reviews"] / goal * 100) if goal else 0
    goal_card = (f'<div class="goal-line"><b>{d["week_reviews"]}</b><span>/ {goal} 道</span>'
                 f'<i>{gpct:.0f}%</i></div>'
                 f'<div class="goal-track"><i style="width:{gpct:.0f}%"></i></div>')
    side = (
        '<div class="side">'
        '<div class="panel">' + '<h2>' + _icon("load") + '未来 7 天负载</h2>' + _cols(d["future"][:7], today_idx=0) + "</div>"
        '<div class="panel">' + '<h2>' + _icon("ring") + '学习状态</h2>' + status_ring + "</div>"
        '<div class="panel">' + '<h2>' + _icon("target") + '本周目标</h2>' + goal_card + "</div>"
        '<div class="panel">' + '<h2>' + _icon("inbox") + '今日打卡</h2><div class="mini-stats">'
        + _stat_chip(_icon("flame"), d["streak"], "连续学习（天）")
        + _stat_chip(_icon("target"), d["reviewed_today"], "已复习（道）")
        + _stat_chip(_icon("trend"), d["week_new"], "本周新增")
        + _stat_chip(_icon("brain"), d["knowledge_items"], "知识库条目")
        + "</div></div></div>")

    main = ('<div class="panel">' + '<h2>' + _icon("due")
            + '今日该重做 <span class="hint">按轻重缓急排序 · 点题名跳转 Obsidian</span>'
            '<button class="pillbtn" onclick="window.print()">打印</button></h2>'
            + (_due_panel(d["due"]) if due else '<div class="zero-state">🎉 今天没有到期的错题</div>')
            + "</div>")
    return (f'<div id="v-today" class="view on">'
            f'<div class="hero-grid">{greet}{banner}</div>'
            f'<div class="grid g21">{main}{side}</div></div>')


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
        + '<div class="panel" style="margin-bottom:20px">' + '<h2>' + _icon("brain") + '本周洞察</h2>'
        + '<div class="insight"><div class="insight-list">' + _insights_html(d) + "</div>"
        + '<div><div class="legend" style="justify-content:flex-start;margin:0 0 8px">科目掌握率（越低越该补）</div>'
        + _msub_html(d) + "</div></div></div>"
        + '<div class="grid g35">'
        '<div class="panel">' + '<h2>' + _icon("target") + "学习进度</h2>" + _funnel(st, total, d["mastery"]) + "</div>"
        '<div class="panel">' + '<h2>' + _icon("pie") + '科目分布 <span class="hint">环形 + 状态构成</span></h2>'
        + _ring(d["subject_counts"], SUBJ_COLORS, total, "道错题")
        + '<div style="margin-top:14px">' + _stack_rows(d["subject_status"]) + "</div></div></div>"
        '<div class="grid g73">'
        '<div class="panel">' + '<h2>' + _icon("heat") + '学习活动热力图 <span class="hint">近 16 周 · 每日新增错题</span></h2>'
        + _heatmap(d["heatmap"], d["today"]) + "</div>"
        '<div class="panel">' + '<h2>' + _icon("trend") + '新增 vs 复习 <span class="hint">近 8 周</span></h2>'
        + _dual_spark(d["week_trend"], d["review_series"]) + "</div></div>"
        '<div class="grid g3">'
        '<div class="panel">' + '<h2>' + _icon("alert") + "错因分布</h2>" + _bars(d["error_counts"], _ERROR_COLORS) + "</div>"
        '<div class="panel">' + '<h2>' + _icon("book") + "哪本书错得最多</h2>" + _bars(d["book_counts"]) + "</div>"
        '<div class="panel">' + '<h2>' + _icon("brain") + "知识点 Top 10</h2>" + _bars(d["topic_counts"]) + "</div></div>")
    return f'<div id="v-review" class="view">{body}</div>'


def _view_bank(d):
    ach = "".join(
        f'<span class="ach{" done" if a["done"] else ""}"><span class="em">{a["icon"]}</span>'
        f'<b>{html.escape(a["name"])}</b></span>' for a in d["achievements"])
    body = (
        '<div class="ach-strip">' + ach + "</div>"
        '<div class="grid g21">'
        '<div class="panel">' + '<h2>' + _icon("trophy") + '高频错题榜 <span class="hint">错过 ≥2 次 · 点击题名跳转</span></h2>'
        + _high_table(d["high"]) + "</div>"
        '<div class="panel">' + '<h2>' + _icon("clock") + "最近录入</h2>" + _recent_table(d["recent"]) + "</div></div>")
    return f'<div id="v-bank" class="view">{body}</div>'


def render(d):
    total = d["total"]
    st = d["status_counts"]
    exam_line = d["exam_date"] or ""
    cd_chip = ""
    if d["days_left"] is not None:
        cd_chip = (f'<span class="tchip" title="初试 {html.escape(exam_line)}（估算）">'
                   f'<b>D-{max(0, d["days_left"])}</b>&nbsp;距初试</span>')
    streak_chip = (f'<span class="tchip keep"><b>{d["streak"]}</b>&nbsp;天连续</span>'
                   if d["streak"] else "")

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
        '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true" stroke="#fff" '
        'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="4" width="13" height="17" rx="2.5"/>'
        '<path d="M7 8.5h5M7 12h5M7 15.5h3"/>'
        '<circle cx="16.5" cy="16.5" r="4.5"/>'
        '<path d="M14.6 16.5l1.4 1.4 2.6-2.9"/>'
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
            f'<div class="brand"><span class="appicon">{brand_svg}</span>'
            '<span class="bname">考研工作台</span><span class="bver">v7</span></div>'
            f'{tabs}'
            f'<div class="tchips">{cd_chip}{streak_chip}'
            f'<button class="tbtn" id="themeBtn" title="切换深浅色">{sun}{moon}</button></div></nav>'
            "<main>" + body + "</main>"
            f'<div class="foot">星期{d["weekday"]} · {d["today"]} · 生成于 {d["generated_at"]} · '
            "说「刷新工作台」重新生成 · F5 看最新 · 数据全部来自本地错题笔记<br>"
            "快捷键 <span class=\"kbd\">1</span> 今日 <span class=\"kbd\">2</span> 复盘 "
            "<span class=\"kbd\">3</span> 题库 <span class=\"kbd\">T</span> 换主题</div>"
            "</div><script>" + _JS + "</script></body></html>")