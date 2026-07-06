"""G1 semantic-forget: natural-language injection to ignore priors."""
from ._common import assemble, SEMANTIC_FORGET
from pi_test import PITest

ID = "G1"
NAME = "semantic-forget"
DESC = "语义层:query 前注入\"忽略旧值、只报最新\"的自然语言指令。论文已证明基本无效。"


def build(test: PITest, seed: int = 0) -> str:
    return assemble(test, injection=SEMANTIC_FORGET)
