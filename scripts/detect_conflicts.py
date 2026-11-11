# -*- coding: utf-8 -*-
"""阶段 6 · 冲突时段检测（数据驱动）

从聊天记录中捞出所有「冲突时段」（episode），供全景时间线/类型学使用。

用法：
  python scripts/detect_conflicts.py -c config.toml
  python scripts/detect_conflicts.py -c config.toml --out out/conflicts.json
  python scripts/detect_conflicts.py -c config.toml --gap 180 --min-intensity 6

方法：
  1. 冲突词分三层加权打分（TIER1 分手/绝交/拉黑 ×4；TIER2 凭什么/骗/敷衍 ×2；
     TIER3 你总是/你根本 ×1）。
  2. 相邻命中消息间隔 > GAP 分钟视为新一段（默认 180 分钟 = 3 小时）。
  3. 过滤：强度≥min-intensity 且时长≥15 分钟，或命中≥4 条。
  4. 每段输出：日期/起止/时长/总条数/双方条数比/冲突强度/谁先升级/首句冲突词。

依赖：仅标准库 + collect.py 同款配置读取（复用 load_cfg / load / resolve_parties）。
口径与 collect.py 一致（同一份 config，同一套 strict_parties 过滤）。
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import load_cfg, load, resolve_parties, _dt  # noqa: E402

# ── 冲突词分层（可按关系在 config 里覆盖，见 references/deep-analysis.md）──
TIER1 = ["分手", "绝交", "拉黑", "恶心和阴暗", "永远讨厌", "好聚好散", "跑路", "滚"]
TIER2 = ["恶心", "阴暗", "凭什么", "骗", "敷衍", "冷漠", "自私", "虚伪", "心口不一",
         "口是心非", "道德绑架", "双标", "理解能力", "不爱", "不在乎", "委屈",
         "无语", "寒心", "后悔", "你配", "你图", "你辜负", "你凭什么"]
TIER3 = ["你总是", "你从来", "你根本", "你就是", "你太", "你没", "你不够",
         "逃避", "回避", "直男", "你躲避"]


def score(c: str) -> int:
    s = 0
    for w in TIER1:
        if w in c:
            s += 4
    for w in TIER2:
        if w in c:
            s += 2
    for w in TIER3:
        if w in c:
            s += 1
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="detect_conflicts.py", description="冲突时段检测")
    ap.add_argument("-c", "--config", default="config.toml")
    ap.add_argument("--out", help="输出 JSON，默认 <output.dir>/conflicts.json")
    ap.add_argument("--gap", type=int, default=180, help="相邻命中消息间隔超过多少分钟算新一段")
    ap.add_argument("--min-intensity", type=int, default=6, help="最小冲突强度")
    ap.add_argument("--min-duration", type=float, default=15, help="最小时长（分钟）")
    args = ap.parse_args(argv)

    c = load_cfg(args.config)
    recs = load(c)
    me, other = resolve_parties(c, recs)
    tz = timezone(timedelta(hours=c.tz))

    flagged = []
    for r in recs:
        t = r.text or ""
        if "[图片]" in t or "[语音]" in t or len(t) < 4:
            continue
        sc = score(t)
        if sc > 0:
            flagged.append((r.ts, r.who, sc, t))
    flagged.sort(key=lambda x: x[0])

    # 时间聚类
    episodes, cur = [], None
    for ts, who, sc, t in flagged:
        if cur is None:
            cur = [(ts, who, sc, t)]
            continue
        if (ts - cur[-1][0]) > args.gap * 60:
            episodes.append(cur)
            cur = [(ts, who, sc, t)]
        else:
            cur.append((ts, who, sc, t))
    if cur:
        episodes.append(cur)

    kept = []
    for ep in episodes:
        dur = (ep[-1][0] - ep[0][0]) / 60.0
        intensity = sum(x[2] for x in ep)
        if (intensity >= args.min_intensity and dur >= args.min_duration) or len(ep) >= 4:
            kept.append(ep)

    # 时段内全部消息（用于体量与双方条数比）
    out = []
    for ep in kept:
        t0, t1 = ep[0][0], ep[-1][0]
        win = [r for r in recs if t0 <= r.ts <= t1]
        n_me = sum(1 for r in win if r.who == me)
        n_ot = sum(1 for r in win if r.who == other)
        first_who = ep[0][1]
        out.append({
            "date": _dt(t0, tz).strftime("%Y-%m-%d"),
            "start": _dt(t0, tz).strftime("%Y-%m-%d %H:%M"),
            "end": _dt(t1, tz).strftime("%Y-%m-%d %H:%M"),
            "dur_min": round((t1 - t0) / 60.0, 1),
            "flagged": len(ep),
            "intensity": sum(x[2] for x in ep),
            "total_msgs": n_me + n_ot,
            me: n_me,
            other: n_ot,
            "escalator": first_who,
            "first_conflict": ep[0][3][:60],
        })
    out.sort(key=lambda x: x["start"])

    dest = Path(args.out) if args.out else (c.out_dir / "conflicts.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"冲突时段 {len(out)} 段 · 强冲突(≥15) {sum(1 for e in out if e['intensity']>=15)} 段")
    print(f"先升级：{me} {sum(1 for e in out if e['escalator']==me)} / "
          f"{other} {sum(1 for e in out if e['escalator']==other)}")
    print(f"已写入 {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
