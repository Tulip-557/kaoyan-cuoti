#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""库维护脚本：错题库的 lint / 统计 / 到期清单 / FSRS 调度（纯标准库，零第三方依赖）。

AI 在会话开场、统计类请求、更新重做调度时优先调用本脚本；脚本失败才人工遍历。
用法:
  python 工具/库维护.py due                                   # 今日到期错题 + 收件箱积压
  python 工具/库维护.py stats [--week]                        # 按科目/错因/topic/book 统计（--week 只看本周）
  python 工具/库维护.py lint                                  # 错题笔记 frontmatter 合规校验
  python 工具/库维护.py fsrs --history "2026-10-01:3,2026-10-05:1" --rating 3
  python 工具/库维护.py check-agents                          # AGENTS.md 字符数检查
  python 工具/库维护.py dashboard                             # 生成 工作台.html 本地仪表盘
"""
import argparse
import html
import datetime as dt
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODAY = dt.date.today()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── 与《分类规则》一致的取值表 ────────────────────────────────────────────
SUBJECTS = {"数学", "英语", "政治", "专业课"}
TYPES = {
    "数学": {"选择", "填空", "计算", "证明", "应用"},
    "英语": {"完形", "阅读", "新题型", "翻译", "写作", "词汇", "长难句"},
    "政治": {"单选", "多选", "材料分析", "时政"},
    "专业课": {"计算", "分析", "设计", "简答", "证明", "画图"},
}
ERRORS = {"概念不清", "条件误用", "公式记错", "计算失误", "思路不会",
          "审题失误", "知识盲区", "表达问题", "时间不够", "待确认"}
STATUSES = {"未掌握", "复习中", "已掌握"}
WEIGHTS = {"重点", "一般", "了解"}
REQUIRED_KEYS = ["subject", "module", "type", "method", "topic", "error", "status",
                 "weight", "book", "source", "date", "reviews", "next_review",
                 "wrong_count", "tags"]

# ── FSRS-4.5（open-spaced-repetition，默认参数；复习记录 ≥100 次后可用官方优化器调参）──
W = [0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.031,
     1.6474, 0.1367, 1.0461, 2.1072, 0.0793, 0.3246, 1.587, 0.2272, 2.8755]
DECAY, FACTOR, RETENTION = -0.5, 19 / 81, 0.9


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def retrievability(days, s):
    return (1 + FACTOR * days / s) ** DECAY if days > 0 and s > 0 else 1.0


def next_interval(s):
    """使遗忘曲线恰好落到目标保留率的天数。"""
    return max(1, round((s / FACTOR) * (RETENTION ** (1 / DECAY) - 1)))


def fsrs_schedule(history, rating):
    """history: [(date, rating1-4)] 从早到晚（首次复习视同初学）；rating: 本次评级。
    返回 (interval_days, stability, difficulty)。"""
    if history:
        d0, r0 = history[0]
        s, d = W[r0 - 1], clamp(W[4] - (r0 - 3) * W[5], 1, 10)
        for (d_prev, _), (d_cur, g) in zip(history, history[1:]):
            s, d = _apply(s, d, (d_cur - d_prev).days, g)
        elapsed = (TODAY - history[-1][0]).days
    else:
        s, d, elapsed = -1.0, -1.0, 0
    if s < 0:  # 首次复习 = 初学
        s = W[rating - 1]
        d = clamp(W[4] - (rating - 3) * W[5], 1, 10)
    else:
        s, d = _apply(s, d, elapsed, rating)
    return next_interval(s), s, d


def _apply(s, d, elapsed, g):
    r = retrievability(elapsed, s)
    if g == 1:  # 重忘：w11-w14 是重忘后的稳定度参数
        s_new = W[11] * d ** (-W[12]) * ((s + 1) ** W[13] - 1) * math.exp(W[14] * (1 - r))
    else:       # 记起：w8-w10 稳定度增长，w15 困难惩罚，w16 简单奖励
        s_new = s * (1 + math.exp(W[8]) * (11 - d) * s ** (-W[9])
                     * (math.exp(W[10] * (1 - r)) - 1)
                     * (W[15] if g == 2 else 1) * (W[16] if g == 4 else 1))
    d = d - W[6] * (g - 3)
    d = clamp(W[7] * W[4] + (1 - W[7]) * d, 1, 10)  # 均值回归，锚定正常评级的初始难度
    return max(0.1, s_new), d


# ── frontmatter 解析（覆盖本库用到的子集：标量 / 内联列表 / 块列表）──────────
def parse_frontmatter(text):
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    block, body = text[3:end], text[end + 4:]
    props, cur = {}, None
    for raw in block.splitlines():
        if not raw.strip() or raw.strip() == "---":
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", raw)
        if m and not raw.startswith((" ", "\t", "-")):
            key, val = m.group(1), m.group(2).strip()
            if val == "":
                cur, props[key] = key, []
            elif val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                props[key] = [v.strip().strip("\"'") for v in inner.split(",")] if inner else []
                cur = None
            else:
                props[key], cur = val.strip("\"'"), None
        elif raw.lstrip().startswith("-") and cur:
            props[cur].append(raw.lstrip()[1:].strip().strip("\"'"))
    return props, body


def error_notes():
    """遍历错题目录，产出 (path, props, text)。跳过索引。"""
    for sub in sorted((ROOT / "错题").glob("*")):
        if not sub.is_dir():
            continue
        for f in sorted(sub.glob("*.md")):
            if "索引" in f.name:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            props, _ = parse_frontmatter(text)
            if props is not None:
                yield f, props, text


def load_books():
    """从 个人配置.md 的材料表解析 book 取值。"""
    books = {"其它"}
    cfg = ROOT / "个人配置.md"
    if cfg.exists():
        in_table = False
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("## 材料"):
                in_table = True
                continue
            if in_table and line.startswith("## "):
                break
            if in_table and line.strip().startswith("|") and not line.strip().startswith("| book"):
                name = line.strip().strip("|").split("|")[0].strip()
                if name and name != "---" and "/" not in name:
                    books.update(name.split(" / "))
                elif name and "/" in name:
                    books.update(n.strip() for n in name.split("/"))
    return books


def date_of(v):
    try:
        return dt.date.fromisoformat(str(v).strip()[:10])
    except (ValueError, TypeError):
        return None


# ── 子命令 ────────────────────────────────────────────────────────────────
def cmd_due(_):
    due = []
    for f, p, _t in error_notes():
        nr, st = date_of(p.get("next_review")), p.get("status", "")
        if nr and nr <= TODAY and st != "已掌握":
            due.append((p.get("subject", "?"), f.name, p.get("topic"), nr))
    inbox = [x.name for x in (ROOT / "收件箱").iterdir()
             if x.is_file() and x.name != "说明.md"] if (ROOT / "收件箱").exists() else []
    pending = [x.name for x in (ROOT / "收件箱" / "待确认").iterdir()
               if x.is_file() and x.name != "说明.md"] if (ROOT / "收件箱" / "待确认").exists() else []
    print(f"今日到期错题: {len(due)} 道；收件箱待处理: {len(inbox)} 张；待确认区: {len(pending)} 张")
    for sub, name, topic, nr in sorted(due, key=lambda x: (x[0], x[3])):
        print(f"  [到期 {nr}] {sub} · {name} · {topic}")
    if pending:
        print("  待确认区文件：" + "、".join(pending))


def cmd_stats(args):
    notes = list(error_notes())
    if args.week:
        monday = TODAY - dt.timedelta(days=TODAY.weekday())
        notes = [(f, p, t) for f, p, t in notes
                 if (d := date_of(p.get("date"))) and d >= monday]
    print(f"范围: {'本周' if args.week else '全部'} · 错题总数: {len(notes)}")
    for key, title in [("subject", "科目"), ("error", "错因"), ("status", "状态"), ("book", "材料")]:
        dist = {}
        for _f, p, _t in notes:
            dist[p.get(key, "（空）")] = dist.get(p.get(key, "（空）"), 0) + 1
        print(f"{title}: " + " · ".join(f"{k} {v}" for k, v in sorted(dist.items(), key=lambda x: -x[1])))
    topics = {}
    for _f, p, _t in notes:
        tv = p.get("topic")
        for t in (tv if isinstance(tv, list) else [tv]):
            if t:
                topics[t] = topics.get(t, 0) + 1
    top = sorted(topics.items(), key=lambda x: -x[1])[:10]
    print("知识点 Top: " + (" · ".join(f"{k} {v}" for k, v in top) if top else "（暂无）"))


def cmd_lint(_):
    problems, books = [], load_books()
    count = 0
    for f, p, _t in error_notes():
        count += 1
        rel = f.relative_to(ROOT)
        miss = [k for k in REQUIRED_KEYS if k not in p]
        if miss:
            problems.append(f"{rel}: 缺属性 {','.join(miss)}")
        if p.get("subject") not in SUBJECTS:
            problems.append(f"{rel}: subject 非法 → {p.get('subject')}")
        elif p.get("type") and p["type"] not in TYPES[p["subject"]]:
            problems.append(f"{rel}: type 非法 → {p['type']}")
        if p.get("error") not in ERRORS:
            problems.append(f"{rel}: error 非法 → {p.get('error')}")
        if p.get("status") not in STATUSES:
            problems.append(f"{rel}: status 非法 → {p.get('status')}")
        if p.get("weight") not in WEIGHTS:
            problems.append(f"{rel}: weight 非法 → {p.get('weight')}")
        if p.get("book") and p["book"] not in books:
            problems.append(f"{rel}: book 不在《个人配置》材料表 → {p['book']}")
        for k in ("date", "next_review"):
            if k in p and not date_of(p[k]):
                problems.append(f"{rel}: {k} 不是 YYYY-MM-DD → {p[k]}")
        d, nr = date_of(p.get("date")), date_of(p.get("next_review"))
        if d and nr and nr < d:
            problems.append(f"{rel}: next_review 早于 date")
        wc = p.get("wrong_count")
        try:
            if int(wc) < 1:
                raise ValueError
        except (TypeError, ValueError):
            problems.append(f"{rel}: wrong_count 应为 ≥1 整数 → {wc}")
        tags = p.get("tags", [])
        tags = tags if isinstance(tags, list) else [tags]
        if "错题" not in tags:
            problems.append(f"{rel}: tags 缺「错题」")
        if int(wc or 1) >= 3 and "高频错题" not in tags:
            problems.append(f"{rel}: wrong_count≥3 但缺「高频错题」标签")
    print(f"lint 完成：{count} 道错题，{len(problems)} 处问题")
    for p in problems:
        print("  ⚠ " + p)


def cmd_fsrs(args):
    history = []
    if args.history:
        for pair in args.history.split(","):
            d, r = pair.strip().rsplit(":", 1)
            history.append((date_of(d), int(r)))
        history = [(d, r) for d, r in history if d and 1 <= r <= 4]
        history.sort()
    ivl, s, d = fsrs_schedule(history, args.rating)
    nxt = TODAY + dt.timedelta(days=ivl)
    print(f"本次评级 {args.rating}（1重忘 2困难 3正常 4简单）· 历史复习 {len(history)} 次")
    print(f"FSRS 建议间隔: {ivl} 天 → next_review: {nxt.isoformat()}（稳定度 S={s:.2f}，难度 D={d:.1f}）")
    print("写入笔记时：next_review 用上面的日期；reviews 追加今天；status 按 AGENTS.md 一.6 映射。")


def cmd_check_agents(_):
    f = ROOT / "AGENTS.md"
    chars = len(f.read_text(encoding="utf-8"))
    hard, soft = 8000, 5000
    print(f"AGENTS.md 字符数: {chars}（注入硬上限 {hard}，本库目标 ≤{soft}）")
    if chars > hard:
        print("  ✗ 已超硬上限——WorkBuddy 等工具会静默截断，必须瘦身！")
    elif chars > soft:
        print("  ⚠ 超过目标值，继续往里加内容前先外移细节")
    else:
        print("  ✓ 在目标范围内")


# ── 工作台（dashboard）：从错题笔记生成单文件 HTML 仪表盘 ──────────────────
_DASH_CSS = """
:root{--bg:#f5f6f8;--card:#fff;--ink:#1f2430;--sub:#6b7280;--line:#e5e7eb;--accent:#4c6ef5;--warn:#e8590c}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;background:var(--bg);color:var(--ink);padding:24px 16px 48px}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:22px;margin-bottom:4px}
.meta{color:var(--sub);font-size:13px;margin-bottom:20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:12px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.card .n{font-size:26px;font-weight:700}
.card .t{font-size:12px;color:var(--sub);margin-top:2px}
.card.warn .n{color:var(--warn)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;margin-bottom:16px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.panel h2{font-size:15px;margin-bottom:12px}
.row{display:flex;align-items:center;gap:8px;margin:6px 0;font-size:13px}
.row .lb{flex:0 0 118px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right}
.row .bar{flex:1;background:#eef0f3;border-radius:5px;height:10px;overflow:hidden}
.row .bar i{display:block;height:10px;border-radius:5px}
.row b{flex:0 0 34px;text-align:right;color:var(--sub);font-weight:600}
.donut{width:150px;height:150px;border-radius:50%;margin:6px auto;position:relative}
.donut::after{content:"";position:absolute;inset:26%;background:var(--card);border-radius:50%}
.donut .cap{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:1;font-weight:700}
.cap small{font-weight:400;color:var(--sub);font-size:11px}
.leg{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;font-size:12px;color:var(--sub);margin-top:8px}
.leg i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px}
.cols{display:flex;align-items:flex-end;gap:6px;height:110px}
.cols .c{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;height:100%;justify-content:flex-end}
.cols .c i{display:block;width:70%;background:var(--accent);border-radius:3px 3px 0 0;min-height:2px}
.cols .c.today i{background:var(--warn)}
.cols .c em{font-style:normal;font-size:10px;color:var(--sub);white-space:nowrap}
.list{font-size:13px}
.list .it{display:flex;gap:8px;align-items:baseline;padding:7px 0;border-bottom:1px dashed var(--line)}
.list .it:last-child{border:none}
.tag{font-size:11px;padding:1px 7px;border-radius:10px;white-space:nowrap}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 6px;border-bottom:1px solid var(--line);white-space:nowrap;max-width:260px;overflow:hidden;text-overflow:ellipsis}
th{color:var(--sub);font-weight:600}
.empty{text-align:center;padding:40px 0;color:var(--sub);line-height:1.9}
.empty b{font-size:17px;color:var(--ink)}
.foot{color:var(--sub);font-size:12px;margin-top:22px;text-align:center}
.over{color:var(--warn)}
"""

SUBJ_COLORS = {"数学": "#4c6ef5", "英语": "#2f9e6e", "政治": "#e8a33d", "专业课": "#9a5fd0"}
_ERROR_COLORS = {"概念不清": "#4c6ef5", "条件误用": "#2f9e6e", "公式记错": "#e8a33d", "计算失误": "#9a5fd0",
                 "思路不会": "#e8590c", "审题失误": "#0ca678", "知识盲区": "#f76707", "表达问题": "#5c7cfa",
                 "时间不够": "#8a94a6", "待确认": "#adb5bd"}


def _as_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _topic_str(v):
    return "、".join(v) if isinstance(v, list) else (v or "")


def _ob_link(path, text):
    from urllib.parse import quote
    href = "obsidian://open?vault=%E8%80%83%E7%A0%94&file=" + quote(
        str(path.relative_to(ROOT)).replace("\\", "/"))
    return f'<a href="{href}">{html.escape(text)}</a>'


def _bars(dist, colors=None):
    maxc = max((c for _l, c in dist), default=0)
    out = []
    for label, count in dist:
        color = (colors or {}).get(label, "#748ffc")
        w = int(count / maxc * 100) if maxc else 0
        esc = html.escape(str(label))
        out.append(f'<div class="row"><span class="lb" title="{esc}">{esc}</span>'
                   f'<span class="bar"><i style="width:{w}%;background:{color}"></i></span>'
                   f'<b>{count}</b></div>')
    return ("".join(out) if out else
            '<div class="row"><span class="lb">（暂无）</span><span class="bar"></span><b>0</b></div>')


def _donut(dist, total, cap):
    stops, acc = [], 0.0
    for label, count in dist:
        pct = count / total * 100 if total else 0
        color = SUBJ_COLORS.get(label, "#8a94a6")
        stops.append(f"{color} {acc:.1f}% {acc + pct:.1f}%")
        acc += pct
    grad = ",".join(stops) if stops else "#dee2e6 0% 100%"
    leg = "".join(
        f'<span><i style="background:{SUBJ_COLORS.get(l, "#8a94a6")}"></i>{html.escape(str(l))} {c}</span>'
        for l, c in dist) or "<span>（暂无）</span>"
    return (f'<div class="donut" style="background:conic-gradient({grad})">'
            f'<div class="cap">{total}<small>{cap}</small></div></div><div class="leg">{leg}</div>')


def _cols_chart(pairs, today_idx=None):
    maxc = max((c for _l, c in pairs), default=0)
    out = []
    for i, (label, count) in enumerate(pairs):
        h = 6 + (count / maxc * 96 if maxc else 0)
        cls = ' class="today"' if today_idx is not None and i == today_idx else ""
        out.append(f'<div class="c"{cls}><i style="height:{h:.0f}px"></i>'
                   f'<em>{html.escape(str(label))}</em></div>')
    return '<div class="cols">' + "".join(out) + "</div>"


def cmd_dashboard(_):
    notes = [(f, p) for f, p, _t in error_notes()]
    total = len(notes)

    def dist(key):
        d = {}
        for _f, p in notes:
            v = p.get(key) or "（空）"
            d[v] = d.get(v, 0) + 1
        return sorted(d.items(), key=lambda x: -x[1])

    subjects, errors, books, statuses = dist("subject"), dist("error"), dist("book"), dist("status")
    st = dict(statuses)
    topics = {}
    for _f, p in notes:
        for t in (p.get("topic") if isinstance(p.get("topic"), list) else [p.get("topic")]):
            if t:
                topics[t] = topics.get(t, 0) + 1
    top_topics = sorted(topics.items(), key=lambda x: -x[1])[:10]

    due_list = []
    for f, p in notes:
        nr = date_of(p.get("next_review"))
        if nr and nr <= TODAY and p.get("status") != "已掌握":
            due_list.append((nr, p.get("subject", "?"), f, p))
    due_list.sort(key=lambda x: (x[0], x[2].name))
    high = sorted((n for n in notes if _as_int(n[1].get("wrong_count")) >= 2),
                  key=lambda x: -_as_int(x[1].get("wrong_count")))[:10]

    monday = TODAY - dt.timedelta(days=TODAY.weekday())
    wk = {monday - dt.timedelta(weeks=i): 0 for i in range(8)}
    for _f, p in notes:
        d = date_of(p.get("date"))
        if d:
            ws = d - dt.timedelta(days=d.weekday())
            if ws in wk:
                wk[ws] += 1
    week_pairs = [(f"{w.month}/{w.day}", c) for w, c in sorted(wk.items())]
    new_this_week = wk.get(monday, 0)

    fut = {TODAY + dt.timedelta(days=i): 0 for i in range(14)}
    for _f, p in notes:
        nr = date_of(p.get("next_review"))
        if nr in fut and p.get("status") != "已掌握":
            fut[nr] += 1
    fut_pairs = [(("今天" if i == 0 else f"{d.month}/{d.day}"), c)
                 for i, (d, c) in enumerate(sorted(fut.items()))]

    inbox_n = sum(1 for x in (ROOT / "收件箱").iterdir()
                  if x.is_file() and x.name != "说明.md") if (ROOT / "收件箱").exists() else 0
    pend_dir = ROOT / "收件箱" / "待确认"
    pend_n = sum(1 for x in pend_dir.iterdir()
                 if x.is_file() and x.name != "说明.md") if pend_dir.exists() else 0
    last_date = max((date_of(p.get("date")) for _f, p in notes if date_of(p.get("date"))), default=None)

    cards = [
        (total, "错题总数", False), (st.get("未掌握", 0), "未掌握", False),
        (st.get("复习中", 0), "复习中", False), (st.get("已掌握", 0), "已掌握", False),
        (len(due_list), "今日到期", bool(due_list)), (new_this_week, "本周新增", False),
        (sum(1 for _f, p in notes if _as_int(p.get("wrong_count")) >= 3), "高频错题", False),
        (inbox_n, f"收件箱积压{f'（含待确认 {pend_n}）' if pend_n else ''}", bool(inbox_n)),
    ]
    cards_html = "".join(
        f'<div class="card{" warn" if w else ""}"><div class="n">{n}</div>'
        f'<div class="t">{html.escape(t)}</div></div>' for n, t, w in cards)

    if due_list:
        items = []
        for nr, subj, f, p in due_list[:20]:
            over = ' class="over"' if nr < TODAY else ""
            color = SUBJ_COLORS.get(subj, "#4c6ef5")
            items.append(
                f'<div class="it"><span class="tag" style="background:{color}1e;color:{color}">'
                f'{html.escape(str(subj))}</span><span>{_ob_link(f, f.stem)}</span>'
                f'<span style="color:var(--sub);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
                f'{html.escape(_topic_str(p.get("topic")))}</span>'
                f'<span{over}>{"逾期 " if nr < TODAY else ""}{nr.month}/{nr.day}</span></div>')
        tail = (f'<div class="it" style="color:var(--sub)">… 共 {len(due_list)} 道</div>'
                if len(due_list) > 20 else "")
        today_html = '<div class="list">' + "".join(items) + tail + "</div>"
    else:
        today_html = '<div class="empty">今天没有到期的错题 🎉</div>'

    if high:
        rows = "".join(
            f"<tr><td>{_ob_link(f, f.stem)}</td><td>{html.escape(str(p.get('subject', '')))}</td>"
            f"<td>{html.escape(_topic_str(p.get('topic')))}</td>"
            f"<td>{_as_int(p.get('wrong_count'))}</td><td>{html.escape(str(p.get('status', '')))}</td></tr>"
            for f, p in high)
        high_html = ("<table><tr><th>题目</th><th>科目</th><th>知识点</th><th>错次</th><th>状态</th></tr>"
                     + rows + "</table>")
    else:
        high_html = '<div class="empty">还没有错过 2 次以上的题</div>'

    if total:
        body = (
            '<div class="cards">' + cards_html + "</div>"
            + '<div class="grid"><div class="panel"><h2>今日该重做（' + str(len(due_list)) + "）</h2>"
            + today_html + '</div><div class="panel"><h2>科目分布</h2>'
            + _donut(subjects, total, "道错题") + "</div></div>"
            + '<div class="grid"><div class="panel"><h2>未来两周复习负载</h2>'
            + _cols_chart(fut_pairs, today_idx=0)
            + '</div><div class="panel"><h2>近 8 周新增错题</h2>'
            + _cols_chart(week_pairs) + "</div></div>"
            + '<div class="grid"><div class="panel"><h2>错因分布</h2>'
            + _bars(errors, _ERROR_COLORS)
            + '</div><div class="panel"><h2>哪本书错得最多</h2>'
            + _bars(books) + "</div></div>"
            + '<div class="grid"><div class="panel"><h2>知识点 Top 10</h2>'
            + _bars(top_topics)
            + '</div><div class="panel"><h2>高频错题榜（错 ≥2 次）</h2>'
            + high_html + "</div></div>")
    else:
        body = ('<div class="cards">' + cards_html + "</div>"
                + '<div class="panel"><div class="empty">📷<b>还没有任何错题数据</b><br>'
                "拍照发给 AI 工具（或丢进 收件箱/），归档后这里就会亮起来。<br>"
                "随时说一句「刷新工作台」重新生成本页面。</div></div>")

    last = f"最近录入：{last_date.isoformat()}" if last_date else "尚未录入"
    page = ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>考研错题工作台</title><style>" + _DASH_CSS + "</style></head>"
            '<body><div class="wrap"><h1>考研错题工作台</h1>'
            f'<div class="meta">数据快照 {TODAY.isoformat()} · {last} · '
            "由 工具/库维护.py dashboard 生成 · 随归档自动刷新</div>"
            + body
            + '<div class="foot">点题目可跳转到 Obsidian 笔记 · 数据全部来自本地错题笔记</div>'
            "</div></body></html>")
    out = ROOT / "工作台.html"
    out.write_text(page, encoding="utf-8")
    print(f"工作台已生成：{out}")
    print(f"快照：错题 {total} · 未掌握 {st.get('未掌握', 0)} · 复习中 {st.get('复习中', 0)}"
          f" · 已掌握 {st.get('已掌握', 0)} · 今日到期 {len(due_list)} · 收件箱 {inbox_n}")


def main():
    ap = argparse.ArgumentParser(description="考研错题库维护脚本")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("due", help="今日到期 + 收件箱积压")
    sp = sub.add_parser("stats", help="错题统计")
    sp.add_argument("--week", action="store_true", help="只看本周（周一起）新增")
    sub.add_parser("lint", help="frontmatter 合规校验")
    fp = sub.add_parser("fsrs", help="FSRS 计算下次间隔")
    fp.add_argument("--history", default="", help="历次复习 日期:评级，逗号分隔，如 2026-10-01:3,2026-10-05:1")
    fp.add_argument("--rating", type=int, required=True, choices=[1, 2, 3, 4])
    sub.add_parser("check-agents", help="AGENTS.md 字符数检查")
    sub.add_parser("dashboard", help="生成 工作台.html 本地仪表盘")
    args = ap.parse_args()
    {"due": cmd_due, "stats": cmd_stats, "lint": cmd_lint,
     "fsrs": cmd_fsrs, "check-agents": cmd_check_agents,
     "dashboard": cmd_dashboard}[args.cmd](args)


if __name__ == "__main__":
    main()
