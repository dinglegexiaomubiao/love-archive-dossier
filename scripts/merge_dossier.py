# -*- coding: utf-8 -*-
"""阶段末 · 把多份 section HTML 合并成「单一恋爱档案」自包含网页。

用法：
  python scripts/merge_dossier.py -c dossier.toml
  python scripts/merge_dossier.py -c dossier.toml --out 恋爱档案-对方.html

配置（dossier.example.toml）：
  [dossier]
  title / subtitle / intro / footer / nav_brand
  theme = "dark" | "light"   # 默认 dark（黑底机甲红+金橙，见 references/theme 说明）
  out   = "恋爱档案.html"
  [[dossier.section]]
  id / nav / title / desc / source   # source 为 .html 或 .md（md 会做轻量转 HTML）
  [[dossier.inject]]                  # 可选：把一段 HTML 注入到某个 section 末尾
  into = "portrait"
  html = '<div>...</div>'

设计要点：
  1. 抽取各源 <body>，剥掉自带 header/封面/页脚外层容器与 <style>/<script>。
  2. 统一 CSS 外壳（dark = 关系全档案合并版同款视觉），不拼接源文档各自 CSS。
  3. 图表 base64 内嵌由源文档自己保证；本脚本只搬运 <img src="data:...">。
  4. inject 用于「结论回写」——把深描结论补进画像 section，避免模块孤立。
"""
import argparse
import re
import tomllib
from pathlib import Path

# ── 默认深色主题：黑底 #0f1115 / 机甲红 #E0353F / 金橙 #E8A33D ──
CSS_DARK = """
:root{
  --bg:#0f1115; --card:#171a21; --card2:#1d212b; --line:#2a2f3a;
  --txt:#e6e9ef; --sub:#9aa3b2; --acc:#E0353F; --gold:#E8A33D;
  --green:#3fb950; --yellow:#d8b84a; --blue:#5aa9e6; --red:#e0564f; --purple:#b08be0;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--txt);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.75;margin:0;padding:0 0 80px}
.page{max-width:1000px;margin:0 auto;padding:0 18px}
.toc{position:sticky;top:0;z-index:50;background:rgba(15,17,21,.93);backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line);padding:11px 18px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.toc .brand{font-weight:700;color:var(--gold);margin-right:6px;font-size:14px}
.toc a{color:var(--sub);text-decoration:none;font-size:13px;padding:5px 11px;border:1px solid var(--line);border-radius:20px}
.toc a:hover{color:var(--txt);border-color:var(--gold)}
.master{background:linear-gradient(135deg,#1a1d26,#20242f);border:1px solid var(--gold);border-radius:14px;padding:24px;margin:24px 0}
.master h1{font-size:26px;margin:0 0 8px;border-left:5px solid var(--gold);padding-left:14px;color:#fff}
.master p{color:var(--sub);font-size:14px;margin:6px 0 0}
.parthead{margin:46px 0 8px;padding:14px 16px;border-radius:12px;background:var(--card2);
  border:1px solid var(--line);border-left:5px solid var(--gold)}
.parthead .t{font-size:19px;font-weight:700;color:#fff}
.parthead .d{font-size:13px;color:var(--sub);margin-top:4px}

h1{font-size:24px;letter-spacing:.5px;margin:18px 0 8px}
h2{font-size:20px;margin:34px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line);color:#fff}
h3{font-size:16px;margin:20px 0 8px;color:var(--gold)}
h4{font-size:14.5px;margin:14px 0 6px;color:var(--blue)}
p{margin:9px 0;color:#d7dbe4}
.lead{color:var(--sub);font-size:14px;margin-bottom:20px}
.tag{font-size:12px;color:var(--sub)}
.note{font-size:12.5px;color:var(--sub);margin:10px 2px}

.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.stat{background:var(--card2);border:1px solid var(--line);border-radius:10px;padding:14px;text-align:center}
.stat .n{font-size:22px;font-weight:700;color:var(--gold)}
.stat .l{font-size:12px;color:var(--sub);margin-top:4px}

.ov{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden;border:1px solid var(--line)}
.ov th,.ov td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:center;font-size:13.5px}
.ov th{background:var(--card2);color:#fff}
.ov tr:nth-child(even){background:rgba(255,255,255,.02)}
.cols{display:flex;gap:18px;flex-wrap:wrap;margin-top:18px}
.card.blue{border-top:4px solid var(--blue)} .card.pink{border-top:4px solid var(--acc)}
.card h3{margin:0 0 4px;font-size:19px;color:#fff}
.card.blue h3{color:var(--blue)} .card.pink h3{color:var(--acc)}
.tagline{color:var(--sub);font-size:13px;margin:0 0 12px;border-left:3px solid var(--line);padding-left:8px}
.card h4{margin:14px 0 6px;font-size:14.5px;color:#fff;border-bottom:1px dashed var(--line);padding-bottom:3px}
.card ul{margin:4px 0;padding-left:18px;font-size:13.5px} .card li{margin:3px 0;color:#d7dbe4}
.dyn{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin-top:18px}
.dyn h3{margin-top:0;color:#fff} .dyn h4{color:var(--blue);font-size:15px;margin:14px 0 6px}
.dyn ul{font-size:13.5px;padding-left:18px} .dyn li{color:#d7dbe4}
.ev{width:100%;border-collapse:collapse;margin:10px 0;font-size:12.8px;background:var(--card)}
.ev th,.ev td{border:1px solid var(--line);padding:7px 9px;vertical-align:top}
.ev th{background:rgba(224,53,63,.20);color:#ffb3c0}
.ev td:nth-child(2){background:rgba(224,53,63,.06)}
.ev td:nth-child(3){background:rgba(90,169,230,.06)}
section{margin-top:22px}
.cloud{display:flex;gap:16px;flex-wrap:wrap}
.cloud .box{flex:1;min-width:300px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;text-align:center}
.cloud .box h4{margin:2px 0 8px;color:#fff}
.w{display:inline-block;margin:3px 5px;line-height:1.2;font-weight:600;color:var(--gold)}
img.chart{width:100%;border-radius:10px;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.3);margin:8px 0}

.quote{background:#11141a;border-left:3px solid var(--gold);padding:8px 12px;margin:8px 0;font-size:13px;color:#cfd4dd;border-radius:4px}
.quote b{color:var(--gold)}
.quote.liu,.quote.l{border-left-color:var(--red)} .quote.liu b,.quote.l b{color:var(--red)}
.quote.u{border-left-color:var(--blue)} .quote.u b{color:var(--blue)}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11.5px;font-weight:600;white-space:nowrap}
.b-own{background:rgba(224,86,79,.16);color:var(--red);border:1px solid rgba(224,86,79,.4)}
.b-part{background:rgba(216,184,74,.16);color:var(--yellow);border:1px solid rgba(216,184,74,.4)}
.b-proj{background:rgba(90,169,230,.16);color:var(--blue);border:1px solid rgba(90,169,230,.4)}
.b-u{background:rgba(90,169,230,.16);color:var(--blue);border:1px solid rgba(90,169,230,.4)}
.b-l{background:rgba(224,86,79,.16);color:var(--red);border:1px solid rgba(224,86,79,.4)}
.b-both{background:rgba(176,139,224,.16);color:var(--purple);border:1px solid rgba(176,139,224,.4)}

.own{background:rgba(224,86,79,.08);border:1px solid rgba(224,86,79,.35);border-radius:12px;padding:16px 18px;margin:14px 0}
.proj{background:rgba(90,169,230,.08);border:1px solid rgba(90,169,230,.35);border-radius:12px;padding:16px 18px;margin:14px 0}
.good{background:rgba(63,185,80,.08);border:1px solid rgba(63,185,80,.35);border-radius:12px;padding:16px 18px;margin:14px 0}
.summary{background:linear-gradient(135deg,#1a1d26,#20242f);border:1px solid var(--gold);border-radius:14px;padding:22px 24px;margin:20px 0}
.summary p{color:#d7dbe4}

.bar{height:22px;border-radius:6px;background:linear-gradient(90deg,var(--gold),#f0c46b);display:flex;align-items:center;justify-content:flex-end;padding-right:8px;font-size:11px;color:#1a1208;font-weight:700}
.bar.blue{background:linear-gradient(90deg,var(--blue),#8cc6f0)}
.bar-row{display:flex;align-items:center;gap:10px;margin:8px 0}
.bar-row .lab{width:160px;font-size:13px;color:var(--sub)}
.bar-row .track{flex:1;background:var(--card2);border-radius:6px;overflow:hidden}
.bar-row .val{width:90px;font-size:12px;text-align:right;color:var(--sub)}

.fight{border:1px solid var(--line);border-radius:14px;margin:22px 0;overflow:hidden;background:var(--card)}
.fight .head{background:linear-gradient(90deg,#1d212b,#171a21);padding:14px 18px;border-bottom:1px solid var(--line)}
.fight .head .t{font-size:17px;font-weight:700;color:#fff}
.fight .head .m{font-size:12.5px;color:var(--sub);margin-top:3px}
.fight .body{padding:14px 18px}
.link{background:rgba(232,163,61,.08);border:1px solid rgba(232,163,61,.3);border-radius:10px;padding:10px 13px;margin:10px 0;font-size:12.5px;color:var(--sub)}
.link b{color:var(--gold)}
.rule{background:var(--card2);border:1px solid var(--line);border-left:4px solid var(--gold);border-radius:8px;padding:13px 15px;margin:14px 0}
.rule .h{font-size:14px;font-weight:700;color:#fff;margin-bottom:6px}

table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px}
th,td{border:1px solid var(--line);padding:9px 10px;vertical-align:top;text-align:left}
th{background:var(--card2);color:#fff;font-weight:600}
td.q{color:var(--sub);font-size:12.5px}
ul{margin:8px 0 8px 4px;padding-left:18px} li{margin:6px 0;color:#d7dbe4}
.foot{margin-top:40px;color:var(--sub);font-size:12px;text-align:center;border-top:1px solid var(--line);padding-top:16px}
.hl{color:var(--gold);font-weight:600} .hlred,.hlr{color:var(--red);font-weight:600} .hlgreen,.hlg{color:var(--green);font-weight:600}
"""

CSS_LIGHT = """
:root{
  --bg:#f6f8fc; --card:#ffffff; --card2:#eef2fa; --line:#d7deee;
  --txt:#1a2030; --sub:#5b6785; --acc:#E0353F; --gold:#c8862a;
  --green:#2f9e57; --yellow:#b8941f; --blue:#3f7fc0; --red:#d23b46; --purple:#7d5fb0;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--txt);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.75;margin:0;padding:0 0 80px}
.page{max-width:1000px;margin:0 auto;padding:0 18px}
.toc{position:sticky;top:0;z-index:50;background:rgba(246,248,252,.95);backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line);padding:11px 18px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.toc .brand{font-weight:700;color:var(--gold);margin-right:6px;font-size:14px}
.toc a{color:var(--sub);text-decoration:none;font-size:13px;padding:5px 11px;border:1px solid var(--line);border-radius:20px}
.toc a:hover{color:var(--txt);border-color:var(--gold)}
.master{background:linear-gradient(135deg,#ffffff,#eef2fa);border:1px solid var(--gold);border-radius:14px;padding:24px;margin:24px 0}
.master h1{font-size:26px;margin:0 0 8px;border-left:5px solid var(--gold);padding-left:14px;color:#111827}
.master p{color:var(--sub);font-size:14px;margin:6px 0 0}
.parthead{margin:46px 0 8px;padding:14px 16px;border-radius:12px;background:var(--card2);
  border:1px solid var(--line);border-left:5px solid var(--gold)}
.parthead .t{font-size:19px;font-weight:700;color:#111827}
.parthead .d{font-size:13px;color:var(--sub);margin-top:4px}
h1{font-size:24px;letter-spacing:.5px;margin:18px 0 8px}
h2{font-size:20px;margin:34px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line);color:#111827}
h3{font-size:16px;margin:20px 0 8px;color:var(--gold)}
h4{font-size:14.5px;margin:14px 0 6px;color:var(--blue)}
p{margin:9px 0;color:#38445f}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.stat{background:var(--card2);border:1px solid var(--line);border-radius:10px;padding:14px;text-align:center}
.stat .n{font-size:22px;font-weight:700;color:var(--gold)}
.stat .l{font-size:12px;color:var(--sub);margin-top:4px}
.ov{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden;border:1px solid var(--line)}
.ov th,.ov td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:center;font-size:13.5px}
.ov th{background:var(--card2);color:#111827}
.ov tr:nth-child(even){background:rgba(0,0,0,.02)}
.cols{display:flex;gap:18px;flex-wrap:wrap;margin-top:18px}
.card.blue{border-top:4px solid var(--blue)} .card.pink{border-top:4px solid var(--acc)}
.card h3{margin:0 0 4px;font-size:19px;color:#111827}
.card.blue h3{color:var(--blue)} .card.pink h3{color:var(--acc)}
.card h4{margin:14px 0 6px;font-size:14.5px;color:#111827;border-bottom:1px dashed var(--line);padding-bottom:3px}
.card ul{margin:4px 0;padding-left:18px;font-size:13.5px} .card li{margin:3px 0;color:#38445f}
.dyn{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin-top:18px}
.dyn h3{margin-top:0;color:#111827} .dyn h4{color:var(--blue);font-size:15px;margin:14px 0 6px}
.dyn ul{font-size:13.5px;padding-left:18px} .dyn li{color:#38445f}
.ev{width:100%;border-collapse:collapse;margin:10px 0;font-size:12.8px;background:var(--card)}
.ev th,.ev td{border:1px solid var(--line);padding:7px 9px;vertical-align:top}
.ev th{background:rgba(224,53,63,.12);color:#a01f1f}
section{margin-top:22px}
.cloud{display:flex;gap:16px;flex-wrap:wrap}
.cloud .box{flex:1;min-width:300px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;text-align:center}
.cloud .box h4{margin:2px 0 8px;color:#111827}
.w{display:inline-block;margin:3px 5px;line-height:1.2;font-weight:600;color:var(--gold)}
img.chart{width:100%;border-radius:10px;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.1);margin:8px 0}
.quote{background:#f0f3f9;border-left:3px solid var(--gold);padding:8px 12px;margin:8px 0;font-size:13px;color:#3a4256;border-radius:4px}
.quote b{color:var(--gold)}
.quote.liu,.quote.l{border-left-color:var(--red)} .quote.liu b,.quote.l b{color:var(--red)}
.quote.u{border-left-color:var(--blue)} .quote.u b{color:var(--blue)}
.own{background:rgba(224,86,79,.06);border:1px solid rgba(224,86,79,.3);border-radius:12px;padding:16px 18px;margin:14px 0}
.proj{background:rgba(90,169,230,.06);border:1px solid rgba(90,169,230,.3);border-radius:12px;padding:16px 18px;margin:14px 0}
.good{background:rgba(63,185,80,.06);border:1px solid rgba(63,185,80,.3);border-radius:12px;padding:16px 18px;margin:14px 0}
.summary{background:linear-gradient(135deg,#ffffff,#eef2fa);border:1px solid var(--gold);border-radius:14px;padding:22px 24px;margin:20px 0}
.summary p{color:#38445f}
.bar{height:22px;border-radius:6px;background:linear-gradient(90deg,var(--gold),#e6c489);display:flex;align-items:center;justify-content:flex-end;padding-right:8px;font-size:11px;color:#1a1208;font-weight:700}
.bar.blue{background:linear-gradient(90deg,var(--blue),#9fc3e0)}
.bar-row{display:flex;align-items:center;gap:10px;margin:8px 0}
.bar-row .lab{width:160px;font-size:13px;color:var(--sub)}
.bar-row .track{flex:1;background:var(--card2);border-radius:6px;overflow:hidden}
.bar-row .val{width:90px;font-size:12px;text-align:right;color:var(--sub)}
.fight{border:1px solid var(--line);border-radius:14px;margin:22px 0;overflow:hidden;background:var(--card)}
.fight .head{background:linear-gradient(90deg,#eef2fa,#ffffff);padding:14px 18px;border-bottom:1px solid var(--line)}
.fight .head .t{font-size:17px;font-weight:700;color:#111827}
.fight .head .m{font-size:12.5px;color:var(--sub);margin-top:3px}
.fight .body{padding:14px 18px}
.link{background:rgba(200,134,42,.08);border:1px solid rgba(200,134,42,.3);border-radius:10px;padding:10px 13px;margin:10px 0;font-size:12.5px;color:var(--sub)}
.link b{color:var(--gold)}
.rule{background:var(--card2);border:1px solid var(--line);border-left:4px solid var(--gold);border-radius:8px;padding:13px 15px;margin:14px 0}
.rule .h{font-size:14px;font-weight:700;color:#111827;margin-bottom:6px}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px}
th,td{border:1px solid var(--line);padding:9px 10px;vertical-align:top;text-align:left}
th{background:var(--card2);color:#111827;font-weight:600}
ul{margin:8px 0 8px 4px;padding-left:18px} li{margin:6px 0;color:#38445f}
.foot{margin-top:40px;color:var(--sub);font-size:12px;text-align:center;border-top:1px solid var(--line);padding-top:16px}
.hl{color:var(--gold);font-weight:600} .hlred,.hlr{color:var(--red);font-weight:600} .hlgreen,.hlg{color:var(--green);font-weight:600}
"""


def extract_body(path: Path) -> str:
    txt = path.read_text(encoding="utf-8")
    m = re.search(r"<body[^>]*>(.*)</body>", txt, re.S)
    body = m.group(1) if m else txt
    body = re.sub(r"<header.*?</header>", "", body, flags=re.S)
    body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
    body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    return body.strip()


def md_to_html(src: str) -> str:
    """极简 MD→HTML：标题/表格/引用/列表/粗体。复杂内容请直接给 HTML。"""
    lines = src.splitlines()
    out, in_tbl = [], False
    for ln in lines:
        s = ln.rstrip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            if not in_tbl:
                out.append("<table>")
                out.append("<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
                in_tbl = True
            else:
                out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_tbl:
            out.append("</table>")
            in_tbl = False
        if s.startswith("#"):
            n = len(s) - len(s.lstrip("#"))
            out.append(f"<h{n}>{s.lstrip('# ').strip()}</h{n}>")
        elif s.startswith(">"):
            out.append(f"<div class='quote'>{s.lstrip('> ').strip()}</div>")
        elif re.match(r"^[-*] ", s):
            out.append(f"<li>{s[2:].strip()}</li>")
        elif s.strip() == "":
            out.append("")
        else:
            out.append(f"<p>{s}</p>")
    if in_tbl:
        out.append("</table>")
    html = "\n".join(out)
    html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
    return html


def load_section(src: str, base: Path) -> str:
    p = Path(src)
    if not p.is_absolute():
        p = base / p
    if not p.is_file():
        raise SystemExit(f"源文件不存在：{p}")
    if p.suffix.lower() in (".md", ".markdown"):
        return md_to_html(p.read_text(encoding="utf-8"))
    return extract_body(p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="merge_dossier.py", description="合并档案为单一网页")
    ap.add_argument("-c", "--config", default="dossier.toml")
    ap.add_argument("--out", help="覆盖配置里的输出路径")
    args = ap.parse_args(argv)

    cfg_path = Path(args.config).expanduser()
    with cfg_path.open("rb") as f:
        cfg = tomllib.load(f)
    d = cfg.get("dossier", {})
    base = cfg_path.resolve().parent
    sections = d.get("section", [])
    if not sections:
        raise SystemExit("配置里没有 [[dossier.section]]")

    theme = d.get("theme", "dark")
    css = CSS_LIGHT if theme == "light" else CSS_DARK

    parts = ["<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             f"<title>{d.get('title','关系全档案')}</title>",
             f"<style>{css}</style></head><body>"]
    parts.append("<nav class='toc'><span class='brand'>" +
                 d.get("nav_brand", "关系全档案") + "</span>")
    for s in sections:
        parts.append(f"<a href='#{s['id']}'>{s.get('nav', s['title'])}</a>")
    parts.append("</nav><div class='page'>")
    parts.append("<div class='master'><h1>" + d.get("title", "关系全档案") + "</h1>")
    if d.get("subtitle"):
        parts.append("<p><b>" + d["subtitle"] + "</b></p>")
    if d.get("intro"):
        parts.append("<p>" + d["intro"] + "</p>")
    parts.append("</div>")

    injects = {}
    for inj in d.get("inject", []):
        injects.setdefault(inj["into"], []).append(inj["html"])

    for s in sections:
        parts.append(f"<section id='{s['id']}'>")
        parts.append("<div class='parthead'><div class='t'>" + s["title"] + "</div>")
        if s.get("desc"):
            parts.append("<div class='d'>" + s["desc"] + "</div>")
        parts.append("</div>")
        parts.append(load_section(s["source"], base))
        for h in injects.get(s["id"], []):
            parts.append(h)
        parts.append("</section>")

    parts.append("<div class='foot'>" + d.get("footer", "") + "</div>")
    parts.append("</div></body></html>")

    out = Path(args.out) if args.out else Path(d.get("out", "关系全档案.html"))
    if not out.is_absolute():
        out = base / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"已生成 {out} · {out.stat().st_size:,} bytes · {len(sections)} 个 section")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
