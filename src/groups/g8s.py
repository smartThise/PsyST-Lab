"""G8s hackreset (paper-faithful): the REAL get_fake_conversation.

G8 is the broken answer-injection (test.targets, end-position). G8s matches the
paper instead:
  1. Injected values = snapshot of each key's value CURRENT AT THE INJECTION POINT
     (last occurrence before len-tail), NOT test.targets. Most are STALE relative
     to the final query (the trailing batch overwrites them), so the model cannot
     win by copying them.
  2. Position = mid-stream at len-tail (120 trailing updates), via assemble_midstream.
  3. Three-part structure: fake user query + fake assistant reply (snapshot) +
     a NEW user instruction re-opening the task -- the actual task boundary.

The paper's lift (when it appears) comes from the boundary making the model treat
pre-boundary input as a closed task and focus on the trailing batch -- NOT from
the injected values. So G8s is the honest test of the paper's mechanism."""
from pi_test import PITest, build_base_query

ID = "G8s"
NAME = "hackreset-paper"
COLOR = "#0e7c7b"
DESC = "★论文 hackreset 忠实复刻:中段注入,伪造对话里的值=注入点处的快照(相对最终多数过期),三段含'新任务'边界。测论文边界机制。"


def _snapshot_at_cut(test: PITest) -> dict:
    """Each key's most recent value seen before the injection cut (len-tail).
    Uses the same _default_tail_updates as assemble_midstream, so the snapshot
    matches the actual injection position."""
    from groups._common import _default_tail_updates
    n = len(test.updates)
    cut = n - min(_default_tail_updates(len(test.keys)), n - 1)
    snap: dict = {}
    for i in range(cut):
        snap[test.updates[i]["key"]] = test.updates[i]["value"]
    return snap


def feature(test: PITest, seed: int = 0) -> str:
    from groups._common import paper_instruction
    NL = chr(10)
    snap = _snapshot_at_cut(test)
    current = NL.join(f"The current value of {k} is {v}." for k, v in snap.items())
    question = build_base_query(test.keys)
    instruction = paper_instruction(test)
    # three-part fake conversation: completed Q&A (closure prop) + fresh task (boundary)
    return NL.join([
        '{"role": "user", "content": "' + question + '"}',
        '{"role": "assistant", "content": "Okay, Here are the current values of the specified keys:',
        '',
        current,
        '"}',
        '{"role": "user", "content": "' + instruction + '"}',
    ])


def build(test: PITest, seed: int = 0) -> str:
    from groups._common import assemble_midstream
    return assemble_midstream(test, injection=feature(test, seed))
