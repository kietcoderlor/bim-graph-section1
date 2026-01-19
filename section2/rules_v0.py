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
    Filter dst types to avoid noisy precedence (e.g., slab->slab, slab->railing).
    """
    t = type_of(facts)

    allowed_dst = {
        "IfcWall", "IfcWallStandardCase",
        "IfcColumn", "IfcBeam", "IfcMember",
        "IfcStair",
        # "IfcDoor", "IfcWindow",  # bật nếu bạn muốn slab->opening
    }

    outs = []
    for x, y in build_above_pairs(facts):
        # x above y
        if t.get(y) != "IfcSlab":
            continue
        if t.get(x) not in allowed_dst:
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

def rule_column_before_beam(facts: List[Fact]):
    """
    Column -> Beam if same storey and adjacent.
    """
    t = type_of(facts)
    st = storey_of(facts)
    adj = build_adj_set(facts)

    outs = []
    for a, b in adj:
        if a in st and b in st and st[a] != st[b]:
            continue

        if t.get(a) == "IfcColumn" and t.get(b) == "IfcBeam":
            outs.append({
                "src": a, "dst": b,
                "edge_type": "requires_before",
                "rule_id": "R5_COLUMN_BEFORE_BEAM",
                "confidence": 0.72,
                "evidence": "adjacent|has_type|in_storey"
            })
        if t.get(b) == "IfcColumn" and t.get(a) == "IfcBeam":
            outs.append({
                "src": b, "dst": a,
                "edge_type": "requires_before",
                "rule_id": "R5_COLUMN_BEFORE_BEAM",
                "confidence": 0.72,
                "evidence": "adjacent|has_type|in_storey"
            })
    return outs

def rule_beam_before_slab(facts: List[Fact]):
    """
    Beam -> Slab if same storey and (adjacent OR slab above beam).
    This avoids edge explosion.
    """
    t = type_of(facts)
    st = storey_of(facts)
    adj = build_adj_set(facts)
    above = set(build_above_pairs(facts))  # (x above y)

    outs = []

    # Adjacent-based
    for a, b in adj:
        if a in st and b in st and st[a] != st[b]:
            continue

        if t.get(a) == "IfcBeam" and t.get(b) == "IfcSlab":
            outs.append({
                "src": a, "dst": b,
                "edge_type": "requires_before",
                "rule_id": "R6_BEAM_BEFORE_SLAB",
                "confidence": 0.70,
                "evidence": "adjacent|has_type|in_storey"
            })
        if t.get(b) == "IfcBeam" and t.get(a) == "IfcSlab":
            outs.append({
                "src": b, "dst": a,
                "edge_type": "requires_before",
                "rule_id": "R6_BEAM_BEFORE_SLAB",
                "confidence": 0.70,
                "evidence": "adjacent|has_type|in_storey"
            })

    # Above-based (slab above beam -> beam before slab)
    # If slab (x) above beam (y): above(x,y) where x=slab, y=beam
    for x, y in above:
        if t.get(x) == "IfcSlab" and t.get(y) == "IfcBeam":
            if x in st and y in st and st[x] != st[y]:
                continue
            outs.append({
                "src": y, "dst": x,
                "edge_type": "requires_before",
                "rule_id": "R6_BEAM_BEFORE_SLAB",
                "confidence": 0.74,
                "evidence": "above|has_type|in_storey"
            })

    return outs

def rule_slab_before_wall(facts: List[Fact]):
    """Slab -> Wall if same storey and wall is above slab OR adjacent.
    Prefer above evidence (stronger), fallback adjacent."""
    t = type_of(facts)
    st = storey_of(facts)
    adj = build_adj_set(facts)
    above = set(build_above_pairs(facts))  # (x above y)

    outs = []

    # above-based: wall above slab -> slab before wall
    for x, y in above:
        # x above y
        if t.get(x) in ("IfcWall", "IfcWallStandardCase") and t.get(y) == "IfcSlab":
            if x in st and y in st and st[x] != st[y]:
                continue
            outs.append({
                "src": y, "dst": x,
                "edge_type": "requires_before",
                "rule_id": "R7_SLAB_BEFORE_WALL",
                "confidence": 0.80,
                "evidence": "above|has_type|in_storey"
            })

    # adjacency-based fallback (weaker)
    for a, b in adj:
        if a in st and b in st and st[a] != st[b]:
            continue

        if t.get(a) == "IfcSlab" and t.get(b) in ("IfcWall", "IfcWallStandardCase"):
            outs.append({
                "src": a, "dst": b,
                "edge_type": "requires_before",
                "rule_id": "R7_SLAB_BEFORE_WALL",
                "confidence": 0.65,
                "evidence": "adjacent|has_type|in_storey"
            })
        if t.get(b) == "IfcSlab" and t.get(a) in ("IfcWall", "IfcWallStandardCase"):
            outs.append({
                "src": b, "dst": a,
                "edge_type": "requires_before",
                "rule_id": "R7_SLAB_BEFORE_WALL",
                "confidence": 0.65,
                "evidence": "adjacent|has_type|in_storey"
            })

    return outs

