"""G2 mock-QA reset (honest version): fake User->Assistant->User dialogue.
Does NOT inject answers — contrast with G8 (hackreset). Composable mid-stream feature."""
from ._common import assemble_midstream, MOCK_QA_DIALOGUE
from ..pi_test import PITest

ID = "G2"
NAME = "mock-qa-reset"
COLOR = "#0969da"
DESC = "结构层(诚实版):流中段伪造 User→Assistant→User 对话标记\"前任务结束\"。不含答案。可组合。"


def feature(test: PITest, seed: int = 0) -> str:
    return MOCK_QA_DIALOGUE


def build(test: PITest, seed: int = 0) -> str:
    return assemble_midstream(test, injection=feature(test, seed))
