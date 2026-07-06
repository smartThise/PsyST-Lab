"""S3 stack: mock-QA + structural cliff + glitch tokens."""
from ._common import assemble, STRUCTURAL_CLIFF, SYMBOL_WALL, MOCK_QA_DIALOGUE, _load_glitch_tokens
from pi_test import PITest

ID = "S3"
NAME = "stack: mock+cliff+glitch"
DESC = "堆叠:G2 mock-QA + G3 断崖 + G4 glitch 三层叠加。"


def build(test: PITest, seed: int = 0) -> str:
    glitch = _load_glitch_tokens(n=8, seed=seed)
    injection = f"{STRUCTURAL_CLIFF}\n.{glitch}.\n{MOCK_QA_DIALOGUE}"
    return assemble(test, injection=injection)
