---
name: parcel-kau-a
description: Track Taiwan parcel deliveries by tracking number. Use when the user asks about a package's delivery status, shipping progress, or where a parcel is — including phrases like 查包裹, 包裹進度, 貨態, 到了沒, tracking, or when they paste a Taiwanese courier tracking number. Also use when the user asks which of their parcels are still on the way rather than about one specific number — 還有哪些包裹在路上, 哪些包裹還沒到, 未結案包裹, 我的包裹清單 — which is answered from the local query history without contacting any courier. When they instead want the live, right-now status of everything still pending — 幫我更新一下未結案包裹, 未結案的都查一下最新進度, 全部包裹現在到哪了 — that live-queries each one instead of reading the snapshot. Supports 黑貓宅急便 (T-cat), 嘉里大榮 (Kerry TJ), 台灣宅配通 (e-can), 網家速配 (PChome Express), 富昇物流／momo 自營 (Fusheng), and 蝦皮店到店 (Shopee SPX). 中華郵政, 全家, 7-11 交貨便, and 新竹物流 cannot be read directly (CAPTCHA) but are reachable via 17TRACK if the user supplies their own API key.
---

# parcel-kau-a

輸入台灣包裹單號，回配送時間軸。無需 API key。

## 用法

macOS / Linux 用 `python3`；**Windows 要用 `python`**（`python3` 在 Windows 是
Microsoft Store 的捷徑，直接執行會回 9009「Python was not found」）。

```bash
python3 scripts/track.py <單號> --carrier tcat       # 指定物流商（使用者提到物流商時一律這樣）
python3 scripts/track.py <單號>                      # 格式或紀錄能唯一判定時才會查；否則列候選、exit 8
python3 scripts/track.py <單號> --auto               # 使用者同意後：依序詢問所有格式相符的物流商
python3 scripts/track.py <單號> --carrier tcat --label "momo 耳機"   # 查到後幫這筆取名稱
python3 scripts/track.py <單號> --json               # 機器可讀輸出
python3 scripts/track.py --find 耳機                 # 用名稱或單號尾碼（例如 0001）找包裹（不連線）
python3 scripts/track.py --rename <單號> "新名稱"     # 改名稱（不連線）
python3 scripts/track.py --clear-label <單號>        # 清除名稱（不連線）
python3 scripts/track.py --pending                   # 只列尚未結案的包裹（不連線）
python3 scripts/track.py --refresh-pending           # 對每筆未結案包裹即時查詢，回報彙整摘要
python3 scripts/track.py --refresh-pending --match 耳機   # 只更新名稱符合的那幾筆
python3 scripts/track.py --history                   # 列出查詢紀錄（含已完成）
python3 scripts/track.py --forget <單號>             # 刪除某筆紀錄與名稱
python3 scripts/track.py --endpoints                 # 列出目前生效的查詢網址
```

列表類輸出（`--pending`／`--history`／`--find`／`--refresh-pending`）預設只顯示單號末四碼；
需要完整單號時加 `--full-numbers`，或改用 `--json`（JSON 一律帶完整單號）。

Windows（PowerShell）：

```powershell
python scripts\track.py <單號> --carrier tcat
python scripts\track.py --pending
```

`--carrier` 可用值：`tcat`（黑貓）、`kerrytj`（嘉里大榮）、`ecan`（宅配通）、`pchome`（網家速配）、`fusheng`（富昇/momo）、`spx`（蝦皮店到店）。

## 判別規則：不猜物流商，不經同意不送出單號

黑貓、嘉里大榮、宅配通、網家速配、富昇的單號同為 12 碼數字，**格式無法區分**。蝦皮 SPX 為 `TW` 開頭，可由格式判定。

CLI 只在物流商可以唯一判定時才送出查詢：有 `--carrier`、格式唯一（SPX）、或查詢紀錄已知這個單號屬於哪家。
否則**一筆都不送**，列出候選物流商並以 **exit 8** 結束。Agent 的處理方式：

1. **使用者提到物流商名稱 → 一律帶 `--carrier`。**
2. 使用者只說購物通路（「momo 買的」「蝦皮買的」）而不是物流商 → **問是哪家物流**，不要自行對應（momo 同時有自營富昇與委外黑貓／宅配通／新竹）。
3. CLI 回 exit 8 → 轉述候選清單，問使用者是哪一家。使用者不知道時，說明「會把單號依序送到這幾家網站查詢，查到即停」，**使用者同意後**才加 `--auto` 重跑。
4. 使用者講的物流商不在支援清單（例如新竹物流）→ 告知不支援直連。可選的路是使用者自備 key 走 `--via-17track`，**要使用者明確同意才用**；不要改用裸單號查詢，也不要換別家試。
5. CLI 回 exit 2「無法判別貨運公司」→ 轉述並詢問，不要加 `--auto`，也不要自動改走 17TRACK。

紀錄裡的物流商這次查詢失敗（逾時、缺 Playwright、站方改版）時，CLI 直接回報錯誤，不會改問別家。
只有站方明確回「查無資料」（紀錄可能過時）才會列出其他候選，同樣需要 `--auto` 才會送出。

## 支援範圍

| 貨運 | code | 方式 |
|------|------|------|
| 黑貓宅急便 | `tcat` | HTTP（資料保留 3 個月） |
| 嘉里大榮 | `kerrytj` | HTTP JSON API |
| 台灣宅配通 | `ecan` | HTTP（資料保留 2 個月） |
| 網家速配 | `pchome` | HTTP（PChome 自營車隊） |
| 富昇物流（momo） | `fusheng` | HTTP（momo 自營配送） |
| 蝦皮店到店 | `spx` | 需 Playwright（見下） |

**直連不支援**：中華郵政、全家店到店、7-ELEVEN 交貨便、新竹物流 —— 這四家的查詢頁都有圖形驗證碼，本 skill 不做驗證碼破解。

## 17TRACK（選配，補上述四家）

使用者自備 API key，設在環境變數 `PARCEL_KAU_A_17TRACK_KEY`：

```bash
python3 scripts/track.py <單號> --via-17track                          # 讓 17TRACK 自動判別
python3 scripts/track.py <單號> --via-17track --carrier chunghwa-post   # 指定貨運
```

`--carrier` 搭配 `--via-17track` 時可用：`chunghwa-post`、`famiport`、`seven-eleven`、`hct`（另有已直連的 tcat/kerrytj/ecan/pchome/spx）。

⚠️ **重要**：17TRACK 會消耗使用者自己的額度（免費 200 筆），所以**絕不自動使用** —— 只有明確加 `--via-17track` 才會呼叫。單號無法判別時 CLI 會提示這個選項，但不會自作主張去打。未設 key 時只有這條路不可用，直連五家照常。

⚠️ **全家 / 7-11 誠實揭露**：`famiport`／`seven-eleven` 兩個 carrier code 的 parser 只驗證過
17TRACK 官方文件寫的 schema，還沒有人拿真實包裹跑過這條路徑確認過。回報結果時如果是這兩家，
順口帶一句「這條路徑的資料形狀還沒拿真實包裹驗證過」，別講得像已經徹底驗證。

## momo 訂單的判斷

momo 出貨雙軌：自營走**富昇**（`--carrier fusheng`），委外則走黑貓／宅配通／新竹。
momo 頁面顯示的配送單號**就是承運商自己的託運單號**，所以看使用者訂單頁寫的「配送方式」直接選對應 adapter 即可；不確定就問使用者，不要自行猜。

## 蝦皮 SPX 的額外需求

SPX 需要 headless 瀏覽器：

```bash
pip install playwright && playwright install chromium
```

未安裝時只有 `spx` 不可用，其他五家照常。CLI 會直接告訴使用者缺哪一步。

**2026-10 起蝦皮的風控會擋下無頭瀏覽器的查詢**，CLI 會回「蝦皮擋下了這次自動查詢」（結束碼 3）。Agent 的處理方式：
- 照實轉述被擋，**不要說成查無資料**，也**不要嘗試任何繞過方式**（改瀏覽器特徵、逆向簽章、換 IP 等）
- 提供兩條路讓使用者選：自己用瀏覽器開 https://spx.tw/ 查；或自備 17TRACK key 走 `--carrier spx --via-17track`（單號會送到 17TRACK，要使用者明確同意）
- 如果 Agent 有權限操作使用者自己的瀏覽器，經使用者同意後可以代為在 spx.tw 查詢

## 查詢紀錄（v0.2.0 起）

**直連**查到結果時會記下「單號→哪家貨運」到 `~/.cache/parcel-kau-a/history.json`（權限 600）。走 `--via-17track` 不記錄（記成 17track 會讓下次去打付費 API）。
**目的是隱私**：下次查同一單號直接送那一家，不必問使用者是哪家、也不必對多家逐一嘗試。查無資料不記錄。
（`0600` 僅 POSIX 落實；Windows 上該檔繼承使用者目錄 ACL，實測可能被其他群組讀取。）

- 輸出出現 `（依查詢紀錄：…只查這一家）` = 這次只送了一家
- 輸出出現 `（這筆看起來已完成，可用 --forget xxx 刪除紀錄）` → **主動問使用者要不要清掉**，
  同意才跑 `--forget`。CLI 刻意不做互動提示（非互動硬規則 + agent 環境會卡死）
- 使用者若表示某次查詢不想留紀錄，加 `--no-record`
- 紀錄檔毀損時，下一次寫入會把它另存為 `history.json.corrupt-<時間>` 再重新記錄；CLI 會在 stderr 印出路徑

## 包裹名稱（v0.5.0 起）

使用者可以替查過的包裹取名稱，之後用名稱找。名稱只存在本機 `labels.json`（與 history.json 同目錄、同權限）。

- **名稱只能由使用者明確提供。** 不要從物流頁、訂單頁或商品名稱推測，也不要自己取名
- 「把這個單號命名為耳機」→ `<單號> --carrier <code> --label 耳機`（查到結果才會存名稱；查無資料不存）
- 「改名」→ `--rename <單號> 新名稱`；「拿掉名稱」→ `--clear-label <單號>`；兩者都不連線
- 已有名稱時再 `--label` 會覆蓋舊名稱，CLI 會印出「已將名稱從「舊」改為「新」」
- 使用者只記得末四碼（列表上顯示的）→ `--find 0001`；撞號時同樣列出全部讓使用者選
- `--find` 結果標「只剩名稱，查詢紀錄已不存在」→ 告訴使用者那筆紀錄已遺失，可用 `--clear-label` 清掉名稱，或重新查一次單號
- 「查一下耳機那個包裹」→ 先跑 `--find 耳機`（不連線）：
  - 找不到 → 告訴使用者，不要改用別的關鍵字亂試
  - 1 筆 → 轉述那筆快照；使用者要現況就用那筆的物流商查一次
  - 多筆（exit 8）→ **列出全部讓使用者選，絕不自行挑一筆**。使用者說「全部」時，先告知會送出幾次查詢再查
- 名稱檔毀損時寫入一律拒絕（exit 7），讀取時不顯示名稱；修正或改名該檔即可恢復，`--forget-all` 也會刪除它

## 未結案清單（v0.3.0 起）

使用者問「還有哪些包裹在路上／哪些還沒到」這類**不指名單號**的問題時，跑 `--pending`：

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

- 「未結案」＝ 查詢紀錄裡沒被判定為已完成的（判定同上面的 `looks_complete`）
- **這是本機紀錄的快照，不是即時貨態**——`--pending` 一個請求都不發。
  轉述時要講明「這是 X 時查到的狀態」；使用者想知道現在到哪了，就查那一筆或用 `--refresh-pending`
- 兩種時間不要混用：**物流事件**是包裹最後一次有動靜的時間（`N 天沒有新進度`）；**上次查詢**是這份資料多舊。
  上次查詢超過 7 天會標「資料可能過期」，轉述時一併說明
- 出現「物流事件已超過物流商查詢保留期」（黑貓 3 個月、宅配通 2 個月）→ **主動建議 `--forget`**，
  那種紀錄再查也查不到了，只會一直佔著清單

## 即時更新未結案包裹（v0.4.0 起，v0.5.0 加入範圍控制）

`--pending` 與 `--refresh-pending` 回答的是不同層次的問題——**先判斷使用者要的是快照還是現況**：

| 使用者問法 | 用哪個 | 為什麼 |
|---|---|---|
| 還有哪些包裹在路上／哪些還沒到／未結案包裹／我的包裹清單 | `--pending` | 純讀本機、不發請求，秒回；多數情況這樣就夠 |
| 幫我更新一下未結案包裹／未結案的都查一下最新進度／全部包裹現在到哪了／有沒有新進度 | `--refresh-pending` | 使用者明確要「現在」的狀態，措辭含「更新／現在／最新」 |
| 把耳機那幾個更新一下 | `--refresh-pending --match 耳機` | 只更新名稱符合的；命中多筆會先列出、exit 8 |

`--refresh-pending` 對未結案清單逐一即時查詢（序列不並行、無重試），查完印出依結果分類的彙整：

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

- 分類：**新結案**／**有新進度**（顯示「前 → 後」）／**無變化**／**已略過**／**查詢失敗**（附「仍保留上次成功快照：X 查詢」）
- 縮小範圍：`--match <名稱>`（命中多筆時要使用者明確說「全部」才加 `--all-matches`）、`--carrier <code>`、`--limit N`（依最新物流事件新到舊取前 N 筆）、`--dry-run`（只列出會查哪些，不連線、不寫入）
- 查到的結果會**覆寫該筆紀錄快照**；`--no-record` 可抑制寫入
- 某筆查詢失敗**不會**中止整批；只要有一筆失敗或快照存不進去，結束碼是 **6**，轉述時要講哪幾筆沒更新成功
- **批次更新永不呼叫 17TRACK**，即使設了 key（key 存在不等於這次同意）。這類項目列為已略過並附單筆查詢指令；要查就問使用者，同意後逐筆 `--via-17track`
- 轉述給使用者時明講「這是剛查到的最新狀態」，跟 `--pending` 的「上次查到的快照」區分清楚
- 包裹數多時就是照樣一筆一筆查，會花比較久——CLI 開查前會先講清楚幾筆，Agent 也先轉述筆數
- `--history` 維持列出全部（含已完成並標 `✓可刪`），兩者用途不同

## 結束碼

| 碼 | 意義 | Agent 該做的事 |
|---|---|---|
| 0 | 成功（查無資料也是 0） | 轉述結果 |
| 2 | 參數錯誤、無法判別物流商、名稱不合法 | 轉述原因並詢問，不要自行換參數重試 |
| 3 | 環境缺依賴（例如 SPX 缺 Playwright） | 轉述補救指令 |
| 4 | 站方頁面結構已變 | 引導回報 issue |
| 5 | 網路錯誤、逾時、站方錯誤 | 轉述；稍後再試 |
| 6 | 批次更新部分失敗 | 說明哪些成功、哪些沒更新 |
| 7 | `--label`／`--rename`／`--clear-label`／`--forget`／`--forget-all` 沒有完整保存或刪除（含另一個程序正在寫入）。一般查詢的紀錄存不進去仍是 0，只在 stderr 提示 | 轉述已完成與未完成的部分；可重試 |
| 8 | 需要使用者選擇（物流商候選、名稱多筆相符）；**未送出任何查詢** | 列出候選請使用者選 |

`--json` 時：單筆查詢輸出原本的結果物件，但單筆查詢的錯誤（未知 `--carrier`、無法判別、exit 3/4/5）仍是一般文字，**先看結束碼再解析**。其餘命令、物流商選擇（exit 8）與這些命令的錯誤輸出 `{"schema_version": 1, "operation": …}` envelope，錯誤帶 `ok: false` 與 `exit_code`；這些情況下 stdout 只有一份 JSON，提示在 stderr。

## 查詢網址失效時

站方改版會讓網址失效，訊息會明講（例：`查詢網址回 404，該網址可能已失效`）。
此時可用 `--endpoints` 看目前設定，並在 `~/.cache/parcel-kau-a/endpoints.json`
覆寫新網址 —— **不需要改程式**。引導使用者回報 issue 讓預設值一起更新。

## 回報結果時

- 查無資料是正常結果（單號未登錄、輸入錯誤、或超過站方保留期限），不是錯誤
- 出現「頁面結構已變」訊息代表站方改版，parser 需更新——請引導使用者回報 issue
- 輸出已含來源網址與查詢時間，轉述時保留
- 轉述單號時預設只講末四碼，使用者要完整單號才給

## 免責

本 skill 讀取各貨運公司的**公開查詢頁面**，非官方 API、未獲授權。僅供個人低頻查詢；站方改版即可能失效。使用者需自行遵守各站服務條款。
