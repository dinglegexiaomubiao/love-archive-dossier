#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collect.py —— 恋爱档案的数据采集器。

把导出的聊天记录算成一份 metrics.json，供 scaffold.py 生成档案骨架，
或供人/AI 直接读取做判断。

用法：
    python collect.py -c config.toml              # 全量指标 → out/metrics.json
    python collect.py -c config.toml spikes       # 只看拐点与空白期
    python collect.py -c config.toml grep "算了" 2022-01-01 2023-03-01
    python collect.py -c config.toml dump 2022-02-15 2022-02-16

零强制依赖（Python 3.11+ 用内置 tomllib；jieba 可选）。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics as st
import sys
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2b00-\u2bff]")
CJK = re.compile(r"[\u4e00-\u9fa5]+")
TXT_LINE = re.compile(r"^\s*[\[［](?P<t>[^\]］]+)[\]］]\s*(?P<who>[^:：]{1,40})[:：]\s*(?P<text>.*)$")

BUILTIN_STOP = """
的 了 是 我 你 他 她 它 在 不 就 都 也 还 有 和 跟 吗 吧 啊 呢 哦 嗯 呀 啦 呗 嘛 哈 嘿
一个 这个 那个 什么 怎么 可以 就是 没有 我们 你们 他们 自己 现在 时候 知道 觉得
但是 因为 所以 如果 这样 那样 一下 一样 已经 真的 不是 还是 有点 好像 应该 可能
然后 而且 其实 感觉 这么 那么 多少 几个 一点 有些 那些 这些 只是 不过 反正
表情 图片 链接 视频 文件 语音 转账 红包 消息 聊天 微信 撤回 内容
""".split()

try:
    import jieba
    jieba.setLogLevel(60)
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False


# ══════════════════ 配置 ══════════════════

@dataclass
class Cfg:
    fmt: str = "wechat-export"
    path: str = ""
    fields: dict = field(default_factory=dict)
    me: str = ""
    other: str = ""
    tz: float = 8
    title: str = ""
    session_gap_hours: float = 4
    reply_delay_max_hours: float = 24
    night_hours: list = field(default_factory=lambda: [0, 1, 2, 3, 4])
    phrase_min_count: int = 30
    top_words: int = 60
    spike_ratio: float = 2.5
    spike_min_messages: int = 80
    spike_min_delta: int = 50
    spike_window: int = 7
    trend_drop_ratio: float = 0.75
    trend_min_drop: int = 500
    max_phases: int = 10
    min_phase_days: int = 14
    keywords: dict = field(default_factory=dict)
    categories: dict = field(default_factory=dict)
    positive: str = ""
    negative: str = ""
    stopwords: list = field(default_factory=list)
    out_dir: Path = Path("out")
    # 合并转发展开后会出现第三方 sender（群聊成员/被转发者），会污染
    # 开场归属、月度/年度分布，甚至把关系起点伪造成几年以前。
    # 默认只保留 me / other / 系统 三方参与统计（见 pitfalls.md 第 14 条）。
    strict_parties: bool = True


def load_cfg(path: str | None) -> Cfg:
    c = Cfg()
    if path:
        p = Path(path).expanduser()
        if not p.is_file():
            raise SystemExit(f"配置文件不存在：{p}")
        with p.open("rb") as f:
            d = tomllib.load(f)
        src = d.get("source", {})
        c.fmt = src.get("format", c.fmt)
        c.path = src.get("path", c.path)
        c.fields = dict(src.get("fields", {}))
        m = d.get("meta", {})
        c.me = m.get("me", c.me)
        c.other = m.get("other", c.other)
        c.title = m.get("title", c.title)
        c.tz = m.get("timezone_offset", c.tz)
        s = d.get("stats", {})
        c.session_gap_hours = s.get("session_gap_hours", c.session_gap_hours)
        c.reply_delay_max_hours = s.get("reply_delay_max_hours", c.reply_delay_max_hours)
        c.night_hours = list(s.get("night_hours", c.night_hours))
        c.phrase_min_count = s.get("phrase_min_count", c.phrase_min_count)
        c.top_words = s.get("top_words", c.top_words)
        c.strict_parties = bool(s.get("strict_parties", c.strict_parties))
        dt = d.get("detect", {})
        sp = dt.get("spike", {})
        c.spike_ratio = sp.get("ratio", c.spike_ratio)
        c.spike_min_messages = sp.get("min_messages", c.spike_min_messages)
        c.spike_min_delta = sp.get("min_delta", c.spike_min_delta)
        c.spike_window = sp.get("window_days", c.spike_window)
        c.trend_drop_ratio = sp.get("trend_drop_ratio", c.trend_drop_ratio)
        c.trend_min_drop = sp.get("trend_min_drop", c.trend_min_drop)
        c.max_phases = sp.get("max_phases", c.max_phases)
        c.min_phase_days = sp.get("min_phase_days", c.min_phase_days)
        c.keywords = dict(dt.get("keywords", {}))
        c.categories = dict(d.get("topics", {}).get("categories", {}))
        e = d.get("emotion", {})
        c.positive = e.get("positive", c.positive)
        c.negative = e.get("negative", c.negative)
        c.stopwords = list(d.get("stopwords", {}).get("extra", []))
        o = d.get("output", {})
        if "dir" in o:
            c.out_dir = Path(o["dir"])
    c.stopwords = list(dict.fromkeys(BUILTIN_STOP + c.stopwords))
    if not c.out_dir.is_absolute():
        c.out_dir = (Path.cwd() / c.out_dir).resolve()
    c.out_dir.mkdir(parents=True, exist_ok=True)
    return c


# ══════════════════ 加载 ══════════════════

@dataclass(slots=True)
class Rec:
    ts: int
    who: str
    typ: str
    text: str


def parse_time(v, tz_hours: float = 8) -> int | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v / 1000) if float(v) > 1e11 else int(v)
    s = str(v).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{9,13}", s):
        n = int(s)
        return n // 1000 if n > 10 ** 11 else n
    tzn = timezone(timedelta(hours=tz_hours))
    s2 = re.sub(r"\.\d+", "", s.replace("/", "-").replace("Z", "+00:00"))
    try:
        dt = datetime.fromisoformat(s2)
        return int(dt.timestamp()) if dt.tzinfo else int(dt.replace(tzinfo=tzn).timestamp())
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%m-%d %H:%M"):
        try:
            dt = datetime.strptime(s2, fmt)
            if fmt.startswith("%m"):
                dt = dt.replace(year=datetime.now().year)
            return int(dt.replace(tzinfo=tzn).timestamp())
        except ValueError:
            continue
    return None


def _pick(row, key, default):
    return row.get(key, row.get(default, ""))


def load(c: Cfg) -> list[Rec]:
    p = Path(c.path).expanduser()
    if not p.is_file():
        raise SystemExit(f"数据文件不存在：{p}")
    fmt = c.fmt.lower()
    out: list[Rec] = []

    if fmt == "wechat-export":
        payload = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            payload = {"messages": payload}
        for it in payload.get("messages", []):
            fw = it.get("forwarded_messages")
            if fw:
                for e in fw:
                    ts = parse_time(e.get("timestamp"), c.tz)
                    if ts:
                        out.append(Rec(ts, str(e.get("sender") or ""),
                                       str(e.get("type") or "文本"), str(e.get("content") or "")))
                continue
            ts = parse_time(it.get("timestamp"), c.tz)
            if ts:
                out.append(Rec(ts, str(it.get("sender") or ""),
                               str(it.get("type") or "文本"), str(it.get("content") or "")))
    elif fmt == "jsonl":
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_time(_pick(row, c.fields.get("time", "time"), "timestamp"), c.tz)
            if ts:
                out.append(Rec(ts, str(_pick(row, c.fields.get("sender", "sender"), "who") or ""),
                               str(_pick(row, c.fields.get("type", "type"), "type") or "文本"),
                               str(_pick(row, c.fields.get("content", "content"), "text") or "")))
    elif fmt == "csv":
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                ts = parse_time(_pick(row, c.fields.get("time", "time"), "timestamp"), c.tz)
                if ts:
                    out.append(Rec(ts, str(_pick(row, c.fields.get("sender", "sender"), "who") or ""),
                                   str(_pick(row, c.fields.get("type", "type"), "type") or "文本"),
                                   str(_pick(row, c.fields.get("content", "content"), "text") or "")))
    elif fmt == "txt":
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = TXT_LINE.match(line)
            if not m:
                continue
            ts = parse_time(m.group("t"), c.tz)
            if ts:
                out.append(Rec(ts, m.group("who").strip(), "文本", m.group("text").strip()))
    else:
        raise SystemExit(f"未知格式：{c.fmt}（可选 wechat-export / jsonl / csv / txt）")

    out = [r for r in out if r.who]
    out.sort(key=lambda r: r.ts)

    # ── 合并转发第三方过滤（见 pitfalls.md 第 14 条）───────────────────
    # 展开 forwarded_messages 后，sender 可能是第三方（群成员 / 被转发者）。
    # 这些消息若参与统计，会污染开场归属、月度/年度分布，并把关系起点
    # 伪造成几年以前。默认只保留双方 + 系统消息（撤回归属需要）。
    # 用 config 的 [stats] strict_parties = false 可恢复旧行为。
    if c.strict_parties and out:
        cnt = Counter(r.who for r in out)
        me = c.me or ("我" if "我" in cnt else cnt.most_common(1)[0][0])
        other = c.other or max(
            ((w, n) for w, n in cnt.items() if w != me and w != "系统"),
            key=lambda x: x[1], default=("", 0))[0]
        allowed = {x for x in (me, other, "系统") if x}
        out = [r for r in out if r.who in allowed]
    return out


def resolve_parties(c: Cfg, recs: list[Rec]) -> tuple[str, str]:
    cnt = Counter(r.who for r in recs)
    me = c.me or ("我" if "我" in cnt else (cnt.most_common(1)[0][0] if cnt else ""))
    if c.other:
        other = c.other
    else:
        rest = [(w, n) for w, n in cnt.items() if w != me]
        other = max(rest, key=lambda x: x[1])[0] if rest else ""
    return me, other


# ══════════════════ 指标 ══════════════════

def _dt(ts, tz):
    return datetime.fromtimestamp(ts, tz)


def person_metrics(c: Cfg, recs, who, tz) -> dict:
    mine = [r for r in recs if r.who == who]
    texts = [r for r in mine if r.typ == "文本" and r.text]
    lens = [len(r.text) for r in texts]
    hours = Counter(_dt(r.ts, tz).hour for r in mine)
    return {
        "messages": len(mine),
        "chars": sum(lens),
        "avg_len": round(sum(lens) / len(lens), 1) if lens else 0,
        "max_len": max(lens) if lens else 0,
        "emoji": sum(len(EMOJI.findall(r.text)) for r in texts),
        "night_msgs": sum(1 for r in mine if _dt(r.ts, tz).hour in c.night_hours),
        "peak_hours": hours.most_common(3),
        "hour_hist": [hours.get(h, 0) for h in range(24)],
        "types": dict(Counter(r.typ for r in mine).most_common()),
    }


def sessions(c: Cfg, recs) -> dict:
    if not recs:
        return {"count": 0, "avg": 0, "median": 0, "longest": 0, "initiator": {}}
    gap = c.session_gap_hours * 3600
    groups, cur = [], [recs[0]]
    for r in recs[1:]:
        if r.ts - cur[-1].ts > gap:
            groups.append(cur)
            cur = [r]
        else:
            cur.append(r)
    groups.append(cur)
    lens = [len(g) for g in groups]
    return {
        "count": len(groups),
        "avg": round(sum(lens) / len(lens), 1),
        "median": st.median(lens),
        "longest": max(lens),
        "initiator": dict(Counter(g[0].who for g in groups).most_common()),
        "initiator_length": {
            w: {
                "median": st.median([len(g) for g in groups if g[0].who == w]) if any(g[0].who == w for g in groups) else 0,
                "avg": round(sum(len(g) for g in groups if g[0].who == w) /
                             max(1, sum(1 for g in groups if g[0].who == w)), 1),
            } for w in {g[0].who for g in groups}
        },
    }


def delays(c: Cfg, recs, who) -> dict:
    cap = c.reply_delay_max_hours * 3600
    d = []
    for a, b in zip(recs, recs[1:]):
        if b.who == who and a.who != who:
            g = b.ts - a.ts
            if 0 < g <= cap:
                d.append(g)
    if not d:
        return {"count": 0, "median": None, "mean": None, "p90": None, "under1m": 0}
    d.sort()
    return {
        "count": len(d),
        "median": round(st.median(d)),
        "mean": round(sum(d) / len(d)),
        "p90": d[int(len(d) * 0.9)],
        "under1m": sum(1 for x in d if x <= 60),
    }


def daily(recs, tz) -> dict:
    d = defaultdict(Counter)
    for r in recs:
        d[_dt(r.ts, tz).strftime("%Y-%m-%d")][r.who] += 1
    return d


def spikes(c: Cfg, recs, tz) -> list[dict]:
    dc = daily(recs, tz)
    days = sorted(dc)
    totals = [sum(dc[d].values()) for d in days]
    out = []
    for i, d in enumerate(days):
        prev = totals[max(0, i - c.spike_window):i]
        if len(prev) < 2:
            continue
        avg = sum(prev) / len(prev)
        if avg <= 0 or totals[i] < c.spike_min_messages:
            continue
        if totals[i] - avg < c.spike_min_delta:
            continue
        ratio = totals[i] / avg
        if ratio >= c.spike_ratio:
            out.append({"date": d, "messages": totals[i], "prev_avg": round(avg, 1),
                        "ratio": round(ratio, 2), "delta": int(totals[i] - avg)})
    return out


def trend_breaks(c: Cfg, recs, tz) -> list[dict]:
    m = defaultdict(int)
    for r in recs:
        m[_dt(r.ts, tz).strftime("%Y-%m")] += 1
    ks = sorted(m)
    out = []
    for a, b in zip(ks, ks[1:]):
        if m[a] <= 0:
            continue
        ratio = m[b] / m[a]
        if ratio <= c.trend_drop_ratio and (m[a] - m[b]) >= c.trend_min_drop:
            out.append({"from": a, "to": b, "ratio": round(ratio, 2), "drop": m[a] - m[b]})
    return out


def calendar_gaps(recs, tz, min_days=7) -> list[dict]:
    if not recs:
        return []
    dc = daily(recs, tz)
    cur = _dt(recs[0].ts, tz).date()
    end = _dt(recs[-1].ts, tz).date()
    out, run = [], None
    while cur <= end:
        key = cur.strftime("%Y-%m-%d")
        if key not in dc:
            if run is None:
                run = cur
        else:
            if run and (cur - run).days >= min_days:
                out.append({"start": run.strftime("%Y-%m-%d"),
                            "end": (cur - timedelta(days=1)).strftime("%Y-%m-%d"),
                            "days": (cur - run).days})
            run = None
        cur += timedelta(days=1)
    if run and (end - run).days + 1 >= min_days:
        out.append({"start": run.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d"),
                    "days": (end - run).days + 1})
    return out


def phases(c: Cfg, recs, tz, sp, tb) -> list[dict]:
    if not recs:
        return []
    start = _dt(recs[0].ts, tz).date()
    end = _dt(recs[-1].ts, tz).date()
    cand = [(datetime.strptime(s["date"], "%Y-%m-%d").date(), float(s["delta"])) for s in sp]
    cand += [(datetime.strptime(f"{b['to']}-01", "%Y-%m-%d").date(), float(b["drop"])) for b in tb]
    valid = sorted([(d, w) for d, w in cand if start < d <= end], key=lambda x: -x[1])
    bounds = [start] + sorted({d for d, _ in valid[: max(0, c.max_phases - 1)]})

    raw = []
    for i, b in enumerate(bounds):
        nb = bounds[i + 1] if i + 1 < len(bounds) else end + timedelta(days=1)
        seg = [r for r in recs if b <= _dt(r.ts, tz).date() < nb]
        if seg:
            raw.append({"start": b, "end": nb - timedelta(days=1), "recs": seg})

    merged = []
    for seg in raw:
        d = (seg["end"] - seg["start"]).days + 1
        if merged and d < c.min_phase_days:
            merged[-1]["end"] = seg["end"]
            merged[-1]["recs"].extend(seg["recs"])
        else:
            merged.append(seg)

    out = []
    for seg in merged:
        days = (seg["end"] - seg["start"]).days + 1
        n = len(seg["recs"])
        out.append({"start": seg["start"].strftime("%Y-%m-%d"),
                    "end": seg["end"].strftime("%Y-%m-%d"),
                    "days": days, "messages": n,
                    "per_day": round(n / days, 1) if days else n})
    for i, p in enumerate(out):
        if i == 0:
            p["label"] = "起步" if p["per_day"] >= 1 else "近乎空白"
            p["change"] = 1.0
            continue
        prev = out[i - 1]["per_day"] or 1
        ch = p["per_day"] / prev
        p["change"] = round(ch, 2)
        p["label"] = "升温" if ch >= 1.5 else ("退潮" if ch <= 0.7 else "平稳")
    return out


def _tokens(text, stop) -> list[str]:
    if HAS_JIEBA:
        raw = jieba.cut(text)
    else:
        raw = CJK.findall(text)
    return [w for w in raw if len(w) >= 2 and w not in stop and not w.isdigit()
            and not re.fullmatch(r"[\W_]+", w)]


def semantic(c: Cfg, recs, parties) -> dict:
    stop = set(c.stopwords)
    cats = {k: re.compile(v) for k, v in c.categories.items()}
    pos = re.compile(c.positive) if c.positive else None
    neg = re.compile(c.negative) if c.negative else None

    cat_out = {k: Counter() for k in cats}
    emo_out = {w: {"pos": 0, "neg": 0} for w in parties if w}
    words, phrases = {}, {}

    for w in parties:
        if not w:
            continue
        blob = "\n".join(r.text for r in recs if r.who == w and r.typ == "文本" and r.text)
        words[w] = Counter(_tokens(blob, stop)).most_common(c.top_words)
        pc = Counter()
        for t in (r.text for r in recs if r.who == w and r.typ == "文本" and r.text):
            for n in (2, 3, 4):
                for i in range(0, max(0, len(t) - n + 1)):
                    s = t[i:i + n]
                    if CJK.fullmatch(s) and s not in stop:
                        pc[s] += 1
        phrases[w] = [(p, n) for p, n in pc.most_common(400) if n >= c.phrase_min_count][:40]

    for r in recs:
        if r.typ != "文本" or not r.text:
            continue
        for k, pat in cats.items():
            n = len(pat.findall(r.text))
            if n:
                cat_out[k][r.who] += n
        if r.who in emo_out:
            if pos:
                emo_out[r.who]["pos"] += len(pos.findall(r.text))
            if neg:
                emo_out[r.who]["neg"] += len(neg.findall(r.text))

    for w, v in emo_out.items():
        t = v["pos"] + v["neg"]
        v["ratio"] = round(v["pos"] / t, 2) if t else None

    # 探针词：跨档案固定同一组，才能横向比
    probe = ["乖宝", "宝", "喜欢你", "爱你", "想你", "mua", "哈哈", "emmm", "好的吧",
             "算了", "呜呜", "烦死", "咱就是说", "注意", "早点睡", "多喝",
             "对不起", "我错了", "可恶", "嘿嘿"]
    probe_counts = {}
    for w in parties:
        if not w:
            continue
        texts = [r.text for r in recs if r.who == w and r.typ == "文本" and r.text]
        probe_counts[w] = {kw: sum(t.count(kw) for t in texts) for kw in probe}

    return {
        "categories": {k: dict(v) for k, v in cat_out.items() if v},
        "emotion": emo_out,
        "top_words": words,
        "catchphrases": phrases,
        "probe_words": probe_counts,
        "tokenizer": "jieba" if HAS_JIEBA else "char-ngram",
    }


def build_metrics(c: Cfg) -> dict:
    recs = load(c)
    me, other = resolve_parties(c, recs)
    tz = timezone(timedelta(hours=c.tz))
    first, last = recs[0].ts, recs[-1].ts
    days = max(1, (last - first) / 86400)
    parties = (me, other)

    pp = {w: person_metrics(c, recs, w, tz) for w in parties if w}
    sp = spikes(c, recs, tz)
    tb = trend_breaks(c, recs, tz)

    monthly = defaultdict(Counter)
    yearly = defaultdict(Counter)
    for r in recs:
        monthly[_dt(r.ts, tz).strftime("%Y-%m")][r.who] += 1
        yearly[_dt(r.ts, tz).strftime("%Y")][r.who] += 1

    s = sessions(c, recs)
    return {
        "meta": {
            "title": c.title or f"{me} 与 {other}",
            "records": len(recs),
            "first": _dt(first, tz).isoformat(),
            "last": _dt(last, tz).isoformat(),
            "days": round(days, 1),
            "years": round(days / 365.25, 2),
            "per_day": round(len(recs) / days, 1),
            "me": me, "other": other,
            "tokenizer": "jieba" if HAS_JIEBA else "char-ngram",
        },
        "per_person": pp,
        "sessions": s,
        "reply_delay": {w: delays(c, recs, w) for w in parties if w},
        "monthly": {k: dict(v) for k, v in sorted(monthly.items())},
        "yearly": {k: dict(v) for k, v in sorted(yearly.items())},
        "spikes": sp,
        "trend_breaks": tb,
        "phases": phases(c, recs, tz, sp, tb),
        "blank_gaps": calendar_gaps(recs, tz),
        "silence_top": _silence(recs, tz),
        "semantic": semantic(c, recs, parties),
        "hour_total": _hour_total(recs, tz),
    }


def _silence(recs, tz, top=10) -> list[dict]:
    out = []
    for a, b in zip(recs, recs[1:]):
        g = b.ts - a.ts
        if g >= 3 * 86400:
            out.append({"start": _dt(a.ts, tz).strftime("%Y-%m-%d %H:%M"),
                        "end": _dt(b.ts, tz).strftime("%Y-%m-%d %H:%M"),
                        "days": round(g / 86400, 1), "resumed_by": b.who})
    out.sort(key=lambda x: -x["days"])
    return out[:top]


def _hour_total(recs, tz) -> list[int]:
    h = Counter(_dt(r.ts, tz).hour for r in recs)
    return [h.get(i, 0) for i in range(24)]


# ══════════════════ 子命令 ══════════════════

def cmd_analyze(c: Cfg) -> None:
    m = build_metrics(c)
    p = c.out_dir / "metrics.json"
    p.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    meta = m["meta"]
    print(f"记录 {meta['records']:,} 条 · {meta['first'][:10]} → {meta['last'][:10]} · "
          f"{meta['days']:.0f} 天 · 日均 {meta['per_day']}")
    print(f"双方：{meta['me']} / {meta['other']}")
    for w in (meta["me"], meta["other"]):
        p2 = m["per_person"].get(w, {})
        d = m["reply_delay"].get(w, {})
        print(f"  {w}: {p2.get('messages',0):,} 条 / {p2.get('chars',0):,} 字 / "
              f"平均 {p2.get('avg_len',0)} 字 / 回复中位 {d.get('median')}s")
    print(f"会话 {m['sessions']['count']:,} 场 · 平均 {m['sessions']['avg']} 条 · "
          f"最长 {m['sessions']['longest']:,} 条")
    print(f"开场：{m['sessions']['initiator']}")
    print("\n阶段：")
    for x in m["phases"]:
        print(f"  {x['start']} → {x['end']}  {x['days']:>4} 天  {x['messages']:>7,} 条  "
              f"日均 {x['per_day']:>7}  [{x['label']}]")
    print(f"\n已写入 {p}")
    print("下一步：python scripts/scaffold.py -c config.toml --index 1 --name \"对方称呼\"")


def cmd_spikes(c: Cfg) -> None:
    recs = load(c)
    tz = timezone(timedelta(hours=c.tz))
    sp = spikes(c, recs, tz)
    tb = trend_breaks(c, recs, tz)
    gaps = calendar_gaps(recs, tz)
    print(f"突增日 {len(sp)} 个（×{c.spike_ratio}，≥{c.spike_min_messages} 条，增量 ≥{c.spike_min_delta}）")
    for s in sp[:30]:
        print(f"  {s['date']}  {s['messages']:>6,} 条  ×{s['ratio']:<5} 前均 {s['prev_avg']}")
    if tb:
        print(f"\n月度下滑拐点 {len(tb)} 个")
        for b in tb[:10]:
            print(f"  {b['from']} → {b['to']}  环比 ×{b['ratio']}  减少 {b['drop']:,}")
    if gaps:
        print(f"\n完全空白 ≥7 天 {len(gaps)} 段")
        for g in gaps[:10]:
            print(f"  {g['start']} → {g['end']}  {g['days']} 天")


def cmd_grep(c: Cfg, pattern: str, start: str | None, end: str | None,
             ctx: int = 2, limit: int = 30) -> None:
    recs = load(c)
    tz = timezone(timedelta(hours=c.tz))
    pat = re.compile(pattern)
    lo = parse_time(start, c.tz) if start else 0
    hi = parse_time(end, c.tz) if end else 2 ** 40
    if end and len(end) == 10:
        hi += 86400
    idx = [i for i, r in enumerate(recs)
           if lo <= r.ts < hi and r.typ == "文本" and pat.search(r.text)]
    print(f"命中 {len(idx)} 处（最多显示 {limit}）\n")
    for n, i in enumerate(idx[:limit], 1):
        print("-" * 64)
        for j in range(max(0, i - ctx), min(len(recs), i + ctx + 1)):
            r = recs[j]
            t = _dt(r.ts, tz).strftime("%Y-%m-%d %H:%M")
            mark = ">>" if j == i else "  "
            print(f"{mark} [{t}] {r.who}: {r.text[:110]}")


def cmd_dump(c: Cfg, start: str, end: str, limit: int = 0) -> None:
    recs = load(c)
    tz = timezone(timedelta(hours=c.tz))
    lo, hi = parse_time(start, c.tz), parse_time(end, c.tz)
    if lo is None or hi is None:
        raise SystemExit("时间格式无法解析，示例：2022-02-15")
    if len(end) == 10:
        hi += 86400
    sel = [r for r in recs if lo <= r.ts < hi]
    print(f"# {start} ~ {end}  共 {len(sel)} 条\n")
    for r in (sel[:limit] if limit else sel):
        t = _dt(r.ts, tz).strftime("%m-%d %H:%M")
        tag = "" if r.typ == "文本" else f" <{r.typ}>"
        print(f"[{t}] {r.who}{tag}: {r.text.replace(chr(10), ' / ')}")


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        if s and hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except Exception:
                pass
    ap = argparse.ArgumentParser(prog="collect.py", description="恋爱档案数据采集器")
    ap.add_argument("-c", "--config", default="config.toml")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("analyze", help="全量指标 → out/metrics.json（默认）")
    sub.add_parser("spikes", help="拐点与空白期")
    g = sub.add_parser("grep", help="关键词 + 上下文")
    g.add_argument("pattern")
    g.add_argument("start", nargs="?")
    g.add_argument("end", nargs="?")
    g.add_argument("--context", type=int, default=2)
    g.add_argument("--limit", type=int, default=30)
    d = sub.add_parser("dump", help="导出时间窗")
    d.add_argument("start")
    d.add_argument("end")
    d.add_argument("--limit", type=int, default=0)

    a = ap.parse_args(argv)
    c = load_cfg(a.config)

    if a.cmd == "spikes":
        cmd_spikes(c)
    elif a.cmd == "grep":
        cmd_grep(c, a.pattern, a.start, a.end, a.context, a.limit)
    elif a.cmd == "dump":
        cmd_dump(c, a.start, a.end, a.limit)
    else:
        cmd_analyze(c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
