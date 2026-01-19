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
    new_facts_added = True
    max_iters = 5
    iter_no = 0

    step = 0

    while new_facts_added and iter_no < max_iters:
        iter_no += 1
        new_facts_added = False

        current_facts = list(fb.facts)

        # R1: slab -> element above slab  (edge + derived requires_before fact)
        for row in rules_v0.rule_slab_before_above(current_facts):
            step += 1
            precedence_rows.append(row)

            # also write as derived fact
            rb_fact = (row["src"], "requires_before", row["dst"])
            if fb.add(rb_fact):
                derived_new.append(rb_fact)
                new_facts_added = True

            src = row["src"]  # slab
            dst = row["dst"]  # element
            evidence = []
            evidence += get_fact(fb, dst, "above", src)
            evidence += get_fact(fb, src, "has_type", "IfcSlab")
            for s, p, o in fb.get("in_storey"):
                if s == src or s == dst:
                    evidence.append([s, p, o])

            append_trace(trace_path, {
                "step": step,
                "iter": iter_no,
                "rule_id": row["rule_id"],
                "bindings": {"slab": src, "elem": dst},
                "evidence": evidence,
                "new_edges": [row],
                "new_facts": [[rb_fact[0], rb_fact[1], rb_fact[2]]]
            })

        current_facts = list(fb.facts)

        # R2: wall -> door/window (edge + derived requires_before + hard constraint cannot_before)
        for row in rules_v0.rule_wall_before_door(current_facts):
            step += 1
            precedence_rows.append(row)

            rb_fact = (row["src"], "requires_before", row["dst"])
            if fb.add(rb_fact):
                derived_new.append(rb_fact)
                new_facts_added = True

            # hard constraint
            constraints.append((row["dst"], "cannot_before", row["src"]))

            src = row["src"]  # wall
            dst = row["dst"]  # opening
            evidence = []
            evidence += get_fact(fb, src, "adjacent", dst)
            evidence += get_fact(fb, src, "has_type", "IfcWallStandardCase")
            if not evidence:
                evidence += get_fact(fb, src, "has_type", "IfcWall")
            evidence += get_fact(fb, dst, "has_type", "IfcDoor")
            if not evidence:
                evidence += get_fact(fb, dst, "has_type", "IfcWindow")
            for s, p, o in fb.get("in_storey"):
                if s == src or s == dst:
                    evidence.append([s, p, o])

            append_trace(trace_path, {
                "step": step,
                "iter": iter_no,
                "rule_id": row["rule_id"],
                "bindings": {"wall": src, "opening": dst},
                "evidence": evidence,
                "new_edges": [row],
                "new_facts": [[rb_fact[0], rb_fact[1], rb_fact[2]],
                            [dst, "cannot_before", src]]
            })

        current_facts = list(fb.facts)

        # R3: beam -> member (edge + derived requires_before fact)
        for row in rules_v0.rule_beam_before_member(current_facts):
            step += 1
            precedence_rows.append(row)

            rb_fact = (row["src"], "requires_before", row["dst"])
            if fb.add(rb_fact):
                derived_new.append(rb_fact)
                new_facts_added = True

            src = row["src"]  # beam
            dst = row["dst"]  # member
            evidence = []
            evidence += get_fact(fb, src, "adjacent", dst)
            evidence += get_fact(fb, src, "has_type", "IfcBeam")
            evidence += get_fact(fb, dst, "has_type", "IfcMember")
            for s, p, o in fb.get("in_storey"):
                if s == src or s == dst:
                    evidence.append([s, p, o])

            append_trace(trace_path, {
                "step": step,
                "iter": iter_no,
                "rule_id": row["rule_id"],
                "bindings": {"beam": src, "member": dst},
                "evidence": evidence,
                "new_edges": [row],
                "new_facts": [[rb_fact[0], rb_fact[1], rb_fact[2]]]
            })

        current_facts = list(fb.facts)
        
        #R5 column -> Beam
        current_facts = list(fb.facts)
        for row in rules_v0.rule_column_before_beam(current_facts):
            step += 1
            precedence_rows.append(row)

            rb_fact = (row["src"], "requires_before", row["dst"])
            if fb.add(rb_fact):
                derived_new.append(rb_fact)
                new_facts_added = True

            src = row["src"]  # column
            dst = row["dst"]  # beam

            evidence = []
            evidence += get_fact(fb, src, "adjacent", dst)
            evidence += get_fact(fb, src, "has_type", "IfcColumn")
            evidence += get_fact(fb, dst, "has_type", "IfcBeam")
            for s, p, o in fb.get("in_storey"):
                if s == src or s == dst:
                    evidence.append([s, p, o])

            append_trace(trace_path, {
                "step": step,
                "iter": iter_no,
                "rule_id": row["rule_id"],
                "bindings": {"column": src, "beam": dst},
                "evidence": evidence,
                "new_edges": [row],
                "new_facts": [[rb_fact[0], rb_fact[1], rb_fact[2]]]
            })
            
        #R6 Beam -> Slab
        current_facts = list(fb.facts)
        for row in rules_v0.rule_beam_before_slab(current_facts):
            step += 1
            precedence_rows.append(row)

            rb_fact = (row["src"], "requires_before", row["dst"])
            if fb.add(rb_fact):
                derived_new.append(rb_fact)
                new_facts_added = True

            src = row["src"]  # beam
            dst = row["dst"]  # slab

            evidence = []
            # evidence can come from adjacent OR above depending on how rule fired
            evidence += get_fact(fb, src, "adjacent", dst)
            evidence += get_fact(fb, dst, "adjacent", src)
            evidence += get_fact(fb, dst, "above", src)  # slab above beam case
            evidence += get_fact(fb, src, "has_type", "IfcBeam")
            evidence += get_fact(fb, dst, "has_type", "IfcSlab")
            for s, p, o in fb.get("in_storey"):
                if s == src or s == dst:
                    evidence.append([s, p, o])

            append_trace(trace_path, {
                "step": step,
                "iter": iter_no,
                "rule_id": row["rule_id"],
                "bindings": {"beam": src, "slab": dst},
                "evidence": evidence,
                "new_edges": [row],
                "new_facts": [[rb_fact[0], rb_fact[1], rb_fact[2]]]
            })
        
        #R7
        current_facts = list(fb.facts)
        for row in rules_v0.rule_slab_before_wall(current_facts):
            step += 1
            precedence_rows.append(row)

            rb_fact = (row["src"], "requires_before", row["dst"])
            if fb.add(rb_fact):
                derived_new.append(rb_fact)
                new_facts_added = True

            src = row["src"]  # slab
            dst = row["dst"]  # wall

            evidence = []
            evidence += get_fact(fb, dst, "above", src)   # wall above slab
            evidence += get_fact(fb, src, "adjacent", dst)
            evidence += get_fact(fb, src, "has_type", "IfcSlab")
            evidence += get_fact(fb, dst, "has_type", "IfcWallStandardCase")
            if not evidence:
                evidence += get_fact(fb, dst, "has_type", "IfcWall")

            for s, p, o in fb.get("in_storey"):
                if s == src or s == dst:
                    evidence.append([s, p, o])

            append_trace(trace_path, {
                "step": step,
                "iter": iter_no,
                "rule_id": row["rule_id"],
                "bindings": {"slab": src, "wall": dst},
                "evidence": evidence,
                "new_edges": [row],
                "new_facts": [[rb_fact[0], rb_fact[1], rb_fact[2]]]
            })


        # R4: supports from above (facts)
        for fact in rules_v0.rule_supports_from_above(current_facts):
            if fb.add(fact):
                derived_new.append(fact)
                new_facts_added = True

                step += 1
                append_trace(trace_path, {
                    "step": step,
                    "iter": iter_no,
                    "rule_id": "R4_SUPPORTS_FROM_ABOVE",
                    "bindings": {"support": fact[0], "supported": fact[2]},
                    "evidence": get_fact(fb, fact[2], "above", fact[0]),
                    "new_edges": [],
                    "new_facts": [[fact[0], fact[1], fact[2]]]
                })

    best = {}
    for r in precedence_rows:
        key = (r["src"], r["dst"], r["edge_type"])
        if key not in best or float(r["confidence"]) > float(best[key]["confidence"]):
            best[key] = r
    precedence_rows = list(best.values())
    precedence_rows = [r for r in precedence_rows if r["src"] != r["dst"]]
    


    # write outputs
    write_facts_tsv(derived_path, derived_new)
    write_precedence_csv(precedence_path, precedence_rows)
    logic_graph_path = os.path.join(sec2_dir, "construction_logic_graph.csv")
    write_precedence_csv(logic_graph_path, precedence_rows)
    print("logic_graph:", logic_graph_path)

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
