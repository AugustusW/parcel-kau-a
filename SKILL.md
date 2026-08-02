---
name: parcel-kau-a
description: Track Taiwan parcel deliveries by tracking number. Use when the user asks about a package's delivery status, shipping progress, or where a parcel is — including phrases like 查包裹, 包裹進度, 貨態, 到了沒, tracking, or when they paste a Taiwanese courier tracking number. Supports 黑貓宅急便 (T-cat), 嘉里大榮 (Kerry TJ), 台灣宅配通 (e-can), 網家速配 (PChome Express), 富昇物流／momo 自營 (Fusheng), and 蝦皮店到店 (Shopee SPX). 中華郵政, 全家, 7-11 交貨便, and 新竹物流 cannot be read directly (CAPTCHA) but are reachable via 17TRACK if the user supplies their own API key.
---

# parcel-kau-a

輸入台灣包裹單號，回配送時間軸。無需 API key。

## 用法

```bash
python3 scripts/track.py <單號>                      # 自動判別貨運公司
python3 scripts/track.py <單號> --carrier tcat       # 指定（建議：省下無謂請求）
python3 scripts/track.py <單號> --json               # 機器可讀輸出
python3 scripts/track.py --history                   # 列出查詢紀錄
python3 scripts/track.py --forget <單號>             # 刪除某筆紀錄
python3 scripts/track.py --endpoints                 # 列出目前生效的查詢網址
```

`--carrier` 可用值：`tcat`（黑貓）、`kerrytj`（嘉里大榮）、`ecan`（宅配通）、`pchome`（網家速配）、`fusheng`（富昇/momo）、`spx`（蝦皮店到店）。

## 判別規則

黑貓、嘉里大榮、宅配通、網家速配、富昇的單號同為 12 碼數字，**格式無法區分**——不指定 `--carrier` 時會依序查詢、命中即停（最壞 5 次請求）。蝦皮 SPX 為 `TW` 開頭，可由格式判定。

**使用者若提到貨運公司名稱，請務必帶上 `--carrier`。**

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

## momo 訂單的判斷

momo 出貨雙軌：自營走**富昇**（`--carrier fusheng`），委外則走黑貓／宅配通／新竹。
momo 頁面顯示的配送單號**就是承運商自己的託運單號**，所以看使用者訂單頁寫的「配送方式」直接選對應 adapter 即可；不確定就讓它自動判別。

## 蝦皮 SPX 的額外需求

SPX 需要 headless 瀏覽器：

```bash
pip install playwright && playwright install chromium
```

未安裝時只有 `spx` 不可用，其他三家照常。CLI 會直接告訴使用者缺哪一步。

## 查詢紀錄（v0.2.0 起）

**直連**查到結果時會記下「單號→哪家貨運」到 `~/.cache/parcel-kau-a/history.json`（權限 600）。走 `--via-17track` 不記錄（記成 17track 會讓下次自動判別去打付費 API）。
**目的是隱私**：下次查同一單號直接送那一家，不必對五家逐一嘗試。查無資料不記錄。

- 輸出出現 `（依查詢紀錄：…只查這一家）` = 這次只送了一家
- 輸出出現 `（這筆看起來已完成，可用 --forget xxx 刪除紀錄）` → **主動問使用者要不要清掉**，
  同意才跑 `--forget`。CLI 刻意不做互動提示（非互動硬規則 + agent 環境會卡死）
- 使用者若表示某次查詢不想留紀錄，加 `--no-record`

## 查詢網址失效時

站方改版會讓網址失效，訊息會明講（例：`查詢網址回 404，該網址可能已失效`）。
此時可用 `--endpoints` 看目前設定，並在 `~/.cache/parcel-kau-a/endpoints.json`
覆寫新網址 —— **不需要改程式**。引導使用者回報 issue 讓預設值一起更新。

## 回報結果時

- 查無資料是正常結果（單號未登錄、輸入錯誤、或超過站方保留期限），不是錯誤
- 出現「頁面結構已變」訊息代表站方改版，parser 需更新——請引導使用者回報 issue
- 輸出已含來源網址，轉述時保留

## 免責

本 skill 讀取各貨運公司的**公開查詢頁面**，非官方 API、未獲授權。僅供個人低頻查詢；站方改版即可能失效。使用者需自行遵守各站服務條款。
