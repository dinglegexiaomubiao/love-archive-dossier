---
name: love-archive-dossier
description: 微信聊天记录 → 一份「恋爱档案」单一 HTML。输入一段关系的聊天导出，自动产出唯一交付物：关系全档案（双向画像 + 争吵全景 + 逐场深析 + 冲突深描 + 主题深描），暖色书本风（参照《对话精选》调性：米白纸感 + 宋体衬线 + 窄阅读栏），单一自包含网页、断网可看、可打印。
---

# love-archive-dossier · 恋爱档案

> **本 skill 做一件事，产出一个文件：一份《恋爱档案》HTML。**
> 输入：一个人（你 × 对方）的微信聊天记录导出（JSON）。
> 输出：`恋爱档案-（对方）.html` —— 单一自包含网页，零外部资源、断网可看、可打印。
> UI 风格：暖色纸感（米白 `#FDF9F3` + 暖陶红 `#B5533C` + 暖金 `#C8862A`），宋体衬线大标题、窄阅读栏书本式、暖色编号目录，参照《对话精选》观感。

恋爱档案采用「单文件合订」设计：把双向画像、争吵全景、逐场深析、冲突深描、主题深描装进同一份 HTML，便于断网查看、打印、单文件归档与分享。

---

## 何时用

- 用户说「分析我和 XXX 的聊天记录」「给我做一份恋爱档案」「复盘一下我和 XX 的关系」。
- 数据：微信 4.x 本机解密导出（`wechat-chat-export`），或任何含 `messages` 数组的 JSON。

---

## 工作流（6 步）

```
① 取数      wechat-chat-export 严格导出 → 聊天记录.json（坏页加 --tolerant）
② 准备      python scripts/solo_pipeline.py init -e <导出.json> -m <我> -o <对方> -w <工作目录>
              → 自动写 config.toml、跑 collect(指标)、跑 detect_conflicts(冲突)、生成 6 段草稿 HTML
③ 精读      用 out/metrics.json + out/conflicts.json + 三筛子，定位 6–10 个事件（每个有日期+原话）
④ 填 6 段   按 references/archive-schema.md 填充 1_双向画像.html … 6_主题_家族.html
⑤ 合并      python scripts/solo_pipeline.py build -w <工作目录>
              → 恋爱档案-（对方）.html（唯一交付物）
⑥ 交付      present 该 HTML；提示「明文私密内容，请勿外传」
```

> `solo_pipeline.py init` 一步完成 ①② 并生成草稿；`build` 完成 ⑤。③ ④ 由你（AI）完成。

---

## 六个 section（合并进同一份 HTML）

| id | 文件 | 内容 |
|---|---|---|
| 1 | `1_双向画像.html` | 双向用户画像（锐评版）：数据速览、双方优缺点、对比图 |
| 2 | `2_争吵全景.html` | 关键争吵·全景与类型学：冲突时段、月度频率、谁先升级、六类类型学 |
| 3 | `3_吵架深析.html` | 关键吵架深度分析：5–8 场触发→升级→转折→收尾 |
| 4 | `4_冲突深描.html` | 关键冲突事件深描：双向逐句还原 + 归因四分类 |
| 5 | `5_主题_价值感.html` | 主题深描·价值感/物化/既要又要/道德绑架（回原文取证） |
| 6 | `6_主题_家族.html` | 主题深描·家族与指责辩析（证据表逐条裁决） |

结构默认 6 段，可在 `dossier.toml` 用 `[[dossier.section]]` 增删。

---

## 数据与脚本

- `scripts/collect.py` —— 统一口径全量指标 → `out/metrics.json`（cross-relation 可比）。
- `scripts/detect_conflicts.py` —— 冲突时段检测（分层打分 + 时间聚类）→ `out/conflicts.json`。
- `scripts/merge_dossier.py` —— 多 HTML → 单一自包含网页（warm 默认 = 暖色书本风，参照《对话精选》）。
- `scripts/solo_pipeline.py` —— `init`（准备工程）/ `build`（合并交付）编排器。
- `dossier.example.toml` / `config.example.toml` —— 配置模板。

## 参考

- `references/archive-schema.md` —— 六段必含内容 + 版式组件表（`.card`/`.quote`/`.fight`/`.ev`/`.bar-row` 等）。**填 section 前必读**。
- `references/deep-analysis.md` —— 深度分析方法（口径/三筛子/镜像锐评/主题深描/踩坑）。**精读与写作前必读**。
- `references/reading-method.md` —— 三筛子精读法。
- `references/pitfalls.md` —— 写作纪律与常见错误（平视/证据挂回/双向裁决/归因四分类/诚实三件事）。
- `references/writing-voice.md` —— 文案去 AI 味：**写六段前必读**，避免升华式总结、破折号堆砌、规则三、替读者下结论等 AI 腔。

---

## 写作纪律（硬性）

- **平视**：写「他做了 X，她做了 Y，X 和 Y 撞在一起产生 Z」，不写「他很自私」。
- **证据挂回**：每个判断后面能填出时间戳或统计值；动机标「推断」。
- **双向裁决**：任一方指控都要能反向裁决，避免单方定罪。
- **诚实三件事**：数据缺失、推断而非事实、即使改了也未必挽回。
- **归因四分类**：我的责任 / 对方的责任 / 共同的责任 / **不是任何人的责任**（末行空着不合格）。
- **不站队、不定罪、不替读者下「爱与不爱」定论**。
- **私密**：所有引号出自聊天原文（已脱敏）；交付时提示明文风险，不要主动建议分享。

---

## 验收（完成定义）

- [ ] `init` 成功：`out/metrics.json` + `out/conflicts.json` 存在，6 个 section 草稿已生成。
- [ ] 6 段全部填充，无 `（此处填写…）` 占位。
- [ ] `build` 成功：生成 `恋爱档案-（对方）.html`，单一文件、零外部资源（无 `http(s)://`/`<script src`/`<link>`）。
- [ ] 目录 6 个锚点可跳转；含「归因四分类」且末类非空。
- [ ] 数据中「完整性」如实写明（尤其用了 `--tolerant` 坏页导出时）。

---

## 常见错误

| 错误 | 后果 | 正确做法 |
|---|---|---|
| 违反单文件约定，另拆出多个 HTML | 破坏「一份档案」设计 | 全部内容装进这一个 HTML 的 6 段里 |
| 用其他渲染器/模板替代 merge_dossier | 丢掉合并版的完整结构与主题样式 | 恋爱档案 = merge_dossier 合成的关系全档案（暖色书本风，默认） |
| 只给定性不给证据 | 等于没复盘 | 每个判断挂时间戳/统计值 |
| 单方定罪 | 失真、不客观 | 互为原被告，双向裁决 |
| 合并时拼接各 section 自带 CSS | 字号/栏宽跳变 | merge_dossier 统一外壳，只抽 `<body>` |
| 归因只写前三类、末行空着 | 不合格 | 必填「不是任何人的责任」 |
