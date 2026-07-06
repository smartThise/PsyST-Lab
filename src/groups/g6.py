"""G6 self-generation: query override asking for disruption tokens then answer.
Uses autoregressive KV feedback within one generation. Needs high temperature."""
from ._common import assemble, self_gen_query
from pi_test import PITest

ID = "G6"
NAME = "self-generation"
DESC = "自生成:改写 query 让模型先吐扰乱 token 再回答(利用 KV 回喂),高温采样。"

OVERRIDES = {"temperature": 0.8}


def build(test: PITest, seed: int = 0) -> str:
    return assemble(test, query=self_gen_query(test))
