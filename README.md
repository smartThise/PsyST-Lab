# pi-release-exp

> Prompt 端 PI(前涉干扰)释放实验框架。测试单条消息内的干预能否解除 LLM 的
> **proactive interference**,并度量效果。
>
> 基于 [arXiv:2506.08184](https://arxiv.org/abs/2506.08184)
> (*Unable to Forget*)。设计文档: `../working_memory/think1.md`。
>
> 论文代码本地克隆在 `../Unable-to-Forget-paper/`，供逐行比对。

独立 git 仓库 → [github.com/smartThise/pi-release-exp](https://github.com/smartThise/pi-release-exp)(私有)。

---

## 原理

每次 run 向模型发送一段高干扰的 key-value 更新流(同一 key 被反复覆盖),然后问"每个 key 的最新值是什么?",测量 prompt 级**干预**(注入的 cue)能否帮模型取对答案。

**评分标准 = 论文逐行移植**(已核对 `compute_accuracy` + `extract_pieces_response_to_dict`):精确字符串匹配(strip+lower),分母 = 全部 46 key,漏答 = 错。**acc 与论文直接可比。**

三个指标:
- **RE**(Release Efficiency):比 baseline 高多少。干预的释放量。
- **CP**(Context Preservation):干预后模型是否还保留无关早期信息(区分 release vs 全面崩溃)。
- **Robustness Δ**:删除 1 个字符后的 RE 变化(分辨深层机制 vs 脆弱的 token exploit)。

---

## 架构(2026-07 重构)

### Feature + Task 模型

不再有固定的"组列表"。干预被模块化为 **feature** 原语,启动时按**有序组合**构成 **task**。

**Feature 原语**(`src/groups/g0.py`~`g9.py`,`g8s.py`):

| feature | 说明 | 位置 |
|---|---|---|
| G0 | 基线,无干预(空 feature = 基线 task) | — |
| G1 | 语义遗忘:NL 指令"忽略旧值" | 流中段 |
| G2 | mock-QA reset:伪造 User→Assistant→User 对话"前任务结束" | 流中段 |
| G3 | 句法断崖:`};}}}---===` 结构闭合符号 | 流中段 |
| G4 | glitch token:高范数罕见 token | 流中段 |
| G5 | unicode/控制字节:RTL/零宽/null/组合字符 | 流中段 |
| G6 | 自生成 cue:先吐扰乱 token 再答 | 流中段 |
| G7 | recency 锚定指令 | 流中段 |
| **G8s** | **论文 hackreset 忠实复刻**(中段 + 注入点过期快照 + 三段"新任务"边界) | 流中段 |
| G8 | 答案注入对照(末尾 + 最终正确值 → 作弊) | 末尾 |
| G9 | G8 对照(末尾 + 错误旧值) | 末尾 |

**Task = 有序 feature 列表**: `[]` = 基线 G0; `[G2]` = 旧 G2; `[G3,G4,G2]` = 旧 S3。midstream 类按序拼一块注入 `len-tail`(tail≈2.6×n_keys,46→120,论文同款位置),end 类(G8/G9)拼一块注入 query 前。**顺序敏感**(G1+G2 ≠ G2+G1)。

**S3/S5 已删除**(用 task 表达);**experiment.yaml 的 `groups:` 块已删除**(包自动发现 = 唯一真相源)。

### 注入位置:论文中段(已修复严重 bug)

**⚠️ 旧版 `assemble` 把干预注在整条流的末尾(0 trailing updates)——不是论文做法。** 论文图 11:所有干预插在"第 120 个 update 前"(流中段,后面留 120 个 update 形成任务边界)。已改为 `assemble_midstream`,旧版末尾注入的所有结果作废。

### 启动面板:拖拽任务编辑器

`localhost:8765` →「启动」tab:左侧 feature 调色板(G1–G8s,每行 = 可拖彩色 chip + 说明文字),拖 chip 到任务框组成有序 task,支持多任务并行、任务内/跨任务拖拽重排(光标落 chip 左半插前、右半插后)、× 移除。启动发送 `tasks: [{features:[...], name?}]`。首页有强制停止按钮(杀进程 + 删未完成 run 目录)。

---

## 关键结果(deepseek-chat,46 key,10 trials,k_repeats=3)

**评分与论文对齐,acc 直接可比。**

### 46×100(baseline 0.653,中等干扰)

| 干预 | acc | 说明 |
|---|---|---|
| G8s(单) | 0.684(+0.03) | hackreset 小幅正 |
| **G2+G8s** | **0.791(+0.138)** | mock-QA + hackreset 协同,最佳 |
| G1+G8s | 0.751 | |
| G2+G4+G3+G8s | 0.765 | |
| G1–G7(单,不含 G8s) | ≤0.65 | 全部 ≤ baseline,多数有害;G6 最差 0.384 |
| G8(答案注入) | 1.000 | 作弊(SOTA 验证),非 release |
| G9(错误注入) | 0.258 | 对照组,模型照抄错误值 |

### 46×400(baseline 0.391,高干扰,论文预测 ~0% 但 deepseek-chat 更结实)

| 干预 | acc | 说明 |
|---|---|---|
| G8s(单) | 0.512(**+0.121**) | hackreset 大幅放大于 46×100,复现论文"高 PI 区 release 更强" |
| **G2+G8s** | **0.620(+0.228)** | |
| **G2+G4+G3+G8s** | **0.666(+0.275)** | **最佳,接近论文 Gemini Flash 量级** |
| G7+G2+G8s | 0.627(+0.236) | |
| G2+G4+G8s | 0.628(+0.237) | |

### 核心发现

1. **G8s 忠实复刻了论文 hackreset 的方向和负载依赖**:低干扰 +0.03,高干扰 +0.12~0.28,论文 Gemini Flash 大 lift 在我们的模型上可复现(幅度因模型更强而缩小)。
2. **G2+G8s 是王者组合**:mock-QA 伪造的"前任务结束"信号和 hackreset 的伪造答案回合形成强边界。
3. **"破坏性 cue 反转"**:G3(断崖)/G4(glitch)在 46×100 有害(低于 baseline),到 46×400 在 G8s 堆叠里反成促进剂。低负载扰动 = 干扰,高负载扰动 = 助力。
4. **G8 的 100% 是答案注入假象**:G8 把最终正确答案(非快照)放在末尾,模型纯抄。G8s(中段 + 过期快照)才是真机制。

---

## 快速开始

```bash
# 1. 安装依赖
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置 API
cp config/config.example.yaml config/config.yaml
# 编辑 config.yaml:填入 api_key, model, base_url

# 3. 命令行启动(legacy:跑全部单组)
python scripts/run_all.py                    # 所有 feature
python scripts/run_all.py --groups G0 G2     # 指定组

# 4. 启动仪表板(推荐:拖拽组合 task)
python dashboard/server.py
# → http://127.0.0.1:8765
```

---

## 仓库结构

```
pi-release-exp/
├── config/
│   ├── config.example.yaml      # API 配置模板
│   ├── config.yaml              # 密钥(gitignored)
│   └── experiment.yaml          # PI 参数 + eval 配置(无硬编码组列表)
├── src/
│   ├── api_client.py            # OpenAI 兼容 client + 重试/退避
│   ├── pi_test.py               # PI 压力测试流生成器(pseudo_randomize)
│   ├── metrics.py               # 论文评分移植 + RE/CP/Robustness
│   ├── runner.py                # task 编排器(支持 --tasks-file)
│   ├── utils.py
│   └── groups/                  # feature 模块包(自动发现)
│       ├── __init__.py          # 注册表:REGISTRY/FEATURES/build_task_message
│       ├── _common.py           # 共享脚手架(assemble/assemble_midstream/assemble_hybrid)
│       ├── g0.py ~ g9.py        # feature 原语
│       └── g8s.py               # 论文 hackreset 忠实复刻
├── scripts/
│   └── run_all.py               # CLI 入口
├── dashboard/
│   ├── server.py                # 零依赖 stdlib HTTP 服务(含 /api/launch tasks)
│   ├── index.html               # 仪表板 UI
│   ├── style.css
│   └── app.js                   # 拖拽任务编辑器 + 结果展示
├── data/
│   ├── glitch_tokens.txt
│   └── word_categories.json     # 46 类词汇(论文同款)
├── runs/                        # 输出(gitignored)
└── README.md
```

---

## 添加新 feature

在 `src/groups/` 下新建 `.py` 文件,声明以下属性即可(包自动发现,无须改任何注册表):

```python
# src/groups/my_feature.py
from pi_test import PITest

ID = "X1"
NAME = "my-feature"
COLOR = "#ff6600"
POSITION = "midstream"   # "midstream"(默认) 或 "end"
DESC = "我的新干预描述。"

def feature(test: PITest, seed: int = 0) -> str:
    return "要注入的文本"

def build(test: PITest, seed: int = 0) -> str:
    from groups._common import assemble_midstream
    return assemble_midstream(test, injection=feature(test, seed))
```

启动仪表板后自动出现在 feature 调色板中,可直接拖入任务。

---

## 配置实验参数

编辑 `config/experiment.yaml`:

```yaml
pi_test:
  n_keys: 46
  updates_per_key: 100
  n_trials: 10
  seed: 42

eval:
  k_repeats: 3
  measure_cp: true
  measure_robustness: true
```

无需配置组列表——组从包自动发现,task 在启动面板实时组合。

---

## 输出

每次 run 落在 `runs/<tag>/`(`<tag>`=`<时间戳>_<model>`):

- `run_config.json` — 完整快照(密钥已剥离),含 tasks 定义
- `results.jsonl` — 每行一条 `(task, trial)`,字段 `group`=task_id, `features`, `accuracy`, `cp`, `robustness_delta`
- `summary.json` — 按 task 聚合,仪表板数据源

---

## 与机制阶段(think2)的关系

prompt 端产出两类结果供后续白盒阶段:

1. **顶效干预组合**(如 G2+G8s)——在开源模型上重放并记录 attention,定位激活的 heads/layers。
2. **差分候选**(高 PI 下有效、低 PI 下无效的干预 = "PI 指纹")。

桥梁:prompt 端顶效变体激活的 heads,应与机制端 patching 独立识别的 release 回路一致。

---

## 许可与引用

实验代码:MIT。PI-LLM 范式源自 Wang & Sun, *Unable to Forget*, arXiv:2506.08184——基于该工作请引用原文。
