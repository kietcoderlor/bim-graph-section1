from typing import List, Tuple, Iterable
import csv

Fact = Tuple[str, str, str]  # (subject, predicate, object)

def read_facts_tsv(path: str) -> List[Fact]:
    facts: List[Fact] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            # your file has header: subject predicate object
            if parts[0] == "subject" and len(parts) >= 3 and parts[1] == "predicate":
                continue
            if len(parts) < 3:
                continue
            s, p, o = parts[0].strip(), parts[1].strip(), parts[2].strip()
            facts.append((s, p, o))
    return facts

def write_facts_tsv(path: str, facts: Iterable[Fact]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("subject\tpredicate\tobject\n")
        for s, p, o in facts:
            f.write(f"{s}\t{p}\t{o}\n")

def write_precedence_csv(path: str, rows: Iterable[dict]) -> None:
    fieldnames = ["src", "dst", "edge_type", "rule_id", "confidence", "evidence"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def write_constraints_tsv(path: str, facts: Iterable[Fact]) -> None:
    # same format as facts.tsv
    write_facts_tsv(path, facts)
