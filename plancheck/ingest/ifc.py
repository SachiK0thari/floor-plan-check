"""Reading back from IFC. For now only the room graph, which the round-trip test needs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ifcopenshell

from plancheck.model.types import EXTERIOR, GraphEdge, RoomGraph


def read_room_graph(source: str | Path | ifcopenshell.file) -> RoomGraph:
    """Rebuild the room graph from an IFC file's spaces and space boundaries.

    A door, or an opening with nothing filling it, becomes an edge between the spaces it
    bounds. One that bounds a single space leads to the exterior.
    """
    f = source if isinstance(source, ifcopenshell.file) else ifcopenshell.open(str(source))
    nodes = [space.Name for space in f.by_type("IfcSpace")]
    passages: list[Any] = [
        *f.by_type("IfcDoor"),
        *(void for void in f.by_type("IfcOpeningElement") if not void.HasFillings),
    ]
    edges = []
    for passage in passages:
        rooms = sorted({rel.RelatingSpace.Name for rel in passage.ProvidesBoundaries})
        if not rooms or len(rooms) > 2:
            raise ValueError(f"{passage.Name}: bounds {len(rooms)} spaces, expected 1 or 2")
        other = rooms[1] if len(rooms) == 2 else EXTERIOR
        edges.append(GraphEdge(opening_id=passage.Name, a=rooms[0], b=other))
    return RoomGraph(nodes=[*nodes, EXTERIOR], edges=edges)
