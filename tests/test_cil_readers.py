#!/usr/bin/env python
# encoding: utf-8
"""Tests of the two CIL storm readers, ``StormTrack.read_ibtracs_processed`` and
``StormTrack.read_emanuel`` (see CIL_CHANGELOG.md).

They hold the readers to the contract upstream's readers keep (``test_met_objects.py``):
``t`` a ``datetime64[s]`` array, ``time_offset`` a ``datetime64``, string arrays for
``classification`` and ``event``, ``file_paths`` and ``file_format`` recorded, a new track
on every read, and missing radii left as NaN for ``write_geoclaw`` to fill. The inputs are
small files built in each test, in the layouts the two readers read: the lab's processed
IBTrACS (dimensions ``storm`` and ``time``) and its processed version of Kerry Emanuel's
tracks (dimensions ``storm``, ``ensemble`` and ``time``).
"""
from pathlib import Path
import sys
import warnings

import numpy as np
import pytest

import clawpack.geoclaw.met.storm as storm
from clawpack.geoclaw.met.track import StormTrack, missing_data_warning_str

# ``tests/`` has no package __init__; make the sibling helpers importable.
sys.path.insert(0, str(Path(__file__).parent))
from test_storm import _storm_input_path  # noqa: E402

N_TIME = 6
START = np.datetime64("2002-09-10T00:00:00", "ns")


def _write_ibtracs_processed(path, sids=("S0", "S1"), starts=None):
    """A processed-IBTrACS file with one storm per entry of *sids*.

    Each storm has 6 six-hourly times and makes landfall at index 3. In every storm, the
    storm radius at index 1 is missing from the measured values and filled from the
    estimated ones, and at index 2 it is missing from both, so it stays missing. The RMW
    is measured everywhere. The last time of each storm has no wind or pressure, as in
    the padded tracks of the real files.
    """
    xr = pytest.importorskip("xarray")
    n = len(sids)
    if starts is None:
        starts = [START + np.timedelta64(k, "D") for k in range(n)]
    hours = np.arange(N_TIME) * np.timedelta64(6, "h")
    times = np.array([np.datetime64(s, "ns") + hours for s in starts])
    nan = np.nan
    one = np.ones((n, 1))
    v_total = one * np.array([25.0, 30, 35, 40, 38, nan])
    pstore = one * np.array([1000.0, 995, 990, 985, 990, nan])
    rmstore = one * np.array([50.0, 45, 40, 35, 40, 45])
    rmstore_est = np.full((n, N_TIME), nan)
    roci = one * np.array([300.0, nan, nan, 350, 360, 370])
    roci_est = one * np.array([nan, 320.0, nan, nan, nan, nan])
    dist2land = one * np.array([300.0, 200, 50, -10, -20, -30])
    dims = ("storm", "time")
    ds = xr.Dataset(
        {"sid": ("storm", np.array(sids, dtype=object)),
         "name": ("storm", np.array([f"STORM{k}" for k in range(n)], dtype=object)),
         "datetime": (dims, times), "v_total": (dims, v_total), "pstore": (dims, pstore),
         "rmstore": (dims, rmstore), "rmstore_estimated": (dims, rmstore_est),
         "storm_radius": (dims, roci), "storm_radius_estimated": (dims, roci_est),
         "longstore": (dims, one * np.linspace(-80.0, -85.0, N_TIME)),
         "latstore": (dims, one * np.linspace(25.0, 30.0, N_TIME)),
         "dist2land": (dims, dist2land)},
        coords={"time": np.arange(N_TIME)})
    ds.to_netcdf(path)
    return path


def _write_emanuel(path):
    """A processed-Emanuel zarr store: 2 storms x 2 ensemble members x 8 times; storm 1
    ends with two times without a wind speed, which the reader drops."""
    xr = pytest.importorskip("xarray")
    pytest.importorskip("zarr")
    n_storm, n_ens, n_time = 2, 2, 8
    starts = [np.datetime64("2030-08-01T00:00"), np.datetime64("2031-09-10T06:00")]
    dt = np.array([[s + np.timedelta64(6 * k, "h") for k in range(n_time)] for s in starts])
    k = np.arange(n_time)[None, None, :]
    s = np.arange(n_storm)[:, None, None]
    e = np.arange(n_ens)[None, :, None]
    shape = (n_storm, n_ens, n_time)
    v_total = np.broadcast_to(30.0 + 3.0 * k + 5.0 * s + 1.0 * e, shape).copy()
    v_total[1, :, -2:] = np.nan
    dims3 = ("storm", "ensemble", "time")
    ds = xr.Dataset(
        {"datetime": (("storm", "time"), dt),
         "longstore": (dims3, np.broadcast_to(-60.0 - 1.5 * k - 10.0 * s, shape).copy()),
         "latstore": (dims3, np.broadcast_to(15.0 + 0.8 * k + 5.0 * s, shape).copy()),
         "v_total": (dims3, v_total),
         "rmstore": (dims3, np.broadcast_to(40.0 + 2.0 * k + 0.5 * e, shape).copy()),
         "pstore": (dims3, np.broadcast_to(990.0 - 3.0 * k - 5.0 * s, shape).copy()),
         "storm_radius": (dims3, np.broadcast_to(300.0 + 10.0 * k + 0.0 * e, shape).copy()),
         "sid": (("storm",), np.array(["fixture_storm_0", "fixture_storm_1"]))},
        coords={"storm": np.arange(n_storm), "ensemble": np.arange(n_ens),
                "time": np.arange(n_time)})
    ds.to_zarr(path, mode="w", zarr_format=2)
    return path


def _assert_track_contract(track, path, file_format):
    """What upstream's readers return (see test_met_objects.py)."""
    assert isinstance(track, StormTrack)
    assert track.file_format == file_format
    assert [str(p) for p in track.file_paths] == [str(path)]
    assert isinstance(track.t, np.ndarray)
    assert track.t.dtype == np.dtype("datetime64[s]")
    assert isinstance(track.t[0], np.datetime64)
    assert isinstance(track.time_offset, np.datetime64)
    assert track.classification.dtype.kind == "U"
    assert track.event.dtype.kind == "U"
    assert track.center.shape == (len(track.t), 2)
    for field in ("max_wind_speed", "central_pressure", "max_wind_radius", "storm_radius"):
        assert not (np.asarray(getattr(track, field)) < 0).any(), field


# ---------------------------------------------------------------------------
# read_ibtracs_processed
# ---------------------------------------------------------------------------

@pytest.mark.python
@pytest.mark.storm
def test_read_ibtracs_processed_contract(tmp_path):
    """Types and metadata as in upstream's readers; the missing radius stays NaN and warns."""
    path = _write_ibtracs_processed(tmp_path / "ibtracs_processed.nc")
    with pytest.warns(UserWarning) as record:
        track = StormTrack.read_ibtracs_processed(path, sid="S0")
    assert any(str(w.message) == missing_data_warning_str for w in record)

    _assert_track_contract(track, path, "ibtracs_processed")
    # the last time has no wind or pressure, so it is dropped
    assert len(track.t) == N_TIME - 1
    assert track.t[0] == np.datetime64("2002-09-10T00:00:00")
    # landfall at index 3, the last one, sets time_offset
    assert track.event[3] == "L"
    assert track.time_offset == track.t[3]
    # radius: measured at 0, estimated at 1, missing from both at 2 (km to m)
    assert track.storm_radius[0] == 300.0e3
    assert track.storm_radius[1] == 320.0e3
    assert np.isnan(track.storm_radius[2])


@pytest.mark.python
@pytest.mark.storm
def test_read_ibtracs_processed_missing_radius_reaches_the_fill(tmp_path):
    """write_geoclaw calls storm_radius_fill for the missing radius, and only for it."""
    path = _write_ibtracs_processed(tmp_path / "ibtracs_processed.nc")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s = storm.Storm(path=str(path), file_format="ibtracs_processed", sid="S0")

    calls = []

    def fill(t, this_storm):
        calls.append(t)
        return 7.0e5

    out = tmp_path / "S0.storm"
    s.write(str(out), file_format="geoclaw", storm_radius_fill=fill)
    assert len(calls) == 1 and calls[0] == s.t[2]

    lines = out.read_text().splitlines()
    assert int(lines[0]) == len(s.t)
    # the date line of a datetime64 time_offset
    assert lines[1] == np.datetime_as_string(s.time_offset, unit="s")
    rows = [line.split() for line in lines[3:] if line.strip()]
    assert float(rows[2][-1]) == 7.0e5
    assert float(rows[1][-1]) == 320.0e3


@pytest.mark.python
@pytest.mark.storm
def test_read_ibtracs_processed_duplicate_sid(tmp_path):
    """With several storms per SID, start_date picks the one that starts closest to it."""
    starts = [START, np.datetime64("2003-07-01T00:00:00", "ns")]
    path = _write_ibtracs_processed(tmp_path / "duplicate.nc", sids=("DUP", "DUP"),
                                    starts=starts)
    with pytest.raises(ValueError):
        StormTrack.read_ibtracs_processed(path, sid="DUP")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        later = StormTrack.read_ibtracs_processed(path, sid="DUP", start_date="2003-06-30")
        earlier = StormTrack.read_ibtracs_processed(path, sid="DUP",
                                                    start_date=np.datetime64("2002-09-11"))
    assert later.t[0] == np.datetime64("2003-07-01T00:00:00")
    assert earlier.t[0] == np.datetime64("2002-09-10T00:00:00")


@pytest.mark.python
@pytest.mark.storm
def test_read_ibtracs_processed_unknown_sid(tmp_path):
    path = _write_ibtracs_processed(tmp_path / "ibtracs_processed.nc")
    with pytest.raises(ValueError):
        StormTrack.read_ibtracs_processed(path, sid="NOT_THERE")


# ---------------------------------------------------------------------------
# read_emanuel
# ---------------------------------------------------------------------------

@pytest.mark.python
@pytest.mark.storm
def test_read_emanuel_contract(tmp_path):
    """Types and metadata as in upstream's readers; times without wind are dropped."""
    path = _write_emanuel(tmp_path / "emanuel.zarr")
    track = StormTrack.read_emanuel(path, storm_index=1, ensemble=0)
    _assert_track_contract(track, path, "emanuel")
    assert len(track.t) == 6
    assert track.t[0] == np.datetime64("2031-09-10T06:00:00")
    # time_offset is the last time of the track
    assert track.time_offset == track.t[-1]
    assert track.ID == "fixture_storm_1"
    assert track.storm_radius[0] == 300.0e3


@pytest.mark.python
@pytest.mark.storm
def test_read_emanuel_writes_geoclaw(tmp_path):
    """A GeoClaw file with one row per time, offsets in seconds from time_offset."""
    path = _write_emanuel(tmp_path / "emanuel.zarr")
    s = storm.Storm(path=str(path), file_format="emanuel", storm_index=0, ensemble=1)
    out = tmp_path / "emanuel.storm"
    s.write(str(out), file_format="geoclaw")
    lines = out.read_text().splitlines()
    assert int(lines[0]) == 8
    assert lines[1] == np.datetime_as_string(s.time_offset, unit="s")
    first = float(lines[3].split()[0])
    assert first == (s.t[0] - s.time_offset) / np.timedelta64(1, "s")


# ---------------------------------------------------------------------------
# Storm wrappers
# ---------------------------------------------------------------------------

@pytest.mark.python
@pytest.mark.storm
@pytest.mark.parametrize("file_format", ["ibtracs_processed", "emanuel"])
def test_cil_readers_start_from_a_new_track(tmp_path, file_format):
    """Reading into a Storm that held an ATCF track leaves nothing of it behind."""
    if file_format == "emanuel":
        path, kwargs = _write_emanuel(tmp_path / "emanuel.zarr"), {"storm_index": 0,
                                                                   "ensemble": 0}
    else:
        path, kwargs = _write_ibtracs_processed(tmp_path / "ib.nc"), {"sid": "S0"}
    s = storm.Storm(path=_storm_input_path("atcf"), file_format="atcf")
    assert s.track.basin_code is not None and s.track.wind_radii is not None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s.read(str(path), file_format=file_format, **kwargs)
    assert s.track.basin_code is None
    assert s.track.wind_radii is None
    assert s.file_format == file_format
    assert len(s.file_paths) == 1
    assert s.parametric.track is s.track
