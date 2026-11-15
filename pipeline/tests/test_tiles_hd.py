"""HiRISE tile pyramid: Leaflet EPSG4326 grid, no invented pixels, transparent no-data, determinism."""

import json
from pathlib import Path
import logging

import numpy as np
import pytest
from PIL import Image

from pipeline.preview_hd import bounds_around
from pipeline.tests.test_registration import CENTER, write
from pipeline.tiles_hd import build_pyramid, tile_bounds, tile_range


def test_grid_matches_leaflet_epsg4326():
    # Level 0 is two 180-degree tiles; tile (0, 0) is the western hemisphere.
    assert tile_bounds(0, 0, 0) == (-90.0, -180.0, 90.0, 0.0)
    box = (54.15, -147.91, 54.16, -147.89)
    x0, x1, y0, y1 = tile_range(box, 17)
    south, west, _, _ = tile_bounds(x0, y1, 17)
    _, _, north, east = tile_bounds(x1, y0, 17)
    assert south <= box[0] and west <= box[1] and north >= box[2] and east >= box[3]
    assert tile_bounds(x0, y0, 17)[3] > box[1]  # first column actually overlaps the box


@pytest.fixture(scope="module")
def two_tone(tmp_path_factory):
    """0.25 m source: west half 100, east half 200, a null (0) strip on the far west."""
    root = tmp_path_factory.mktemp("tiles")
    data = np.full((1200, 1200), 200, np.uint8)
    data[:, :600] = 100
    data[:, :150] = 0
    return root, write(root / "src.tif", data, 0.25)


def build(root, source, name, **kwargs):
    """Pyramid for a 250 m box around CENTER at zooms 15..17 into root/name."""
    return build_pyramid(source, bounds_around(*CENTER, 250, 250), root / name, min_zoom=15, max_zoom=17, **kwargs)


def test_pyramid_writes_tiles_without_dark_seams(two_tone, caplog):
    root, source = two_tone
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    meta = build(root, source, "a")
    out = root / "a"
    files = sorted(out.rglob("*.webp"))
    assert len(files) == sum(meta["tile_counts"].values()) and meta["tile_counts"]["17"] > meta["tile_counts"]["15"]
    assert json.loads((out / "tiles.json").read_text())["grid"] == "leaflet_epsg4326"
    saw_transparent = any((np.asarray(Image.open(p).convert("RGBA"))[..., 3] == 0).any() for p in files)
    assert saw_transparent  # null strip and outside-box areas are transparent, not black
    logged = [r for r in caplog.records if getattr(r, "event", "") == "hd_tiles_written"][0].fields
    assert logged["evidence"] == "nasa_derived" and {str(k): v for k, v in logged["tile_counts"].items()} == meta["tile_counts"]


def test_bright_half_stays_bright_at_every_zoom(two_tone):
    """Tile pixels over the 200-valued half stay at full brightness after averaging (no null blending)."""
    root, source = two_tone
    build(root, source, "b")
    box = bounds_around(*CENTER, 250, 250)
    for zoom in (15, 16, 17):
        x0, x1, y0, y1 = tile_range((box["south"], box["west"], box["north"], box["east"]), zoom)
        with Image.open(root / "b" / str(zoom) / str(x1) / f"{y0}.webp") as image:  # north-east tile: bright half
            rgba = np.asarray(image.convert("RGBA"))
        bright = rgba[..., 0][rgba[..., 3] > 0]
        assert bright.size and np.median(bright) >= 240


def test_pyramid_is_deterministic_and_refuses_busy_output(two_tone):
    root, source = two_tone
    build(root, source, "c1")
    build(root, source, "c2")
    for path in sorted((root / "c1").rglob("*.webp")):
        assert path.read_bytes() == (root / "c2" / path.relative_to(root / "c1")).read_bytes()
    with pytest.raises(FileExistsError):
        build(root, source, "c1")


def test_context_ring_reads_reduced_pixels_without_null_darkening(two_tone):
    """read_factor=4 (~1 m context) keeps geometry and brightness, and records itself in tiles.json."""
    root, source = two_tone
    meta = build_pyramid(source, bounds_around(*CENTER, 250, 250), root / "ctx", min_zoom=14, max_zoom=15,
                         read_factor=4, url_prefix="hirise-tiles/context", role="context")
    assert meta["read_factor"] == 4 and meta["role"] == "context" and meta["source_resolution_m"][0] == 1.0
    assert meta["url_template"] == "hirise-tiles/context/{z}/{x}/{y}.webp"
    box = bounds_around(*CENTER, 250, 250)
    x0, x1, y0, y1 = tile_range((box["south"], box["west"], box["north"], box["east"]), 15)
    with Image.open(root / "ctx" / "15" / str(x1) / f"{y0}.webp") as image:
        rgba = np.asarray(image.convert("RGBA"))
    assert np.median(rgba[..., 0][rgba[..., 3] > 0]) >= 240
    with pytest.raises(ValueError, match="read_factor"):
        build_pyramid(source, box, root / "bad", 14, 15, read_factor=3)


def test_bounds_outside_image_fail(two_tone, tmp_path):
    _, source = two_tone
    with pytest.raises(ValueError, match="outside"):
        build_pyramid(source, {"south": 10, "west": 10, "north": 10.01, "east": 10.01}, tmp_path / "x", 15, 17)


def test_refused_directory_rename_falls_back_to_copy(two_tone, monkeypatch, caplog):
    """Docker bind mounts on Windows refuse directory renames; the tiles must still be published, manifest last."""
    import pipeline.tiles_hd as tiles

    root, source = two_tone
    real_replace = tiles.os.replace

    def refuse_dirs(src, dst):
        """Refuse only directory renames, as the Windows bind mount does."""
        if Path(src).is_dir():
            raise PermissionError(13, "Permission denied")
        return real_replace(src, dst)

    monkeypatch.setattr(tiles.os, "replace", refuse_dirs)
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    meta = build(root, source, "copied")
    assert json.loads((root / "copied" / "tiles.json").read_text()) == meta
    assert len(list((root / "copied").rglob("*.webp"))) == sum(meta["tile_counts"].values())
    assert not [p for p in root.iterdir() if p.name.startswith(".staging-")]
    assert any(getattr(r, "event", "") == "hd_tiles_promoted_by_copy" for r in caplog.records)


def test_wide_strip_read_factor_16_and_invalid_factor(two_tone):
    """The whole-strip set reads 16x averages; non-power-of-two factors are refused before any output."""
    root, source = two_tone
    meta = build_pyramid(source, bounds_around(*CENTER, 250, 250), root / "wide", min_zoom=12, max_zoom=13,
                         read_factor=16, role="wide", url_prefix="hirise-tiles/wide")
    assert meta["role"] == "wide" and meta["read_factor"] == 16 and sum(meta["tile_counts"].values()) > 0
    with pytest.raises(ValueError, match="read_factor"):
        build_pyramid(source, bounds_around(*CENTER, 250, 250), root / "bad", read_factor=3)
    assert not (root / "bad").exists()
