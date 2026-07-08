"""G9 fake-hackreset (control for G8): same fake prior Q&A as G8, but the
assistant turn injects WRONG values (the FIRST / oldest values, not the
current ones).

If the model echoes the injected wrong values (output matches first_values,
not targets), it proves G8's lift was pure echo of the prefill — not genuine
retrieval. If accuracy stays at baseline, the model ignores wrong prefill and
keeps trying to retrieve (a different finding).
"""
from ._common import assemble, hackreset_injection
from ..pi_test import PITest

ID = "G9"
NAME = "hackreset-wrong"
COLOR = "#bf4dd6"
POSITION = "end"
DESC = "★G8 对照:同样伪造对话但塞错误答案(旧值),末尾注入。验证模型是否无脑照抄。"


def feature(test: PITest, seed: int = 0) -> str:
    return hackreset_injection(test, test.first_values)


def build(test: PITest, seed: int = 0) -> str:
    return assemble(test, injection=feature(test, seed))
