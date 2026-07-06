"""S5 full firepower: cliff + glitch + unicode + mock-QA + self-gen query."""
from ._common import (
    assemble, STRUCTURAL_CLIFF, MOCK_QA_DIALOGUE, _load_glitch_tokens,
    _unicode_payload, self_gen_query,
)
from pi_test import PITest

ID = "S5"
NAME = "stack: full firepower"
DESC = "全栈:断崖+glitch+unicode+mock-QA+自生成,最大火力。"

OVERRIDES = {"temperature": 0.8}


def build(test: PITest, seed: int = 0) -> str:
    glitch = _load_glitch_tokens(n=10, seed=seed)
    injection = (
        f"{STRUCTURAL_CLIFF}\n.{glitch}.\n{_unicode_payload()}\n{MOCK_QA_DIALOGUE}"
    )
    return assemble(test, injection=injection, query=self_gen_query(test))
