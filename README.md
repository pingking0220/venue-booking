# 力行國小場地預約

取代臺北市校務行政系統（eschool）「C02 場地管理／申請場地借用」的場地預約網頁。
單一 `index.html`，GitHub Pages 靜態網站；資料庫與登入沿用頒獎座位系統的 Firebase 專案 **`award-seat`**
（同一套 @lsps.tp.edu.tw Google 登入、同一份 `/roles` 身分，`admin` 即場地管理者）。

- 使用說明：`guide.html`（截圖由 `tools/guide_shots.py` 產生）
- 示範模式：網址加 `?demo`，不連 Firebase，資料只存在瀏覽器，可切換「老師／審核人／管理者」

## 資料結構（Realtime Database，`/venue` 底下）

| 路徑 | 內容 |
|---|---|
| `places/{pid}` | 場地：name, site, order, active（開放借用）, needApproval, approvers `{email(.→,): true}`, notes |
| `config/semesterEnd` | 學期結束日，「每週重複」預設借到這天 |
| `bk/{YYYY-MM-DD}/{pid}/{節次}` | 一格預約：title, by(email), name, unit, status(`ok`/`wait`), at, series?, time?, note?, src?(`eschool`) |
| `notice/{email(.→,)}/{id}` | 退回／取消通知：text, at |

節次 key：`m` 早自習、`p1`–`p7`、`nap` 午休、`aft` 放學後、`eve` 晚上（時間見 `index.html` 的 `SLOTS`）。
以「格子」為 key，同一格只能有一筆 → 衝突由資料庫結構與安全規則保證；多格一次寫入是原子性的（一格衝突整批失敗）。

## 安全規則

兩個系統共用同一個資料庫，規則只有一份，放在 **award-seating** repo 的 `database.rules.json`。
`venue` 節點由 `tools/build_rules.py` 產生後合併進去：

```bash
python tools/build_rules.py ../award-seating/database.rules.json
cd ../award-seating && firebase deploy --only database --project award-seat
```

規則測試（Firebase 模擬器，需 Java）：

```bash
cp ../award-seating/database.rules.json tools/rules-test/ && cd tools/rules-test && npm install @firebase/rules-unit-testing@3 firebase@10
firebase emulators:exec --only database --project demo-venue "node test.mjs"
```

## 其他工具

- `tools/test_flow.py`：示範模式流程測試（Playwright）
- `tools/import_eschool.py`：把校務系統「已通過」的預約匯入（公開 API，不需登入）；先試跑，確認後加 `--write`
- `seed-places.json`：初始場地（取自校務系統「可內借」的場地，合併重複的桌球教室）
