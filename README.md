# BIM → Graph (Section 1 Prototype)

This repo implements **Section 1: BIM → Graph Representation** for the CEVIEAI research pipeline.

Goal: convert an IFC/BIM model into a **controlled typed graph** that is usable for:
- **ML / GNN** (graph learning)
- **Symbolic reasoning** (rule-based inference)

## What it does

### 1) IFC → Typed Graph
- Parses IFC models using IfcOpenShell.
- Builds a typed graph (NetworkX MultiDiGraph):
  - **Nodes:** building elements (IfcElement + subtypes), spaces (IfcSpace), storeys (IfcBuildingStorey), systems (IfcSystem)
  - **Edges:** containment + part-of + (optional) connections
- Applies a **controlled allowlist**:
  - Keeps only nodes relevant to construction reasoning
  - Drops spatial roots (IfcProject/IfcBuilding/IfcSite) + noisy metadata proxies (e.g., origin, geo-reference)

### 2) Dual-output exports
Single source of truth:
- `graph.json`

ML-ready:
- `nodes.csv` (node indices + node_type_id + geometry-lite bbox/centroid features)
- `edges.csv` (src/dst + edge_type_id + src_idx/dst_idx)

Reasoning-ready:
- `facts.tsv` as triples: `subject  predicate  object`
- Derived fact: `in_storey(x, storey)` from containment edges

### 3) Spatial derived relations (geometry-lite)
Infers additional spatial edges from bounding boxes:
- `ADJACENT`
- `ABOVE`
- `BELOW`

## Requirements
- Python 3.10+
- ifcopenshell
- networkx

Install:
```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install ifcopenshell networkx pandas
