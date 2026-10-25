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
"""
import argparse
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
    args = ap.parse_args()
    {"due": cmd_due, "stats": cmd_stats, "lint": cmd_lint,
     "fsrs": cmd_fsrs, "check-agents": cmd_check_agents}[args.cmd](args)


if __name__ == "__main__":
    main()
