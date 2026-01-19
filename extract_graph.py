import json
import sys
import csv
import ifcopenshell
import networkx as nx
import math
import os



def node_id(ent):
    # Stable id for graph nodes
    return f"{ent.is_a()}_{ent.GlobalId}" if hasattr(ent, "GlobalId") else f"{ent.is_a()}_{id(ent)}"

def add_node(G, model, ent):
    nid = node_id(ent)
    if nid in G:
        return nid

    ifc_type = ent.is_a()
    name = getattr(ent, "Name", None)

    # ---------------------------
    # OPTION B (Controlled graph / allowlist)
    # Keep:
    #   - Physical elements: IfcElement + all subtypes (IfcWall, IfcSlab, ...)
    #   - Context nodes: IfcSpace, IfcBuildingStorey, IfcSystem
    # Drop:
    #   - Root spatial context nodes: IfcProject, IfcBuilding, IfcSite
    #   - Noisy metadata proxies by name (origin, geo-reference)
    # ---------------------------

    # Drop spatial roots (noise for construction logic)
    if ifc_type in ("IfcProject", "IfcBuilding", "IfcSite"):
        return None

    # Drop noisy metadata proxies by name
    bad_names = {"origin", "geo-reference"}
    if name and str(name).strip().lower() in bad_names:
        return None

    # Keep context nodes explicitly
    if ifc_type in ("IfcSpace", "IfcBuildingStorey", "IfcSystem"):
        pass
    else:
        # For everything else, keep only IfcElement or its subtypes
        try:
            if not ent.is_a("IfcElement"):
                return None
        except Exception:
            return None

    # Geometry-lite features (bbox/centroid)
    bbox, centroid = try_get_bbox_centroid(model, ent)

    G.add_node(
        nid,
        ifc_type=ifc_type,
        name=name,
        bbox=bbox,
        centroid=centroid,
    )
    return nid

def safe_by_type(model, type_name):
    try:
        return model.by_type(type_name)
    except RuntimeError:
        return []

def try_get_bbox_centroid(model, ent):
    """
    Returns (bbox, centroid) where:
      bbox = (minx, miny, minz, maxx, maxy, maxz)
      centroid = (cx, cy, cz)
    If geometry backend is unavailable or element has no shape, returns (None, None).
    """
    try:
        import ifcopenshell.geom
    except Exception:
        return None, None

    try:
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)

        shape = ifcopenshell.geom.create_shape(settings, ent)
        verts = shape.geometry.verts  # flat list [x1,y1,z1,x2,y2,z2,...]
        if not verts or len(verts) < 6:
            return None, None

        xs = verts[0::3]
        ys = verts[1::3]
        zs = verts[2::3]

        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        minz, maxz = min(zs), max(zs)

        cx = (minx + maxx) / 2.0
        cy = (miny + maxy) / 2.0
        cz = (minz + maxz) / 2.0

        return (minx, miny, minz, maxx, maxy, maxz), (cx, cy, cz)
    except Exception:
        return None, None


def bbox_xy_overlap(a, b):
    # a,b: (minx,miny,minz,maxx,maxy,maxz)
    return (a[0] <= b[3] and a[3] >= b[0]) and (a[1] <= b[4] and a[4] >= b[1])


def bbox_min_distance(a, b):
    """
    Minimum Euclidean distance between two axis-aligned bounding boxes.
    0 if they overlap/touch.
    """
    dx = max(0.0, max(a[0] - b[3], b[0] - a[3]))
    dy = max(0.0, max(a[1] - b[4], b[1] - a[4]))
    dz = max(0.0, max(a[2] - b[5], b[2] - a[5]))
    return math.sqrt(dx*dx + dy*dy + dz*dz)


def export_csv_nodes_edges(G: nx.MultiDiGraph, nodes_csv="nodes.csv", edges_csv="edges.csv"):
    # Assign integer indices for ML (edge_index style)
    nodes = list(G.nodes())
    idx_map = {nid: i for i, nid in enumerate(nodes)}

    # --- NEW: create type->id mappings for ML ---
    node_types = sorted({G.nodes[n].get("ifc_type") for n in nodes if G.nodes[n].get("ifc_type")})
    node_type_to_id = {t: i for i, t in enumerate(node_types)}

    edge_types = sorted({attrs.get("rel") for _, _, attrs in G.edges(data=True) if attrs.get("rel")})
    edge_type_to_id = {t: i for i, t in enumerate(edge_types)}

    # nodes.csv
    with open(nodes_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "idx", "node_id", "ifc_type", "node_type_id", "name",
            "cx", "cy", "cz",
            "minx", "miny", "minz", "maxx", "maxy", "maxz"
        ])
        for nid in nodes:
            attrs = G.nodes[nid]
            t = attrs.get("ifc_type")

            cent = attrs.get("centroid")
            bbox = attrs.get("bbox")

            if cent:
                cx, cy, cz = cent
            else:
                cx = cy = cz = ""

            if bbox:
                minx, miny, minz, maxx, maxy, maxz = bbox
            else:
                minx = miny = minz = maxx = maxy = maxz = ""

            w.writerow([
                idx_map[nid], nid, t, node_type_to_id.get(t, -1), attrs.get("name"),
                cx, cy, cz,
                minx, miny, minz, maxx, maxy, maxz
            ])


    # edges.csv
    with open(edges_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["src", "dst", "rel", "edge_type_id", "src_idx", "dst_idx"])
        for u, v, attrs in G.edges(data=True):
            rel = attrs.get("rel")
            w.writerow([u, v, rel, edge_type_to_id.get(rel, -1), idx_map[u], idx_map[v]])

    # (Optional) return mappings too, useful later
    return idx_map, node_type_to_id, edge_type_to_id

def export_facts(G: nx.MultiDiGraph, facts_tsv="facts.tsv"):
    """
    Reasoning-ready export as triples:
      subject \t predicate \t object
    We export:
      - has_type(node, IfcWall)
      - has_name(node, "Wall A") (if exists)
      - rel edges as predicates: contained_in, part_of, connects (lowercased)
    """
    def norm_pred(p: str) -> str:
        return p.strip().lower()

    with open(facts_tsv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["subject", "predicate", "object"])

        # Node facts
        for nid, attrs in G.nodes(data=True):
            ifc_type = attrs.get("ifc_type")
            if ifc_type:
                w.writerow([nid, "has_type", ifc_type])
            name = attrs.get("name")
            if name:
                w.writerow([nid, "has_name", str(name)])

        # Edge facts
        for u, v, attrs in G.edges(data=True):
            rel = attrs.get("rel")
            if not rel:
                continue

            pred = norm_pred(rel)
            w.writerow([u, pred, v])

            # --- NEW: derived fact for construction reasoning ---
            # in_storey(x, storey) if contained_in(x, storey) AND storey is IfcBuildingStorey
            v_type = G.nodes[v].get("ifc_type")
            if pred == "contained_in" and v_type == "IfcBuildingStorey":
                w.writerow([u, "in_storey", v])


def main(ifc_path: str, out_json: str = "graph.json"):
    model = ifcopenshell.open(ifc_path)
    G = nx.MultiDiGraph()
        # Put all outputs next to out_json
    out_dir = os.path.dirname(out_json)
    if out_dir == "":
        out_dir = "."
    os.makedirs(out_dir, exist_ok=True)

    nodes_csv = os.path.join(out_dir, "nodes.csv")
    edges_csv = os.path.join(out_dir, "edges.csv")
    facts_tsv = os.path.join(out_dir, "facts.tsv")

    # --- Nodes (robust across schemas incl. IFC4X3) ---
    elements = safe_by_type(model, "IfcElement")
    spaces   = safe_by_type(model, "IfcSpace")
    storeys  = safe_by_type(model, "IfcBuildingStorey")
    systems  = safe_by_type(model, "IfcSystem")

    for ent in elements + spaces + storeys + systems:
        add_node(G, model, ent)  # add_node already filters if needed


    # --- Edges: containment (spatial structure) ---
    for rel in safe_by_type(model, "IfcRelContainedInSpatialStructure"):
        container = getattr(rel, "RelatingStructure", None)
        if not container:
            continue

        # --- FILTER 2: keep containment only into Space/Storey ---
        if container.is_a() not in ("IfcSpace", "IfcBuildingStorey"):
            continue

        c_id = add_node(G, model, container)
        if c_id is None:
            continue

        for obj in (getattr(rel, "RelatedElements", None) or []):
            o_id = add_node(G, model, obj)
            if o_id is None:
                continue
            G.add_edge(o_id, c_id, rel="CONTAINED_IN")


    # --- Edges: aggregates (part-of) ---
    for rel in safe_by_type(model, "IfcRelAggregates"):
        whole = getattr(rel, "RelatingObject", None)
        if not whole:
            continue
        w_id = add_node(G, model, whole)
        if w_id is None:
            continue

        for part in (getattr(rel, "RelatedObjects", None) or []):
            p_id = add_node(G, model, part)
            if p_id is None:
                continue
            G.add_edge(p_id, w_id, rel="PART_OF")

    # --- Edges: connects elements (topology) ---
    for rel in safe_by_type(model, "IfcRelConnectsElements"):
        a = getattr(rel, "RelatingElement", None)
        b = getattr(rel, "RelatedElement", None)
        if a and b:
            a_id = add_node(G, model, a)
            b_id = add_node(G, model, b)
            if a_id is None or b_id is None:
                continue
            G.add_edge(a_id, b_id, rel="CONNECTS")

    # --- Derived spatial relations (geometry-lite) ---
    # Thresholds (units depend on IFC; for most samples it's meters)
    ADJ_EPS = 0.05   # 5 cm: consider adjacent if bbox distance <= eps
    Z_GAP_MIN = 0.00 # allow touching as above/below
    Z_GAP_MAX = 1.00 # 1 m: limit for above/below inference (avoid weird far relations)

    # Collect nodes that have bbox and are physical-ish elements (not spaces)
    bbox_nodes = []
    for nid, attrs in G.nodes(data=True):
        if attrs.get("bbox") is None:
            continue
        t = attrs.get("ifc_type")
        # skip spaces in spatial adjacency (optional)
        if t in ("IfcSpace", "IfcBuildingStorey"):
            continue
        bbox_nodes.append(nid)

    # Optionally: restrict comparisons within same storey using your in_storey facts
    # We'll infer storey membership from CONTAINED_IN edges to IfcBuildingStorey.
    in_storey = {}
    for u, v, eattrs in G.edges(data=True):
        if eattrs.get("rel") == "CONTAINED_IN" and G.nodes[v].get("ifc_type") == "IfcBuildingStorey":
            in_storey[u] = v

    # Group by storey to avoid O(n^2) across whole building
    groups = {}
    for nid in bbox_nodes:
        key = in_storey.get(nid, "__NO_STOREY__")
        groups.setdefault(key, []).append(nid)

    for key, group in groups.items():
        # pairwise within group (OK for now; later can replace by spatial index)
        for i in range(len(group)):
            a = group[i]
            abox = G.nodes[a]["bbox"]
            for j in range(i + 1, len(group)):
                b = group[j]
                bbox = G.nodes[b]["bbox"]

                # ADJACENT if bboxes touch/near
                d = bbox_min_distance(abox, bbox)
                if d <= ADJ_EPS:
                    G.add_edge(a, b, rel="ADJACENT")
                    G.add_edge(b, a, rel="ADJACENT")

                # ABOVE/BELOW if XY overlap + vertical ordering
                if bbox_xy_overlap(abox, bbox):
                    # a above b?
                    gap_ab = abox[2] - bbox[5]  # a.minz - b.maxz
                    if Z_GAP_MIN <= gap_ab <= Z_GAP_MAX:
                        G.add_edge(a, b, rel="ABOVE")
                        G.add_edge(b, a, rel="BELOW")

                    # b above a?
                    gap_ba = bbox[2] - abox[5]
                    if Z_GAP_MIN <= gap_ba <= Z_GAP_MAX:
                        G.add_edge(b, a, rel="ABOVE")
                        G.add_edge(a, b, rel="BELOW")
    
    # --- Export JSON (single source of truth) ---
    data = {
        "schema": getattr(model, "schema", None),
        "num_nodes": G.number_of_nodes(),
        "num_edges": G.number_of_edges(),
        "nodes": [{"id": n, **G.nodes[n]} for n in G.nodes()],
        "edges": [{"src": u, "dst": v, **attrs} for (u, v, attrs) in G.edges(data=True)],
    }
    
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # --- Dual-output exports ---
    idx_map, node_type_to_id, edge_type_to_id = export_csv_nodes_edges(G, nodes_csv=nodes_csv, edges_csv=edges_csv)
    export_facts(G, facts_tsv=facts_tsv)

    print(f"✅ Wrote {out_json}")
    print(f"✅ Wrote {nodes_csv} / {edges_csv} (ML-ready indices)")
    print(f"✅ Wrote {facts_tsv} (Reasoning-ready triples)")
    print(f"   schema={data['schema']}")
    print(f"   nodes={data['num_nodes']}, edges={data['num_edges']}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_graph.py sample.ifc [out.json]")
        raise SystemExit(2)
    ifc_path = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) >= 3 else "graph.json"
    main(ifc_path, out)
