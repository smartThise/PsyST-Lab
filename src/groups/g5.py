"""G5 unicode/control bytes: real RTL/zero-width/null/combining chars."""
from ._common import assemble, _unicode_payload
from pi_test import PITest

ID = "G5"
NAME = "unicode-bytes"
DESC = "字节级:注入 RTL/零宽/null/组合字符等真实控制字节。可能被 API 转义或拒绝。"


def build(test: PITest, seed: int = 0) -> str:
    return assemble(test, injection=_unicode_payload())
