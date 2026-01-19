from typing import Dict, List, Tuple, Set
from section2.engine import FactBase

Fact = Tuple[str, str, str]

def type_of(facts: List[Fact]) -> Dict[str, str]:
    t = {}
    for s, p, o in facts:
        if p == "has_type":
            t[s] = o
    return t

def storey_of(facts: List[Fact]) -> Dict[str, str]:
    st = {}
    for s, p, o in facts:
        if p == "in_storey":
            st[s] = o
    return st

def build_adj_set(facts: List[Fact]) -> Set[Tuple[str, str]]:
    return set((s, o) for s, p, o in facts if p == "adjacent")

def build_above_pairs(facts: List[Fact]) -> List[Tuple[str, str]]:
    # returns (x, y) for x above y
    return [(s, o) for s, p, o in facts if p == "above"]

# ---- RULES ----

def rule_slab_before_above(facts: List[Fact]):
    """
    If x above y AND y is IfcSlab -> y must be before x.
    """
    t = type_of(facts)
    outs = []
    for x, y in build_above_pairs(facts):
        if t.get(y) != "IfcSlab":
            continue
        outs.append({
            "src": y, "dst": x,
            "edge_type": "requires_before",
            "rule_id": "R1_SLAB_BEFORE_ABOVE",
            "confidence": 0.75,
            "evidence": "above|has_type"
        })
    return outs

def rule_wall_before_door(facts: List[Fact]):
    """
    If door adjacent wall -> wall before door
    """
    t = type_of(facts)
    st = storey_of(facts)
    adj = build_adj_set(facts)

    outs = []
    for a, b in adj:
        ta, tb = t.get(a), t.get(b)
        if ta is None or tb is None:
            continue
        # wall-standardcase or wall
        is_wall_a = ta in ("IfcWall", "IfcWallStandardCase")
        is_wall_b = tb in ("IfcWall", "IfcWallStandardCase")
        is_door_a = ta == "IfcDoor"
        is_door_b = tb == "IfcDoor"

        # same storey if available (avoid cross-storey adjacency noise)
        if a in st and b in st and st[a] != st[b]:
            continue

        if is_wall_a and is_door_b:
            outs.append({
                "src": a, "dst": b,
                "edge_type": "requires_before",
                "rule_id": "R2_WALL_BEFORE_DOOR",
                "confidence": 0.85,
                "evidence": "adjacent|has_type|in_storey"
            })
        if is_wall_b and is_door_a:
            outs.append({
                "src": b, "dst": a,
                "edge_type": "requires_before",
                "rule_id": "R2_WALL_BEFORE_DOOR",
                "confidence": 0.85,
                "evidence": "adjacent|has_type|in_storey"
            })
    return outs

def rule_beam_before_member(facts: List[Fact]):
    """
    Roof/member (IfcMember) often depends on beams/purlins.
    If member adjacent beam -> beam before member.
    """
    t = type_of(facts)
    st = storey_of(facts)
    adj = build_adj_set(facts)

    outs = []
    for a, b in adj:
        ta, tb = t.get(a), t.get(b)
        if ta is None or tb is None:
            continue
        if a in st and b in st and st[a] != st[b]:
            continue

        if ta == "IfcBeam" and tb == "IfcMember":
            outs.append({
                "src": a, "dst": b,
                "edge_type": "requires_before",
                "rule_id": "R3_BEAM_BEFORE_MEMBER",
                "confidence": 0.70,
                "evidence": "adjacent|has_type|in_storey"
            })
        if tb == "IfcBeam" and ta == "IfcMember":
            outs.append({
                "src": b, "dst": a,
                "edge_type": "requires_before",
                "rule_id": "R3_BEAM_BEFORE_MEMBER",
                "confidence": 0.70,
                "evidence": "adjacent|has_type|in_storey"
            })
    return outs

def rule_supports_from_above(facts: List[Fact]):
    """
    If x above y -> y supports x (symbolic fact)
    """
    new_facts = []
    for x, y in build_above_pairs(facts):
        new_facts.append((y, "supports", x))
    return new_facts
