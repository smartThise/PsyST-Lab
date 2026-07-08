"""G0 baseline: paper-faithful prompt, no intervention. The RE=0 reference.

Also the canonical "empty feature" — feature() returns "" so composing [G0] into
a task is a no-op (equivalent to a baseline run)."""
from ._common import assemble
from ..pi_test import PITest

ID = "G0"
NAME = "baseline"
COLOR = "#8c959f"
DESC = "论文逐字节基线:instruction + 流 + query,无任何干预。所有 release 效果的参照点(RE=0)。"


def feature(test: PITest, seed: int = 0) -> str:
    return ""


def build(test: PITest, seed: int = 0) -> str:
    return assemble(test)
