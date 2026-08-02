# parcel-kau-a

> **貼上台灣包裹單號，回配送時間軸。免 API key、免帳號、免註冊。**

[English](./README.md) | 繁體中文

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](#前置準備)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-skill-orange.svg)](https://claude.com/claude-code)
[![Codex](https://img.shields.io/badge/Codex-compatible-black.svg)](https://developers.openai.com/codex/skills)

一個 agent skill（採開放的 [SKILL.md 標準](https://developers.openai.com/codex/skills)，[Claude Code](https://claude.com/claude-code) 與 [Codex](https://developers.openai.com/codex/skills) 都能用），讀取六家台灣貨運公司的**公開查詢頁**，回標準化的配送時間軸。名字取自台語 *kàu--ah*（到啊）。

## 為什麼？

台灣沒有免費、可自助申請的貨運追蹤 API。本土貨運公司要嘛完全沒有 API，要嘛鎖在簽約制 B2B 流程後面——所以查個包裹得先想是哪家、開對網站、找到表單、手動打單號。聚合服務覆蓋完整，但 API 存取要付費。

```text
沒有 parcel-kau-a                      有 parcel-kau-a
─────────────────                      ────────────────
這張是哪家寄的來著？                    貼上單號
找那家的查詢頁                          拿到時間軸
重打一次單號                            知道哪家就加 --carrier
每張重來一次                            --json 接後續處理
```

## 特色

- ✓ 六家免帳號：黑貓宅急便、嘉里大榮、台灣宅配通、網家速配、富昇物流（momo）、蝦皮店到店
- ✓ 自動判別貨運公司，也可用 `--carrier` 直接指定
- ✓ 跨貨運統一輸出格式——不管來自哪個站，結構一樣
- ✓ `--json` 供程式使用；預設是人讀的時間軸
- ✓ 黑貓給**完整**歷程（摘要頁只有最新一筆，本工具會續打詳細頁）
- ✓ Playwright 是選配：裝了才有蝦皮，不裝其餘五家照常
- ✓ 網路錯誤逐家降級——某站逾時不會中斷整趟查詢
- ✓ 離線測試：parser 對照擷取下來的 fixtures，跑測試不需要網路
- ✓ 選配 17TRACK 橋接，補上被驗證碼擋住的四家 —— 用**你自己的** API key，不主動呼叫
- ✓ 記住單號屬於哪家，之後重查只送**一家**而不是五家——紀錄可列出、可刪除（`--history`、`--forget`）
- ✓ 無遙測、無分析回報；除了向貨運公司發出的那個請求，沒有東西離開你的電腦

## 安裝

```bash
# Claude Code（使用者層級）
cp -r parcel-kau-a ~/.claude/skills/parcel-kau-a
pip install -r ~/.claude/skills/parcel-kau-a/requirements.txt

# Codex——同一份資料夾，換個位置放（開放 SKILL.md 標準，不需修改）
cp -r parcel-kau-a ~/.codex/skills/parcel-kau-a

# 選配——只有蝦皮店到店需要
pip install playwright && playwright install chromium
```

這個 skill 沒有任何 Claude 專屬相依：它就是一份 `SKILL.md` 加一支 Python CLI，同一份資料夾兩邊都能跑。

## 前置準備

| 需求 | 說明 |
|---|---|
| Python | 3.10 以上 |
| `requests`、`beautifulsoup4` | 必要（見 `requirements.txt`） |
| `playwright` + chromium | **選配**——僅蝦皮 SPX 需要 |

## 用法

```bash
python3 scripts/track.py 900000000001                    # 自動判別
python3 scripts/track.py 900000000001 --carrier tcat     # 直接指定
python3 scripts/track.py TW254414081298F --carrier spx   # 蝦皮店到店
python3 scripts/track.py 900000000001 --json             # 機器可讀

python3 scripts/track.py --history                       # 看記住了哪些
python3 scripts/track.py --forget 900000000001           # 忘掉某一筆
python3 scripts/track.py --forget-all                    # 全部忘掉
python3 scripts/track.py --endpoints                     # 看目前生效的查詢網址
```

```text
黑貓宅急便　900000000001

2026/01/15 18:30　配送完成　示範門市
2026/01/15 09:12　配送中

來源：https://www.t-cat.com.tw/Inquire/TraceDetail.aspx?BillID=900000000001
```

在 Claude Code 裡不需要自己下指令——直接說「查一下這個包裹 900000000001」即可。

## 支援範圍

| 貨運 | `--carrier` | 方式 | 資料保留 |
|---|---|---|---|
| 黑貓宅急便 | `tcat` | HTTP（ASP.NET postback → 詳細頁） | 3 個月 |
| 嘉里大榮 | `kerrytj` | HTTP JSON API | — |
| 台灣宅配通 | `ecan` | HTTP（Big5 編碼的經典 ASP） | 2 個月 |
| 網家速配 | `pchome` | HTTP（SSR 頁面，單號放在 URL path） | — |
| 富昇物流（momo） | `fusheng` | HTTP（SSR 頁面，單號放在 query string） | — |
| 蝦皮店到店 | `spx` | Playwright（headless） | — |

**無法直連與原因**：中華郵政、全家店到店、7-ELEVEN 交貨便、新竹物流的查詢表單都有圖形驗證碼。本 skill 不做驗證碼破解。這四家可透過下方的[17TRACK 選配橋接](#17track選配)查詢。

## 17TRACK（選配）

17TRACK 是商業聚合服務，涵蓋上述四家。本橋接是**選配、自備金鑰**——本專案不內建 key、不代為轉發，不明確要求就不會呼叫：

```bash
export PARCEL_KAU_A_17TRACK_KEY=...        # 於 https://api.17track.net 申請（免費 200 筆）
python3 scripts/track.py 83546610320956 --via-17track
python3 scripts/track.py 83546610320956 --via-17track --carrier chunghwa-post
```

此模式的 `--carrier` 可用值：`chunghwa-post`、`famiport`、`seven-eleven`、`hct`（另有已直連的五家，若你想改走 17TRACK 也可指定）。

**費用怎麼算，以及它留下什麼**：17TRACK 按「登錄的單號數」計費——`register` 扣 1 筆額度，`gettrackinfo` 與 webhook 推送不扣，所以查過的單號再查是免費的，免費額度（2026-01-07 後新帳號一次性 200 筆）等於 200 個不同包裹。重查之所以免費，是因為那組單號**留在你的 17TRACK 帳號裡**、由他們持續替你追蹤。這也是它與直連六家最本質的差別：直連是問完就走，走 17TRACK 則是把單號寄存在第三方，直到你自己刪除。用完之後只能整包預購年度額度，最低 US$119 買 5,000 筆、12 個月到期，沒有隨用隨付方案。本 adapter 刻意不呼叫 `getRealTimeTrackInfo`——它的 `Instant` 快取層級一次要扣 10 筆額度。

刻意設下的限制：

- **絕不自動使用**：聚合 adapter 的 `detect()` 永遠回 `False`，自動判別不可能花掉你的額度，只有 `--via-17track` 走得到。
- **獨立降級**：沒設 key 時只有這條路不可用，直連五家完全不受影響。
- **第三方揭露**：使用它等於把單號送給 17TRACK 這個第三方，其有自己的條款與隱私政策——不同於直連模式，那裡單號只會到達發出它的貨運公司。

## 關於自動判別

黑貓、嘉里大榮、宅配通、網家速配、富昇的單號**都是 12 碼數字**，格式無從區分。不指定 `--carrier` 時會依序查詢、命中即停——最壞情況五次請求。蝦皮單號以 `TW` 開頭，可由格式判定。

**知道是哪家就加 `--carrier`**，一次請求勝過五次。

## 運作原理

每家貨運各自實作 `detect(number)` 與 `track(number)` 的 adapter；CLI 挑選 adapter、依序執行，把各站回應正規化成同一個 `TrackResult` 結構。這五家底層差異很大：

- **黑貓**是 ASP.NET WebForm——要先抓 `__VIEWSTATE`/`__EVENTVALIDATION` 再回傳，然後續打 `TraceDetail.aspx` 才有完整貨態歷程。
- **嘉里大榮**前端看起來是 Vue，底下其實是乾淨的 JSON 端點。
- **宅配通**是 **Big5** 編碼的經典 ASP，表單編碼與回應解碼都得明講。
- **網家速配**與**富昇物流**是六家中最單純的：SSR 頁面、單號直接放在網址裡，連表單來回都不用。
- **蝦皮**的追蹤 API 帶一個由瀏覽器 JavaScript 計算的簽章。與其逆向那個簽章（站方下次改版就碎），adapter 直接開 headless 瀏覽器，讓站方自己的頁面產生它。

## 隱私

- **有一樣東西會存，而它的目的正是減少揭露**：**直連**查到結果時會把「單號→貨運公司」（連同最新狀態與時間）記進 `~/.cache/parcel-kau-a/history.json`。檔案以 `0600` 建立——**POSIX 會落實，Windows 不會**：Windows 沒有 POSIX 權限位元，那裡的保護程度取決於你使用者目錄本身的 ACL，不是本工具給的「僅擁有者可讀」保證。走 `--via-17track` 的查詢刻意**不記錄**：把 carrier 存成 `17track` 會讓之後每次自動判別都去打付費 API。（因此 `--no-record` 在那條路上沒有作用。）重點在下一次查詢：有紀錄就只送**一家**，不必對五家逐一嘗試。查無資料不會記錄；`--no-record` 可略過寫入，`--history` 列出全部，`--forget` / `--forget-all` 刪除。
- **那個檔案放哪，講精確一點**：macOS 的 Time Machine 只自動排除 `~/Library/Caches`，**不會**排除 `~/.cache`——所以這個檔案會進備份。如果某個單號不想留在任何地方，用 `--no-record`，或等包裹到了用 `--forget` 刪掉（包裹看似送達時 CLI 會主動提醒你這件事）。
- **無遙測**：沒有分析回報、沒有 log、不會回傳任何東西。每次查詢都是即時請求，結果印出來。
- **自動判別會把單號送給不是它主人的貨運公司**：黑貓、嘉里大榮、宅配通、網家速配、富昇的單號都是 12 碼純數字，所以不加 `--carrier` 時會依序送去查、直到某一家回報查得到——最多有五家看到這組只屬於其中一家的單號。每個請求都與你在該站公開表單手動查詢時相同，各站也不會知道你是誰，但單號本身的揭露範圍比直覺想像的廣。**加上 `--carrier` 就只會送給一家。** CLI 會在送出第一個請求之前先列出即將查詢的貨運公司，所以這件事在使用當下就看得到，不是只寫在這裡。
- 在 Claude Code 中，回傳的時間軸會進入你自己的 Claude session，如同任何指令輸出。
- **單號不是匿名資料**：在多數站台上它可辨識一件包裹，時間軸還可能含門市或營業所名稱。請比照收據對待。

## 已知限制

- 本工具讀取的是**公開網頁**。非官方 API、未獲任何貨運公司授權，站方改版即會失效。失效時會明確報錯，而不是回空結果。
- 適用於**個人低頻**查詢。無重試迴圈、無並行；請求 10 秒逾時後直接失敗。請勿拿來批次跑單號清單。
- **嘉里大榮的表單要求先勾選同意法律聲明與個資保護聲明**。本工具直接呼叫底層端點，因此不會顯示該勾選項——使用本工具即代表你自行承擔遵守其條款的責任。
- **蝦皮**：只使用 `spx.tw/` 的公開查詢框；其 robots.txt 標示 disallow 的路徑不會造訪。
- 各站自有的資料保留期限適用（見[支援範圍](#支援範圍)）——超過期限的包裹是站方本身回「查無」，非本 skill 的問題。

## 貨運公司改版時

爬蟲會壞，這是本質。這個 skill 用到的每個網址都放在 `scripts/endpoints.py`，而且可以**逐鍵覆寫、完全不動程式**——把要改的鍵寫進 `~/.cache/parcel-kau-a/endpoints.json` 即可：

```json
{ "pchome": { "query": "https://www.gopchome.com.tw/whatever/{number}" } }
```

`--endpoints` 會印出目前生效的值與覆寫檔路徑。覆寫檔壞掉時會退回預設並印警告，不會讓工具整個不能用。

**但這只涵蓋「網址搬家」，不涵蓋「整站改版」**。貨運公司若改了 HTML 結構、API 回應格式、表單欄位或 CSS class，parser 就得跟著改——設定檔表達不了這些。你會拿到的是誠實的失敗：adapter 拋「頁面結構已變，請回報 issue」，而不是回一個看起來像「查無資料」的空結果。

錯誤訊息也分類了，讓你知道該往哪查：`404` 表示網址可能已失效並指向設定檔、`5xx` 表示對方伺服器有問題、連線逾時與連不上則分開顯示。

## 平台差異

開發與日常使用在 macOS，Linux 由 CI 覆蓋。有兩件事在其他平台不一樣，講明比含糊帶過好：

- **檔案權限**：紀錄檔以 `0600` 寫入。POSIX 會落實。Windows 不理會 POSIX 權限位元，該檔改為繼承使用者目錄的 ACL——在一台真實 Windows 上實測到的 ACL 包含 `CodexSandboxUsers:(RX)`，也就是**不只你讀得到**。請把 `0600` 當成僅限 POSIX 的保證。在意內容的話用 `--no-record`，或包裹到了就 `--forget`。
- **存放位置**：`~/.cache/parcel-kau-a/` 沿用 XDG 慣例。在 Windows 上會解析成 `C:\Users\你\.cache\parcel-kau-a\`，能運作但不是該平台自己的慣例（`%LOCALAPPDATA%`）。想放別處可設 `PARCEL_KAU_A_HOME`。
- **執行指令**：Windows 上用 `python` 而不是 `python3`——後者是 Microsoft Store 的捷徑，執行會回 9009「Python was not found」。
- **安裝**：`requirements.txt` 刻意只用 ASCII：pip 以系統 locale 編碼讀取該檔，非 ASCII 註解會讓繁中 Windows（cp950）安裝失敗。

CI 在 Linux 上跑 Python 3.10–3.13、在 Windows 上跑 3.10 與 3.13。

## 開發

```bash
pip install -r requirements.txt pytest
python3 -m pytest tests -q          # 離線；不需網路、不下載 fixtures
```

Parser 對照 `tests/fixtures/` 內擷取下來的回應測試，每份都附 `*_notes.md` 記錄當時的請求方式與回應樣貌。

## 狀態

v0.2.2（[CHANGELOG](./CHANGELOG.md)）——133 個離線單元測試。**各家的驗證程度不同，值得精確說明**：

| 貨運 | 查無資料路徑 | 有資料路徑 |
|---|---|---|
| 黑貓 T-cat | 已對真實回應驗證 | **已驗證**——真實包裹，2026-08-02 |
| 嘉里大榮 | 已對真實回應驗證 | 合成 fixture（欄位名為真，值未驗證） |
| 台灣宅配通 | 已對真實回應驗證 | 合成 fixture（表頭為真，列內容未驗證） |
| 網家速配 | 已對真實回應驗證 | 合成 fixture（class 結構為真，值未驗證） |
| 富昇物流 | 已對真實回應驗證 | **已驗證**——真實包裹 4 筆歷程，2026-08-02 |
| 蝦皮 SPX | — | DOM selector 取自實際頁面 snapshot，尚未對真實包裹跑過 |

驗證環境：macOS 26.5.1（Apple M4 Pro）／Python 3.12.13。上表標示「合成」的三家，有真實單號後會重新校準；在那之前，那些程式路徑帶有 `UNVERIFIED` 註解。

## 未來規劃

沒有既定計畫。[狀態](#狀態)表中標示「合成」的 parser 會隨真實單號出現而重新校準；其餘功能依實際需求增補。

## 授權

MIT——見 [LICENSE](LICENSE)。
