# parcel-kau-a

> **A Taiwan tracking number in, a delivery timeline out. No API key, no account, no signup.**

English | [繁體中文](./README.zh-TW.md)

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](#prerequisites)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-skill-orange.svg)](https://claude.com/claude-code)
[![Codex](https://img.shields.io/badge/Codex-compatible-black.svg)](https://developers.openai.com/codex/skills)

An agent skill — open [SKILL.md standard](https://developers.openai.com/codex/skills), works in
[Claude Code](https://claude.com/claude-code) **and** [Codex](https://developers.openai.com/codex/skills) —
that reads the **public tracking pages** of six Taiwanese couriers and returns a normalized
delivery timeline. The name is Taiwanese Hokkien: *kàu--ah*（到啊）— "it's here."

## Why?

Taiwan has no free, self-serve tracking API. Every domestic courier either has no API at all, or
gates it behind a signed B2B contract — so checking a parcel means opening the right site,
finding the right form, and typing the number in by hand. Aggregators cover everything, but
charge for API access.

```text
Without parcel-kau-a                  With parcel-kau-a
────────────────────                  ─────────────────
which courier was it again?           paste the number
find that courier's tracking page     get the timeline
retype the number                     --carrier if you know it
repeat per parcel                     --json to pipe onward
```

## Features

- ✓ Six couriers, no credentials: 黑貓宅急便 (T-cat), 嘉里大榮 (Kerry TJ), 台灣宅配通 (e-can), 網家速配 (PChome Express), 富昇物流/momo (Fusheng), 蝦皮店到店 (Shopee SPX)
- ✓ Carrier auto-detection, with `--carrier` to skip straight to one
- ✓ Normalized output across couriers — same shape whichever site it came from
- ✓ `--json` for machine consumption; human-readable timeline by default
- ✓ T-cat returns the **full** history (the summary page shows only the latest scan; this follows through to the detail page)
- ✓ Playwright is optional: install it for SPX, skip it and the other five still work
- ✓ Network failures degrade per-carrier — a timeout at one site doesn't abort the run
- ✓ Offline test suite: parsers are pinned to captured fixtures, no network needed to run tests
- ✓ Optional 17TRACK bridge for the four CAPTCHA-blocked couriers — **your** API key, never called unless you ask for it
- ✓ Remembers which courier a number belongs to, so repeat lookups go to **one** company instead
  of five — a local record you can list and delete (`--history`, `--forget`)
- ✓ `--pending` answers "which of my parcels are still on the way?" from that local record, with
  no network request at all — a snapshot of what each parcel last reported, and how long ago
- ✓ `--refresh-pending` answers "what's the status of everything still pending, *right now*?" —
  it live-queries each unresolved number in turn, updates the local snapshot, and prints a digest
  grouped by outcome (newly delivered / changed / unchanged / skipped / failed)
- ✓ No telemetry, no analytics, nothing leaves your machine except the courier request itself

## Install

```bash
# Claude Code (user-level)
cp -r parcel-kau-a ~/.claude/skills/parcel-kau-a
pip install -r ~/.claude/skills/parcel-kau-a/requirements.txt

# Codex — same folder, different home (open SKILL.md standard, no changes needed)
cp -r parcel-kau-a ~/.codex/skills/parcel-kau-a

# optional — only needed for 蝦皮店到店 (SPX)
pip install playwright && playwright install chromium
```

Nothing in the skill is Claude-specific: it is a `SKILL.md` plus a Python CLI, so the same folder
works in either host.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python | 3.10+ |
| `requests`, `beautifulsoup4` | required (`requirements.txt`) |
| `playwright` + chromium | **optional** — SPX only |

## Usage

```bash
python3 scripts/track.py 900000000001                    # auto-detect
python3 scripts/track.py 900000000001 --carrier tcat     # go straight to one
python3 scripts/track.py TW254414081298F --carrier spx   # Shopee SPX
python3 scripts/track.py 900000000001 --json             # machine-readable

python3 scripts/track.py --pending                       # what is still on the way
python3 scripts/track.py --refresh-pending               # live-query everything still pending
python3 scripts/track.py --history                       # what has been remembered
python3 scripts/track.py --forget 900000000001           # forget one number
python3 scripts/track.py --forget-all                    # forget everything
python3 scripts/track.py --endpoints                     # show the URLs in effect
```

```text
黑貓宅急便　900000000001

2026/01/15 18:30　配送完成　示範門市
2026/01/15 09:12　配送中

來源：https://www.t-cat.com.tw/Inquire/TraceDetail.aspx?BillID=900000000001
```

`--pending` answers a different question — not "where is this one?" but "how many are still
coming?":

```text
未結案包裹（2 筆）

900000000001　黑貓宅急便　配送中　2026/08/06 14:20　（1 天沒更新）
900000000002　台灣宅配通　已到轉運站　2026/7/20 09:05　（18 天沒更新）
```

That list comes entirely from the local record and **makes no request**, so it shows what each
parcel reported the last time you looked it up; `（N 天沒更新）` is how long ago that event was.
To find out where a parcel is right now, look its number up again — or refresh all of them at once:

```text
未結案包裹更新（2 筆，依最後事件時間新→舊逐一查詢）

新結案 1　無變化 1

── 新結案（1）──
900000000001　黑貓宅急便　順利送達　2026/08/08 11:02

── 無變化（1）──
900000000002　台灣宅配通　已到轉運站　2026/7/20 09:05
```

`--refresh-pending` walks the same local list `--pending` reads, but instead of printing the
stored snapshot it live-queries each number — one at a time, through the same per-carrier path a
single lookup uses — and sorts the results into a digest: 新結案 (delivered since the last check),
有新進度 (the latest event changed but the parcel isn't done), 無變化, 已略過, and 查詢失敗. A
successful refresh overwrites that number's stored snapshot, the same way an ordinary lookup does
(`--no-record` still suppresses that). One courier failing doesn't stop the rest of the batch —
each number's own outcome, including its error, is what you see in its row. If a pending entry
names a courier that needs the [17TRACK bridge](#17track-optional) and no key is configured, it's
reported as 已略過 with the reason rather than as a failure — and, since it isn't 17TRACK's call to
make, nothing is sent to them without a key present.

Both commands answer different questions, deliberately: `--pending` is instant and free because it
never leaves your machine; `--refresh-pending` costs one request per pending parcel and takes
proportionally longer, because it's asking each courier again.

In Claude Code you don't call the script yourself — say *"查一下這個包裹 900000000001"*,
*"還有哪些包裹在路上"*, or *"幫我更新一下未結案包裹"* and the skill handles it.

## Coverage

| Courier | `--carrier` | Method | Retention |
|---|---|---|---|
| 黑貓宅急便 T-cat | `tcat` | HTTP (ASP.NET postback → detail page) | 3 months |
| 嘉里大榮 Kerry TJ | `kerrytj` | HTTP JSON API | — |
| 台灣宅配通 e-can | `ecan` | HTTP (Big5-encoded classic ASP) | 2 months |
| 網家速配 PChome Express | `pchome` | HTTP (server-rendered page, number in the URL path) | — |
| 富昇物流 Fusheng (momo) | `fusheng` | HTTP (server-rendered page, number in the query string) | — |
| 蝦皮店到店 SPX | `spx` | Playwright (headless) | — |

**Not readable directly, and why:** 中華郵政, 全家店到店, 7-ELEVEN 交貨便, and 新竹物流 all put a
CAPTCHA on their tracking form. This skill does not attempt CAPTCHA solving. They are reachable
through the optional [17TRACK bridge](#17track-optional) below.

## 17TRACK (optional)

17TRACK is a commercial aggregator that covers all of the above. The bridge is **opt-in and
brings your own key** — this project ships no key, proxies nothing, and never calls the service
unless you explicitly ask:

```bash
export PARCEL_KAU_A_17TRACK_KEY=...        # from https://api.17track.net (200 free lookups)
python3 scripts/track.py 83546610320956 --via-17track
python3 scripts/track.py 83546610320956 --via-17track --carrier chunghwa-post
```

`--carrier` values in this mode: `chunghwa-post`, `famiport`, `seven-eleven`, `hct` (plus the
five already covered directly, if you'd rather route them through 17TRACK).

**What it costs you — and what it keeps.** 17TRACK charges per *registered* number: `register`
deducts one quota, while `gettrackinfo` and webhook pushes deduct nothing — so re-checking a
number you've already looked up is free, and the free allowance (200 one-time, for accounts
created after 2026-01-07) means 200 distinct parcels. The reason repeat lookups are free is that
the number **stays registered in your 17TRACK account** and they keep tracking it for you. That
is the real difference from the direct six: a direct lookup asks a question and leaves, while a
17TRACK lookup files the number with a third party until you delete it. Past that, 17TRACK sells prepaid annual packs only, starting at
US$119 for 5,000 quota, expiring after 12 months; there is no pay-as-you-go tier. This adapter
deliberately does not call `getRealTimeTrackInfo`, whose `Instant` cache level costs 10 quota per
call.

Design constraints, deliberately:

- **Never automatic.** The aggregator's `detect()` always returns `False`, so auto-detection can
  never spend your quota. Only `--via-17track` reaches it.
- **Degrades in isolation.** No key set means only this path is unavailable; the five direct
  couriers are untouched.
- **Third-party disclosure.** Using it sends your tracking number to 17TRACK, a third party with
  its own terms and privacy policy — unlike the direct couriers, where the number only reaches
  the company that issued it.

### Walkthrough: tracking a 全家 or 7-ELEVEN parcel

全家店到店 and 7-ELEVEN 交貨便 are two of the four couriers this project cannot read directly —
their tracking forms sit behind a CAPTCHA (see [Coverage](#coverage)) — so 17TRACK is the only
path this skill has to either of them.

1. **Get a key.** Sign up at [api.17track.net](https://api.17track.net); the free tier is 200
   one-time lookups (for accounts created after 2026-01-07). The key lives somewhere in their own
   dashboard under an API/token section — 17TRACK's own UI, not something this project controls,
   so the exact menu wording may drift.
2. **Export it once per shell session** (or put it in your shell profile):
   ```bash
   export PARCEL_KAU_A_17TRACK_KEY=...
   ```
3. **Query the parcel**, naming which of the two it is:
   ```bash
   python3 scripts/track.py <你的單號> --via-17track --carrier famiport       # 全家店到店
   python3 scripts/track.py <你的單號> --via-17track --carrier seven-eleven   # 7-ELEVEN 交貨便
   ```
   Omitting `--carrier` lets 17TRACK guess the courier itself instead of you naming it; naming it
   is one fewer thing that can go wrong.

**Honesty about what "works" means here.** The 17TRACK adapter's parser (`parse_response` in
`scripts/carriers/seventeentrack.py`) is tested against 17TRACK's *documented* API schema —
`tests/test_seventeentrack.py` builds payloads by hand from their published field names
(`time_iso`/`time_raw`, `description`, `providers[].events[]`, and so on), the same schema
regardless of which underlying courier is being tracked. What that verifies is that this
project's code handles the shape 17TRACK says it returns. It does **not** verify that a real
全家 or 7-11 shipment actually comes back in that shape — nobody has run a real parcel from either
courier through this path yet and captured what 17TRACK sent back. If you have one in transit and
are willing to help close that gap, `scripts/capture_fixture.py` (see [Develop](#develop)) can
capture and de-identify a real response for exactly this purpose — that is what it exists for.

The output *shape* below is real — every `--via-17track` query renders through the same code path
as a direct lookup, and that path is exercised by tests. The *content* is not: it is illustrative,
built from 17TRACK's documented event fields, not a real 全家/7-11 response.

```text
⚠️ 這是根據官方文件畫出來的欄位形狀示意，不是真實包裹的擷取結果——目前沒有人拿真實
全家或 7-11 包裹跑過這條路徑，確認官方文件講的形狀是否真的照著回。

17TRACK　<你的單號>

2026/01/15 18:30　順利投遞　（示意：description 欄位）
2026/01/15 09:12　已收寄

來源：https://t.17track.net/
```

## Auto-detection, honestly

T-cat, Kerry TJ, e-can, PChome Express, and Fusheng all issue **12-digit numeric** tracking
numbers. They are not distinguishable by format. Without `--carrier`, the skill queries them in
sequence and stops at the first hit — worst case, five requests. SPX numbers start with `TW` and *are* identifiable.

**If you know the courier, pass `--carrier`.** It's one request instead of five.

## How it works

Each courier gets an adapter implementing `detect(number)` and `track(number)`; the CLI picks
adapters, runs them in order, and normalizes whatever comes back into the same `TrackResult`
shape. The couriers are not similar under the hood:

- **T-cat** is an ASP.NET WebForm — fetch `__VIEWSTATE`/`__EVENTVALIDATION` first, post them back,
  then follow through to `TraceDetail.aspx` for the full scan history.
- **Kerry TJ** looks like a Vue app but sits on a clean JSON endpoint underneath.
- **e-can** is classic ASP served in **Big5**; both the form encoding and the response decoding
  have to say so explicitly.
- **PChome Express** and **Fusheng** are the simplest of the six: a server-rendered page with the number in the
  URL path, no form round-trip at all.
- **SPX** signs its tracking API with a token computed in browser JavaScript. Rather than reverse
  that signature (which would break on their next deploy), the adapter drives a headless browser
  and lets their own page produce it.

## Privacy

- **One thing is stored, and it is there to reduce disclosure.** A successful lookup records
  `number → courier` (plus its latest status and timestamps) in `~/.cache/parcel-kau-a/history.json`,
  mode `0600`. The point is the next lookup: with a record, the number goes to **one** courier
  instead of being tried against five. Failed lookups are never recorded, `--no-record` skips
  writing, `--history` lists everything, `--pending` narrows that to the parcels still in transit
  (read-only, no request), `--refresh-pending` live-queries that same narrowed list and rewrites
  each entry's snapshot with what comes back, and `--forget` / `--forget-all` delete it.
- **`--refresh-pending` never re-broadcasts a number.** Every pending entry already has a known
  courier — that is what got it into the record — so refreshing it sends the number back to that
  one company again, the same disclosure profile as passing `--carrier` explicitly. It does not
  redo auto-detection against the other four.
- **Where that file lives, precisely.** On macOS, Time Machine excludes `~/Library/Caches` but
  **not** `~/.cache` — so this file is included in backups. If a number shouldn't persist anywhere,
  use `--no-record`, or `--forget` it once the parcel arrives (the CLI points this out for you when
  a parcel looks delivered).
- **No telemetry.** No analytics, no logs, no phoning home. Each query is a live request whose
  result is printed.
- **Auto-detection sends the number to couriers that don't own it.** T-cat, Kerry TJ, e-can,
  PChome Express, and Fusheng all issue 12-digit numeric tracking numbers, so a bare number with
  no `--carrier` is tried against them in turn until one reports a hit — up to five companies
  see a number that belongs to one of them. Each request is the same one your browser would make
  on their public form, and none of them learns who you are, but the number itself is disclosed
  more widely than you might assume. **Passing `--carrier` sends it to exactly one company.** The CLI names the couriers it is about to query before the first request goes out, so this is visible at the point of use, not just here.
- In Claude Code, the returned timeline enters your own Claude session like any other command
  output.
- **A tracking number is not anonymous.** On most of these sites it identifies a parcel, and
  the timeline can include a store or depot name. Treat it as you would a receipt.

## Limitations

- This reads **public web pages**. It is not an official API, is not authorized by any of the
  couriers, and will break when they change their markup. Errors say so explicitly rather than
  returning empty results.
- Intended for **personal, low-volume** lookups. There is no retry loop and no concurrency;
  requests time out at 10 seconds and fail fast. Do not point this at a queue of numbers.
  `--refresh-pending` is no exception — it queries the pending list sequentially, one request at a
  time, and simply takes longer the more parcels are still open.
- **Kerry TJ's own form asks you to accept their legal/privacy notice before searching.** This
  tool calls the underlying endpoint directly and therefore does not surface that checkbox —
  by using it you take on responsibility for complying with their terms.
- **SPX**: only the public search box on `spx.tw/` is used; paths disallowed in their robots.txt
  are not visited.
- Each courier's own retention limit applies (see [Coverage](#coverage)) — older parcels return
  "not found" from the site itself, not from this skill.

## When a courier changes its site

Scrapers break; that is the deal. Every URL this skill uses lives in `scripts/endpoints.py`, and
each one can be overridden per key without touching code — write only the keys you want to change
into `~/.cache/parcel-kau-a/endpoints.json`:

```json
{ "pchome": { "query": "https://www.gopchome.com.tw/whatever/{number}" } }
```

`--endpoints` prints what is currently in effect, along with the override file's path. A broken
override file falls back to the defaults with a warning rather than taking the tool down.

**This covers a URL moving, not a site being rebuilt.** If a courier changes its HTML structure,
its API's response shape, its form fields, or its CSS classes, the parser has to change with it —
configuration can't express that. What you get instead is an honest failure: the adapter raises
"頁面結構已變，請回報 issue" rather than returning an empty result that looks like "not found".

Error messages distinguish the cases so you know where to look: a `404` says the URL is likely
stale and points at the config, a `5xx` says the courier's server is having trouble, and timeouts
read differently from refused connections.

## Platform notes

Developed and used on macOS; Linux is covered by CI. Two things differ elsewhere and are worth
stating rather than glossing over:

- **File permissions.** The history file is written with mode `0600`. POSIX honours that. Windows
  ignores POSIX modes, so the file inherits the ACL of your profile directory instead — on a real
  Windows install this was observed to include `CodexSandboxUsers:(RX)`, i.e. readable by more
  than just you. **Treat `0600` as a POSIX-only guarantee.** If the contents matter, use
  `--no-record`, or `--forget` once a parcel arrives.
- **Where it lives.** `~/.cache/parcel-kau-a/` follows the XDG convention. On Windows that resolves
  to `C:\Users\<you>\.cache\parcel-kau-a\`, which works but is not the platform's own
  convention (`%LOCALAPPDATA%`). Set `PARCEL_KAU_A_HOME` to put it wherever you prefer.
- **Invoking it.** Use `python` on Windows, not `python3` — the latter is a Microsoft Store alias
  that exits 9009 with "Python was not found".
- **Installing it.** `requirements.txt` is deliberately ASCII-only: pip reads it with the system
  locale encoding, and non-ASCII comments break installation on a Traditional Chinese Windows
  (cp950).

CI runs the suite on Linux across Python 3.10–3.13 and on Windows across 3.10 and 3.13.

## Develop

```bash
pip install -r requirements.txt pytest
python3 -m pytest tests -q          # offline; no network, no fixtures downloaded
```

Parsers are tested against captured fixtures in `tests/fixtures/`, each with a `*_notes.md`
recording how the request was made and what the response looked like on the capture date.

### Capturing real fixtures (contributors)

Kerry TJ, e-can, and PChome Express's found-path parsers currently run against *synthetic*
fixtures — real field names and structure, but values nobody has actually seen a courier return
(see [Status](#status)). If you have a real, in-transit tracking number for one of these and want
to help close that gap:

```bash
python3 scripts/capture_fixture.py <真實單號> --carrier kerrytj
python3 scripts/capture_fixture.py <真實單號> --carrier ecan
python3 scripts/capture_fixture.py <真實單號> --carrier pchome
python3 scripts/capture_fixture.py <真實單號> --carrier famiport --via-17track   # needs a 17TRACK key
```

This makes one live request through the same adapter code a normal lookup uses, then writes two
files into `tests/fixtures/`: the de-identified raw response (`<carrier>_found_captured.<ext>`)
and a notes skeleton (`<carrier>_found_captured_notes.md`) with a TODO checklist for folding it
into the real fixture set. It also prints what the current parser extracted from that response, so
you can eyeball whether the fields line up with what the page actually showed.

**⚠️ De-identification is a first pass, not a guarantee.** Before writing the fixture, the tool
replaces the real tracking number and scrubs phone numbers, ID-number-shaped strings, email
addresses, and common Taiwan address patterns with conservative regexes. It does **not** attempt
to detect Chinese personal names — a 2-4 character Chinese name has no reliable regex signature
that would not also match ordinary status text, so that check is left to you entirely. **Open the
captured file and read it before running `git add` on it.** SPX is not supported here: it scrapes
a rendered page via Playwright rather than returning a single HTTP response this tool can
intercept, so calibrating it still means opening browser devtools by hand.

## Status

v0.4.0 ([CHANGELOG](./CHANGELOG.md)) — 199 offline unit tests. Verification status differs per
courier and is worth stating precisely:

| Courier | not-found path | found path |
|---|---|---|
| 黑貓 T-cat | verified against live response | **verified** — real parcel, 2026-08-02 |
| 嘉里大榮 Kerry TJ | verified against live response | synthetic fixture (real field names, values unverified) |
| 台灣宅配通 e-can | verified against live response | synthetic fixture (real headers, row values unverified) |
| 網家速配 PChome | verified against live response | synthetic fixture (real class structure, values unverified) |
| 富昇物流 Fusheng | verified against live response | **verified** — real parcel, 4-event history, 2026-08-02 |
| 蝦皮 SPX | — | DOM selectors from a live page snapshot; not yet run against a real parcel |

Verified on macOS 26.5.1 (Apple M4 Pro) / Python 3.12.13. Found-path parsing for the three
couriers above marked *synthetic* will be re-calibrated as real tracking numbers become
available; until then those code paths carry `UNVERIFIED` comments.

## Roadmap

17TRACK integration is the obvious next step — it is the only aggregator covering all eight of the
Taiwanese couriers surveyed, including the four blocked by CAPTCHA here. It requires an API key and,
past the free tier, payment, so it is deliberately not part of v0.1.0.

## License

MIT — see [LICENSE](LICENSE).
