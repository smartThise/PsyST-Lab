"""G1 semantic-forget: NL cue to ignore priors. Composable mid-stream feature."""
from ._common import assemble_midstream, SEMANTIC_FORGET
from ..pi_test import PITest

ID = "G1"
NAME = "semantic-forget"
COLOR = "#636c76"
DESC = "语义层:流中段注入\"忽略旧值、只报最新\"的 NL 指令。可组合 feature。"


def feature(test: PITest, seed: int = 0) -> str:
    return SEMANTIC_FORGET


def build(test: PITest, seed: int = 0) -> str:
    return assemble_midstream(test, injection=feature(test, seed))
