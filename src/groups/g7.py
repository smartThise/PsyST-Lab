"""G7 query engineering: recency-anchored phrasing + forced answer prefix."""
from ._common import assemble, engineered_query
from pi_test import PITest

ID = "G7"
NAME = "query-engineering"
DESC = "Query 工程:recency 锚定措辞 + 强制答案前缀('Based on the most recent update,')。"


def build(test: PITest, seed: int = 0) -> str:
    return assemble(test, query=engineered_query(test))
