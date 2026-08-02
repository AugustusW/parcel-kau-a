# 富昇物流（momo 自營）抓取紀錄（2026-08-02 實測）

- 公司：富昇物流，momo（富邦媒體）100% 持股自營車隊。官網 `www.fs.com.tw`
  （注意：`fusheng-express.com.tw` DNS 不存在，勿用）
- 查詢頁：`GET https://tmsvendor.fs.com.tw/search-result?ship_num1=<單號>` —— 單號在 query string
- 純 SSR、無 CAPTCHA、無登入、零 XHR（Playwright network log 驗證）
- found 結構：`.panel-heading .list_title` 有 [託運單號]/[最新狀態]/[最新時間] 摘要；
  完整歷程在 `.panel-body ul li`，每個 li 為「時間 &nbsp&nbsp&nbsp 狀態 &nbsp&nbsp&nbsp 站點」
- 查無：頁面含「尚未能查詢」
- 單號：官方表單接受 `\d{10,32}`，實務 momo 配送單號 12 碼。本 adapter 限縮為 12 碼以降低撞號
- **momo 雙軌**：自營走富昇；委外走黑貓/宅配通/新竹，且 momo 顯示的單號就是承運商託運單號，
  因此委外訂單直接用對應 adapter 查即可，不需 momo 專屬邏輯
- **匿名化**：fixtures 單號代換為 900000000004、站名代換為甲配送站/乙分轉中心
