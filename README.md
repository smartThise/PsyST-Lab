# PsyST Lab

> 轻量化模块化 LLM 认知实验平台。加新实验范式 = 在 `modules/` 下建一个文件夹 + 写一个 `BaseModule` 子类 = 自动出现在仪表板。

独立 git 仓库 → [github.com/smartThise/pi-release-exp](https://github.com/smartThise/pi-release-exp) (私有)。

---

## 已搭载模块

| 模块 | 说明 | 条件数 |
|---|---|---|
| `pi_release` | PI 前涉干扰释放实验 (基于 [arXiv:2506.08184](https://arxiv.org/abs/2506.08184)) | 11 个干预组 |
| `recall_rating` | Recall vs Rating 序列偏差对比 (基于 Mewhort et al. 2018) | 12 词对 × 3 模式 = 36 条件 |

---

## 架构

```
psy-st-lab/
├── core/                         # 共享基础设施 (~190 行)
│   ├── base.py                   # BaseModule ABC + Condition/Task/Result
│   ├── registry.py               # 模块自动发现 (扫描 modules/*/)
│   ├── runner.py                 # 通用 ExperimentRunner
│   ├── api.py                    # OpenAI 兼容 client
│   ├── utils.py                  # JSON/配置
│   └── charts.py                 # UI 规格系统 (KPISpec/ChartSpec/ColumnSpec/LaunchConfig)
│
├── modules/                      # 实验模块 (插件式)
│   ├── pi_release/               # PI release 模块
│   │   ├── groups/               # 干预组 G0-G9 + G8s
│   │   ├── pi_test.py            # PI 压力测试流生成
│   │   ├── metrics.py            # 论文评分 + RE/CP/Robustness
│   │   └── data/                 # glitch tokens + 词表
│   └── recall_rating/            # Recall-Rating 模块
│       ├── tasks.py / words.py   # 实验生成 + 词表
│       ├── prompts.py / metrics.py
│       └── data/                 # Mewhort/Wickens 12 对类别词表
│
├── dashboard/                    # Web 控制面板 (模块驱动, 零硬编码)
│   ├── server.py / index.html
│   ├── app.js                    # 多关键字排序 / 导出 CSV / 动态图表
│   └── style.css
│
├── config/                       # API 配置 + 实验参数
├── launch.py                     # 统一 CLI 入口
└── runs/<module>/<tag>/          # 运行时输出
```

---

## 快速开始

```bash
# 安装
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 配置 API
cp config/config.example.yaml config/config.yaml
# 编辑 config.yaml: base_url, api_key, model, extra_body

# 列出所有模块
python launch.py --list

# 运行实验
python launch.py -m pi_release                    # PI release, 全部 11 组
python launch.py -m pi_release -c G0 G2 G8s       # 只跑指定组
python launch.py -m recall_rating -c WN_exp TC_exp # 只跑指定词对

# 启动仪表板
python launch.py --dashboard
# → http://127.0.0.1:8765
```

---

## 仪表板功能

- **模块切换** — 顶部下拉, 自动切换图表/KPI/表格/启动面板
- **多关键字排序** — 点列表头设主关键字 ▲/▼, Shift+点添加次级关键字; 排序栏芯片可见
- **CSV 导出** — 按当前排序导出详情表; 对比表也可导出
- **对比面板** — 多 run 彩色矩阵对比, 支持 RE/Accuracy 切换
- **拖拽任务编排器** (pi_release) — 从 feature 调色板拖 chip 到任务框, 支持多任务并行和跨任务重排
- **勾选条件面板** (recall_rating) — 勾选要测试的词对
- **设置页** — API profile 增删改

---

## 加新模块

在 `modules/` 下新建文件夹, 写一个继承 `BaseModule` 的类, 实现 3 个方法 + 可选 UI 自描述:

```python
# modules/my_exp/__init__.py
from core.base import BaseModule, Condition, Task, Result
from core.charts import register_kpi, register_chart, register_column, register_launch, KPISpec, ChartSpec, ColumnSpec, LaunchConfig

# UI 自描述 — 仪表板自动渲染
register_launch("my_exp", LaunchConfig(composer="checklist", description="选择条件运行实验。"))
register_kpi("my_exp", KPISpec("kpi1", "准确率", "accuracy", aggregate="mean", fmt="pct"))
register_chart("my_exp", ChartSpec("chart1", "准确率按条件", "bar", data_key="accuracy"))
register_column("my_exp", ColumnSpec("accuracy", "准确率", fmt="pct"))

class MyExp(BaseModule):
    module_id = "my_exp"
    module_name = "我的实验"

    def build_conditions(self) -> list[Condition]:
        return [Condition(id="c1", name="条件1"), Condition(id="c2", name="条件2")]

    def build_task(self, condition: Condition, seed: int) -> Task:
        prompt = f"请评估: {condition.name}"
        return Task(messages=[{"role": "user", "content": prompt}],
                    metadata={"condition_id": condition.id})

    def score(self, task: Task, response: str) -> Result:
        return Result(condition_id=task.metadata["condition_id"],
                      scores={"accuracy": len(response) / 100})
```

不用碰 `core/`、`dashboard/`、`launch.py` 或任何其他文件。

---

## PI Release 关键结果 (deepseek-chat)

**46×400** (高干扰, baseline 0.391):

| 干预 | acc | 说明 |
|---|---|---|
| **G2+G4+G3+G8s** | **0.666 (+0.275)** | 最佳, 接近论文 Gemini Flash 量级 |
| G2+G8s | 0.620 (+0.228) | mock-QA + hackreset 协同 |
| G8s 单 | 0.512 (+0.121) | hackreset 忠实复刻 |

核心发现: G8s 复刻论文方向 + 高负载放大; G2+G8s 是王者组合; "破坏性 cue" (G3/G4) 低负载有害、高负载在堆叠中反成促进剂。

---

## 配置

`config/experiment.yaml`:
```yaml
pi_test:
  n_keys: 46
  updates_per_key: 4
  n_trials: 10
  seed: 42
eval:
  k_repeats: 3
  measure_cp: true
  measure_robustness: true
```
