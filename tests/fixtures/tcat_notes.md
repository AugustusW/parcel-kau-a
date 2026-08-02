# T-cat 抓取紀錄（2026-08-02 實測）

- GET https://www.t-cat.com.tw/Inquire/Trace.aspx → ASP.NET WebForm（__VIEWSTATE/__VIEWSTATEGENERATOR/__EVENTVALIDATION 三件套）
- POST 同 URL，欄位 `ctl00$ContentPlaceHolder1$txtQuery1..10`（一次最多 10 筆）+ `ctl00$ContentPlaceHolder1$btnSend=確認送出`
- 假單號 903123456789 → 回應含 `<script>alert('903123456789 非有效單號 !!');</script>`（server 端 checksum 驗證）+ `<!-- 查詢結果1 -->` 空註解
- UNVERIFIED：有效單號的結果表 HTML 未取得（需真實單號），found-case parser 待校準

- **匿名化**：本 fixture 取自真實查詢，單號已代換為 900000000001、門市名已代換為「示範門市」（OSS 發佈前必做，2026-08-02 code-reviewer Critical）

- `tcat_found_multi.html`：真實多筆歷程（3 筆貨態，2026-08-02 擷取）。單號代換為 900000000003、營業所代換為甲/乙營業所。鎖住多筆列結構（首列多一格 rowspan 單號欄）——單筆 fixture 測不到這點。
