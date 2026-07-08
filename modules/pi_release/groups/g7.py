"""G7 query-engineering cue: recency-anchored instruction. Composable mid-stream feature."""
from ._common import assemble_midstream, ENGINEERED_CUE
from ..pi_test import PITest

ID = "G7"
NAME = "query-engineering"
COLOR = "#1f6feb"
DESC = "Query 工程:流中段注入 recency 锚定指令。可组合。"


def feature(test: PITest, seed: int = 0) -> str:
    return ENGINEERED_CUE


def build(test: PITest, seed: int = 0) -> str:
    return assemble_midstream(test, injection=feature(test, seed))
