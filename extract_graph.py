import json
import sys
import csv
import ifcopenshell
import networkx as nx

def node_id(ent):
    # Stable id for graph nodes
    return f"{ent.is_a()}_{ent.GlobalId}" if hasattr(ent, "GlobalId") else f"{ent.is_a()}_{id(ent)}"

def add_node(G, ent):
    nid = node_id(ent)
    if nid not in G:
        name = getattr(ent, "Name", None)
        G.add_node(nid, ifc_type=ent.is_a(), name=name)
    return nid

def safe_by_type(model, type_name):
    try:
        return model.by_type(type_name)
    except RuntimeError:
        return []

def export_csv_nodes_edges(G: nx.MultiDiGraph, nodes_csv="nodes.csv", edges_csv="edges.csv"):
    # Assign integer indices for ML (edge_index style)
    nodes = list(G.nodes())
    idx_map = {nid: i for i, nid in enumerate(nodes)}

    # nodes.csv
    with open(nodes_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["idx", "node_id", "ifc_type", "name"])
        for nid in nodes:
            attrs = G.nodes[nid]
            w.writerow([idx_map[nid], nid, attrs.get("ifc_type"), attrs.get("name")])

    # edges.csv
    with open(edges_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["src", "dst", "rel", "src_idx", "dst_idx"])
        for u, v, attrs in G.edges(data=True):
            rel = attrs.get("rel")
            w.writerow([u, v, rel, idx_map[u], idx_map[v]])

    return idx_map

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
            w.writerow([u, norm_pred(rel), v])

def main(ifc_path: str, out_json: str = "graph.json"):
    model = ifcopenshell.open(ifc_path)
    G = nx.MultiDiGraph()

    # --- Nodes (robust across schemas incl. IFC4X3) ---
    elements = safe_by_type(model, "IfcElement")
    spaces   = safe_by_type(model, "IfcSpace")
    storeys  = safe_by_type(model, "IfcBuildingStorey")
    systems  = safe_by_type(model, "IfcSystem")

    for ent in elements + spaces + storeys + systems:
        add_node(G, ent)

    # --- Edges: containment (spatial structure) ---
    for rel in safe_by_type(model, "IfcRelContainedInSpatialStructure"):
        container = getattr(rel, "RelatingStructure", None)
        if not container:
            continue
        c_id = add_node(G, container)
        for obj in (getattr(rel, "RelatedElements", None) or []):
            o_id = add_node(G, obj)
            G.add_edge(o_id, c_id, rel="CONTAINED_IN")

    # --- Edges: aggregates (part-of) ---
    for rel in safe_by_type(model, "IfcRelAggregates"):
        whole = getattr(rel, "RelatingObject", None)
        if not whole:
            continue
        w_id = add_node(G, whole)
        for part in (getattr(rel, "RelatedObjects", None) or []):
            p_id = add_node(G, part)
            G.add_edge(p_id, w_id, rel="PART_OF")

    # --- Edges: connects elements (topology) ---
    for rel in safe_by_type(model, "IfcRelConnectsElements"):
        a = getattr(rel, "RelatingElement", None)
        b = getattr(rel, "RelatedElement", None)
        if a and b:
            a_id = add_node(G, a)
            b_id = add_node(G, b)
            G.add_edge(a_id, b_id, rel="CONNECTS")

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
    idx_map = export_csv_nodes_edges(G, nodes_csv="nodes.csv", edges_csv="edges.csv")
    export_facts(G, facts_tsv="facts.tsv")

    print(f"✅ Wrote {out_json}")
    print(f"✅ Wrote nodes.csv / edges.csv (ML-ready indices)")
    print(f"✅ Wrote facts.tsv (Reasoning-ready triples)")
    print(f"   schema={data['schema']}")
    print(f"   nodes={data['num_nodes']}, edges={data['num_edges']}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_graph.py sample.ifc [out.json]")
        raise SystemExit(2)
    ifc_path = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) >= 3 else "graph.json"
    main(ifc_path, out)
