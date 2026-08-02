# Changelog

All notable changes to this project are documented here. Every release adds an entry below and
is tagged in git; the version lives here and in the git tag (SKILL.md carries no version field).

## [0.2.0] - 2026-08-02

Remembers which courier a number belongs to — so the second lookup asks one company, not five.

### Added
- **Query history** (`~/.cache/parcel-kau-a/history.json`, mode `0600`). A successful lookup
  records `number → courier`; the next lookup for that number goes straight there. Failed lookups
  are never recorded. `--history` lists, `--forget` / `--forget-all` delete, `--no-record` skips
  writing for one query.
- **Delivered parcels are flagged, not auto-deleted.** When a recorded status looks complete the
  CLI prints the `--forget` command for that number. It does not prompt interactively — that
  would hang under an agent — so the calling agent is the one that asks.
- **Endpoints are configuration now** (`scripts/endpoints.py`, overridable per key via
  `~/.cache/parcel-kau-a/endpoints.json`). When a courier restructures its site, the fix is a
  config line rather than a code change. `--endpoints` shows what is in effect.

### Fixed
- **Network errors said "connection failed" for everything.** A wrong or stale URL returns 404,
  which is a configuration problem, not a network one — the old message sent you to check your
  network. Now classified: 404/410 point at the endpoint config, 429 is rate limiting, 5xx is the
  courier's server, and timeouts read differently from refused connections.
- **"Nothing is stored" appeared in five places**, not one. All rewritten to describe what the
  history file holds, where it lives, and how to delete it — including the note that macOS Time
  Machine excludes `~/Library/Caches` but **not** `~/.cache`, so the file is backed up.
- **The 17TRACK section sold the benefit without the cost.** Repeat lookups are free *because*
  the number stays registered in your 17TRACK account until you delete it — now stated next to
  the quota explanation and in Privacy, against the contrast that direct lookups keep nothing.
- A recorded courier that raises (site changed, missing Playwright, network) no longer fails
  silently before falling back to the other carriers — the reason is printed, and the fallback
  itself is announced rather than happening behind a "only this one" promise.
- Completion detection no longer trips on forward-looking phrases such as 預計送達.

- **Python 3.10/3.11 could not import the package at all.** A nested-quote f-string (valid only
  from 3.12 under PEP 701) in the 17TRACK adapter raised `SyntaxError` at import time, and the
  carrier registry imports it eagerly — so the whole CLI was broken on two of the three versions
  the README claims to support. Compilation is now verified against real 3.10 and 3.11
  interpreters, not just the development one.
- **Corrupt history meant "the file won't parse," but a single malformed entry crashed.** A
  non-dict value under one tracking number raised `AttributeError` from `record()` and
  `--history`, contradicting the module's own "always degrade to no history" guarantee. Filtering
  now happens once in `entries()`, so every caller inherits it.
- **Endpoint overrides were accepted without validation.** A URL missing `{number}` silently
  queried the same page for every parcel; a mistyped placeholder raised an uncaught `KeyError`.
  Both are now rejected with a reason, falling back to the default.
- An unavailable carrier (e.g. SPX with no Playwright) no longer aborts an auto-detected run —
  it is reported and the remaining carriers are still tried, which is what the fallback message
  promises. It stays fatal when that carrier was named explicitly.

### Notes
- 109 offline unit tests. Tests are isolated from the real history file by an autouse fixture —
  without it, running the suite writes into the developer's own `~/.cache` (which is exactly what
  happened before the fixture existed).

## [0.1.1] - 2026-08-02

Privacy disclosure fix — the README contradicted what auto-detection actually does.

### Fixed
- **Privacy section was wrong about auto-detection.** It claimed tracking numbers "go to the
  courier that owns them," but T-cat, Kerry TJ, e-can, PChome Express, and Fusheng all issue
  12-digit numeric numbers — so a bare number with no `--carrier` is tried against them in turn,
  and up to five companies see a number belonging to one of them. Both READMEs now state this
  plainly and point at `--carrier` as the one-company path.

### Added
- **Codex install path documented.** The skill has no Claude-specific dependencies — a `SKILL.md`
  plus a Python CLI — so the same folder drops into `~/.codex/skills/` and works as-is. Verified
  by running the installed copy under both homes.
- The CLI now says so **before it sends anything**: when no `--carrier` is given and the number
  matches more than one courier's format, it names every courier that will be queried and shows
  the `--carrier` values that would narrow it to one — printed ahead of the first request, so the
  choice is still yours to make. Suppressed under `--json` so machine-readable output stays
  parseable.

## [0.1.0] - 2026-08-02

First release. Six Taiwanese couriers with no API key, plus an opt-in 17TRACK bridge.

### Added
- **Carrier adapters**: 黑貓宅急便 (T-cat), 嘉里大榮 (Kerry TJ), 台灣宅配通 (e-can),
  網家速配 (PChome Express), 富昇物流/momo (Fusheng), 蝦皮店到店 (Shopee SPX) — each implementing `detect()` / `track()` against a shared
  `TrackResult` shape
- **T-cat full history**: the summary page carries only the latest scan, so the adapter follows
  through to `TraceDetail.aspx` for the complete timeline
- **CLI** (`scripts/track.py`): carrier auto-detection, `--carrier` to target one, `--json` for
  machine consumption
- **Playwright as an optional dependency**: SPX degrades with an actionable message when either
  the package or the chromium binary is missing; the other five couriers are unaffected
- **Per-carrier degradation**: a timeout, connection failure, or page-structure change at one
  site is reported and skipped in auto-detect mode instead of aborting the run
- **17TRACK bridge (opt-in, bring your own key)**: covers 中華郵政, 全家, 7-11 交貨便, and
  新竹物流, which cannot be read directly because their tracking forms carry a CAPTCHA. The
  aggregator's `detect()` always returns `False` so auto-detection can never spend the user's
  quota — only an explicit `--via-17track` reaches it. Key comes from
  `PARCEL_KAU_A_17TRACK_KEY`; unset means only this path is unavailable
- 60 offline unit tests pinned to captured fixtures; each fixture ships with a `*_notes.md`
  recording how it was captured

### Notes
- Found-path parsing is verified against real parcels for **T-cat** (including a 3-event history)
  and **Fusheng** (4-event history). Kerry TJ, e-can, and PChome Express use synthetic found
  fixtures built from real field names; SPX selectors come from a live page snapshot but have not
  been run against a real parcel. Those paths carry `UNVERIFIED` comments and will be
  re-calibrated as real tracking numbers become available.
- 中華郵政, 全家店到店, 7-ELEVEN 交貨便, and 新竹物流 cannot be read directly: all four gate their
  tracking form behind a CAPTCHA. No CAPTCHA solving is attempted — use the 17TRACK bridge above
  if you need them.
- 17TRACK quota, for what it's worth: only `register` deducts (1 per number); `gettrackinfo` and
  webhook pushes are free, so re-checking a number costs nothing. The adapter deliberately avoids
  `getRealTimeTrackInfo`, whose `Instant` cache level costs 10 per call.
