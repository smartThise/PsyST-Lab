"""基类定义 — 所有实验模块的接口契约.

要添加新实验范式, 只需:
  1. 在 modules/ 下新建子包
  2. 写一个继承 BaseModule 的类
  3. 实现 build_conditions / build_task / score 三个方法
  4. 模块会被自动发现和注册
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Condition:
    """一个实验条件 — 等价于 "一组要测试的参数组合".

    对 PI release 来说, 一个 Condition = 一个干预组 (G0, G1, ...).
    对 recall_rating 来说, 一个 Condition = 一个类别对 × 一个模式.
    """
    id: str                             # 唯一标识
    name: str                           # 人类可读名称
    params: dict[str, Any] = field(default_factory=dict)  # 额外参数


@dataclass
class Task:
    """一次 API 调用所需的所有信息.

    messages:  要发送到 LLM 的消息列表 (符合 OpenAI Chat API 格式)
    metadata:  评分所需的元数据 (期望答案、刺激值、条件参数等)
    overrides: 本次调用的临时参数覆盖 (temperature, max_tokens 等)
    """
    messages: list[dict[str, str]]
    metadata: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """一次 API 调用后的评分结果.

    condition_id: 属于哪个实验条件
    scores:       结构化指标 (accuracy, RPI, sequential_bias 等)
    raw:          原始响应数据 (用于追溯和二次分析)
    """
    condition_id: str
    scores: dict[str, float | None]
    raw: dict[str, Any] = field(default_factory=dict)


class BaseModule(ABC):
    """实验模块基类.

    子类可以声明:
      - module_id:  str  — 唯一标识, 用于 URL、目录名
      - module_name: str — 显示名称

    必须实现:
      - build_conditions() -> list[Condition]
      - build_task(condition, seed) -> Task
      - score(task, response) -> Result

    可选覆盖:
      - setup(config) — 读取模块专属配置
      - pre_run / post_run — 生命周期钩子
    """

    module_id: str = ""
    module_name: str = ""

    def setup(self, config: dict[str, Any]) -> None:
        """模块初始化 — 读取配置、加载数据等. runner 会在 run() 开始时调用."""
        self.config = config

    @abstractmethod
    def build_conditions(self) -> list[Condition]:
        """返回该模块下所有需要测试的实验条件."""
        ...

    @abstractmethod
    def build_task(self, condition: Condition, seed: int) -> Task:
        """为指定条件生成一次 API 调用的完整任务."""
        ...

    @abstractmethod
    def score(self, task: Task, response: str) -> Result:
        """对 LLM 的响应进行评分, 返回结构化结果."""
        ...

    # ---- UI 规格 (模块自描述, dashboard 无知组装) ----
    def get_spec(self) -> dict:
        """返回模块完整 UI 规格: kpis + charts + columns + launch.

        模块通过 register_kpi/register_chart/register_column/register_launch
        在 __init__.py 中声明. 此方法聚合返回, dashboard 唯一调用入口.
        """
        from .charts import get_module_spec
        return get_module_spec(self.module_id)

    def get_launch_config(self) -> dict:
        """返回启动面板配置. 模块覆盖或在 __init__.py 中调用 register_launch()."""
        return self.get_spec().get("launch") or {"composer": "checklist", "extra_params": [], "features": []}

    def pre_run(self, conditions: list[Condition]) -> None:
        """运行前钩子 — 可选, 用于预热、数据准备等."""
        pass

    def post_run(self, results: list[Result]) -> None:
        """运行后钩子 — 可选, 用于汇总、写报告等."""
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.module_id})>"
