"""G6 self-generation cue: disruption-token instruction. Composable mid-stream feature."""
from ._common import assemble_midstream, SELF_GEN_CUE
from ..pi_test import PITest

ID = "G6"
NAME = "self-generation"
COLOR = "#1a7f37"
DESC = "自生成:流中段注入\"先吐扰乱 token 再答\"指令。可组合。"


def feature(test: PITest, seed: int = 0) -> str:
    return SELF_GEN_CUE


def build(test: PITest, seed: int = 0) -> str:
    return assemble_midstream(test, injection=feature(test, seed))
