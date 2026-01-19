import os
from section2.io_utils import (
    read_facts_tsv,
    write_facts_tsv,
    write_precedence_csv,
    write_constraints_tsv,
)

from section2 import rules_v0
from section2.engine import FactBase, append_trace, get_fact


def main(sec1_dir: str, sec2_dir: str):
    os.makedirs(sec2_dir, exist_ok=True)

    facts_in = os.path.join(sec1_dir, "facts.tsv")

    # outputs
    enriched_path = os.path.join(sec2_dir, "enriched_facts.tsv")      # can be empty v0
    derived_path = os.path.join(sec2_dir, "derived_facts.tsv")
    precedence_path = os.path.join(sec2_dir, "precedence_edges.csv")
    trace_path = os.path.join(sec2_dir, "trace.jsonl")
    constraints_path = os.path.join(sec2_dir, "constraints.tsv")

    # reset trace
    open(trace_path, "w", encoding="utf-8").close()

    base_facts = read_facts_tsv(facts_in)

    # v0: enrichment optional, if file exists -> load it
    all_facts = list(base_facts)
    if os.path.exists(enriched_path):
        try:
            enriched = read_facts_tsv(enriched_path)
            all_facts.extend(enriched)
        except Exception:
            pass

    fb = FactBase(all_facts)

    # --- apply rules once (v0). later you can do fixpoint chaining.
    precedence_rows = []
    derived_new = []
    constraints = [] 

    step = 0

    # R1 precedence
    for row in rules_v0.rule_slab_before_above(all_facts):
        step += 1
        precedence_rows.append(row)
        src = row["src"]  # slab
        dst = row["dst"]  # element above slab

        evidence = []
        # evidence core: dst above src
        evidence += get_fact(fb, dst, "above", src)

        # if bạn đã siết R1 theo has_type(slab)=IfcSlab thì thêm evidence này:
        evidence += get_fact(fb, src, "has_type", "IfcSlab")

        # storey evidence (nếu có)
        # (không bắt buộc, nhưng rất tốt để paper)
        # Note: storey id không nằm trong row, ta lấy từ fb:
        # Cách lấy storey của một element:
        # - duyệt facts in_storey của element
        for s, p, o in fb.get("in_storey"):
            if s == src:
                evidence.append([s, p, o])
            if s == dst:
                evidence.append([s, p, o])

        append_trace(trace_path, {
            "step": step,
            "rule_id": row["rule_id"],
            "bindings": {"slab": src, "elem": dst},
            "evidence": evidence,
            "new_edges": [row],
            "new_facts": []
        })

    # R2 wall->door/window + HARD constraint cannot_before(opening, wall)
    for row in rules_v0.rule_wall_before_door(all_facts):
        step += 1
        precedence_rows.append(row)

        src = row["src"]  # wall
        dst = row["dst"]  # opening (door/window)

        evidence = []
        evidence += get_fact(fb, src, "adjacent", dst)

        # wall can be IfcWallStandardCase or IfcWall
        evidence += get_fact(fb, src, "has_type", "IfcWallStandardCase")
        if not evidence:
            evidence += get_fact(fb, src, "has_type", "IfcWall")

        # opening can be door/window (depending on your rule implementation)
        evidence += get_fact(fb, dst, "has_type", "IfcDoor")
        if not evidence:
            evidence += get_fact(fb, dst, "has_type", "IfcWindow")

        # storey evidence (optional but good)
        for s, p, o in fb.get("in_storey"):
            if s == src or s == dst:
                evidence.append([s, p, o])

        append_trace(trace_path, {
            "step": step,
            "rule_id": row["rule_id"],
            "bindings": {"wall": src, "opening": dst},
            "evidence": evidence,
            "new_edges": [row],
            "new_facts": []
        })

        # HARD constraint: opening cannot be before wall
        constraints.append((dst, "cannot_before", src))



    # R3 beam->member
    for row in rules_v0.rule_beam_before_member(all_facts):
        step += 1
        precedence_rows.append(row)
        append_trace(trace_path, {
            "step": step,
            "rule_id": row["rule_id"],
            "bindings": {"src": row["src"], "dst": row["dst"]},
            "evidence": row["evidence"],
            "new_edges": [row],
            "new_facts": []
        })

    # R4 supports fact
    for fact in rules_v0.rule_supports_from_above(all_facts):
        if fb.add(fact):
            derived_new.append(fact)

    # write outputs
    write_facts_tsv(derived_path, derived_new)
    write_precedence_csv(precedence_path, precedence_rows)

    # create empty enriched_facts.tsv if not exists (helps pipeline stability)
    if not os.path.exists(enriched_path):
        write_facts_tsv(enriched_path, [])

    constraints = list(dict.fromkeys(constraints))
    write_constraints_tsv(constraints_path, constraints)
    print("constraints:", constraints_path)
    print("Section2 done.")
    print("derived_facts:", derived_path)
    print("precedence_edges:", precedence_path)
    print("trace:", trace_path)

if __name__ == "__main__":
    import sys
    # Usage: python -m section2.run_section2 outputs/ac20_fzk outputs/ac20_fzk_sec2
    main(sys.argv[1], sys.argv[2])
