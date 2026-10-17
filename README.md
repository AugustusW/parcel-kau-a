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
- ✓ Never guesses the courier: when a number's format fits several couriers, nothing is sent until
  you pick one (`--carrier`) or agree to try them all (`--auto`)
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
  no network request at all. Every snapshot is labelled as one and shows both the courier's last
  event time and when you last checked, so a week-old status is never mistaken for today's
- ✓ Name your parcels (`--label`, `--find`): look one up as "earphones" instead of by its number.
  When several names match, all of them are listed; the tool never picks one for you
- ✓ `--refresh-pending` answers "what's the status of everything still pending, *right now*?" —
  it live-queries each unresolved number in turn, updates the local snapshot, and prints a digest
  grouped by outcome (newly delivered / changed / unchanged / skipped / failed). Narrow it with
  `--match`, `--carrier`, `--limit`, or preview it with `--dry-run`
- ✓ Lists show only the last four digits of each number unless you ask (`--full-numbers`)
- ✓ No telemetry, no analytics, nothing leaves your machine except the courier request itself

## Install

```bash
# Claude Code (user-level)
git clone https://github.com/AugustusW/parcel-kau-a.git ~/.claude/skills/parcel-kau-a
pip install -r ~/.claude/skills/parcel-kau-a/requirements.txt

# Codex — same folder, different home (open SKILL.md standard, no changes needed)
git clone https://github.com/AugustusW/parcel-kau-a.git ~/.codex/skills/parcel-kau-a

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
python3 scripts/track.py 900000000001 --carrier tcat     # query one courier
python3 scripts/track.py TW254414081298F                 # SPX numbers identify themselves
python3 scripts/track.py 900000000001                    # ambiguous: lists candidates, sends nothing (exit 8)
python3 scripts/track.py 900000000001 --auto             # agree to try each matching courier in turn
python3 scripts/track.py 900000000001 --carrier tcat --json      # machine-readable

python3 scripts/track.py 900000000001 --carrier tcat --label "momo earphones"   # name it
python3 scripts/track.py --find earphones                # find by name (no request)
python3 scripts/track.py --rename 900000000001 "work earphones"
python3 scripts/track.py --clear-label 900000000001

python3 scripts/track.py --pending                       # what is still on the way (no request)
python3 scripts/track.py --refresh-pending               # live-query everything still pending
python3 scripts/track.py --refresh-pending --match earphones --dry-run   # preview a narrower refresh
python3 scripts/track.py --history                       # what has been remembered
python3 scripts/track.py --forget 900000000001           # forget one number and its name
python3 scripts/track.py --forget-all                    # forget everything
python3 scripts/track.py --endpoints                     # show the URLs in effect
```

```text
黑貓宅急便　900000000001

2026/01/15 18:30　配送完成　示範門市
2026/01/15 09:12　配送中

來源：https://www.t-cat.com.tw/Inquire/TraceDetail.aspx?BillID=900000000001
查詢時間：2026/01/15 19:02（剛剛即時查詢）
```

A bare 12-digit number fits five couriers, so on its own it is not sent anywhere:

```text
單號格式符合多家物流商，尚未送出任何查詢。
可能的物流商：
  tcat　黑貓宅急便
  kerrytj　嘉里大榮
  ecan　台灣宅配通
  pchome　網家速配
  fusheng　富昇物流（momo）
知道是哪一家：加 --carrier <code> 只送那一家
同意依序詢問以上全部：加 --auto（單號會被送到其中多家，命中即停）
```

`--pending` answers a different question — not "where is this one?" but "how many are still
coming?":

```text
未結案包裹（2 筆，本機歷史快照；未連線）

momo 耳機保護殼　黑貓宅急便　配送中
單號末四碼：0001
物流事件：2026/10/16 14:20（1 天沒有新進度）
上次查詢：2026/10/16 15:03（約 1 天前）

momo 藍牙耳機　台灣宅配通　已到轉運站
單號末四碼：0002
物流事件：2026/10/09 09:05（8 天沒有新進度）
上次查詢：2026/10/09 09:08（約 8 天前，資料可能過期）

需要目前貨態時，請使用 --refresh-pending 或指定其中一筆重新查詢。
```

That list comes entirely from the local record and **makes no request**. Each entry carries two
different times: 物流事件 is when the courier last scanned the parcel, and 上次查詢 is when this tool
last asked. A snapshot checked more than 7 days ago is marked 資料可能過期 (possibly out of date).
To find out where a parcel is right now, look its number up again — or refresh all of them at once:

```text
未結案包裹更新完成（2 筆，剛剛即時查詢）

新結案 1　有新進度 1

── 新結案 ──
momo 耳機保護殼　黑貓宅急便　順利送達
單號末四碼：0001
物流事件：2026/10/17 11:02
查詢時間：2026/10/17 11:05

── 有新進度 ──
momo 藍牙耳機　台灣宅配通　已到轉運站 → 配送中
單號末四碼：0002
物流事件：2026/10/17 10:42
查詢時間：2026/10/17 11:05
```

`--refresh-pending` walks the same local list `--pending` reads, but instead of printing the
stored snapshot it live-queries each number — one at a time, through the same per-carrier path a
single lookup uses — and sorts the results into a digest: 新結案 (delivered since the last check),
有新進度 (shown as before → after), 無變化, 已略過, and 查詢失敗 (which says which earlier snapshot is
still kept). A successful refresh overwrites that number's stored snapshot, the same way an
ordinary lookup does (`--no-record` still suppresses that). One courier failing doesn't stop the
rest of the batch; if any parcel fails, the command exits with `6`.

To refresh only some parcels: `--match <name>` (several matches are listed and nothing is sent
unless you add `--all-matches`), `--carrier <code>`, `--limit N` (the N with the most recent
courier events), and `--dry-run` to see what would be queried without sending or writing anything.

`--refresh-pending` never calls 17TRACK, even when a key is set: a key in your environment is not
consent for a whole batch. Entries that would need it are reported as 已略過 with the command to
query them one at a time.

In Claude Code you don't call the script yourself — say *"查一下這個黑貓包裹 900000000001"*,
*"還有哪些包裹在路上"*, or *"幫我更新一下未結案包裹"* and the skill handles it.

### Naming parcels

A name is attached to a number when you look it up with `--label`, and only if the courier found
it (nothing is saved for a not-found result). After that, `--find` looks parcels up by full
number, exact name, or part of a name, in that order of preference. `--find` and the name commands
never contact a courier.

```text
找到 2 個名稱相近的包裹（本機歷史快照；未連線）

1. momo 耳機保護殼　黑貓宅急便　配送中
單號末四碼：0001
...
2. momo 藍牙耳機　台灣宅配通　已到轉運站
單號末四碼：0002
...
這些不是即時貨態。請指定編號或完整名稱；若要全部更新，請明確說「全部更新」。
```

When more than one parcel matches, all of them are listed and the command exits with `8`: choosing
between them is the user's call. Labelling a number that already has a name replaces the old one
and says so. Names may contain letters, digits, punctuation, symbols, emoji, and spaces, up to 100
characters; control characters, bidirectional-text controls, and other invisible formatting
characters are rejected, because a name is printed to your terminal and into an agent's context.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (a not-found result is a success) |
| 2 | Bad arguments, courier cannot be determined, invalid name |
| 3 | A dependency is missing (e.g. Playwright for SPX) |
| 4 | The courier's page structure changed |
| 5 | Network error, timeout, or server error |
| 6 | `--refresh-pending` finished, but at least one parcel failed or could not be saved |
| 7 | `--label`, `--rename`, `--clear-label`, `--forget`, or `--forget-all` could not fully save or delete (including: another process is writing). A plain lookup whose record could not be saved still exits 0 with a note on stderr, because the record is only a convenience |
| 8 | A choice is needed (which courier, or which of several matching names); **nothing was sent** |

### JSON

`track.py <number> --json` prints the same result object as earlier versions. Every other command
with `--json`, and every error from those commands, prints one envelope:

```json
{"schema_version": 1, "operation": "pending", "snapshot": true, "live_query": false, "items": [
  {"number": "900000000001", "carrier": "tcat", "label": "momo 耳機保護殼",
   "latest_status": "配送中", "event_time": "2026/10/16 14:20",
   "event_at": "2026-10-16T14:20:00+08:00", "event_timezone": "+08:00",
   "checked_at": "2026-10-16T15:03:00+08:00", "checked_age_seconds": 86400,
   "freshness": "recent", "source_type": "official-http",
   "past_retention": false, "looks_complete": false}]}
```

`operation` is one of `history`, `pending`, `find`, `refresh_pending`, `detect` (courier
selection), `rename`, `clear_label`, `forget`, `forget_all`, or `error`. `freshness` is `fresh`
(under 24 h), `recent` (under 7 days), `stale`, or `unknown`. `event_at` is filled in only when the
courier's time zone is known. `refresh_pending` adds `attempted_at`, `counts`, `partial_failure`,
and per-parcel `outcomes` with `query_succeeded` and `snapshot_saved` reported separately. Errors
carry `"ok": false` and `exit_code`. For these commands stdout holds exactly one JSON document, and
progress and messages go to stderr. A single lookup keeps its earlier behavior: its result is one
JSON object, but its errors (unknown `--carrier`, courier cannot be determined, exit 3/4/5) are
still printed as plain text, so check the exit code before parsing. JSON always includes full
numbers, because an agent needs them for the next command.

### Which flags combine

- `--forget`, `--forget-all`, `--history`, `--pending`, `--refresh-pending`, `--endpoints`,
  `--find`, `--rename`, and `--clear-label` cannot be combined with each other.
- `--label` needs a tracking number, and cannot be used with `--no-record` or `--via-17track`
  (neither writes a record to attach the name to).
- `--auto` cannot be used with `--carrier` or `--via-17track`.
- `--match`, `--all-matches`, `--limit`, and `--dry-run` only work with `--refresh-pending`;
  `--all-matches` needs `--match`; with `--refresh-pending`, `--carrier` accepts only the six
  direct couriers.

Every conflict exits with `2` before anything is sent.

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
numbers. They are not distinguishable by format. SPX numbers start with `TW` and *are*
identifiable.

Up to v0.4.0, a bare 12-digit number was tried against all five in turn until one answered. Since
v0.5.0 it is not sent anywhere unless the courier is known: from `--carrier`, from a format only
one courier uses, or from the local record of an earlier lookup. Otherwise the CLI lists the
candidates and exits with `8`. `--auto` restores the old behavior for that one command, when you
agree to the number being sent to each candidate in turn.

**If you know the courier, pass `--carrier`.** It's one request, to the company that owns the
number.

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
  each entry's snapshot with what comes back, and `--forget` / `--forget-all` delete it. If the
  file is ever corrupt, the next write keeps it as `history.json.corrupt-<time>` (delete that copy
  by hand once you no longer need it) and starts a new record.
- **Names are stored separately, and only if you give them.** `--label` writes
  `number → name` to `labels.json` in the same folder, with the same `0600` mode. A name can say
  more about you than the number does ("mum's prescription"), so it is never derived from the
  courier's page or the order; it is exactly what you typed. `--clear-label` removes one,
  `--forget` removes the number's name before its record, and `--forget-all` removes both files.
  Like `history.json`, `labels.json` is included in Time Machine and other backups of `~/.cache`.
- **Lists show the last four digits.** `--history`, `--pending`, `--find`, and the refresh digest
  print 單號末四碼 unless you pass `--full-numbers`, so a screenshot of the list doesn't carry
  full numbers. JSON output always carries them.
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
- **A number is only sent to a courier that is known to own it, unless you say otherwise.** Five
  couriers share the 12-digit format, so a bare number fits all of them. Without `--carrier`, a
  unique format, or a local record, nothing is sent; the CLI lists the candidates instead.
  `--auto` is your explicit agreement to try them in turn, which means up to five companies see a
  number that belongs to one of them. Each request is the same one your browser would make on
  their public form, and none of them learns who you are.
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

v0.5.0 ([CHANGELOG](./CHANGELOG.md)) — 369 offline unit tests. Verification status differs per
courier and is worth stating precisely:

| Courier | Method | not-found path | found path | Last verified |
|---|---|---|---|---|
| 黑貓 T-cat | official page, HTTP | verified against live response | **verified** — real parcel, 2026-08-02 | 2026-08 |
| 嘉里大榮 Kerry TJ | official API, HTTP | verified against live response | synthetic fixture (real field names, values unverified) | 2026-08 |
| 台灣宅配通 e-can | official page, HTTP | verified against live response | synthetic fixture (real headers, row values unverified) | 2026-08 |
| 網家速配 PChome | official page, HTTP | verified against live response | synthetic fixture (real class structure, values unverified) | 2026-08 |
| 富昇物流 Fusheng | official page, HTTP | verified against live response | **verified** — real parcel, 4-event history, 2026-08-02 | 2026-08 |
| 蝦皮 SPX | official page, Playwright | — | DOM selectors from a live page snapshot; not yet run against a real parcel | 2026-08 |
| 中華郵政／全家／7-ELEVEN／新竹 | 17TRACK (optional) | official pages have a CAPTCHA | 17TRACK documented schema only | 2026-08 |

"Last verified" is when the maintainer last confirmed the adapter or the courier's page flow, not
the time of any parcel's status. This is an unofficial personal tool with no affiliation with any
courier; their sites can change at any time.

New couriers are added with `auto_detect_allowed: False` in `scripts/carriers/__init__.py`
(`CARRIER_META`) until a real found-path response has been captured, so a bare number is never
sent to an adapter that has not been verified.

Verified on macOS 26.5.1 (Apple M4 Pro) / Python 3.12.13. Found-path parsing for the three
couriers above marked *synthetic* will be re-calibrated as real tracking numbers become
available; until then those code paths carry `UNVERIFIED` comments.

## Roadmap

The 17TRACK bridge has shipped as an opt-in (see [17TRACK (optional)](#17track-optional)); it stays
off unless you supply your own key. What remains is re-calibrating the found-path parsers for
Kerry TJ, e-can and PChome Express against real tracking numbers (see [Status](#status)).
That is waiting on real numbers, not on code.

## License

MIT — see [LICENSE](LICENSE).
