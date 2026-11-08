from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest
import trimesh
from ezdxf import bbox
from ezdxf.entities import Insert

from plancheck.export.dxf import DOOR_BLOCK, export_dxf
from plancheck.export.gltf import export_gltf, wall_mesh_mm
from plancheck.export.heights import Heights
from plancheck.model.types import BuildingModel
from tests.test_geometry import D1_GAP, D2_GAP, UNCUT_AREA, WINDOW_GAP

# ---------------------------------------------------------------- DXF


def test_dxf_units_and_layers(two_rooms: BuildingModel, tmp_path: Path) -> None:
    doc = ezdxf.readfile(export_dxf(two_rooms, tmp_path / "plan.dxf"))
    assert doc.header["$INSUNITS"] == 4  # millimetres
    assert doc.header["$MEASUREMENT"] == 1  # metric
    for layer in ("A-WALL", "A-DOOR", "A-GLAZ", "A-AREA", "A-AREA-IDEN"):
        assert layer in doc.layers
    assert not doc.audit().has_errors


def test_dxf_is_at_true_size(two_rooms: BuildingModel, tmp_path: Path) -> None:
    doc = ezdxf.readfile(export_dxf(two_rooms, tmp_path / "plan.dxf"))
    walls = doc.modelspace().query('LWPOLYLINE[layer=="A-WALL"]')
    extents = bbox.extents(walls)
    assert tuple(extents.extmin)[:2] == pytest.approx((-100.0, -100.0))
    assert tuple(extents.extmax)[:2] == pytest.approx((8100.0, 4100.0))


def test_dxf_doors_are_blocks_with_the_right_swing(
    two_rooms: BuildingModel, tmp_path: Path
) -> None:
    doc = ezdxf.readfile(export_dxf(two_rooms, tmp_path / "plan.dxf"))
    blockrefs = [e for e in doc.modelspace().query("INSERT") if isinstance(e, Insert)]
    inserts = {i.get_attrib_text("ID"): i for i in blockrefs}
    assert set(inserts) == {"D1", "D2"}
    assert all(i.dxf.name == DOOR_BLOCK for i in inserts.values())
    assert inserts["D1"].get_attrib_text("LEAF_WIDTH_MM") == "914.4"

    # The block's line is the open leaf: it must run from the hinge to the leaf tip.
    # D2 is the mirrored case (hinge at the far end of the opening).
    expected = {
        "D1": ((3950.0, 1517.8), (3035.6, 1517.8)),
        "D2": ((6482.2, 100.0), (6482.2, 1014.4)),
    }
    for door_id, (hinge, tip) in expected.items():
        leaf = next(e for e in inserts[door_id].virtual_entities() if e.dxftype() == "LINE")
        assert tuple(leaf.dxf.start)[:2] == pytest.approx(hinge)
        assert tuple(leaf.dxf.end)[:2] == pytest.approx(tip)


def test_dxf_rooms_and_windows(two_rooms: BuildingModel, tmp_path: Path) -> None:
    msp = ezdxf.readfile(export_dxf(two_rooms, tmp_path / "plan.dxf")).modelspace()
    assert len(msp.query('LWPOLYLINE[layer=="A-AREA"]')) == 2
    assert sorted(t.dxf.text for t in msp.query('TEXT[layer=="A-AREA-IDEN"]')) == [
        "OFFICE",
        "RECEPTION",
    ]
    assert len(msp.query('LINE[layer=="A-GLAZ"]')) == 3


# ---------------------------------------------------------------- glTF


def test_wall_mesh_volume_single_wall(one_wall: BuildingModel) -> None:
    mesh = wall_mesh_mm(one_wall, Heights(wall_mm=2700.0))
    assert mesh.is_watertight
    assert mesh.volume == pytest.approx(4200.0 * 200.0 * 2700.0)


def test_wall_mesh_volume_with_openings(two_rooms: BuildingModel) -> None:
    # Three bands: doors only are open below the sill, everything between sill and head,
    # nothing above the heads.
    heights = Heights(
        wall_mm=2700.0, door_head_mm=2100.0, window_sill_mm=900.0, window_head_mm=2100.0
    )
    expected = (
        (UNCUT_AREA - D1_GAP - D2_GAP) * 900.0
        + (UNCUT_AREA - D1_GAP - D2_GAP - WINDOW_GAP) * 1200.0
        + UNCUT_AREA * 600.0
    )
    assert wall_mesh_mm(two_rooms, heights).volume == pytest.approx(expected)


def test_gltf_is_in_metres_with_y_up(one_wall: BuildingModel, tmp_path: Path) -> None:
    path = export_gltf(one_wall, tmp_path / "wall.glb", Heights(wall_mm=2700.0))
    scene = trimesh.load_scene(path)
    (minx, miny, minz), (maxx, maxy, maxz) = scene.bounds
    assert (minx, maxx) == pytest.approx((-0.1, 4.1))  # length along x, in metres
    assert (miny, maxy) == pytest.approx((0.0, 2.7))  # height is on the y axis
    assert (minz, maxz) == pytest.approx((-0.1, 0.1))  # thickness


def test_gltf_keeps_plan_handedness(two_rooms: BuildingModel, tmp_path: Path) -> None:
    # Plan +y becomes glTF -z, so the building (y from -100 to 4100) sits at z <= 0.1.
    scene = trimesh.load_scene(export_gltf(two_rooms, tmp_path / "plan.glb"))
    (_, _, minz), (_, _, maxz) = scene.bounds
    assert (minz, maxz) == pytest.approx((-4.1, 0.1))
    mesh = scene.to_geometry()
    assert isinstance(mesh, trimesh.Trimesh)
    assert mesh.volume > 0  # a mirror would turn the mesh inside out
