"""G4 glitch tokens: high-norm / rare tokens. Composable mid-stream feature."""
from ._common import assemble_midstream, _load_glitch_tokens
from pi_test import PITest

ID = "G4"
NAME = "glitch-tokens"
COLOR = "#cf222e"
DESC = "Token 级:流中段注入高范数/罕见 glitch token(如 .SolidGoldMagikarp)。可组合。"


def feature(test: PITest, seed: int = 0) -> str:
    return f".{_load_glitch_tokens(n=8, seed=seed)}."


def build(test: PITest, seed: int = 0) -> str:
    return assemble_midstream(test, injection=feature(test, seed))
