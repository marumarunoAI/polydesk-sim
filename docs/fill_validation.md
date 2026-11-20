# 真實資料成交模擬驗證報告

- 產生時間：2026-11-20T17:57:59+08:00（台北）／2026-11-20T09:57:59Z
- 驗證期間：2026-11-20T17:54:53+08:00 → 預計結束 2026-11-20T17:57:53+08:00（台北），每 ~60 秒輪詢一次
- 性質：純模擬。測試單（`is_test=true`，放 `tickets/test/`）不進 journal、績效與風控；沒有任何簽名或送單，只讀公開 API。
- 判斷程式：`sim.apply_fills()`。獨立檢查用 `validation_report.oracle()`（只看掛單後的真實成交，算上下界）。

## 市場

- `bitcoin-above-60k-on-november-20-2026`：Will the price of Bitcoin be above $60,000 on November 20?（驗證期間觀察到 65 筆 taker 成交）
- `ethereum-above-1700-on-november-20-2026`：Will the price of Ethereum be above $1,700 on November 20?（驗證期間觀察到 14 筆 taker 成交）
- `ethereum-above-1800-on-november-20-2026`：Will the price of Ethereum be above $1,800 on November 20?（驗證期間觀察到 5 筆 taker 成交）
- `bitcoin-above-62k-on-november-20-2026`：Will the price of Bitcoin be above $62,000 on November 20?（驗證期間觀察到 5 筆 taker 成交）

## 掛單與結果

| 市場 | 案例 | 方向@限價 | 掛單時排隊量 | 期間可成交量上界/下界 | 模擬成交 | 狀態 | 合理？ |
|---|---|---|---|---|---|---|---|
| bitcoin-above-60k-on-november-20-2026 | at_bid | YES@0.884 | 5680 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-60k-on-november-20-2026 | bid_plus1 | YES@0.885 | 0 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-60k-on-november-20-2026 | near_ask | YES@0.887 | 0 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-60k-on-november-20-2026 | far_below | YES@0.879 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| bitcoin-above-60k-on-november-20-2026 | no_bid_plus1 | NO@0.113 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| ethereum-above-1700-on-november-20-202 | at_bid | YES@0.864 | 23 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| ethereum-above-1700-on-november-20-202 | bid_plus1 | YES@0.865 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| ethereum-above-1700-on-november-20-202 | near_ask | YES@0.884 | 0 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| ethereum-above-1700-on-november-20-202 | far_below | YES@0.859 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| ethereum-above-1700-on-november-20-202 | no_bid_plus1 | NO@0.116 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| ethereum-above-1800-on-november-20-202 | at_bid | YES@0.08 | 45.9 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| ethereum-above-1800-on-november-20-202 | bid_plus1 | YES@0.09 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| ethereum-above-1800-on-november-20-202 | near_ask | YES@0.1 | 0 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| ethereum-above-1800-on-november-20-202 | far_below | YES@0.03 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| ethereum-above-1800-on-november-20-202 | no_bid_plus1 | NO@0.9 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| bitcoin-above-62k-on-november-20-2026 | at_bid | YES@0.397 | 20 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-62k-on-november-20-2026 | bid_plus1 | YES@0.398 | 0 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-62k-on-november-20-2026 | near_ask | YES@0.407 | 0 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-62k-on-november-20-2026 | far_below | YES@0.392 | 25 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-62k-on-november-20-2026 | no_bid_plus1 | NO@0.593 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |

## 成交明細（模擬判斷）

- 11-20 17:56:29 台北 `at_bid` YES@0.884 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 12.0}
- 11-20 17:55:59 台北 `bid_plus1` YES@0.885 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 20.0}
- 11-20 17:55:29 台北 `near_ask` YES@0.887 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 12.0}
- 11-20 17:55:14 台北 `near_ask` YES@0.884 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 58.34}
- 11-20 17:54:59 台北 `near_ask` YES@0.1 +5 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 5.0}
- 11-20 17:55:14 台北 `near_ask` YES@0.1 +5 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 4245.0}
- 11-20 17:55:44 台北 `at_bid` YES@0.397 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 457.88}
- 11-20 17:55:44 台北 `bid_plus1` YES@0.398 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 457.88}
- 11-20 17:54:59 台北 `near_ask` YES@0.407 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 243.88}
- 11-20 17:56:29 台北 `far_below` YES@0.392 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 750.99}

## 期間真實成交（taker 側，節錄每市場最近 15 筆）

**bitcoin-above-60k-on-november-20-2026**（共 65 筆）

| 台北時間 | outcome | side | price | size |
|---|---|---|---|---|
| 11-20 17:50:23 | Yes | SELL | 0.883 | 8.0 |
| 11-20 17:50:23 | Yes | SELL | 0.883 | 8.0 |
| 11-20 17:50:23 | Yes | SELL | 0.884 | 8.0 |
| 11-20 17:50:23 | Yes | SELL | 0.884 | 8.0 |
| 11-20 17:50:23 | Yes | SELL | 0.884 | 8.0 |
| 11-20 17:50:23 | Yes | SELL | 0.884 | 8.0 |
| 11-20 17:50:23 | Yes | SELL | 0.884 | 8.0 |
| 11-20 17:50:23 | Yes | BUY | 0.884 | 25.51 |
| 11-20 17:50:23 | Yes | SELL | 0.883 | 8.0 |
| 11-20 17:50:25 | Yes | SELL | 0.883 | 8.0 |
| 11-20 17:51:10 | No | BUY | 0.113 | 5.23 |
| 11-20 17:53:50 | Yes | BUY | 0.882 | 5.35 |
| 11-20 17:53:50 | Yes | BUY | 0.882 | 20.0 |
| 11-20 17:54:05 | Yes | BUY | 0.882 | 10.0 |
| 11-20 17:57:22 | Yes | BUY | 0.8849999853 | 3.40113 |

**ethereum-above-1700-on-november-20-2026**（共 14 筆）

| 台北時間 | outcome | side | price | size |
|---|---|---|---|---|
| 11-20 17:40:25 | No | BUY | 0.1485 | 40.0 |
| 11-20 17:40:35 | Yes | BUY | 0.851 | 150.0 |
| 11-20 17:40:38 | Yes | BUY | 0.851 | 80.0 |
| 11-20 17:40:38 | Yes | BUY | 0.851 | 40.0 |
| 11-20 17:40:38 | Yes | BUY | 0.851 | 20.0 |
| 11-20 17:40:38 | Yes | BUY | 0.851 | 70.0 |
| 11-20 17:40:40 | Yes | BUY | 0.851 | 20.0 |
| 11-20 17:40:46 | Yes | BUY | 0.851 | 90.0 |
| 11-20 17:40:46 | Yes | BUY | 0.851 | 112.03 |
| 11-20 17:40:59 | Yes | BUY | 0.851 | 400.0 |
| 11-20 17:43:08 | Yes | BUY | 0.867 | 9.22 |
| 11-20 17:43:10 | Yes | BUY | 0.867 | 11.0 |
| 11-20 17:43:13 | Yes | BUY | 0.867 | 6.0 |
| 11-20 17:48:59 | No | SELL | 0.122 | 30.0 |

**ethereum-above-1800-on-november-20-2026**（共 5 筆）

| 台北時間 | outcome | side | price | size |
|---|---|---|---|---|
| 11-20 17:40:40 | No | BUY | 0.92 | 20.0 |
| 11-20 17:43:08 | No | BUY | 0.92 | 9.22 |
| 11-20 17:43:10 | No | BUY | 0.92 | 11.0 |
| 11-20 17:43:13 | No | BUY | 0.92 | 6.0 |
| 11-20 17:52:16 | Yes | BUY | 0.1 | 25.9 |

**bitcoin-above-62k-on-november-20-2026**（共 5 筆）

| 台北時間 | outcome | side | price | size |
|---|---|---|---|---|
| 11-20 17:43:28 | Yes | BUY | 0.4 | 10.43 |
| 11-20 17:46:55 | Yes | BUY | 0.3879999379 | 5.15464 |
| 11-20 17:47:13 | Yes | BUY | 0.386 | 20.89 |
| 11-20 17:50:43 | Yes | BUY | 0.39 | 30.0 |
| 11-20 17:50:43 | Yes | BUY | 0.39 | 6.5 |

## 額外檢查

- 成交紀錄 API 延遲（首次看到時間 − 成交時間戳）：中位數 319 秒，最大 889 秒，>120 秒者 88/89 筆。`sim.apply_fills` 每次從掛單時間重掃並以交易鍵去重，所以晚到的成交不會漏。
- 「mid 碰到限價但沒有真實賣單成交」的測試單：1 張（bid_plus1×9次輪詢）→ 模擬正確地沒有成交，mid 觸及不算成交。
- 排隊量的假設：同價位只在有真實成交消耗時才前進，不計撤單，所以 `at_bid` 類案例偏保守。
- 訂單簿穿價成交：只有輪詢時對手最佳賣價 ≤ 我們限價才算，數量依該檔深度。

## 結論與發現的問題

- 全部 20 張測試單的模擬成交都落在獨立計算的上下界內：**是**。
- 沒有發現成交判斷錯誤。限制：樣本僅限本次驗證的幾個市場與時段；成交量大的市場才有足夠的對照。
- 已知限制：Data API 回報的是 taker 成交，無法看到 maker 端的撤單，排隊位置只能估；成交時間戳為秒級。
