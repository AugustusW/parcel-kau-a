# 網家速配（PChome Express）抓取紀錄（2026-08-02 實測）

- 公司：網家速配股份有限公司，PChome Online 2018 年成立之 100% 自營車隊（非外包）
- 查詢頁：`https://www.gopchome.com.tw/delivery/historyList/<單號>` —— **單號在 URL path**
- 純 GET、SSR 回完整 HTML；**無 CAPTCHA、無登入、無 XHR、無簽章**；robots.txt 全開放
- 結果結構（div 表格非 <table>）：
  - `.table` > `.tr.top`（表頭：包裹號碼 / 運送狀態 / 資料登入時間）
  - `.tr` > 第一個 `.td` = 單號，`.innerItem` > `.list` > `.td` = 狀態、時間
- 查無：狀態欄文字為「查無此單」
- 單號 12 碼數字 → **與黑貓/嘉里/宅配通撞號**，自動判別輪詢從 3 家增為 4 家
- UNVERIFIED：found case 的 `.innerItem` 多筆歷程結構需真實命中單號校準
