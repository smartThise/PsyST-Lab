"""可复用组件规格系统.

模块通过 register_* 声明自己的 UI 需求.
Dashboard 是无知的组装器 — 从 API 拉 spec → 调用对应 builder → 渲染.

用法 (全部在模块 __init__.py 中, 不碰 dashboard/):
    register_chart("my_mod", ChartSpec(...))
    register_kpi("my_mod", KPISpec(...))
    register_column("my_mod", ColumnSpec(...))
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 规格
# ---------------------------------------------------------------------------
@dataclass
class KPISpec:
    """一个 KPI 卡片的声明."""
    kpi_id: str
    label: str
    data_key: str = ""
    aggregate: str = "first"    # "first" | "max" | "mean" | "sum"
    fmt: str = "pct"            # "pct" | ".3f" | "d" | "str"
    accent: bool = False        # 是否高亮
    exclude_g0: bool = False    # 聚合时排除 G0


@dataclass
class ChartSpec:
    """一个图表的声明."""
    chart_id: str
    title: str
    chart_type: str = "bar"     # "bar" | "scatter" | "line-series" | "heatmap" | "kpi" | "table"
    data_key: str = ""          # scores 中的指标 key
    series_key: str = ""        # line-series: 按 condition_id 的这个字段分组画不同线
    x_key: str = ""             # line-series/heatmap: X 轴字段
    y_key: str = ""             # heatmap: Y 轴字段
    split_key: str = ""         # line-series-grid: 按此字段拆成多张子图
    x_label: str = ""
    y_label: str = ""
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ColumnSpec:
    """结果表格的一列."""
    key: str
    label: str
    fmt: str = ".3f"


@dataclass
class LaunchConfig:
    """启动面板配置."""
    composer: str = "checklist"     # "drag" | "checklist"
    description: str = ""           # 启动面板提示文字
    extra_params: list[dict] = field(default_factory=list)
    features: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------
_KPIS: dict[str, list[KPISpec]] = {}
_CHARTS: dict[str, list[ChartSpec]] = {}
_COLUMNS: dict[str, list[ColumnSpec]] = {}
_LAUNCH: dict[str, LaunchConfig] = {}


def register_kpi(mid: str, kpi: KPISpec) -> KPISpec:
    _KPIS.setdefault(mid, []).append(kpi); return kpi

def register_chart(mid: str, c: ChartSpec) -> ChartSpec:
    _CHARTS.setdefault(mid, []).append(c); return c

def register_column(mid: str, c: ColumnSpec) -> ColumnSpec:
    _COLUMNS.setdefault(mid, []).append(c); return c

def register_launch(mid: str, lc: LaunchConfig) -> LaunchConfig:
    _LAUNCH[mid] = lc; return lc


def get_module_spec(mid: str) -> dict:
    """返回模块的完整 UI 规格 — dashboard 唯一需要调用的方法."""
    kpis = [{"kpi_id": k.kpi_id, "label": k.label, "data_key": k.data_key,
             "aggregate": k.aggregate, "fmt": k.fmt, "accent": k.accent,
             "exclude_g0": k.exclude_g0} for k in _KPIS.get(mid, [])]
    charts = [{"chart_id": c.chart_id, "title": c.title, "chart_type": c.chart_type,
               "data_key": c.data_key, "series_key": c.series_key,
               "x_key": c.x_key, "y_key": c.y_key, "split_key": c.split_key,
               "x_label": c.x_label, "y_label": c.y_label,
               "options": c.options} for c in _CHARTS.get(mid, [])]
    columns = [{"key": c.key, "label": c.label, "fmt": c.fmt}
               for c in _COLUMNS.get(mid, [])]
    launch = None
    if mid in _LAUNCH:
        lc = _LAUNCH[mid]
        launch = {"composer": lc.composer, "description": lc.description,
                  "extra_params": lc.extra_params, "features": lc.features}
    return {"kpis": kpis, "charts": charts, "columns": columns, "launch": launch}


# 向后兼容
get_charts = lambda mid: get_module_spec(mid)["charts"]
get_columns = lambda mid: get_module_spec(mid)["columns"]
