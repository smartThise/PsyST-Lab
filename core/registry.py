"""模块自动发现与注册.

扫描 modules/ 下的所有子包, 找到 BaseModule 的子类并实例化.
新增模块 = 在 modules/ 下新建目录 + 写一个继承 BaseModule 的类 = 自动出现.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

from .base import BaseModule

MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"

_registry: dict[str, BaseModule] | None = None


def _ensure_path() -> None:
    """确保项目根在 sys.path 中 (支持从任意位置运行)."""
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)


def discover_modules() -> dict[str, BaseModule]:
    """扫描 modules/*/ 下所有子包, 找到 BaseModule 子类并实例化.

    约定: 每个模块子包 (如 modules/pi_release/) 的 __init__.py 或
          其中的某个模块定义了继承 BaseModule 的类.
          模块类的 module_id 必须与目录名一致.

    Returns:
        {module_id: module_instance}
    """
    global _registry
    if _registry is not None:
        return _registry

    _ensure_path()
    _registry = {}

    if not MODULES_DIR.exists():
        return _registry

    for entry in sorted(MODULES_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_") or entry.name.startswith("."):
            continue

        pkg_name = f"modules.{entry.name}"
        try:
            pkg = importlib.import_module(pkg_name)
        except Exception as exc:
            print(f"[registry] 跳过 {pkg_name}: 导入失败 ({exc})", file=sys.stderr)
            continue

        # 在包及其子模块中查找 BaseModule 子类
        found = _scan_for_module_class(pkg, entry.name)
        if found:
            instance = found()
            if instance.module_id != entry.name:
                instance.module_id = entry.name
            _registry[instance.module_id] = instance
            print(f"[registry] ✓ {instance.module_id} — {instance.module_name}")
        else:
            print(f"[registry] ⚠ {pkg_name}: 未找到 BaseModule 子类", file=sys.stderr)

    return _registry


def _scan_for_module_class(pkg, expected_id: str) -> type[BaseModule] | None:
    """在包中查找 BaseModule 的子类."""
    from .base import BaseModule as BM

    # 先检查包的 __init__.py 中的直接成员
    candidates = []
    for name in dir(pkg):
        obj = getattr(pkg, name)
        if isinstance(obj, type) and issubclass(obj, BM) and obj is not BM:
            candidates.append(obj)

    # 如果没找到, 尝试扫描包的子模块
    if not candidates:
        try:
            pkg_path = Path(pkg.__file__).resolve().parent if pkg.__file__ else None
        except Exception:
            pkg_path = None

        if pkg_path:
            for m in pkgutil.iter_modules([str(pkg_path)]):
                if m.name.startswith("_"):
                    continue
                try:
                    sub = importlib.import_module(f"{pkg.__name__}.{m.name}")
                    for name in dir(sub):
                        obj = getattr(sub, name)
                        if isinstance(obj, type) and issubclass(obj, BM) and obj is not BM:
                            candidates.append(obj)
                except Exception:
                    pass

    return candidates[0] if candidates else None


def get_module(module_id: str) -> BaseModule:
    """获取已注册模块."""
    registry = discover_modules()
    if module_id not in registry:
        raise KeyError(f"未知模块 {module_id!r}, 可用: {list(registry)}")
    return registry[module_id]


def list_modules() -> list[dict]:
    """列出所有已注册模块的元信息."""
    return [
        {"id": mid, "name": m.module_name}
        for mid, m in discover_modules().items()
    ]
