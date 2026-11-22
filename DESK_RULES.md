# DESK_RULES.md — Polymarket 模擬交易台（唯一的策略存放處）

來源：Argona《How to Build Your Own Polymarket Trading Desk With Fable 5.2》
https://x.com/Argona0x/status/2121600686374699125 （原文存於 argona_article.txt）
版本：v1.2（2026-11-22 台北更新；v1.0 建立於 2026-11-20）
階段：**只模擬**。不下真單、無錢包、無私鑰、無 Polymarket 帳號。只讀公開資料。
虛擬資金：**1,000 USD**。時間一律記台北時間（同時保留 UTC 原始值）。

任何規則修改都必須：在 journal/rule_changes.md 記一行（日期、改了什麼、原因），並通知使用者。不得為了讓數字好看而改規則。

## 十一條總規則
1. **盲算順序**：先寫 `fair/<slug>.json`（含時間戳），才准讀 `evidence/` 或 `board/`。必須由程式強制（fair 檔不存在或時間戳晚於讀價 → 拒絕）。
2. **只掛 maker**（限價單，等成交）。參考：加密市場 taker 費 = 0.07 × p × (1−p)。
3. 只在 `|fair − mid| > fee + 2 pp` 且 tape 不否決時交易。
4. 部位：Kelly × 0.1–0.25。單一觸價市場 ≤ 資金 3%；單一「確定性」部位 ≤ 2–5%。
5. 尚未發生的事，**絕不在 0.97 以上買**。
6. 任何輸入為「unavailable」→ **SKIP**。缺資料不等於零。
7. 不碰短於日線的市場。**不碰體育。**
8. 只有一個席位能花錢，就是使用者（本階段：沒有人能花真錢）。
9. 每日虧損上限 2% 資金；觸發 → 當日唯讀至隔天。
10. 每一筆預測都寫入 journal，有沒有交易都要記。
11. （本台加訂）**不碰選舉與政治市場。**

## 五個策略

### S1 觸價市場（Liquidation Magnet）
- 市場：「BTC/ETH 本月會不會觸及 $X」這類 barrier（任一 Binance 1 分 K 觸到即算）。
- 公平值：`touch ≈ 2 × N(−|ln(X/S)| / (σ√T))`，由程式計算；加上歷史基準率。大事件（如 FOMC）前 σ 要放寬或用 Deribit 隱含波動率。
- 訊號：價格與關卡之間有 ≥ $10B 的清算叢集（tape）。
- 進場：差距 > fee + 2 pp 且 tape 同方向，限價單。新上架市場當天早上就要算。
- 部位：Kelly × 0.1–0.25，每個 barrier ≤ 3%，所有 BTC barrier 合計 ≤ 6%。
- 出場：差距 < 0.5 pp，或到期前 24 小時。
- 停用：滿 30 筆已結算後，策略 Brier 不優於市場 Brier。

### S2 賣樂透（Longshot Tax）
- 市場：「2026 年 BTC 會到多少」等遠檔位，買 NO。
- 訊號：市場 YES 價 ≥ 2 × fair_touch。
- 否決：關卡附近有清算叢集、資金費率極端（≥ 5 × 0.01%/8h）、窗口內有 Fed 會議、山寨幣市場到期前有代幣解鎖。
- 進場：NO 掛限價單，絕不在 0.97 以上。
- 部位：每個 barrier ≤ 3%。
- 出場：邊際 < 0.5 pp、到期前 24 小時，或出現否決條件即出場。
- 停用：單筆虧損大於本策略三個月累積收益。

### S3 同日梯子與鏡像（Noon Print and the Mirror）
- 市場：「BTC 在 X 日高於 $X」，以 12:00 ET（台北 01:00）Binance 1 分 K 收盤結算。
- 公平值：同日各檔用 `N(d2)`；鏡像檢查 hit ≈ 2 × above，比值 < 1.6 或 > 2.4 代表有一邊錯價。
- tape 決定方向：中午前的總經數據、資金費率與 OI、前一日 ETF 流量。
- 進場：差距 > fee + 2 pp，限價單，部位同 S1。
- 出場：持有到中午結算，或邊際 < 0.5 pp。
- 停用：同 S1 的 Brier 門檻。不碰短於日線。

### S4 盤前 FDV（Premarket Peek）
- 市場：「<token> 上線一天後 FDV 高於 $X」。
- 訊號：`implied_FDV = 盤前價 × 總供給`，打 30% 折扣後比對每個檔位。
- 進場：只做離折後 implied FDV ≥ 25% 的檔位，限價單。
- 部位：≤ 可見深度的 5–10%。
- 出場：持有至結算；盤前沒成交或上線日期延後就離場。
- 停用：沒有盤前市場，或上線延後超過市場截止日。

### S5 已公布的事實（Written Fact）
- 訊號：結果已經在市場自己的結算來源公布，但市場尚未結算。
- 進場：價格 ≤ 0.985、距結算 ≤ 7 天、年化報酬 ≥ 50%。
- 排除：措辭模糊、描述裡有「clarifications」、有爭議中。體育、選舉、政治一律排除。
- 部位：資金 2–5%。
- 出場：結算。
- 停用：任何一筆在來源公布前就進場 → 該策略暫停。

## 資料來源（本階段只用免費公開資料，不用 Minara 等付費工具）
- Polymarket：Gamma API（市場清單、規則）、CLOB API（訂單簿、中價）。
- Binance：K 線、資金費率、OI（公開 API）。
- ETF 流量：Farside。隱含波動率：Deribit 公開 API。
- 清算叢集：CoinGlass 免費全市場加總熱力圖（Coin mode，例如 https://www.coinglass.com/LiquidationHeatMap/BTC?mode=coin ，Model 1，時間範圍固定 1 個月）。交易員每日把 BTC、ETH 的清算價位與金額寫入 `evidence/liquidation_clusters.input.json`，程式只讀此檔，不爬網、不呼叫付費 API。缺檔、不是當天台北日期、或格式不符 → unavailable → 依規則 6 SKIP。門檻維持文章的 $10B，不因免費圖上較少見而調降（2026-11-22 使用者決定）。
- 盤前價格、交易所流向：免費來源沒有 → 記「unavailable」→ 依規則 6 SKIP 交易，但**公平值與市場價仍照記 journal**，讓 Brier 可以比較。

## 每週檢查（每週日）
用 journal 計算各策略 `brier_desk` 對 `brier_market` 與虛擬損益；打輸市場的策略觸發其停用規則，並記錄在 journal。

---

## 附錄：實作參數（v1.1，實作細節，**不是規則修改**）
以下是程式員為了讓規則能執行而定的操作值，經 PM模擬-負責人確認（2026-11-20）。正文規則一字未動；要改這些值請由負責人決定。

| 項目 | 實作值 | 程式位置 |
|---|---|---|
| 歷史基準率 | 只記在 `fair/<slug>.json`（`base_rate`），**不混進 fair 數字**，fair 只用公式 | `quant.base_rate()` |
| S2「遠檔位」 | `fair_touch ≤ 10%` 且 市場 YES ≥ 2 × fair | `strategies.FAR_STRIKE_MAX_FAIR` |
| S2 資金費率極端 | `|funding| ≥ 5 × 0.01%/8h` | `strategies.FUNDING_EXTREME_8H` |
| S3 tape 否決 | 資金費率與前一日 ETF 淨流量**同時**與交易方向相反才否決 | `strategies.decide_s3()` |
| S3 鏡像區間 | hit/above 比值 < 1.6 或 > 2.4 標記 | `strategies.MIRROR_LO/HI` |
| Kelly 倍數 | 0.10（允許範圍 0.10–0.25） | `risk_gate.KELLY_MULT` |
| 單一 barrier 上限 | 3% 資金 | `risk_gate.MAX_PER_BARRIER` |
| 同資產合計上限 | reach + above 同資產**合併**計 6%；BTC、ETH 各自計 | `risk_gate.MAX_ASSET_BARRIERS` |
| 確定性部位 | 2–5%（S5，第一版未啟用） | `risk_gate.CERTAIN_*` |
| 買價上限 | 絕不在 0.97 以上買 | `risk_gate.MAX_BUY_PRICE` |
| 每日虧損停機 | 當日損益 ≤ −2% 資金 → 當日唯讀（以台北日計） | `risk_gate.check_daily_loss()` |
| 進場門檻 | `|fair − mid| > 0.07·mid·(1−mid) + 2pp`（fee 取 taker 公式，保守）；模擬成交實際收 maker 費 0 | `strategies._base()`、`fees.py` |
| maker 掛價 | 同側最佳買價 +1 tick，不碰對手最佳賣價，且不高於 `fair側 − 門檻`、不高於 0.97 | `strategies.limit_for()` |
| 波動率 σ | Binance 1h K 線 720 根（30 天）實現波動率；窗口內有 FOMC 決議日 → Deribit DVOL | `quant.price_one()` |
| 觸價已發生 | 上架後 Binance 已觸及關卡 → fair = 1 | `quant.extremes_since()` |
| 市場範圍 | BTC/ETH 觸價（reach/hit/dip）與同日 above；排除 5m/15m/1h/4h、體育、選舉、政治 | `board.py`、`risk_gate.excluded()` |
| 出場觸發 | 邊際 < 0.5pp（持有側 fair − mid）；S1/S2 距到期 ≤ 24h；S2 否決條件出現（窗口內 FOMC、資金費率極端、關卡 ±3% 內有 ≥ $10B 叢集）；S3 持有到中午結算、不適用 24h | `exits.py` |
| 出場做法 | 掛 maker 賣單：自家側最佳賣價 −1 tick（價差僅 1 tick 則排隊在最佳賣價）；成交只認真實成交紀錄判定，不假設以 mid 成交、不吃單；出場單掛到到期，沒成交的部分持有到結算 | `sim.place_exit()` |
| 輸入 unavailable 時的出場 | 邊際無法評估就不出場（只套用時間規則），不當成出場理由 | `exits.exit_reason()` |
| S1 清算叢集（tape） | 價格與關卡之間（含關卡）清算總額 ≥ $10B 才算確認；買 YES 需確認，買 NO 需無叢集；資料源缺 → SKIP，**不用任何代理指標**。來源見下一列 | `strategies.liq_between()` |
| S2 清算否決 | 關卡 ±3% 內有 ≥ $10B 叢集 → 否決 | `strategies.LIQ_NEAR_PCT` |
| 清算叢集資料格式 | 交易員每日寫入 `evidence/liquidation_clusters.input.json`（`asof_taipei` 必須是當天台北日期；`range` 固定為 `1 month`；各資產含 `spot` 與 `levels: [{"price":…, "usd":…}]`，`usd` 單位為美元，網頁寫 84M 就填 84000000）。程式讀入 `evidence.assets.<A>.liquidation_clusters.value`。來源：CoinGlass Coin mode、Model 1、1 個月。不爬網、不付費。缺檔、過期或格式不符 → unavailable（2026-11-22 使用者決定用免費加總圖，門檻不改） | `strategies.liq_clusters_value()` |
| 費率表（依下單/事件時間切換） | 2026-11-20 23:59 UTC 前 Crypto taker 0.07；起 0.01（其他不變：maker 0，公式 fee = shares×rate×p×(1−p)）。進場門檻 fee 用決策當下的費率 | `fees.py` |
| 成交判定 | 只認真實 taker 成交穿過/等於限價（同價先扣排隊量）；訂單簿穿價不算成交。建立時限價會穿過或碰到對手最佳價的單一律 post-only 拒單（不成交、不改 taker、手續費 0、不自動改價，原因記在 journal）。成交紀錄有延遲（實測中位數約 457 秒、最大約 954 秒），掛單一律從下單時間重掃、結算前再重掃一次；成交紀錄 API 失敗則該張單本輪不更新、不撤單、不結算（e4b8bf5，2026-11-20 修正，更保守） | `sim.apply_fills()` |
| 資金費率來源順序 | Binance → OKX → Deribit → Hyperliquid（取第一個可用） | `strategies.FUNDING_ORDER` |
| BTC ETF 流量 | Farside（farside.co.uk/btc、/eth，一般瀏覽器 UA，由共用電腦抓取；US$m），前一美東交易日各基金全部更新才輸出，否則 unavailable → SKIP；不回退其他來源（c109942，2026-11-20 使用者決定） | `evidence.etf_flow()` / `farside_etf_prev_day()` |
| 總經日程 | Nasdaq 經濟日曆（美國 CPI/PPI/NFP/PCE/GDP/FOMC/零售/ISM/失業金），未來 8 天 | `evidence.macro_events()` |
