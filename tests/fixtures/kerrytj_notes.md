# Kerry TJ 抓取紀錄（2026-08-02 實測）

- 前端 `kerrytj.com/zh/checking` 是 Vue 頁：單號進 sessionStorage → `checking_result` 頁呼叫 API
- 真正端點：`POST https://www.kerrytj.com/api/Tracking/GetTracking`，JSON payload:
  `{"trackType":"0","trackNo":[{"idxTxt":"一","value":"<單號>"}, ...共5格空字串]}`
- 查無：list[].course[0].statusId == "ERROR"（statusIdName 查不到該筆資料）+ 頂層 errTrackNo 含該單號
- found case：course[] 有多筆（statusIdName / processDepotIdName / processCargoCrtDate+Time）
- UNVERIFIED：found case 的 date/time 數字格式（疑 YYYYMMDD/HHMMSS int）需真實單號校準
- API 無 CAPTCHA、無簽章（2026-08-02 純 curl 打通）
