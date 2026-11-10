# CIL changes to GeoClaw

Base: clawpack/geoclaw `7e66181` (2026-10-24, merge of PR #767).
Previous CIL `main`: tag `pre-upstream-sync-2026-10-29` (`54c7e20`), the version in the Docker image
at the time of this update.

To find every CIL change, the old `main` was compared with `162d2c2f` (2025-06-12, merge of PR #655),
the upstream commit closest to it: they differ in 19 files, listed below. The earlier syncs were
squash-merged, so git's merge base with upstream (`acac99be`, 2024-03-28) would show 102 files, most of
them upstream code that arrived with those syncs.

## Ported

- `src/2d/shallow/bc2amr.f90`: from the old `main`; upstream has not changed this file
  since 2018. It defines the user-defined boundary condition (type 0), which upstream leaves as a stop
  ("A user defined boundary condition was not provided."): zero-order extrapolation, plus a boundary
  velocity error when the momentum in the non-ghost cells next to a boundary exceeds 5 m2/s
  (`mom_norm_thresh`; `hu` on the west and east boundaries, `hv` on the south and north). Each boundary
  has its own exit code, 2 (west), 3 (east), 4 (south) or 5 (north), to avoid return code 1, which other
  issues also raise; pyTC uses the code to grow the domain on that side. Two pieces of the old file are
  not ported; see Not ported below.
  CIL history of this change: commits `bb5fe080` (2019-05) to `332a9d5d` (2022-08), with PRs #20, #23
  and #24; they stay reachable through the tag above.
- `src/python/geoclaw/met/track.py` and `met/storm.py`: the loaders for our processed IBTrACS
  (`read_ibtracs_processed`) and our processed version of Kerry Emanuel's tracks (`read_emanuel`), from
  the old `src/python/geoclaw/surge/storm.py`. Upstream moved the storm code to `met/` in 2026, and
  `surge/storm.py` is now an alias. Like upstream's readers (`read_atcf`, `read_ibtracs`, ...), they are
  `StormTrack` classmethods in `met/track.py` that build a new track, record `file_paths` and
  `file_format`, and return it; `met/storm.py` has a `Storm` method for each that adopts the track, as
  for the other formats, and their two `_supported_formats` entries. The method bodies are the old
  ones, with three changes to match upstream's readers: each imports `xarray` itself; `t` is a
  `datetime64[s]` array and `time_offset` a `datetime64` (they were a list of `datetime` objects and a
  `datetime`), with `read_ibtracs_processed`'s `classification` an array instead of a list; and in
  `read_ibtracs_processed`, missing values stay `NaN` (they were `-1`, which upstream's `write_geoclaw`
  deprecates) and the missing-radius warning fires when any radius is missing, as in upstream's
  `read_ibtracs` (it fired only when all were). Docstrings and comments that misdescribed the code
  (`sid` optional, "netcdf" for a zarr store, `# drop NaT vals`, `# fill in RMW`) are corrected.
  One fix to the old body: when several storms share a SID, `read_ibtracs_processed` compared
  `start_date` with the shared integer `time` index instead of each storm's first `datetime`, so
  that branch could not work (no SID repeats in our processed IBTrACS); it now uses the first
  `datetime`, and a missing `start_date` raises `ValueError` instead of failing an `assert`.
  CIL history: `read_emanuel` since `115ff305` (2018-10), updated for the new track format in PR #20
  (2022-05); `read_ibtracs_processed` from PR #18 (2020-08).

## Not ported

Already upstream:
- `src/2d/shallow/bc2amr.f90`, the early return for patches with only ghost cells (CIL #24: "periodic
  BCs can create patches with only ghost cells in them. This is not supposed to happen but does."):
  amrclaw fixed the cause in `prefilp.f90`, which GeoClaw compiles, in clawpack/amrclaw PRs #287
  (2023-11) and #315 (2026-08). In a GUSTAV 2002 run with x periodic, the return was never taken with
  the `prefilp.f90` of amrclaw `06b9bbf` (2026-10), and 21,376 times with the one from before PR #287,
  with identical output (coastal-core, `geoclaw_runner/slurm/build_guardlog.sbatch`).
- `src/python/geoclaw/meson.build`: the fix to include `data_storms.py` (CIL #45). Upstream lists it for
  both `met/` and `surge/`.
- `src/python/geoclaw/surge/storm.py`, apart from the two readers: the `construct_fields` fix (`x` to
  `r`) and the `os` and `data_storms` imports are in upstream's `met/`. The rest is formatting and a
  top-level `import xarray` (upstream imports it inside each function).

Sync leftovers (upstream changes that the squash syncs copied only in part):
- `src/python/geoclaw/data.py`: `'willoughby'` in `storm_spec_not_implemented`. Upstream added it in
  `860ba23` (2024-06) and removed it in `7cb1bd8` (2025-03), when Willoughby was enabled.
- `src/python/geoclaw/fgout_tools.py`: `read_fgout_grids_data_pre511` held the body of the post-5.11
  reader, so it could not read pre-5.11 data. pyTC does not use this module.
- `examples/tsunami/chile2010_fgmax-fgout/make_fgout_animation_with_transect.py`: upstream renamed it to
  `make_fgout_animation_transect.py` in `b435c3b4` (2024-12); the old `main` had both.

Formatting only (same behavior):
- `src/python/geoclaw/surge/plot.py`: quotes, line breaks, import order and grouping, and an `f` prefix
  on a string with no fields.
- `src/2d/shallow/fgout_module.f90`, `src/2d/shallow/set_eta_init.f90`,
  `src/2d/shallow/surge/storm_module.f90`, `src/python/geoclaw/util.py`, `tests/test_storm.py`:
  whitespace or blank lines only.

Tests, CI and examples (not used by our runs):
- `.github/workflows/testing.yml`: CIL's version targets `main` and ClimateImpactLab/clawpack and drops
  flake8. GitHub Actions has never run on this fork; upstream's version only runs on `master`.
- `.travis.yml`: removed by CIL (2025) and by upstream (2026).
- `.gitignore`: CIL added `xgeoclaw_omp` and `.vscode`.
- `examples/storm-surge/isaac/test_isaac.py`: import order and a `pass`; upstream rewrote the test.
- `tests/old_dtopotools.py`: CIL fixed calls to numpy/pyplot in this test helper in 2019. Upstream's
  test only uses `set_geometry`, which does not make those calls.
- `tests/test_etopo1.py`: one commented-out line; upstream removed the file in 2026.

Unused:
- `src/2d/shallow/bc2amr.f90`: the imports of `nghost` and `sea_level`, left over from earlier versions
  of the boundary check (`sea_level` unused since `17e03663`, 2020-07, and `nghost` since `332a9d5d`,
  2022-08).
- `src/2d/shallow/fgmax_values_wind.f90` (2019, "make fgmax for wind"): a wind version of
  `fgmax_values` that no Makefile in GeoClaw or pyTC compiles.

## Updating from upstream

Rebase the CIL commits onto a newer clawpack/geoclaw commit and update the Base line. Avoid squash
merges: they hide the shared history from git, which is what made this rebuild necessary.
