"""G3 syntactic cliff: structural close symbols injected before query."""
from ._common import assemble, STRUCTURAL_CLIFF, SYMBOL_WALL
from pi_test import PITest

ID = "G3"
NAME = "syntactic-cliff"
DESC = "句法断崖:注入 }}}}---=== 等结构闭合符号,试图破坏句法连续性。"


def build(test: PITest, seed: int = 0) -> str:
    return assemble(test, injection=f"{STRUCTURAL_CLIFF}\n{SYMBOL_WALL}")
