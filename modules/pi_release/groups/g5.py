"""G5 unicode/control bytes: real RTL/zero-width/null/combining chars. Composable feature."""
from ._common import assemble_midstream, _unicode_payload
from ..pi_test import PITest

ID = "G5"
NAME = "unicode-bytes"
COLOR = "#bf8700"
DESC = "字节级:流中段注入 RTL/零宽/null/组合字符等真实控制字节。可组合。"


def feature(test: PITest, seed: int = 0) -> str:
    return _unicode_payload()


def build(test: PITest, seed: int = 0) -> str:
    return assemble_midstream(test, injection=feature(test, seed))
