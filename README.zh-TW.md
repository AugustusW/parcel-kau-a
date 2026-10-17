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
- ✓ 不猜物流商：單號格式符合多家時一筆都不送，等你選一家（`--carrier`）或同意依序詢問（`--auto`）
- ✓ 跨貨運統一輸出格式——不管來自哪個站，結構一樣
- ✓ `--json` 供程式使用；預設是人讀的時間軸
- ✓ 黑貓給**完整**歷程（摘要頁只有最新一筆，本工具會續打詳細頁）
- ✓ Playwright 是選配：裝了才有蝦皮，不裝其餘五家照常
- ✓ 網路錯誤逐家降級——某站逾時不會中斷整趟查詢
- ✓ 離線測試：parser 對照擷取下來的 fixtures，跑測試不需要網路
- ✓ 選配 17TRACK 橋接，補上被驗證碼擋住的四家 —— 用**你自己的** API key，不主動呼叫
- ✓ 記住單號屬於哪家，之後重查只送**一家**而不是五家——紀錄可列出、可刪除（`--history`、`--forget`）
- ✓ `--pending` 用那份本機紀錄回答「還有哪些包裹在路上」，完全不連線。每份快照都標明是快照，並把物流事件時間與上次查詢時間分開顯示，一週前的狀態不會被誤認成今天的
- ✓ 替包裹取名稱（`--label`、`--find`）：用「耳機」找包裹，不必記單號。多筆名稱相符時全部列出，絕不替你挑一筆
- ✓ `--refresh-pending` 回答「所有未結案包裹**現在**的狀態」——對每個未結案單號逐一即時查詢、更新本機紀錄，並印出依結果分類的彙整（新結案／有新進度／無變化／已略過／查詢失敗）；可用 `--match`、`--carrier`、`--limit` 縮小範圍，或用 `--dry-run` 先預覽
- ✓ 列表預設只顯示單號末四碼，要完整單號才加 `--full-numbers`
- ✓ 無遙測、無分析回報；除了向貨運公司發出的那個請求，沒有東西離開你的電腦

## 安裝

```bash
# Claude Code（使用者層級）
git clone https://github.com/AugustusW/parcel-kau-a.git ~/.claude/skills/parcel-kau-a
pip install -r ~/.claude/skills/parcel-kau-a/requirements.txt

# Codex——同一份資料夾，換個位置放（開放 SKILL.md 標準，不需修改）
git clone https://github.com/AugustusW/parcel-kau-a.git ~/.codex/skills/parcel-kau-a

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
python3 scripts/track.py 900000000001 --carrier tcat     # 指定一家查詢
python3 scripts/track.py TW254414081298F                 # 蝦皮單號格式可自行判定
python3 scripts/track.py 900000000001                    # 符合多家：列出候選、一筆都不送（exit 8）
python3 scripts/track.py 900000000001 --auto             # 同意依序詢問所有格式相符的物流商
python3 scripts/track.py 900000000001 --carrier tcat --json      # 機器可讀

python3 scripts/track.py 900000000001 --carrier tcat --label "momo 耳機"   # 取名稱
python3 scripts/track.py --find 耳機                     # 用名稱找（不連線）
python3 scripts/track.py --rename 900000000001 "工作用耳機"
python3 scripts/track.py --clear-label 900000000001

python3 scripts/track.py --pending                       # 看哪些還在路上（不連線）
python3 scripts/track.py --refresh-pending               # 對未結案包裹逐一即時查詢
python3 scripts/track.py --refresh-pending --match 耳機 --dry-run   # 先預覽縮小範圍的更新
python3 scripts/track.py --history                       # 看記住了哪些
python3 scripts/track.py --forget 900000000001           # 忘掉某一筆與它的名稱
python3 scripts/track.py --forget-all                    # 全部忘掉
python3 scripts/track.py --endpoints                     # 看目前生效的查詢網址
```

```text
黑貓宅急便　900000000001

2026/01/15 18:30　配送完成　示範門市
2026/01/15 09:12　配送中

來源：https://www.t-cat.com.tw/Inquire/TraceDetail.aspx?BillID=900000000001
查詢時間：2026/01/15 19:02（剛剛即時查詢）
```

12 碼純數字符合五家物流商，單獨給這樣一個單號時不會送到任何地方：

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

`--pending` 回答的是另一種問題——不是「這件到哪了」，而是「我還有幾件在路上」：

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

這份清單完全來自本機紀錄，**不會發出任何請求**。每筆有兩種時間：「物流事件」是物流商最後一次掃描包裹的時間，「上次查詢」是本工具最後一次去問的時間；上次查詢超過 7 天會標「資料可能過期」。要知道現在到哪了，就拿那個單號再查一次——或者一次把全部未結案的都更新：

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

`--refresh-pending` 走的是 `--pending` 讀的同一份本機清單，但不是印快照，而是對每個單號逐一
即時查詢——一次一筆、走跟單號查詢相同的路徑——再依結果分類成彙整：**新結案**（這次查到已送達）、
**有新進度**（顯示「前 → 後」）、**無變化**、**已略過**、**查詢失敗**（會寫出仍保留哪一次的快照）。
查成功的那筆會覆寫該號的本機快照，機制跟一般查詢寫入完全相同（`--no-record` 一樣能抑制寫入）。
某一家掛掉不會讓整批中止；只要有一筆失敗，結束碼就是 `6`。

只想更新其中幾筆：`--match <名稱>`（命中多筆時會列出、一筆都不送，要加 `--all-matches` 才會全部更新）、
`--carrier <代號>`、`--limit N`（取最新物流事件最近的 N 筆），以及 `--dry-run`（只列出會查哪些，不連線、不寫入）。

`--refresh-pending` 永遠不呼叫 17TRACK，即使設了 key：環境裡有 key 不等於同意整批送出。需要 17TRACK 的項目會列為**已略過**，並附上逐筆查詢的指令。

在 Claude Code 裡不需要自己下指令——直接說「查一下這個黑貓包裹 900000000001」或
「還有哪些包裹在路上」即可；想要現況而不是上次的快照，就說「幫我更新一下未結案包裹」。

### 替包裹取名稱

用 `--label` 查詢時，查到結果才會把名稱掛到那個單號上（查無資料不存）。之後 `--find` 依「完整單號 → 單號尾碼（至少 4 碼，列表上的末四碼可以直接用）→ 名稱完全相符 → 名稱包含」的順序找包裹。`--find` 與名稱相關指令都不會連線。紀錄已不存在、只剩名稱的單號（例如紀錄檔毀損被另存後）仍找得到，會標「只剩名稱」，`--history` 最後也會列出這類名稱的數量。

多筆相符時全部列出並以 `8` 結束，由使用者決定要哪一筆。對已有名稱的單號再 `--label` 會取代舊名稱並說明。名稱可用文字、數字、標點、符號、emoji 與空白，最多 100 字；控制字元、雙向文字控制字元與其他看不見的格式字元一律拒絕，因為名稱會印到你的終端機、也會進到 Agent 的 context。

### 結束碼

| 碼 | 意義 |
|---|---|
| 0 | 成功（查無資料也算成功） |
| 2 | 參數錯誤、無法判別物流商、名稱不合法 |
| 3 | 缺少依賴（例如蝦皮需要 Playwright） |
| 4 | 物流商頁面結構已變 |
| 5 | 網路錯誤、逾時或站方錯誤 |
| 6 | `--refresh-pending` 跑完，但至少一筆查詢失敗或沒存成功 |
| 7 | `--label`、`--rename`、`--clear-label`、`--forget`、`--forget-all` 沒有完整保存／刪除（包括另一個程序正在寫入）。一般查詢的紀錄存不進去時仍是 0，只在 stderr 提示，因為紀錄只是輔助功能 |
| 8 | 需要選擇（哪家物流商、哪個相符的名稱）；**沒有送出任何查詢** |

### JSON

`track.py <單號> --json` 的輸出與先前版本相同。其他指令加 `--json`、以及這些指令的錯誤，都輸出一份 envelope：`{"schema_version": 1, "operation": …}`。`operation` 為 `history`、`pending`、`find`、`refresh_pending`、`detect`（選物流商）、`rename`、`clear_label`、`forget`、`forget_all` 或 `error`；錯誤帶 `"ok": false` 與 `exit_code`。這些指令的 stdout 只會有一份 JSON，進度與訊息都在 stderr。單筆查詢維持舊行為：結果是一份 JSON 物件，但它的錯誤（未知的 `--carrier`、無法判別物流商、exit 3/4/5）仍是一般文字，解析前請先看結束碼。JSON 一律帶完整單號，因為 Agent 下一步要用。欄位說明見[英文 README](./README.md#json)。

### 哪些參數能一起用

- `--forget`、`--forget-all`、`--history`、`--pending`、`--refresh-pending`、`--endpoints`、`--find`、`--rename`、`--clear-label` 彼此不能同時使用。
- `--label` 需要搭配單號，且不能和 `--no-record` 或 `--via-17track` 同時用（兩者都不寫紀錄，名稱無處可掛）。
- `--auto` 不能和 `--carrier` 或 `--via-17track` 同時用。
- `--match`、`--all-matches`、`--limit`、`--dry-run` 只能搭配 `--refresh-pending`；`--all-matches` 需要 `--match`；搭配 `--refresh-pending` 時，`--carrier` 只接受六家直連物流商。

衝突時一律在送出任何東西之前以 `2` 結束。

## 支援範圍

| 貨運 | `--carrier` | 官方查件頁 | 本工具的讀取方式 | 資料保留 |
|---|---|---|---|---|
| 黑貓宅急便 | `tcat` | [t-cat.com.tw](https://www.t-cat.com.tw/Inquire/Trace.aspx) | HTTP（ASP.NET postback → 詳細頁） | 3 個月 |
| 嘉里大榮 | `kerrytj` | [kerrytj.com](https://www.kerrytj.com/zh/checking) | HTTP JSON API | — |
| 台灣宅配通 | `ecan` | [query2.e-can.com.tw](https://query2.e-can.com.tw/%E5%A4%9A%E7%AD%86%E6%9F%A5%E4%BB%B6A.htm) | HTTP（Big5 編碼的經典 ASP） | 2 個月 |
| 網家速配 | `pchome` | [gopchome.com.tw](https://www.gopchome.com.tw/) | HTTP（SSR 頁面，單號放在 URL path） | — |
| 富昇物流（momo） | `fusheng` | [tmsvendor.fs.com.tw](https://tmsvendor.fs.com.tw/search) | HTTP（SSR 頁面，單號放在 query string） | — |
| 蝦皮店到店 | `spx` | [spx.tw](https://spx.tw/) | Playwright（headless） | — |
| 中華郵政 | `chunghwa-post` | [postserv.post.gov.tw](https://postserv.post.gov.tw/pstmail/main_mail.html) | 官方頁面有驗證碼，只能走 [17TRACK](#17track選配) | — |
| 全家店到店 | `famiport` | [fmec.famiport.com.tw](https://fmec.famiport.com.tw/FP_Entrance/QueryBox) | 官方頁面有驗證碼，只能走 [17TRACK](#17track選配) | — |
| 7-ELEVEN 交貨便 | `seven-eleven` | [eservice.7-11.com.tw](https://eservice.7-11.com.tw/e-tracking/search.aspx) | 官方頁面有驗證碼，只能走 [17TRACK](#17track選配) | — |
| 新竹物流 | `hct` | [cagweb01.hct.com.tw](https://cagweb01.hct.com.tw/search/searchgoods.aspx) | 官方頁面有驗證碼，只能走 [17TRACK](#17track選配) | — |

前六家直接讀官方公開頁面。本 skill 不做驗證碼破解，後四家只能透過下方的 [17TRACK 選配橋接](#17track選配)、用你自己的 API key 查詢，它們的 `--carrier` 代號也只能搭配 `--via-17track` 使用。網址於 2026-10 確認過。

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

### 實例走一遍：查全家或 7-ELEVEN 的包裹

全家店到店與 7-ELEVEN 交貨便是本專案無法直連的四家之二——查詢表單都有圖形驗證碼（見[支援範圍](#支援範圍)）——所以 17TRACK 是這個 skill 唯一能碰到它們的路。

1. **申請 key**：到 [api.17track.net](https://api.17track.net) 註冊，免費額度 200 筆（2026-01-07 後新帳號一次性）。key 放在他們自己後台某個 API/Token 相關的頁面——那是 17TRACK 自己的介面，本專案管不到，選單文字可能會變。
2. **每個 shell session 匯出一次**（或寫進 shell profile）：
   ```bash
   export PARCEL_KAU_A_17TRACK_KEY=...
   ```
3. **查詢包裹，並明講是哪一家**：
   ```bash
   python3 scripts/track.py <你的單號> --via-17track --carrier famiport       # 全家店到店
   python3 scripts/track.py <你的單號> --via-17track --carrier seven-eleven   # 7-ELEVEN 交貨便
   ```
   不加 `--carrier` 會讓 17TRACK 自己猜是哪家，明講可以少一個出錯的環節。

**「測過」在這裡的意思要講清楚**：17TRACK adapter 的 parser（`scripts/carriers/seventeentrack.py` 的 `parse_response`）測的是 17TRACK **官方文件**寫的 schema——`tests/test_seventeentrack.py` 用他們公開的欄位名（`time_iso`/`time_raw`、`description`、`providers[].events[]` 等）手動組出 payload 來驗，不管底層是哪家貨運都是同一份 schema。這驗證的是本專案的程式碼有沒有正確處理「17TRACK 說它會回的形狀」，**不是**驗證真實的全家或 7-11 包裹真的會照這個形狀回來——目前還沒有人拿真實包裹跑過這條路徑、把 17TRACK 實際回的東西存下來確認過。如果你手上正好有一件在路上的全家或 7-11 包裹、願意幫忙補上這塊，`scripts/capture_fixture.py`（見[開發](#開發)）可以擷取並去識別化一份真實回應——這正是它存在的目的。

輸出的**格式**是真的——每次 `--via-17track` 查詢都走跟直連查詢同一套程式碼路徑，這條路徑本身有測試覆蓋。**內容**不是：下面純粹是根據 17TRACK 官方文件畫出來的示意，不是真實回應。

```text
⚠️ 這是根據官方文件畫出來的欄位形狀示意，不是真實包裹的擷取結果——目前沒有人拿真實
全家或 7-11 包裹跑過這條路徑，確認官方文件講的形狀是否真的照著回。

17TRACK　<你的單號>

2026/01/15 18:30　順利投遞　（示意：description 欄位）
2026/01/15 09:12　已收寄

來源：https://t.17track.net/
```

## 關於自動判別

黑貓、嘉里大榮、宅配通、網家速配、富昇的單號**都是 12 碼數字**，格式無從區分；蝦皮單號以 `TW` 開頭，可由格式判定。

v0.4.0 以前，不指定 `--carrier` 的 12 碼單號會依序送去五家查到命中為止。v0.5.0 起，物流商未知時不送：只有 `--carrier`、只有一家使用的格式，或之前查過的本機紀錄，才能決定送去哪家；其他情況列出候選並以 `8` 結束。你同意單號依序送到每一家時，加 `--auto`，舊行為只對那一次指令生效。

**知道是哪家就加 `--carrier`**：一次請求，只送給擁有這個單號的那家。

## 運作原理

每家貨運各自實作 `detect(number)` 與 `track(number)` 的 adapter；CLI 挑選 adapter、依序執行，把各站回應正規化成同一個 `TrackResult` 結構。這五家底層差異很大：

- **黑貓**是 ASP.NET WebForm——要先抓 `__VIEWSTATE`/`__EVENTVALIDATION` 再回傳，然後續打 `TraceDetail.aspx` 才有完整貨態歷程。
- **嘉里大榮**前端看起來是 Vue，底下其實是乾淨的 JSON 端點。
- **宅配通**是 **Big5** 編碼的經典 ASP，表單編碼與回應解碼都得明講。
- **網家速配**與**富昇物流**是六家中最單純的：SSR 頁面、單號直接放在網址裡，連表單來回都不用。
- **蝦皮**的追蹤 API 帶一個由瀏覽器 JavaScript 計算的簽章。與其逆向那個簽章（站方下次改版就碎），adapter 直接開 headless 瀏覽器，讓站方自己的頁面產生它。

## 隱私

- **有一樣東西會存，而它的目的正是減少揭露**：**直連**查到結果時會把「單號→貨運公司」（連同最新狀態與時間）記進 `~/.cache/parcel-kau-a/history.json`。檔案以 `0600` 建立——**POSIX 會落實，Windows 不會**：Windows 沒有 POSIX 權限位元，那裡的保護程度取決於你使用者目錄本身的 ACL，不是本工具給的「僅擁有者可讀」保證。走 `--via-17track` 的查詢刻意**不記錄**：把 carrier 存成 `17track` 會讓之後每次自動判別都去打付費 API。（因此 `--no-record` 在那條路上沒有作用。）重點在下一次查詢：有紀錄就只送**一家**，不必對五家逐一嘗試。查無資料不會記錄；`--no-record` 可略過寫入，`--history` 列出全部，`--pending` 只列還沒結案的那些（純讀，不發請求），`--refresh-pending` 對這份縮小過的清單逐一即時查詢並改寫每筆快照，`--forget` / `--forget-all` 刪除。紀錄檔若毀損，下一次寫入會把它另存為 `history.json.corrupt-<時間>`（不需要時請手動刪除）再重新記錄。
- **名稱分開存，而且只存你給的**：`--label` 把「單號→名稱」寫進同資料夾的 `labels.json`（同樣 `0600`）。名稱可能比單號透露更多（「媽媽的藥」），所以絕不從物流頁或訂單推測，存的就是你打的字。`--clear-label` 刪一筆，`--forget` 先刪名稱再刪紀錄，`--forget-all` 兩個檔都刪。和 `history.json` 一樣，`labels.json` 會進 Time Machine 等 `~/.cache` 的備份。
- **列表只顯示末四碼**：`--history`、`--pending`、`--find` 與更新摘要預設顯示「單號末四碼」，加 `--full-numbers` 才顯示完整單號，截圖分享清單時不會帶出完整單號。JSON 一律帶完整單號。
- **`--refresh-pending` 不會重新對外廣播單號**：每筆未結案紀錄本來就已知道是哪家貨運（不然也不會被記下來），所以更新時只會把單號再送回那一家，跟明確指定 `--carrier` 的揭露範圍相同，不會重跑對其餘四家的自動判別。
- **那個檔案放哪，講精確一點**：macOS 的 Time Machine 只自動排除 `~/Library/Caches`，**不會**排除 `~/.cache`——所以這個檔案會進備份。如果某個單號不想留在任何地方，用 `--no-record`，或等包裹到了用 `--forget` 刪掉（包裹看似送達時 CLI 會主動提醒你這件事）。
- **無遙測**：沒有分析回報、沒有 log、不會回傳任何東西。每次查詢都是即時請求，結果印出來。
- **單號只送給已知擁有它的物流商，除非你另外同意**：五家共用 12 碼格式，單獨一個數字符合全部五家。沒有 `--carrier`、唯一格式或本機紀錄時一筆都不送，改為列出候選。`--auto` 是你明確同意依序嘗試，代表最多有五家看到這組只屬於其中一家的單號；每個請求都與你在該站公開表單手動查詢時相同，各站也不會知道你是誰。
- 在 Claude Code 中，回傳的時間軸會進入你自己的 Claude session，如同任何指令輸出。
- **單號不是匿名資料**：在多數站台上它可辨識一件包裹，時間軸還可能含門市或營業所名稱。請比照收據對待。

## 已知限制

- 本工具讀取的是**公開網頁**。非官方 API、未獲任何貨運公司授權，站方改版即會失效。失效時會明確報錯，而不是回空結果。
- 適用於**個人低頻**查詢。無重試迴圈、無並行；請求 10 秒逾時後直接失敗。請勿拿來批次跑單號清單。
  `--refresh-pending` 也不例外——它對未結案清單一樣是逐一序列查詢，未結案筆數愈多就單純愈久。
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

### 擷取真實 fixture（給貢獻者）

嘉里大榮、宅配通、網家速配這三家的 found-path parser 目前跑在**合成** fixture 上——欄位名稱與結構是真的，但值沒有人真的看過貨運公司回過（見[狀態](#狀態)）。如果你手上有真實、還在路上的單號，想幫忙補上這塊：

```bash
python3 scripts/capture_fixture.py <真實單號> --carrier kerrytj
python3 scripts/capture_fixture.py <真實單號> --carrier ecan
python3 scripts/capture_fixture.py <真實單號> --carrier pchome
python3 scripts/capture_fixture.py <真實單號> --carrier famiport --via-17track   # 需要 17TRACK key
```

這會走跟一般查詢同一套 adapter 程式碼發一次真實請求，然後在 `tests/fixtures/` 寫出兩個檔案：去識別化過的原始回應（`<carrier>_found_captured.<ext>`）與待補完的 notes 草稿（`<carrier>_found_captured_notes.md`，附 TODO 清單），並印出目前 parser 從這次回應抓到了哪些欄位，方便你對照頁面實際內容判斷抓得準不準。

**⚠️ 去識別化只是第一道防線，不是保證。** 寫入前，工具會代換真實單號、並用保守的正則遮蔽電話號碼、身分證字號樣式、email、常見台灣地址樣式。它**不會**偵測中文姓名——2-4 個中文字的姓名沒有可靠的正則特徵能跟一般狀態文字區分開，這件事完全留給你自己判斷。**寫出來的檔案在 `git add` 之前一定要打開看過。** 蝦皮 SPX 不支援：它是靠 Playwright 現場渲染頁面，不是一個這支工具攔得到的單一 HTTP 回應，要校準還是得人工開瀏覽器開發者工具。

## 狀態

v0.5.1（[CHANGELOG](./CHANGELOG.md)）——394 個離線單元測試。**各家的驗證程度不同，值得精確說明**：

| 貨運 | 查詢方式 | 查無資料路徑 | 有資料路徑 | 最後驗證 |
|---|---|---|---|---|
| 黑貓 T-cat | 官方頁面，HTTP | 已對真實回應驗證 | **已驗證**——真實包裹，2026-08-02 | 2026-08 |
| 嘉里大榮 | 官方 API，HTTP | 已對真實回應驗證 | 合成 fixture（欄位名為真，值未驗證） | 2026-08 |
| 台灣宅配通 | 官方頁面，HTTP | 已對真實回應驗證 | 合成 fixture（表頭為真，列內容未驗證） | 2026-08 |
| 網家速配 | 官方頁面，HTTP | 已對真實回應驗證 | 合成 fixture（class 結構為真，值未驗證） | 2026-08 |
| 富昇物流 | 官方頁面，HTTP | 已對真實回應驗證 | **已驗證**——真實包裹 4 筆歷程，2026-08-02 | 2026-08 |
| 蝦皮 SPX | 官方頁面，Playwright | — | DOM selector 取自實際頁面 snapshot，尚未對真實包裹跑過 | 2026-08 |
| 中華郵政／全家／7-ELEVEN／新竹 | 17TRACK（選配） | 官方頁面有驗證碼 | 只驗證過 17TRACK 文件的 schema | 2026-08 |

「最後驗證」是維護者最後確認 adapter 或官方查詢流程的年月，不是包裹狀態時間。本專案為非官方個人工具，與各物流商無隸屬或合作關係；物流網站可能隨時調整查詢介面。

新增的物流商在 `scripts/carriers/__init__.py` 的 `CARRIER_META` 先設 `auto_detect_allowed: False`，取得真實有資料回應之前，裸單號不會被送到尚未驗證的 adapter。

驗證環境：macOS 26.5.1（Apple M4 Pro）／Python 3.12.13。上表標示「合成」的三家，有真實單號後會重新校準；在那之前，那些程式路徑帶有 `UNVERIFIED` 註解。

## 未來規劃

沒有既定計畫。[狀態](#狀態)表中標示「合成」的 parser 會隨真實單號出現而重新校準；其餘功能依實際需求增補。

## 授權

MIT——見 [LICENSE](LICENSE)。
