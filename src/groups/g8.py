"""G8 hackreset (paper's get_fake_conversation): injects correct current values
as a fake prior assistant turn. NOT a fair release technique — used as an
ablation to show the paper's 'Mock-QA works' was answer-injection-driven."""
from ._common import assemble, hackreset_injection
from pi_test import PITest

ID = "G8"
NAME = "hackreset"
DESC = "★论文 hackreset:把正确答案伪造成 assistant 回合注入。不诚实,但复现论文\"有效\"条件(对照用)。"


def build(test: PITest, seed: int = 0) -> str:
    return assemble(test, injection=hackreset_injection(test))
