"""G2 mock-QA reset (honest version): fake User->Assistant->User dialogue.
Does NOT inject answers — contrast with G8 (hackreset)."""
from ._common import assemble, MOCK_QA_DIALOGUE
from pi_test import PITest

ID = "G2"
NAME = "mock-qa-reset"
DESC = "结构层(诚实版):伪造 User→Assistant→User 对话回合信号\"前任务结束\"。不含答案。"


def build(test: PITest, seed: int = 0) -> str:
    return assemble(test, injection=MOCK_QA_DIALOGUE)
