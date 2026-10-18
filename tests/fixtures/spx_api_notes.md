# SPX tracking API fixtures

擷取日期：2026-10-18。來源：`spx.tw` 首頁查詢框按「追蹤」後，頁面自己發出的
`GET https://spx.tw/api/v2/fleet_order/tracking/search?sls_tracking_number=<單號>|<簽章>`
的回應（簽章由站方前端 JS 計算，本專案不重現它）。

- `spx_api_found.json`：一件已配達的真實包裹（使用者同意使用）。單號已換成假值
  `TW0000000000002`，`recipient_name`／`phone` 已清空（擷取時本來就是空字串）。
  `tracking_list[].timestamp` 是 Unix 秒，`message` 是中文貨態，回應裡沒有地點欄位。
- `spx_api_not_found.json`：用不存在的假單號 `TW0000000000001` 查詢的原始回應。
  站方對查無資料回 HTTP 200、`retcode: -1000`、訊息「Server error」、`data: {}`——
  訊息字面像伺服器錯誤，但這是查無資料時的實際回應。
- `spx_api_blocked.json`：無頭 Chromium 的同一個請求，站方回 HTTP 403 與此內容
  （`action_type: 2`、`redirect_to_error_page: true`），連續 3 次皆同。已移除每次
  不同的 `tracking_id`。本專案不繞過這個風控，只把它回報為「蝦皮擋下了自動查詢」。

網址列在查到資料後會變成 `spx.tw/detail/<單號>`，那是頁面內的前端路由；擷取時記錄了
全部請求，沒有任何請求送到伺服器的 `/detail/`（robots.txt 禁止的路徑）。
