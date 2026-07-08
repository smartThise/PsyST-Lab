"""G8 hackreset (answer-injection control): fake assistant turn with CORRECT
values, END-positioned. POSITION='end' so composing it into a task places it
before the query (not mid-stream). Not a fair release technique — ablation only."""
from ._common import assemble, hackreset_injection
from pi_test import PITest

ID = "G8"
NAME = "hackreset"
COLOR = "#1f7a8c"
POSITION = "end"
DESC = "★答案注入对照:把正确答案伪造成 assistant 回合,末尾注入。ablation,非真 release。"


def feature(test: PITest, seed: int = 0) -> str:
    return hackreset_injection(test)


def build(test: PITest, seed: int = 0) -> str:
    return assemble(test, injection=feature(test, seed))
