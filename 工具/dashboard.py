#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作台渲染器：把 库维护.py 扫描好的统计数据渲染成单文件 HTML 仪表盘。

纯标准库、零外部依赖、零 CDN。数据由 库维护.py 的 dashboard 子命令准备，
本模块只负责"长什么样"，便于单独迭代视觉而不动数据逻辑。
"""
import datetime as dt
import html

SUBJ_COLORS = {"数学": "#5b7cfa", "英语": "#17a673", "政治": "#e8a33d", "专业课": "#9a5fd0"}
SUBJ_ORDER = ["数学", "英语", "政治", "专业课", "其它"]
STATUS_COLORS = {"未掌握": "#f0642d", "复习中": "#4c6ef5", "已掌握": "#17a673"}
_ERROR_COLORS = {"概念不清": "#5b7cfa", "条件误用": "#17a673", "公式记错": "#e8a33d",
                 "计算失误": "#9a5fd0", "思路不会": "#f0642d", "审题失误": "#0ca678",
                 "知识盲区": "#f08c00", "表达问题": "#748ffc", "时间不够": "#8a94a6",
                 "待确认": "#adb5bd", "（空）": "#adb5bd"}


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
    for label, count in dist:
        pct = count / total * 100
        color = SUBJ_COLORS.get(label, "#8a94a6")
        segs.append(
            f'<circle cx="21" cy="21" r="15.9155" fill="none" stroke="{color}" stroke-width="6.4" '
            f'pathLength="100" stroke-dasharray="{pct:.2f} {max(0.01, 100 - pct):.2f}" '
            f'stroke-dashoffset="{-acc:.2f}" transform="rotate(-90 21 21)"><title>{html.escape(str(label))} {count}</title></circle>')
        acc += pct
    legend = "".join(
        f'<span class="lg"><i style="background:{SUBJ_COLORS.get(l, "#8a94a6")}"></i>'
        f'{html.escape(str(l))}<b>{c}</b></span>' for l, c in dist)
    return (f'<div class="donut-wrap"><svg viewBox="0 0 42 42" class="donut">{"".join(segs)}</svg>'
            f'<div class="donut-cap"><b>{total}</b><small>{html.escape(cap)}</small></div></div>'
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
                f'<i style="width:{c / tot * 100:.1f}%;background:{STATUS_COLORS[st]}" '
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
            f'<span class="btrack"><i style="width:{w:.1f}%;background:{color}"></i></span>'
            f'<span class="bnum">{count}<small>{pct:.0f}%</small></span></div>')
    return "".join(out)


def _cols(pairs, unit="道", today_idx=None):
    maxc = max((p["count"] for p in pairs), default=0) or 1
    cells = []
    for i, p in enumerate(pairs):
        c = p["count"]
        h = 8 + c / maxc * 88
        cls = " today" if (today_idx is not None and i == today_idx) else ""
        val = f"{c}" if c else ""
        cells.append(
            f'<div class="col{cls}" title="{html.escape(p["label"])} · {c} {unit}">'
            f'<span class="cv">{val}</span>'
            f'<i style="height:{h:.0f}px"></i>'
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
        chips.append(f'<button class="chip" data-f="{html.escape(subj)}">{html.escape(subj)} {c}</button>')
    items = []
    for x in due:
        color = SUBJ_COLORS.get(x["subject"], "#8a94a6")
        if x["overdue"] > 0:
            due_tag = f'<span class="due-tag over">逾期 {x["overdue"]} 天</span>'
        else:
            due_tag = '<span class="due-tag">今天</span>'
        wc = f'<span class="wc" title="累计做错 {x["wrong_count"]} 次">×{x["wrong_count"]}</span>' if x["wrong_count"] else ""
        items.append(
            f'<div class="due" data-subject="{html.escape(x["subject"])}">'
            f'<span class="stag" style="color:{color};background:{_rgba(color, 0.12)}">{html.escape(x["subject"])}</span>'
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
        f'<i style="width:{status_counts[s] / total * 100:.1f}%;background:{STATUS_COLORS[s]}" '
        f'title="{s} {status_counts[s]} 道"></i>' for s in ("未掌握", "复习中", "已掌握") if status_counts[s])
    rows = "".join(
        f'<div class="f-row"><span class="lg"><i style="background:{STATUS_COLORS[s]}"></i>{s}</span>'
        f'<b>{status_counts[s]}</b><small>{status_counts[s] / total * 100:.0f}%</small></div>'
        for s in ("未掌握", "复习中", "已掌握"))
    return (f'<div class="mastery"><b>{mastery:.0f}%</b><span>掌握率</span></div>'
            f'<div class="stack big">{segs}</div><div class="f-rows">{rows}</div>')


def _empty_state():
    return (
        '<div class="panel empty-big">'
        '<svg viewBox="0 0 120 120" class="empty-svg" aria-hidden="true">'
        '<rect x="22" y="18" width="66" height="84" rx="8" fill="none" stroke="currentColor" stroke-width="4"/>'
        '<path d="M36 42h38M36 56h38M36 70h22" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>'
        '<circle cx="82" cy="82" r="20" fill="none" stroke="#5b7cfa" stroke-width="4"/>'
        '<path d="M73 82l6 6 12-13" fill="none" stroke="#5b7cfa" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
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
  --bg:#f3f4f7; --bg2:#eceef3; --card:#ffffff; --ink:#1b2130; --sub:#667085;
  --line:#e4e7ee; --accent:#4c6ef5; --accent2:#6b8bff; --warn:#e8590c; --ok:#17a673;
  --shadow:0 1px 2px rgba(16,24,40,.04),0 8px 24px rgba(16,24,40,.05);
  --h0:#eceef3; --h1:#d7e0ff; --h2:#a5b8ff; --h3:#5b7cfa; --h4:#2f4fd8;
  --gold:#f5b301;
}
html[data-theme="dark"]{
  --bg:#0e1117; --bg2:#12161f; --card:#161b26; --ink:#e7ebf3; --sub:#8b94a7;
  --line:#232a38; --accent:#7c93ff; --accent2:#5b7cfa; --warn:#ff7a45; --ok:#2fbf8f;
  --shadow:0 1px 2px rgba(0,0,0,.5),0 10px 30px rgba(0,0,0,.35);
  --h0:#1c2331; --h1:#26314c; --h2:#35457c; --h3:#4a63d8; --h4:#7c93ff;
  --gold:#ffd04d;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{
  font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  background:var(--bg);color:var(--ink);padding:22px 18px 56px;line-height:1.45;
  transition:background .25s ease,color .25s ease;
}
.wrap{max-width:1140px;margin:0 auto}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.muted{color:var(--sub);font-size:13px}
small{font-weight:400}

/* ── 头部 ── */
.hero{margin-bottom:18px}
.hrow{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:14px}
h1{font-size:24px;letter-spacing:.5px}
.sub{color:var(--sub);font-size:12.5px;margin-top:3px}
.hbtns{display:flex;gap:8px}
.tbtn{
  border:1px solid var(--line);background:var(--card);color:var(--ink);
  border-radius:10px;padding:8px 12px;font-size:13px;cursor:pointer;box-shadow:var(--shadow);
  transition:transform .15s ease,border-color .15s ease;
}
.tbtn:hover{transform:translateY(-1px);border-color:var(--accent)}
.hero-grid{display:grid;grid-template-columns:280px 1fr;gap:14px}
.cd-card{
  background:linear-gradient(135deg,var(--accent) 0%,#7a5cff 100%);
  color:#fff;border-radius:16px;padding:18px 20px;box-shadow:var(--shadow);
  display:flex;flex-direction:column;gap:6px;position:relative;overflow:hidden;
}
.cd-card::after{
  content:"";position:absolute;right:-40px;top:-40px;width:140px;height:140px;
  border-radius:50%;background:rgba(255,255,255,.14);
}
.cd-label{font-size:12px;opacity:.85;letter-spacing:2px}
.cd-num{font-size:46px;font-weight:800;line-height:1.05;font-variant-numeric:tabular-nums}
.cd-num small{font-size:15px;font-weight:500;margin-left:4px;opacity:.85}
.cd-date{font-size:12px;opacity:.8}
.cd-foot{margin-top:auto;padding-top:10px;border-top:1px solid rgba(255,255,255,.25);font-size:12.5px;opacity:.95}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.kpi{
  background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px 16px;
  box-shadow:var(--shadow);transition:transform .15s ease,border-color .15s ease;
}
.kpi:hover{transform:translateY(-2px);border-color:var(--accent)}
.kpi-n{font-size:26px;font-weight:800;font-variant-numeric:tabular-nums;line-height:1.15}
.kpi-n.t-warn{color:var(--warn)}
.kpi-n.t-ok{color:var(--ok)}
.kpi-l{font-size:12.5px;color:var(--sub);margin-top:1px}
.kpi-s{font-size:11.5px;color:var(--sub);opacity:.8}

/* ── 版式 ── */
.grid{display:grid;gap:14px;margin-bottom:14px}
.g32{grid-template-columns:3fr 2fr}
.g23{grid-template-columns:2fr 3fr}
.g3{grid-template-columns:1fr 1fr 1fr}
.g32.b{grid-template-columns:3fr 2fr}
.panel{
  background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;
  box-shadow:var(--shadow);min-width:0;
}
.panel h2{font-size:14.5px;font-weight:700;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.panel h2 .hint{font-size:11.5px;color:var(--sub);font-weight:400;margin-left:auto}
.zero-state{color:var(--sub);font-size:13.5px;padding:26px 0;text-align:center}

/* ── 到期清单 ── */
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.chip{
  border:1px solid var(--line);background:transparent;color:var(--sub);border-radius:999px;
  padding:4px 11px;font-size:12px;cursor:pointer;transition:all .15s ease;
}
.chip:hover{border-color:var(--accent);color:var(--accent)}
.chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.due-list{display:flex;flex-direction:column;max-height:436px;overflow-y:auto;padding-right:4px}
.due-list::-webkit-scrollbar{width:8px}
.due-list::-webkit-scrollbar-thumb{background:var(--line);border-radius:4px}
.due{
  display:flex;align-items:center;gap:9px;padding:9px 2px;
  border-bottom:1px dashed var(--line);font-size:13.5px;
}
.due:last-child{border-bottom:none}
.due-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}
.due-main .note{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tp{font-style:normal;font-size:11.5px;color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.stag{font-size:11px;padding:2px 9px;border-radius:8px;font-weight:600;white-space:nowrap}
.wc{
  font-size:11px;color:var(--warn);border:1px solid var(--warn);border-radius:8px;
  padding:1px 7px;white-space:nowrap;
}
.due-tag{font-size:11.5px;color:var(--sub);white-space:nowrap}
.due-tag.over{color:var(--warn);font-weight:600}

/* ── 图表 ── */
.donut-wrap{position:relative;width:170px;height:170px;margin:4px auto 6px}
.donut{width:100%;height:100%}
.donut-cap{
  position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
  pointer-events:none;
}
.donut-cap b{font-size:26px;font-weight:800;font-variant-numeric:tabular-nums}
.donut-cap small{font-size:11px;color:var(--sub)}
.legend{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;font-size:12px;color:var(--sub);margin-top:6px}
.legend .lg{display:inline-flex;align-items:center;gap:5px}
.legend .lg b{color:var(--ink);margin-left:2px}
.legend i{width:9px;height:9px;border-radius:3px;display:inline-block}
.srow{display:flex;align-items:center;gap:9px;margin:8px 0;font-size:12.5px}
.slb{flex:0 0 46px;font-weight:600}
.stack{flex:1;height:12px;background:var(--bg2);border-radius:6px;overflow:hidden;display:flex}
.stack i{display:block;height:100%}
.stack.big{height:18px;border-radius:9px;margin:10px 0 14px}
.empty-seg{flex:1;background:var(--bg2)}
.snum{flex:0 0 26px;text-align:right;color:var(--sub);font-weight:600}
.brow{display:flex;align-items:center;gap:8px;margin:7px 0;font-size:12.5px}
.blb{flex:0 0 108px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.btrack{flex:1;height:10px;background:var(--bg2);border-radius:5px;overflow:hidden}
.btrack i{display:block;height:100%;border-radius:5px;transition:width .5s ease}
.bnum{flex:0 0 44px;text-align:right;color:var(--sub);font-weight:600}
.bnum small{font-size:10.5px;margin-left:3px;opacity:.75}
.cols{display:flex;align-items:flex-end;gap:7px;height:132px;padding-top:16px}
.col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:3px;position:relative}
.col i{display:block;width:66%;border-radius:4px 4px 0 0;background:linear-gradient(180deg,var(--accent2),var(--accent));min-height:4px;transition:height .5s ease}
.col.today i{background:linear-gradient(180deg,#ff9a5c,var(--warn))}
.col .cv{font-size:10.5px;color:var(--sub);height:14px}
.col em{font-style:normal;font-size:10px;color:var(--sub);white-space:nowrap}
.mastery{display:flex;align-items:baseline;gap:8px}
.mastery b{font-size:40px;font-weight:800;color:var(--ok);font-variant-numeric:tabular-nums}
.mastery span{color:var(--sub);font-size:12.5px}
.f-rows{display:flex;flex-direction:column;gap:6px;font-size:12.5px}
.f-row{display:flex;align-items:center;gap:8px}
.f-row b{margin-left:auto}
.f-row small{color:var(--sub);flex:0 0 42px;text-align:right}

/* ── 热力图 ── */
.heat-wrap{display:flex;gap:8px}
.hweeks{display:flex;flex-direction:column;gap:3px;font-size:9.5px;color:var(--sub);padding-top:19px}
.hweeks span{height:12px;line-height:12px;display:block}
.heat-main{flex:1;min-width:0}
.hlabels{display:flex;gap:3px;font-size:9.5px;color:var(--sub);margin-bottom:4px}
.hlabels span{flex:1;text-align:left;white-space:nowrap;overflow:hidden}
.hgrid{display:flex;gap:3px}
.hcol{display:flex;flex-direction:column;gap:3px;flex:1}
.hcell{display:block;height:12px;border-radius:3px;background:var(--h0)}
.hcell.fut{background:transparent}
.hcell.lv0{background:var(--h0)}
.hcell.lv1{background:var(--h1)}
.hcell.lv2{background:var(--h2)}
.hcell.lv3{background:var(--h3)}
.hcell.lv4{background:var(--h4)}
.hlegend{display:flex;align-items:center;gap:3px;justify-content:flex-end;margin-top:6px;font-size:10.5px;color:var(--sub)}
.hlegend .hcell{width:12px;height:12px}
.hlegend span{margin:0 3px}

/* ── 表格 ── */
.tbl{width:100%;border-collapse:collapse;font-size:12.8px}
.tbl th{text-align:left;color:var(--sub);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap;font-size:11.5px}
.tbl td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
.tbl tr:last-child td{border-bottom:none}
.tbl tbody tr{transition:background .15s ease}
.tbl tbody tr:hover{background:var(--bg2)}
.td-note{max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.td-tp{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--sub)}
.td-date{color:var(--sub);white-space:nowrap}
.rank{
  display:inline-flex;width:20px;height:20px;align-items:center;justify-content:center;
  border-radius:6px;background:var(--bg2);color:var(--sub);font-size:11px;font-weight:700;
}
.rank.gold{background:var(--gold);color:#3a2a00}
.rank.silver{background:#c9d2e3;color:#26303f}
.rank.bronze{background:#e0b48c;color:#4a2f14}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
.wcbig{font-size:14px;color:var(--warn)}
.pill{font-size:11px;padding:2px 9px;border-radius:999px;white-space:nowrap}
.p-未掌握{color:#f0642d;background:rgba(240,100,45,.12)}
.p-复习中{color:#4c6ef5;background:rgba(76,110,245,.12)}
.p-已掌握{color:#17a673;background:rgba(23,166,115,.12)}
html[data-theme="dark"] .p-未掌握{color:#ff8a5c;background:rgba(255,122,69,.15)}
html[data-theme="dark"] .p-复习中{color:#8ea4ff;background:rgba(124,147,255,.15)}
html[data-theme="dark"] .p-已掌握{color:#4fd6a5;background:rgba(47,191,143,.15)}

/* ── 空状态 ── */
.empty-big{text-align:center;padding:56px 20px}
.empty-svg{width:110px;height:110px;color:var(--sub);opacity:.55;margin-bottom:14px}
.empty-big h2{display:block;justify-content:center;font-size:17px;margin-bottom:8px}
.steps{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-top:16px}
.step{
  background:var(--bg2);border:1px solid var(--line);border-radius:12px;padding:14px 16px;
  font-size:12.5px;min-width:180px;text-align:left;
}
.step b{
  display:inline-flex;width:22px;height:22px;border-radius:50%;background:var(--accent);
  color:#fff;align-items:center;justify-content:center;font-size:12px;margin-right:6px;
}
.step small{color:var(--sub)}

/* ── 页脚与响应式 ── */
.foot{color:var(--sub);font-size:11.5px;text-align:center;margin-top:24px;line-height:1.8}
@media (max-width:980px){
  .hero-grid{grid-template-columns:1fr}
  .kpis{grid-template-columns:repeat(3,1fr)}
  .g32,.g23,.g3{grid-template-columns:1fr}
}
@media (max-width:560px){
  body{padding:14px 10px 40px}
  .kpis{grid-template-columns:repeat(2,1fr)}
  h1{font-size:20px}
  .cd-num{font-size:38px}
}
@media print{
  body{background:#fff;color:#000}
  .hbtns,.chips{display:none}
  .panel,.kpi,.cd-card{box-shadow:none;border:1px solid #ddd}
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
  var els=document.querySelectorAll('.count');
  els.forEach(function(el){
    var n=parseInt(el.dataset.n||'0',10);
    if(!isFinite(n)||n>100000){el.textContent=n;return;}
    var s=null,dur=650;
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
    exam_line = (f'{d["exam_date"]}（估算日期）' if d["exam_date"]
                 else "初试日期未配置（去 个人配置.md 填一行）")
    days_left = d["days_left"]
    if days_left is None:
        cd_num = '<span class="count" data-n="0">—</span>'
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
            '<div class="grid g32">'
            '<div class="panel"><h2>今日该重做 <span class="hint">next_review 到期 · 点题名跳转 Obsidian</span></h2>'
            + _due_panel(due) + "</div>"
            '<div class="panel"><h2>未来两周复习负载 <span class="hint">每天到期数</span></h2>'
            + _cols(d["future"], today_idx=0) + "</div></div>"
            '<div class="grid g23">'
            '<div class="panel"><h2>学习进度</h2>' + _funnel(st, total, d["mastery"]) + "</div>"
            '<div class="panel"><h2>科目分布 <span class="hint">环形 + 各科状态构成</span></h2>'
            + _donut(d["subject_counts"], total, "道错题")
            + '<div style="margin-top:12px">' + _stack_rows(d["subject_status"]) + "</div></div></div>"
            '<div class="grid g32">'
            '<div class="panel"><h2>学习活动热力图 <span class="hint">近 16 周 · 每日新增错题</span></h2>'
            + _heatmap(d["heatmap"], d["today"]) + "</div>"
            '<div class="panel"><h2>近 8 周新增 <span class="hint">每周错题量</span></h2>'
            + _cols(d["week_trend"]) + "</div></div>"
            '<div class="grid g3">'
            '<div class="panel"><h2>错因分布</h2>' + _bars(d["error_counts"], _ERROR_COLORS) + "</div>"
            '<div class="panel"><h2>哪本书错得最多</h2>' + _bars(d["book_counts"]) + "</div>"
            '<div class="panel"><h2>知识点 Top 10</h2>' + _bars(d["topic_counts"]) + "</div></div>"
            '<div class="grid g32 b">'
            '<div class="panel"><h2>高频错题榜 <span class="hint">点击题名跳转</span></h2>'
            + _high_table(d["high"]) + "</div>"
            '<div class="panel"><h2>最近录入</h2>' + _recent_table(d["recent"]) + "</div></div>")
    else:
        body = _empty_state()

    head_theme = (
        "<script>(function(){try{var t=localStorage.getItem('ky-theme')||"
        "(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');"
        "document.documentElement.dataset.theme=t}catch(e){}})();</script>"
    )
    return ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light dark">'
            "<title>考研错题工作台</title>" + head_theme +
            "<style>" + _CSS + "</style></head><body><div class=\"wrap\">"
            '<header class="hero"><div class="hrow"><div>'
            "<h1>考研错题工作台</h1>"
            f'<div class="sub">星期{d["weekday"]} · {d["today"]} · 数据快照 {d["generated_at"]}'
            " · 由 工具/库维护.py dashboard 生成</div></div>"
            '<div class="hbtns"><button class="tbtn" id="themeBtn" title="切换深浅色">◐ 主题</button></div></div>'
            '<div class="hero-grid">'
            '<div class="cd-card">'
            '<div class="cd-label">距 初 试</div>'
            f'<div class="cd-num">{cd_num}{cd_unit}</div>'
            f'<div class="cd-date">{html.escape(exam_line)}</div>'
            f'<div class="cd-foot">{streak_txt}</div></div>'
            f'<div class="kpis">{kpis}</div></div></header>'
            "<main>" + body + "</main>"
            '<div class="foot">数据全部来自本地错题笔记（错题/ 目录）· 说「刷新工作台」重新生成<br>'
            "预测区间由 FSRS-4.5 按各题复习历史计算 · 状态以笔记文件现值为准</div>"
            "</div><script>" + _JS + "</script></body></html>")