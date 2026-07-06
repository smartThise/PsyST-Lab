"""G4 glitch tokens: high-norm / rare tokens injected before query."""
from ._common import assemble, _load_glitch_tokens
from pi_test import PITest

ID = "G4"
NAME = "glitch-tokens"
DESC = "Token 级:注入高范数/罕见 glitch token(如 .SolidGoldMagikarp),底层扰动。"


def build(test: PITest, seed: int = 0) -> str:
    glitch = _load_glitch_tokens(n=8, seed=seed)
    return assemble(test, injection=f".{glitch}.")
