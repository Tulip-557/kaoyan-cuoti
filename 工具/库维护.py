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
  python 工具/库维护.py pull                                  # 从坚果云 WebDAV 拉取手机上传的图到 收件箱/
  python 工具/库维护.py push                                  # 把 附件/ 新图上传回坚果云做云端备份
  python 工具/库维护.py weekly                                # 生成本周周报到 重做单/
"""
import argparse
import base64
import datetime as dt
import html
import math
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
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
        # 重做记录行格式：- 日期 · 对/错 · 评级N（评级持久化，用于正确率统计）
        if "## 重做记录" in _t:
            sec = _t.split("## 重做记录", 1)[1].split("\n## ", 1)[0]
            for line in sec.splitlines():
                s = line.strip()
                if s.startswith("- ") and re.search(r"\d{4}-\d{2}-\d{2}", s):
                    if not re.match(r"^- \d{4}-\d{2}-\d{2} · (对|错) · 评级[1-4]", s):
                        problems.append(
                            f"{rel}: 重做记录格式 → {s[:40]}（应为 `- 日期 · 对/错 · 评级N`）")
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


# ── 工作台：扫描库数据，交给 dashboard.py 渲染（渲染与数据分离）─────────────
def _as_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _exam_date():
    cfg = ROOT / "个人配置.md"
    if not cfg.exists():
        return None
    m = re.search(r"初试日期[^\d]*(\d{4})-(\d{1,2})-(\d{1,2})",
                  cfg.read_text(encoding="utf-8", errors="replace"))
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def cmd_dashboard(_):
    from dashboard import render
    parsed = list(error_notes())
    total = len(parsed)
    today_s = TODAY.isoformat()

    def rel(f):
        return str(f.relative_to(ROOT)).replace("\\", "/")

    status_counts = {"未掌握": 0, "复习中": 0, "已掌握": 0}
    subject_status, subject_counts = {}, {}
    error_counts, book_counts, topic_counts = {}, {}, {}
    due, high, recent = [], [], []
    note_days, review_days, reviewed_today = {}, set(), 0

    for f, p, _t in parsed:
        st = p.get("status") or ""
        subj = p.get("subject") or "其它"
        if st in status_counts:
            status_counts[st] += 1
        subject_counts[subj] = subject_counts.get(subj, 0) + 1
        subject_status.setdefault(subj, {"未掌握": 0, "复习中": 0, "已掌握": 0})
        if st in subject_status[subj]:
            subject_status[subj][st] += 1
        err = p.get("error") or "（空）"
        error_counts[err] = error_counts.get(err, 0) + 1
        bk = p.get("book") or "（空）"
        book_counts[bk] = book_counts.get(bk, 0) + 1
        tv = p.get("topic")
        tl = [t for t in (tv if isinstance(tv, list) else [tv]) if t]
        for t in tl:
            topic_counts[t] = topic_counts.get(t, 0) + 1
        wc = _as_int(p.get("wrong_count"))
        nr, d = date_of(p.get("next_review")), date_of(p.get("date"))
        if nr and nr <= TODAY and st != "已掌握":
            due.append({"subject": subj, "file": rel(f), "stem": f.stem,
                        "topic": "、".join(tl), "due": nr.isoformat(),
                        "overdue": (TODAY - nr).days, "wrong_count": wc, "status": st})
        if wc >= 2:
            high.append({"file": rel(f), "stem": f.stem, "subject": subj,
                         "topic": "、".join(tl), "wrong_count": wc, "status": st})
        if d:
            note_days[d.isoformat()] = note_days.get(d.isoformat(), 0) + 1
            recent.append({"file": rel(f), "stem": f.stem, "subject": subj,
                           "topic": "、".join(tl), "date": d.isoformat(), "status": st})
        rv = p.get("reviews")
        rv = rv if isinstance(rv, list) else ([rv] if rv else [])
        for x in rv:
            dd = date_of(x)
            if dd:
                review_days.add(dd.isoformat())
                if dd == TODAY:
                    reviewed_today += 1

    due.sort(key=lambda x: x["due"])
    high.sort(key=lambda x: -x["wrong_count"])
    recent.sort(key=lambda x: x["date"], reverse=True)
    recent = recent[:10]

    monday = TODAY - dt.timedelta(days=TODAY.weekday())
    wk = {monday - dt.timedelta(weeks=i): 0 for i in range(8)}
    for iso, c in note_days.items():
        d = date_of(iso)
        ws = d - dt.timedelta(days=d.weekday())
        if ws in wk:
            wk[ws] += c
    week_trend = [{"label": f"{w.month}/{w.day}", "count": c} for w, c in sorted(wk.items())]

    fut = {TODAY + dt.timedelta(days=i): 0 for i in range(14)}
    for _f, p, _t in parsed:
        nr = date_of(p.get("next_review"))
        if nr in fut and p.get("status") != "已掌握":
            fut[nr] += 1
    future = [{"label": "今天" if i == 0 else f"{d.month}/{d.day}", "count": c, "today": i == 0}
              for i, (d, c) in enumerate(sorted(fut.items()))]

    activity = set(note_days) | review_days
    streak, cursor = 0, TODAY
    if cursor.isoformat() not in activity:
        cursor -= dt.timedelta(days=1)
    while cursor.isoformat() in activity:
        streak += 1
        cursor -= dt.timedelta(days=1)

    knowledge_items = 0
    kp_dir = ROOT / "知识点"
    if kp_dir.exists():
        for mf in kp_dir.glob("*.md"):
            for line in mf.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if s.startswith("- ") and "（暂无）" not in s:
                    knowledge_items += 1

    inbox_n = sum(1 for x in (ROOT / "收件箱").iterdir()
                  if x.is_file() and x.name != "说明.md") if (ROOT / "收件箱").exists() else 0
    pend_dir = ROOT / "收件箱" / "待确认"
    pend_n = sum(1 for x in pend_dir.iterdir()
                 if x.is_file() and x.name != "说明.md") if pend_dir.exists() else 0

    # ── 实用统计（v8）：复习频次、目标、科目掌握、洞察、成就、健康 ──
    week_reviews = 0
    total_reviews = 0
    wk_rev = {monday - dt.timedelta(weeks=i): 0 for i in range(8)}
    for _f, p, _t in parsed:
        rv = p.get("reviews")
        rv = rv if isinstance(rv, list) else ([rv] if rv else [])
        for x in rv:
            dd = date_of(x)
            if not dd:
                continue
            total_reviews += 1
            if monday <= dd <= TODAY:
                week_reviews += 1
            ws = dd - dt.timedelta(days=dd.weekday())
            if ws in wk_rev:
                wk_rev[ws] += 1
    review_series = [{"label": f"{w.month}/{w.day}", "count": c} for w, c in sorted(wk_rev.items())]

    def weekly_goal():
        cfg = ROOT / "个人配置.md"
        if not cfg.exists():
            return 25
        m = re.search(r"每周复习目标[^\d]*(\d+)",
                      cfg.read_text(encoding="utf-8", errors="replace"))
        return max(1, int(m.group(1))) if m else 25

    week_new = week_trend[-1]["count"] if week_trend else 0
    goal = weekly_goal()

    subj_mastery = []
    for subj, counts in subject_status.items():
        tot = sum(counts.values())
        if tot:
            subj_mastery.append({"subject": subj, "total": tot,
                                 "done": counts["已掌握"], "open": counts["未掌握"],
                                 "pct": counts["已掌握"] / tot * 100})
    subj_mastery.sort(key=lambda x: (x["pct"], -x["open"]))

    topic_pain = {}
    for _f, p, _t in parsed:
        tv = p.get("topic")
        tl = [t for t in (tv if isinstance(tv, list) else [tv]) if t]
        for t in tl:
            topic_pain[t] = topic_pain.get(t, 0) + _as_int(p.get("wrong_count"))
    topic_pain_top = sorted(topic_pain.items(), key=lambda kv: -kv[1])[:5]

    min_map = {"数学": 8, "英语": 4, "政治": 5, "专业课": 10}
    est_minutes = sum(min_map.get(x["subject"], 6) for x in due)

    worst_subject = max((s for s in subj_mastery if s["open"]), key=lambda x: x["open"], default=None)
    weakest_topic = topic_pain_top[0] if topic_pain_top else None
    top_error = sorted(error_counts.items(), key=lambda kv: -kv[1])[0] if error_counts else None
    review_ratio = (week_reviews / week_new) if week_new else None

    achievements = [
        {"icon": "🌱", "name": "开张", "done": total >= 1},
        {"icon": "🔥", "name": "连续 7 天", "done": streak >= 7},
        {"icon": "💯", "name": "百次复习", "done": total_reviews >= 100},
        {"icon": "🎯", "name": "掌握 25 题", "done": status_counts["已掌握"] >= 25},
        {"icon": "📥", "name": "收件箱清零", "done": total >= 1 and inbox_n == 0 and pend_n == 0},
        {"icon": "⚡", "name": f"本周 ≥{goal}", "done": week_reviews >= goal},
    ]

    health_issues = 0
    valid_status = {"未掌握", "复习中", "已掌握"}
    for _f, p, _t in parsed:
        if (p.get("subject") not in SUBJECTS or p.get("error") not in ERRORS
                or p.get("status") not in valid_status):
            health_issues += 1
            continue
        nr2, d0 = date_of(p.get("next_review")), date_of(p.get("date"))
        if nr2 is None or (d0 and nr2 < d0):
            health_issues += 1

    # 重做正确率（解析「重做记录」的结构化行：- 日期 · 对/错 · 评级N，近 8 周）
    acc_ok = acc_bad = 0
    for _f, _p, text in parsed:
        if "## 重做记录" not in text:
            continue
        sec = text.split("## 重做记录", 1)[1].split("\n## ", 1)[0]
        for line in sec.splitlines():
            m2 = re.match(r"-\s*(\d{4}-\d{2}-\d{2})\s*·\s*(对|错)\s*·\s*评级([1-4])",
                          line.strip())
            if not m2:
                continue
            dd = date_of(m2.group(1))
            if not dd or dd < TODAY - dt.timedelta(days=56):
                continue
            if m2.group(2) == "对":
                acc_ok += 1
            else:
                acc_bad += 1
    accuracy = (acc_ok / (acc_ok + acc_bad) * 100) if (acc_ok + acc_bad) else None

    exam = _exam_date()
    days_left_v = (exam - TODAY).days if exam else None
    if days_left_v is None:
        phase = ""
    elif days_left_v > 240:
        phase = "基础"
    elif days_left_v > 90:
        phase = "强化"
    else:
        phase = "冲刺"
    data = {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "today": today_s,
        "weekday": "一二三四五六日"[TODAY.weekday()],
        "exam_date": exam.isoformat() if exam else None,
        "days_left": (exam - TODAY).days if exam else None,
        "total": total,
        "status_counts": status_counts,
        "subject_status": subject_status,
        "subject_counts": sorted(subject_counts.items(), key=lambda x: -x[1]),
        "error_counts": sorted(error_counts.items(), key=lambda x: -x[1]),
        "book_counts": sorted(book_counts.items(), key=lambda x: -x[1]),
        "topic_counts": sorted(topic_counts.items(), key=lambda x: -x[1])[:10],
        "due": due,
        "overdue": sum(1 for x in due if x["overdue"] > 0),
        "high": high[:10],
        "recent": recent,
        "week_trend": week_trend,
        "future": future,
        "heatmap": note_days,
        "streak": streak,
        "inbox": inbox_n,
        "pending": pend_n,
        "reviewed_today": reviewed_today,
        "knowledge_items": knowledge_items,
        "avg_reviews": (sum(len(p.get("reviews") or []) for _f, p, _t in parsed) / total) if total else 0,
        "high3": sum(1 for _f, p, _t in parsed if _as_int(p.get("wrong_count")) >= 3),
        "week_new": week_new,
        "mastery": (status_counts["已掌握"] / total * 100) if total else 0,
        "week_reviews": week_reviews,
        "total_reviews": total_reviews,
        "weekly_goal": goal,
        "review_series": review_series,
        "subj_mastery": subj_mastery,
        "weakest_topic": weakest_topic,
        "worst_subject": worst_subject,
        "top_error": top_error,
        "review_ratio": review_ratio,
        "est_minutes": est_minutes,
        "achievements": achievements,
        "health_issues": health_issues,
        "phase": phase,
        "accuracy": accuracy,
        "acc_ok": acc_ok,
        "acc_bad": acc_bad,
    }
    page = render(data)
    out = ROOT / "工作台.html"
    out.write_text(page, encoding="utf-8")
    print(f"工作台已生成：{out}")
    print(f"快照：错题 {total} · 未掌握 {status_counts['未掌握']} · 复习中 {status_counts['复习中']}"
          f" · 已掌握 {status_counts['已掌握']} · 今日到期 {len(due)} · 收件箱 {inbox_n}")


# ── 坚果云 WebDAV：手机上传 → 收件箱；附件 → 云端备份 ─────────────────────
DAV_BASE = "https://dav.jianguoyun.com"


def _nutstore_creds():
    f = ROOT / "工具" / ".nutstore"
    if not f.exists():
        return None
    lines = [ln.strip() for ln in f.read_text(encoding="utf-8", errors="replace").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    return (lines[0], lines[1]) if len(lines) >= 2 else None


def _norm_dav_dir(v, default):
    if not v:
        return default
    v = v.strip()
    if not v.startswith("/"):
        v = "/" + v
    return v if v.endswith("/") else v + "/"


def _dav_dirs():
    inbox, attach = "/dav/考研收件箱/", "/dav/考研附件/"
    cfg = ROOT / "个人配置.md"
    if cfg.exists():
        t = cfg.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"云端收件箱目录[：:]\s*(\S+)", t)
        if m:
            inbox = _norm_dav_dir(m.group(1), inbox)
        m = re.search(r"云端附件目录[：:]\s*(\S+)", t)
        if m:
            attach = _norm_dav_dir(m.group(1), attach)
    return inbox, attach


def _q(path):
    return urllib.parse.quote(path, safe="/")


def _dav(method, url, user, pwd, data=None, headers=None, timeout=25):
    req = urllib.request.Request(url, data=data, method=method)
    token = base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", "Basic " + token)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    return urllib.request.urlopen(req, timeout=timeout)


def _dav_list(url, user, pwd):
    body = (b'<?xml version="1.0" encoding="utf-8"?>'
            b'<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>')
    with _dav("PROPFIND", url, user, pwd, body,
              {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"}) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    ns = {"d": "DAV:"}
    base = urllib.parse.urlparse(url).path.rstrip("/")
    out = []
    for el in root.findall("d:response", ns):
        href_el = el.find("d:href", ns)
        if href_el is None or not href_el.text:
            continue
        path = urllib.parse.urlparse(urllib.parse.unquote(href_el.text)).path
        is_dir = el.find(".//d:resourcetype/d:collection", ns) is not None
        if is_dir or path.rstrip("/") == base:
            continue
        out.append((path.rstrip("/").split("/")[-1], path))
    return out


def _dav_archive_remote(path, inbox_dir, user, pwd):
    """拉取成功后把云端文件移入 云端收件箱/已处理/，避免重复下载。"""
    try:
        _dav("MKCOL", DAV_BASE + inbox_dir + _q("已处理/"), user, pwd)
    except Exception:
        pass
    try:
        name = path.rstrip("/").split("/")[-1]
        _dav("MOVE", DAV_BASE + _q(path), user, pwd,
             headers={"Destination": DAV_BASE + inbox_dir + _q("已处理/" + name),
                      "Overwrite": "T"})
    except Exception as e:
        print(f"  ⚠ 云端移入已处理失败（下次会重复下载）：{e}")


def cmd_pull(_):
    creds = _nutstore_creds()
    if not creds:
        print("未配置坚果云凭据。一次性设置：")
        print("  1) 网页版坚果云 → 账户信息 → 安全选项 → 添加应用密码（名字随意）")
        print("  2) 在 工具/.nutstore 写两行：账号邮箱、应用密码（该文件已 gitignore）")
        return
    user, pwd = creds
    inbox_dir, _attach = _dav_dirs()
    try:
        items = _dav_list(DAV_BASE + inbox_dir, user, pwd)
    except Exception as e:
        print(f"拉取失败（网络或凭据问题，稍后再试）：{e}")
        return
    dest = ROOT / "收件箱"
    dest.mkdir(exist_ok=True)
    got = 0
    for name, path in items:
        if name == "说明.md" or name.startswith("."):
            continue
        local = dest / name
        if local.exists():
            _dav_archive_remote(path, inbox_dir, user, pwd)
            continue
        try:
            with _dav("GET", DAV_BASE + _q(path), user, pwd) as resp:
                data = resp.read()
            local.write_bytes(data)
            got += 1
            _dav_archive_remote(path, inbox_dir, user, pwd)
        except Exception as e:
            print(f"  ⚠ {name}: {e}")
    print(f"拉取完成：新增 {got} 个文件到 收件箱/" if got else "云端收件箱没有新文件")


def cmd_push(_):
    creds = _nutstore_creds()
    if not creds:
        print("未配置坚果云凭据（设置方法见 pull 的提示）。")
        return
    user, pwd = creds
    _inbox, attach_dir = _dav_dirs()
    src = ROOT / "附件"
    if not src.exists():
        print("附件目录不存在")
        return
    try:
        existing = {n for n, _p in _dav_list(DAV_BASE + attach_dir, user, pwd)}
    except Exception as e:
        print(f"读取云端附件目录失败：{e}")
        return
    up = 0
    for f in sorted(src.iterdir()):
        if not f.is_file() or f.name == "说明.md" or f.name in existing:
            continue
        try:
            _dav("PUT", DAV_BASE + attach_dir + urllib.parse.quote(f.name), user, pwd,
                 f.read_bytes(), {"Content-Type": "application/octet-stream"})
            up += 1
        except Exception as e:
            print(f"  ⚠ {f.name}: {e}")
    print(f"上传完成：新增 {up} 个附件到云端" if up else "附件云端已是最新")


# ── 周报：本周 vs 上周 + 正确率 + 待办 ─────────────────────────────────────
def cmd_weekly(_):
    monday = TODAY - dt.timedelta(days=TODAY.weekday())
    last_mon = monday - dt.timedelta(days=7)
    parsed = list(error_notes())
    cur_new = cur_rev = last_new = last_rev = 0
    acc_ok = acc_bad = 0
    subj_week, err_week = {}, {}
    overdue = 0
    for f, p, text in parsed:
        st = p.get("status") or ""
        nr = date_of(p.get("next_review"))
        if nr and nr <= TODAY and st != "已掌握":
            overdue += 1
        d = date_of(p.get("date"))
        if d:
            if monday <= d <= TODAY:
                cur_new += 1
                subj_week[p.get("subject") or "?"] = subj_week.get(p.get("subject") or "?", 0) + 1
                err_week[p.get("error") or "?"] = err_week.get(p.get("error") or "?", 0) + 1
            elif last_mon <= d < monday:
                last_new += 1
        rv = p.get("reviews")
        rv = rv if isinstance(rv, list) else ([rv] if rv else [])
        for x in rv:
            dd = date_of(x)
            if not dd:
                continue
            if monday <= dd <= TODAY:
                cur_rev += 1
            elif last_mon <= dd < monday:
                last_rev += 1
        if "## 重做记录" in text:
            sec = text.split("## 重做记录", 1)[1].split("\n## ", 1)[0]
            for line in sec.splitlines():
                m2 = re.match(r"-\s*(\d{4}-\d{2}-\d{2})\s*·\s*(对|错)\s*·\s*评级([1-4])",
                              line.strip())
                if not m2:
                    continue
                dd = date_of(m2.group(1))
                if dd and monday <= dd <= TODAY:
                    if m2.group(2) == "对":
                        acc_ok += 1
                    else:
                        acc_bad += 1
    inbox_n = sum(1 for x in (ROOT / "收件箱").iterdir()
                  if x.is_file() and x.name != "说明.md") if (ROOT / "收件箱").exists() else 0
    goal = 25
    cfg = ROOT / "个人配置.md"
    if cfg.exists():
        m = re.search(r"每周复习目标[^\d]*(\d+)", cfg.read_text(encoding="utf-8", errors="replace"))
        if m:
            goal = max(1, int(m.group(1)))
    acc = (acc_ok / (acc_ok + acc_bad) * 100) if (acc_ok + acc_bad) else None

    def arrow(a, b):
        return "↑" if b > a else "↓" if b < a else "＝"

    lines = [
        f"# {TODAY.isoformat()} 周报", "",
        f"> 生成于 {dt.datetime.now().strftime('%H:%M')} · 数据来自错题笔记 · 本周范围 {monday.isoformat()} ~ {TODAY.isoformat()}",
        "", "## 本周数据", "",
        "| 指标 | 本周 | 上周 | 变化 |", "|---|---|---|---|",
        f"| 新增错题 | {cur_new} | {last_new} | {arrow(last_new, cur_new)} |",
        f"| 复习次数 | {cur_rev} | {last_rev} | {arrow(last_rev, cur_rev)} |",
        f"| 重做正确率 | {'—' if acc is None else f'{acc:.0f}%'} | — | — |",
        "",
        "## 科目与错因（本周）", "",
        "- 科目：" + (" · ".join(f"{k} {v}" for k, v in sorted(subj_week.items(), key=lambda kv: -kv[1])) or "无新增"),
        "- 错因：" + (" · ".join(f"{k} {v}" for k, v in sorted(err_week.items(), key=lambda kv: -kv[1])) or "无新增"),
    ]
    if acc is not None:
        lines.append(f"- 正确率明细：对 {acc_ok} / 错 {acc_bad}（近 8 周滚动见工作台）")
    lines += ["", "## 待办", "",
              f"- 逾期未重做：{overdue} 道（说「今天该重做什么」）",
              f"- 收件箱待处理：{inbox_n} 张",
              f"- 本周复习目标：{cur_rev}/{goal} 次",
              "", "---", "做完重做单后，把结果告诉我（拍照/口头），下周报会自动变准。"]
    out = ROOT / "重做单" / f"{TODAY.isoformat()} 周报.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"周报已生成：{out}")
    print(f"本周：新增 {cur_new}（上周 {last_new}）· 复习 {cur_rev}（上周 {last_rev}）"
          f" · 正确率 {'—' if acc is None else f'{acc:.0f}%'} · 逾期 {overdue} · 收件箱 {inbox_n}")


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
    sub.add_parser("pull", help="从坚果云 WebDAV 拉取手机上传的图到 收件箱/")
    sub.add_parser("push", help="把 附件/ 新图上传到坚果云做云端备份")
    sub.add_parser("weekly", help="生成本周周报到 重做单/")
    args = ap.parse_args()
    {"due": cmd_due, "stats": cmd_stats, "lint": cmd_lint,
     "fsrs": cmd_fsrs, "check-agents": cmd_check_agents,
     "dashboard": cmd_dashboard, "pull": cmd_pull, "push": cmd_push,
     "weekly": cmd_weekly}[args.cmd](args)


if __name__ == "__main__":
    main()
