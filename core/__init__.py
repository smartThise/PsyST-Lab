"""PsyST Lab — 轻量化 LLM 认知实验平台.

core/     共享基础设施: 基类、运行器、模块注册、API client、图表系统
modules/  实验范式模块 (每个子包 = 一个独立范式, 继承 BaseModule)
runs/     运行时输出 (按 runs/<module_id>/<tag>/ 组织)
dashboard/ 共享 Web 控制面板 (动态渲染模块图表)
"""

from .base import BaseModule, Condition, Task, Result
from .registry import discover_modules, get_module
from .runner import ExperimentRunner
from . import charts
