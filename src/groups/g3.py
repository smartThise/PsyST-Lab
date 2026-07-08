"""G3 syntactic cliff: structural close symbols. Composable mid-stream feature."""
from ._common import assemble_midstream, STRUCTURAL_CLIFF, SYMBOL_WALL
from pi_test import PITest

ID = "G3"
NAME = "syntactic-cliff"
COLOR = "#8250df"
DESC = "句法断崖:流中段注入 }}}---=== 等结构闭合符号,破坏句法连续性。可组合。"


def feature(test: PITest, seed: int = 0) -> str:
    return f"{STRUCTURAL_CLIFF}\n{SYMBOL_WALL}"


def build(test: PITest, seed: int = 0) -> str:
    return assemble_midstream(test, injection=feature(test, seed))
