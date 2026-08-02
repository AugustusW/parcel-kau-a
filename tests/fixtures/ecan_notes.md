# 宅配通 e-can 抓取紀錄（2026-08-02 實測）

- `query2.e-can.com.tw/` root 回 IIS 403.14（目錄不可列）— 不是防爬，是沒有 default document
- 真正入口（從主站 www.e-can.com.tw 連出）：`query2.e-can.com.tw/多筆查件A.htm`（Big5 編碼經典 ASP）
- POST 目標：`query2.e-can.com.tw/多筆查件_oo4o.asp`（URL 需 percent-encode 中文檔名）
  - 欄位：`txtMainID_1..10`（單號 12 碼，maxLength=12）+ `B1=查詢`
  - **表單編碼是 Big5**，urlencode 與回應解碼都要指定 big5
- 查無：回應含「很抱歉，查無資料」
- 資料保留：2 個月（頁面自述）
- UNVERIFIED：found case 表格欄位（項次/宅配單號/出貨單號/結案/最新狀態/細節說明/處理日期/營業所）已知表頭，實際 row 結構需真實單號校準
- 無 CAPTCHA、無 session token（2026-08-02 純 POST 打通）
