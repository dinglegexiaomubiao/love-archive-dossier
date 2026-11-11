#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""love-archive-dossier · 编排器。

把「一份微信聊天记录导出」变成「一份恋爱档案（单一自包含 HTML）」。
本 skill 产出一份合并的《恋爱档案》HTML。

子命令：
  init   准备工程：写 config.toml → 跑 collect（指标）→ 跑 detect_conflicts（冲突时段）
                         → 写 dossier.toml + 6 个 section 草稿 HTML（待 AI 填充）
  build  合并：用 merge_dossier.py 把 6 个 section 合成单一 恋爱档案.html

示例：
  python scripts/solo_pipeline.py init \
      -e "聊天记录.json" -m "我" -o "对方" -w "./work_demo" --title "我 × 对方"
  python scripts/solo_pipeline.py build -w "./work_demo"
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent
CONFIG_TPL = SKILL.parent / "config.example.toml"

# 默认 6 段结构（可在 dossier.toml 里增删）
SECTIONS = [
    ("1_双向画像.html", "双向画像", "第一部分 · 双向用户画像（锐评版）",
     "数据速览、双方喜好/性格/优缺点、话题与情绪对比。", "双向用户画像",
     "分别写「我」与「对方」两张卡片：基本信息、沟通风格、喜好、优缺点；用 .stat/.grid 做量化速览，用 .card.blue/.card.pink 区分双方。"),
    ("2_争吵全景.html", "争吵全景", "第二部分 · 关键争吵 · 全景与类型学",
     "冲突时段检测、全景时间线、月度频率、六类类型学、谁先升级。", "关键争吵 · 全景与类型学",
     "放 conflicts.json 的汇总：总段数、强冲突段数、双方先升级占比；可用 .bar-row 画月度频率/升级方占比；六类用 .card 或表格。"),
    ("3_吵架深析.html", "吵架深析", "第三部分 · 关键吵架深度分析",
     "若干场关键吵架的触发-升级-收尾与跨场规律。", "关键吵架深度分析",
     "每场一个 .fight（head 放日期/主题/强度，body 放触发→升级→转折→收尾，谁先升级/重伤词标注）。"),
    ("4_冲突深描.html", "冲突深描", "第四部分 · 关键冲突事件深描",
     "点名场次的互相指责双向还原 + 双方优缺点 + 转捩点。", "关键冲突事件深描",
     "点名场次逐句还原（.quote.u 蓝=我 / .quote.l 红=对方），最后给「我方/对方/共同/非任何人」四分类归因。"),
    ("5_主题_价值感.html", "主题·价值感", "第五部分 · 主题深描 · 价值感/物化/既要又要/道德绑架",
     "对具体观察回原文取证，逐条坐实或证伪。", "主题深描 · 价值感与物化",
     "用户提出的具体观察 → 回库搜原句 → 逐条坐实/证伪；强判断词一律「观察+证据」呈现，不凭空定罪。"),
    ("6_主题_家族.html", "主题·家族", "第六部分 · 主题深描 · 家族与指责辩析",
     "还原具体指责，核查并给铁证表。", "主题深描 · 家族与指责辩析",
     "还原某次指责原文，列证据表逐条裁决（坐实/部分/需打折），回写画像。"),
]


def run(cmd, cwd):
    print(">>", " ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, cwd=str(cwd))
    if r.returncode != 0:
        raise SystemExit(f"命令失败（exit={r.returncode}）: {' '.join(str(c) for c in cmd)}")


def patch_config(work: Path, export: str, me: str, other: str, title: str):
    txt = CONFIG_TPL.read_text(encoding="utf-8")
    txt = txt.replace('path = "C:/Users/你/Documents/WeChat Exports/某人_xxx/聊天记录.json"',
                       f'path = "{export}"')
    txt = re.sub(r'(?m)^title = "恋爱档案"', f'title = "{title}"', txt)
    txt = re.sub(r'(?m)^me = ""', f'me = "{me}"', txt)
    txt = re.sub(r'(?m)^other = ""', f'other = "{other}"', txt)
    (work / "config.toml").write_text(txt, encoding="utf-8")


def write_dossier(work: Path, me: str, other: str, title: str):
    lines = []
    lines.append("# 恋爱档案 · 合并配置（单份 HTML 交付）")
    lines.append("[dossier]")
    lines.append(f'title     = "{title} · 关系全档案"')
    lines.append('subtitle  = "基于微信聊天记录的关系复盘"')
    lines.append('nav_brand = "关系全档案"')
    lines.append('intro     = "一份文件装下双向画像、争吵全景、逐场深析、冲突事件深描与主题深描。所有引号均出自聊天原文（已脱敏），不站队、不定罪，仅供复盘。"')
    lines.append('theme     = "dark"')
    lines.append(f'out       = "恋爱档案-{other}.html"')
    lines.append(f'footer    = "本恋爱档案由 love-archive-dossier skill 生成 · 明文私密内容，请勿外传"')
    lines.append("")
    for fn, nav, t, desc, _, _ in SECTIONS:
        lines.append("[[dossier.section]]")
        lines.append(f'id     = "{fn.split("_")[0]}"')
        lines.append(f'nav    = "{nav}"')
        lines.append(f'title  = "{t}"')
        lines.append(f'desc   = "{desc}"')
        lines.append(f'source = "{fn}"')
        lines.append("")
    # 结论回写：把深描结论压缩补进画像 section
    lines.append("[[dossier.inject]]")
    lines.append('into = "1"')
    lines.append('html = """')
    lines.append('<div class="card" style="border-top:4px solid var(--gold);margin-top:22px">')
    lines.append('  <h3>⚔ 冲突中暴露的特质（据后续深描回写）</h3>')
    lines.append('  <p>把「吵架深析 / 冲突深描 / 主题深描」的结论各压缩两三行，补进双方画像卡片。合并只统一格式、不改数字。</p>')
    lines.append('</div>')
    lines.append('"""')
    (work / "dossier.toml").write_text("\n".join(lines), encoding="utf-8")


def create_stub(work: Path, fn: str, heading: str, guidance: str):
    html = f"""<!-- section 草稿：由 solo_pipeline.py 生成，AI 在此填充分析内容 -->
<!-- 指引：{guidance} -->
<div class="part">
  <h2>{heading}</h2>
  <p class="lead">（此处填写本部分分析。可用 .card / .cols / .quote / .fight / .ev / .bar-row 等组件，详见 references/archive-schema.md）</p>
</div>
"""
    (work / fn).write_text(html, encoding="utf-8")


def cmd_init(args):
    work = Path(args.workdir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    if not Path(args.export).is_file():
        raise SystemExit(f"导出文件不存在：{args.export}")
    print(f"[init] 工作目录：{work}")
    patch_config(work, args.export, args.me, args.other, args.title or f"{args.me} × {args.other}")
    print("[init] 已写 config.toml")
    run([sys.executable, str(SKILL / "collect.py"), "-c", "config.toml"], cwd=work)
    run([sys.executable, str(SKILL / "detect_conflicts.py"), "-c", "config.toml"], cwd=work)
    write_dossier(work, args.me, args.other, args.title or f"{args.me} × {args.other}")
    for fn, nav, t, desc, h, g in SECTIONS:
        create_stub(work, fn, h, g)
    print("\n[init] 完成。下一步：")
    print(f"  1) 打开 {work}/out/metrics.json 看指标，{work}/out/conflicts.json 看冲突时段")
    print(f"  2) 逐个填充 {work}/1_双向画像.html … {work}/6_主题_家族.html （保留 <section> 内的内容即可）")
    print(f"  3) python scripts/solo_pipeline.py build -w {work}")


def cmd_build(args):
    work = Path(args.workdir).resolve()
    if not (work / "dossier.toml").is_file():
        raise SystemExit(f"未找到 {work}/dossier.toml，请先 init")
    run([sys.executable, str(SKILL / "merge_dossier.py"), "-c", "dossier.toml"], cwd=work)
    # 报告产物
    for p in sorted(work.glob("恋爱档案-*.html")):
        print(f"[build] 交付物：{p}  ({p.stat().st_size:,} bytes)")


def main():
    ap = argparse.ArgumentParser(prog="solo_pipeline.py", description="恋爱档案编排器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="准备工程（config+指标+冲突+草稿）")
    pi.add_argument("-e", "--export", required=True, help="微信聊天记录导出 JSON 路径")
    pi.add_argument("-m", "--me", required=True, help="你的名字/代号（与导出 sender 一致）")
    pi.add_argument("-o", "--other", required=True, help="对方名字/代号")
    pi.add_argument("-w", "--workdir", required=True, help="工作目录（产物与中间文件都放这）")
    pi.add_argument("--title", default="", help="档案标题前缀，默认「我 × 对方」")

    pb = sub.add_parser("build", help="合并成单一恋爱档案 HTML")
    pb.add_argument("-w", "--workdir", required=True, help="init 时的工作目录")

    args = ap.parse_args()
    if args.cmd == "init":
        cmd_init(args)
    else:
        cmd_build(args)


if __name__ == "__main__":
    raise SystemExit(main())
