# -*- coding: utf-8 -*-
"""阶段末 · 把多份 section HTML 合并成「单一恋爱档案」自包含网页。

用法：
  python scripts/merge_dossier.py -c dossier.toml
  python scripts/merge_dossier.py -c dossier.toml --out 恋爱档案-对方.html

配置（dossier.example.toml）：
  [dossier]
  title / subtitle / intro / footer / kicker / nav_brand
  theme = "warm" | "dark"   # 默认 warm（暖色书本风，参照《对话精选》调性）
  out   = "恋爱档案.html"
  [[dossier.section]]
  id / nav / title / desc / source   # source 为 .html 或 .md（md 会做轻量转 HTML）
  [[dossier.inject]]                  # 可选：把一段 HTML 注入到某个 section 末尾
  into = "1"
  html = '<div>...</div>'

设计要点：
  1. 抽取各源 <body>，剥掉自带 header/封面/页脚外层容器与 <style>/<script>。
  2. 统一 CSS 外壳（warm = 暖色纸感 + 宋体衬线大标题，窄阅读栏书本式），不拼接源文档各自 CSS。
  3. 外壳走「封面 + 暖色目录 + 分节（衬线序号）」结构，向《对话精选》的阅读体验看齐。
  4. 图表 base64 内嵌由源文档自己保证；本脚本只搬运 <img src="data:...">。
  5. inject 用于「结论回写」——把深描结论补进画像 section，避免模块孤立。
"""
import argparse
import re
import tomllib
from pathlib import Path

CN = "〇一二三四五六七八九十"


def cn_index(i: int) -> str:
    if i <= 10:
        return CN[i] if i < 10 else "十"
    return ("十" + CN[i - 10]) if i < 20 else str(i)


# ── 默认暖色书本风：米白纸感 #FDF9F3 / 暖陶红 #B5533C / 暖金 #C8862A / 宋体衬线 ──
# 参照《对话精选》的调性：窄阅读栏、衬线大标题、字距 kicker、暖色目录与分角色配色。
CSS_WARM = """
:root{
  --paper:#FDF9F3; --ink:#332C27; --ink2:#5A4F47; --muted:#8E8073; --line:#E6D9C8;
  --warm:#B8603C; --warm-soft:#FBF1E4;
  --her:#B5533C; --her-bg:#FBEDE7;
  --me:#3F6480;  --me-bg:#EAF1F6;
  --gold:#C8862A; --green:#2f9e57; --green-bg:#E8F3EC;
  --yellow:#b8941f; --purple:#7d5fb0;
  --serif:"Songti SC","STSong","Source Han Serif SC","Noto Serif CJK SC",SimSun,serif;
  --sans:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
  font-size:15.5px;line-height:1.9;-webkit-font-smoothing:antialiased}
.wrap{max-width:720px;margin:0 auto;padding:0 28px 110px}

.cover{padding:84px 0 34px;text-align:left}
.cover .k{font-size:11px;letter-spacing:.42em;color:var(--muted);margin-bottom:24px}
.cover h1{font-family:var(--serif);font-size:46px;font-weight:500;margin:0 0 14px;letter-spacing:.1em;color:var(--ink)}
.cover .s{font-family:var(--serif);font-size:17px;color:var(--ink2);line-height:1.9;margin:0 0 24px}
.cover .note{font-size:13.5px;color:var(--muted);line-height:1.95;border-left:2px solid var(--line);padding-left:16px}

.toc{margin:30px 0 10px;padding:20px 24px;background:var(--warm-soft);border-radius:12px}
.toc .th{font-size:11px;letter-spacing:.22em;color:var(--warm);margin-bottom:10px}
.toc ol{margin:0;padding-left:20px;font-size:13.6px;line-height:2.05;color:var(--ink2)}
.toc a{color:var(--ink2);text-decoration:none;border-bottom:1px dotted #CBBBA4}
.toc a:hover{color:var(--warm);border-bottom-color:var(--warm)}
.toc em{font-style:normal;color:var(--muted);font-size:12px;margin-left:6px}

.scene{padding:50px 0 8px;border-top:1px solid var(--line);margin-top:30px}
.scene:first-of-type{border-top:none}
.head{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
.num{font-family:var(--serif);font-size:12.5px;color:var(--warm);letter-spacing:.2em}
.scene h2{font-family:var(--serif);font-size:26px;font-weight:500;margin:0 0 14px;letter-spacing:.03em;line-height:1.4;color:var(--ink)}
.scene .note{font-size:13px;color:var(--muted);line-height:1.9;margin:0 0 18px;border-left:2px solid var(--line);padding-left:14px}

h3{font-size:17px;margin:24px 0 10px;color:var(--warm)}
h4{font-size:15px;margin:18px 0 8px;color:var(--me)}
p{margin:9px 0;color:var(--ink2)}
.lead{color:var(--muted);font-size:14px;margin-bottom:20px}
.tag{font-size:12px;color:var(--muted)}
.note{font-size:12.5px;color:var(--muted);margin:10px 2px}
ul{margin:8px 0 8px 4px;padding-left:18px} li{margin:6px 0;color:var(--ink2)}

.card{background:#FFFDFA;border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.stat{background:var(--warm-soft);border:1px solid var(--line);border-radius:10px;padding:14px;text-align:center}
.stat .n{font-size:22px;font-weight:700;color:var(--gold)}
.stat .l{font-size:12px;color:var(--muted);margin-top:4px}
.ov{width:100%;border-collapse:collapse;background:#FFFDFA;border-radius:10px;overflow:hidden;border:1px solid var(--line)}
.ov th,.ov td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:center;font-size:13.5px}
.ov th{background:var(--warm-soft);color:var(--ink)}
.ov tr:nth-child(even){background:rgba(0,0,0,.02)}
.cols{display:flex;gap:18px;flex-wrap:wrap;margin-top:18px}
.card.blue{border-top:4px solid var(--me)} .card.pink{border-top:4px solid var(--her)}
.card h3{margin:0 0 4px;font-size:19px;color:var(--ink)}
.card.blue h3{color:var(--me)} .card.pink h3{color:var(--her)}
.card h4{margin:14px 0 6px;font-size:14.5px;color:var(--ink);border-bottom:1px dashed var(--line);padding-bottom:3px}
.card ul{margin:4px 0;padding-left:18px;font-size:13.5px} .card li{margin:3px 0;color:var(--ink2)}

.dyn{background:#FFFDFA;border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin-top:18px}
.dyn h3{margin-top:0;color:var(--ink)} .dyn h4{color:var(--me);font-size:15px;margin:14px 0 6px}
.dyn ul{font-size:13.5px;padding-left:18px} .dyn li{color:var(--ink2)}

.bar{height:22px;border-radius:6px;background:linear-gradient(90deg,var(--warm),#d98a5e);display:flex;align-items:center;justify-content:flex-end;padding-right:8px;font-size:11px;color:#fff;font-weight:700}
.bar.blue{background:linear-gradient(90deg,var(--me),#7fa8c8)}
.bar-row{display:flex;align-items:center;gap:10px;margin:8px 0}
.bar-row .lab{width:160px;font-size:13px;color:var(--muted)}
.bar-row .track{flex:1;background:var(--warm-soft);border-radius:6px;overflow:hidden}
.bar-row .val{width:90px;font-size:12px;text-align:right;color:var(--muted)}

.fight{border:1px solid var(--line);border-radius:14px;margin:22px 0;overflow:hidden;background:#FFFDFA}
.fight .head{background:var(--warm-soft);padding:14px 18px;border-bottom:1px solid var(--line)}
.fight .head .t{font-size:17px;font-weight:700;color:var(--ink)}
.fight .head .m{font-size:12.5px;color:var(--muted);margin-top:3px}
.fight .body{padding:14px 18px}

.quote{background:#FBF4EA;border-left:3px solid var(--gold);padding:8px 12px;margin:8px 0;font-size:13px;color:var(--ink2);border-radius:4px}
.quote b{color:var(--warm)}
.quote.liu,.quote.l{border-left-color:var(--her)} .quote.liu b,.quote.l b{color:var(--her)}
.quote.u{border-left-color:var(--me)} .quote.u b{color:var(--me)}

.own{background:rgba(181,83,60,.08);border:1px solid rgba(181,83,60,.35);border-radius:12px;padding:16px 18px;margin:14px 0}
.proj{background:rgba(63,100,128,.08);border:1px solid rgba(63,100,128,.35);border-radius:12px;padding:16px 18px;margin:14px 0}
.good{background:rgba(47,158,87,.08);border:1px solid rgba(47,158,87,.35);border-radius:12px;padding:16px 18px;margin:14px 0}

.summary{background:var(--warm-soft);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin:20px 0}
.summary p{color:var(--ink2)}
.summary .q{font-family:var(--serif);font-size:17.5px;line-height:1.82;color:var(--ink);border-left:3px solid var(--warm);padding-left:16px;margin:16px 0}

.cloud{display:flex;gap:16px;flex-wrap:wrap}
.cloud .box{flex:1;min-width:260px;background:#FFFDFA;border:1px solid var(--line);border-radius:12px;padding:14px;text-align:center}
.cloud .box h4{margin:2px 0 8px;color:var(--ink)}
.w{display:inline-block;margin:3px 5px;line-height:1.2;font-weight:600;color:var(--warm)}

.ev{width:100%;border-collapse:collapse;margin:10px 0;font-size:12.8px;background:#FFFDFA}
.ev th,.ev td{border:1px solid var(--line);padding:7px 9px;vertical-align:top}
.ev th{background:rgba(181,83,60,.12);color:#8a3a28}
.ev td:nth-child(2){background:rgba(63,100,128,.06)}
.ev td:nth-child(3){background:rgba(181,83,60,.06)}

.rule{background:var(--warm-soft);border:1px solid var(--line);border-left:4px solid var(--gold);border-radius:8px;padding:13px 15px;margin:14px 0}
.rule .h{font-size:14px;font-weight:700;color:var(--ink);margin-bottom:6px}

.link{background:rgba(200,134,42,.08);border:1px solid rgba(200,134,42,.3);border-radius:10px;padding:10px 13px;margin:10px 0;font-size:12.5px;color:var(--muted)}
.link b{color:var(--gold)}

table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px}
th,td{border:1px solid var(--line);padding:9px 10px;vertical-align:top;text-align:left}
th{background:var(--warm-soft);color:var(--ink);font-weight:600}
td.q{color:var(--muted);font-size:12.5px}

.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11.5px;font-weight:600;white-space:nowrap}
.b-own{background:rgba(181,83,60,.16);color:var(--her);border:1px solid rgba(181,83,60,.4)}
.b-part{background:rgba(184,148,31,.16);color:var(--yellow);border:1px solid rgba(184,148,31,.4)}
.b-proj{background:rgba(63,100,128,.16);color:var(--me);border:1px solid rgba(63,100,128,.4)}
.b-u{background:rgba(63,100,128,.16);color:var(--me);border:1px solid rgba(63,100,128,.4)}
.b-l{background:rgba(181,83,60,.16);color:var(--her);border:1px solid rgba(181,83,60,.4)}
.b-both{background:rgba(125,95,176,.16);color:var(--purple);border:1px solid rgba(125,95,176,.4)}

img.chart{width:100%;border-radius:10px;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.06);margin:8px 0}
.hl{color:var(--gold);font-weight:600} .hlred,.hlr{color:var(--her);font-weight:600} .hlgreen,.hlg{color:var(--green);font-weight:600}

.foot{margin-top:56px;padding-top:28px;border-top:1px solid var(--line);color:var(--muted);font-size:12px;text-align:center}

@media(max-width:680px){
  .cover h1{font-size:34px}
  .scene h2{font-size:21px}
  .wrap{padding:0 20px 80px}
}
@media print{
  body{background:#fff}
  .scene{page-break-inside:avoid}
}
"""

# ── 旧版暗色机甲主题（legacy，theme="dark" 时启用，默认不再使用）──
CSS_DARK = """
:root{
  --bg:#0f1115; --card:#171a21; --card2:#1d212b; --line:#2a2f3a;
  --txt:#e6e9ef; --sub:#9aa3b2; --acc:#E0353F; --gold:#E8A33D;
  --green:#3fb950; --yellow:#d8b84a; --blue:#5aa9e6; --red:#e0564f; --purple:#b08be0;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--txt);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.75;margin:0;padding:0 0 80px}
.wrap{max-width:1000px;margin:0 auto;padding:0 18px}
.cover{padding:40px 0 10px}
.cover .k{font-size:11px;letter-spacing:.42em;color:var(--sub);margin-bottom:14px}
.cover h1{font-size:30px;font-weight:700;margin:0 0 8px;border-left:5px solid var(--gold);padding-left:14px;color:#fff}
.cover .s{font-size:15px;color:var(--sub);margin:0 0 8px}
.cover .note{font-size:13px;color:var(--sub);line-height:1.8;border-left:2px solid var(--line);padding-left:14px}
.toc{margin:20px 0 4px;padding:16px 18px;background:var(--card2);border:1px solid var(--line);border-radius:12px}
.toc .th{font-size:11px;letter-spacing:.22em;color:var(--gold);margin-bottom:8px}
.toc ol{margin:0;padding-left:20px;font-size:13.4px;line-height:2;color:var(--sub)}
.toc a{color:var(--sub);text-decoration:none}
.toc a:hover{color:var(--txt)}
.toc em{font-style:normal;color:var(--sub);font-size:12px;margin-left:6px}
.scene{margin-top:26px;padding-top:22px;border-top:1px solid var(--line)}
.head{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
.num{font-size:12.5px;color:var(--gold);letter-spacing:.2em}
.scene h2{font-size:22px;font-weight:700;margin:0 0 12px;color:#fff}
.scene .note{font-size:13px;color:var(--sub);margin:0 0 14px}
h3{font-size:16px;margin:20px 0 8px;color:var(--gold)}
h4{font-size:14.5px;margin:14px 0 6px;color:var(--blue)}
p{margin:9px 0;color:#d7dbe4}
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
.card h4{margin:14px 0 6px;font-size:14.5px;color:#fff;border-bottom:1px dashed var(--line);padding-bottom:3px}
.card ul{margin:4px 0;padding-left:18px;font-size:13.5px} .card li{margin:3px 0;color:#d7dbe4}
.dyn{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin-top:18px}
.dyn h3{margin-top:0;color:#fff} .dyn h4{color:var(--blue);font-size:15px;margin:14px 0 6px}
.dyn ul{font-size:13.5px;padding-left:18px} .dyn li{color:#d7dbe4}
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
.quote{background:#11141a;border-left:3px solid var(--gold);padding:8px 12px;margin:8px 0;font-size:13px;color:#cfd4dd;border-radius:4px}
.quote b{color:var(--gold)}
.quote.liu,.quote.l{border-left-color:var(--red)} .quote.liu b,.quote.l b{color:var(--red)}
.quote.u{border-left-color:var(--blue)} .quote.u b{color:var(--blue)}
.own{background:rgba(224,86,79,.08);border:1px solid rgba(224,86,79,.35);border-radius:12px;padding:16px 18px;margin:14px 0}
.proj{background:rgba(90,169,230,.08);border:1px solid rgba(90,169,230,.35);border-radius:12px;padding:16px 18px;margin:14px 0}
.good{background:rgba(63,185,80,.08);border:1px solid rgba(63,185,80,.35);border-radius:12px;padding:16px 18px;margin:14px 0}
.summary{background:linear-gradient(135deg,#1a1d26,#20242f);border:1px solid var(--gold);border-radius:14px;padding:22px 24px;margin:20px 0}
.summary p{color:#d7dbe4}
.summary .q{font-family:inherit;font-size:17.5px;line-height:1.82;color:#fff;border-left:3px solid var(--gold);padding-left:16px;margin:16px 0}
.cloud{display:flex;gap:16px;flex-wrap:wrap}
.cloud .box{flex:1;min-width:300px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;text-align:center}
.cloud .box h4{margin:2px 0 8px;color:#fff}
.w{display:inline-block;margin:3px 5px;line-height:1.2;font-weight:600;color:var(--gold)}
.ev{width:100%;border-collapse:collapse;margin:10px 0;font-size:12.8px;background:var(--card)}
.ev th,.ev td{border:1px solid var(--line);padding:7px 9px;vertical-align:top}
.ev th{background:rgba(224,53,63,.20);color:#ffb3c0}
.ev td:nth-child(2){background:rgba(224,53,63,.06)}
.ev td:nth-child(3){background:rgba(90,169,230,.06)}
.rule{background:var(--card2);border:1px solid var(--line);border-left:4px solid var(--gold);border-radius:8px;padding:13px 15px;margin:14px 0}
.rule .h{font-size:14px;font-weight:700;color:#fff;margin-bottom:6px}
.link{background:rgba(232,163,61,.08);border:1px solid rgba(232,163,61,.3);border-radius:10px;padding:10px 13px;margin:10px 0;font-size:12.5px;color:var(--sub)}
.link b{color:var(--gold)}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px}
th,td{border:1px solid var(--line);padding:9px 10px;vertical-align:top;text-align:left}
th{background:var(--card2);color:#fff;font-weight:600}
td.q{color:var(--sub);font-size:12.5px}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11.5px;font-weight:600;white-space:nowrap}
.b-own{background:rgba(224,86,79,.16);color:var(--red);border:1px solid rgba(224,86,79,.4)}
.b-part{background:rgba(216,184,74,.16);color:var(--yellow);border:1px solid rgba(216,184,74,.4)}
.b-proj{background:rgba(90,169,230,.16);color:var(--blue);border:1px solid rgba(90,169,230,.4)}
.b-u{background:rgba(90,169,230,.16);color:var(--blue);border:1px solid rgba(90,169,230,.4)}
.b-l{background:rgba(224,86,79,.16);color:var(--red);border:1px solid rgba(224,86,79,.4)}
.b-both{background:rgba(176,139,224,.16);color:var(--purple);border:1px solid rgba(176,139,224,.4)}
img.chart{width:100%;border-radius:10px;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.3);margin:8px 0}
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

    theme = d.get("theme", "warm")
    css = CSS_DARK if theme == "dark" else CSS_WARM
    kicker = d.get("kicker", d.get("nav_brand", "恋爱档案"))

    parts = ["<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             f"<title>{d.get('title','恋爱档案')}</title>",
             f"<style>{css}</style></head><body>"]
    parts.append("<div class='wrap'>")

    # 封面（参照《对话精选》的 cover：字距 kicker + 衬线大标题 + 副标 + 注脚）
    parts.append("<header class='cover'>")
    parts.append(f"<div class='k'>{kicker}</div>")
    parts.append(f"<h1>{d.get('title','恋爱档案')}</h1>")
    if d.get("subtitle"):
        parts.append(f"<p class='s'>{d['subtitle']}</p>")
    if d.get("intro"):
        parts.append(f"<p class='note'>{d['intro']}</p>")
    parts.append("</header>")

    # 暖色目录（编号列表，锚点跳转）
    parts.append("<nav class='toc'><div class='th'>目 录</div><ol>")
    for i, s in enumerate(sections, 1):
        label = s.get("nav", s["title"])
        parts.append(f"<li><a href='#{s['id']}'>{i}. {label}</a></li>")
    parts.append("</ol></nav>")

    injects = {}
    for inj in d.get("inject", []):
        injects.setdefault(inj["into"], []).append(inj["html"])

    # 分节（scene 式：衬线序号 + 衬线标题 + 注脚）
    for i, s in enumerate(sections, 1):
        parts.append(f"<section id='{s['id']}' class='scene'>")
        parts.append(f"<div class='head'><span class='num'>{cn_index(i)}</span></div>")
        parts.append(f"<h2>{s['title']}</h2>")
        if s.get("desc"):
            parts.append(f"<p class='note'>{s['desc']}</p>")
        parts.append(load_section(s["source"], base))
        for h in injects.get(s["id"], []):
            parts.append(h)
        parts.append("</section>")

    parts.append(f"<div class='foot'>{d.get('footer','')}</div>")
    parts.append("</div></body></html>")

    out = Path(args.out) if args.out else Path(d.get("out", "恋爱档案.html"))
    if not out.is_absolute():
        out = base / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"已生成 {out} · {out.stat().st_size:,} bytes · {len(sections)} 个 section · theme={theme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
