from typing import Dict, List, Set, Tuple, Iterable
import json

Fact = Tuple[str, str, str]

class FactBase:
    def __init__(self, facts: Iterable[Fact]):
        self.facts: Set[Fact] = set(facts)
        self.by_pred: Dict[str, List[Fact]] = {}
        for s, p, o in self.facts:
            self.by_pred.setdefault(p, []).append((s, p, o))

    def add(self, fact: Fact) -> bool:
        if fact in self.facts:
            return False
        self.facts.add(fact)
        s, p, o = fact
        self.by_pred.setdefault(p, []).append(fact)
        return True

    def get(self, pred: str) -> List[Fact]:
        return self.by_pred.get(pred, [])

def append_trace(trace_path: str, record: dict) -> None:
    with open(trace_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def get_fact(fb: FactBase, subj: str, pred: str, obj: str) -> list:
    """
    Return evidence fact as [subj,pred,obj] if it exists, otherwise [].
    """
    return [[subj, pred, obj]] if (subj, pred, obj) in fb.facts else []
