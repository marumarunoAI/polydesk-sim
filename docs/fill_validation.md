# 真實資料成交模擬驗證報告

- 產生時間：2026-11-20T22:10:31+08:00（台北）／2026-11-20T14:10:31Z
- 驗證期間：2026-11-20T18:44:16+08:00 → 預計結束 2026-11-20T21:44:16+08:00（台北），每 ~60 秒輪詢一次
- 性質：純模擬。測試單（`is_test=true`，放 `tickets/test/`）不進 journal、績效與風控；沒有任何簽名或送單，只讀公開 API。
- 判斷程式：`sim.apply_fills()`。獨立檢查用 `validation_report.oracle()`（只看掛單後的真實成交，算上下界）。

## 市場

- `ethereum-above-1700-on-november-20-2026`：Will the price of Ethereum be above $1,700 on November 20?（驗證期間觀察到 23 筆 taker 成交）
- `bitcoin-above-64k-on-november-20-2026`：Will the price of Bitcoin be above $64,000 on November 20?（驗證期間觀察到 25 筆 taker 成交）
- `bitcoin-above-62k-on-november-20-2026`：Will the price of Bitcoin be above $62,000 on November 20?（驗證期間觀察到 43 筆 taker 成交）
- `will-ethereum-reach-1800-on-november-20-2026`：Will Ethereum reach $1,800 on November 20?（驗證期間觀察到 1 筆 taker 成交）

## 掛單與結果

| 市場 | 案例 | 方向@限價 | 掛單時排隊量 | 期間可成交量上界/下界 | 模擬成交 | 狀態 | 合理？ |
|---|---|---|---|---|---|---|---|
| ethereum-above-1700-on-november-20-202 | at_bid | YES@0.915 | 20 | 10 / 10（穿過 4472.65，同價 0） | 10/10 | filled | 是  |
| ethereum-above-1700-on-november-20-202 | bid_plus1 | YES@0.916 | 0 | 10 / 10（穿過 4472.65，同價 0） | 10/10 | filled | 是  |
| ethereum-above-1700-on-november-20-202 | near_ask | YES@0.921 | 0 | 10 / 10（穿過 4472.65，同價 0） | 10/10 | filled | 是  |
| ethereum-above-1700-on-november-20-202 | far_below | YES@0.91 | 0 | 10 / 10（穿過 4458.71，同價 0） | 10/10 | filled | 是  |
| ethereum-above-1700-on-november-20-202 | no_bid_plus1 | NO@0.079 | 0 | 2.31 / 2.31（穿過 0，同價 2.31） | 2.31/10 | partial_cancelled | 是  |
| bitcoin-above-64k-on-november-20-2026 | at_bid | YES@0.085 | 234 | 10 / 10（穿過 2042.17，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-64k-on-november-20-2026 | bid_plus1 | YES@0.086 | 0 | 10 / 10（穿過 2042.17，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-64k-on-november-20-2026 | near_ask | YES@0.087 | 0 | 10 / 10（穿過 2042.17，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-64k-on-november-20-2026 | far_below | YES@0.08 | 0 | 10 / 10（穿過 2031.25，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-64k-on-november-20-2026 | no_bid_plus1 | NO@0.913 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| bitcoin-above-62k-on-november-20-2026 | at_bid | YES@0.605 | 272.1 | 10 / 10（穿過 33.2354，同價 8.2） | 10/10 | filled | 是  |
| bitcoin-above-62k-on-november-20-2026 | bid_plus1 | YES@0.606 | 0 | 10 / 10（穿過 41.4354，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-62k-on-november-20-2026 | near_ask | YES@0.609 | 0 | 10 / 10（穿過 41.4354，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-62k-on-november-20-2026 | far_below | YES@0.6 | 105.65 | 10 / 10（穿過 33.2354，同價 0） | 10/10 | filled | 是  |
| bitcoin-above-62k-on-november-20-2026 | no_bid_plus1 | NO@0.391 | 0 | 10 / 10（穿過 36.2502，同價 0） | 10/10 | filled | 是  |
| will-ethereum-reach-1800-on-november-2 | at_bid | YES@0.38 | 1287 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| will-ethereum-reach-1800-on-november-2 | bid_plus1 | YES@0.39 | 0 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| will-ethereum-reach-1800-on-november-2 | near_ask | YES@0.42 | 0 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| will-ethereum-reach-1800-on-november-2 | far_below | YES@0.33 | 0 | 0 / 0（穿過 0，同價 0） | 10/10 | filled | 是  |
| will-ethereum-reach-1800-on-november-2 | no_bid_plus1 | NO@0.58 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |

## 成交明細（模擬判斷）

- 11-20 18:48:23 台北 `at_bid` YES@0.915 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 876.0}
- 11-20 18:48:23 台北 `bid_plus1` YES@0.916 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 922.02}
- 11-20 18:45:23 台北 `near_ask` YES@0.921 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 24.53}
- 11-20 18:55:23 台北 `far_below` YES@0.91 +10 股，依據 {'trades_through': 32.819149, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 0.0}
- 11-20 18:50:23 台北 `no_bid_plus1` NO@0.079 +2.31 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 2.31, 'book_crossed_depth': 0.0}
- 11-20 18:47:23 台北 `at_bid` YES@0.085 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 40.93000000000001}
- 11-20 18:47:23 台北 `bid_plus1` YES@0.086 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 738.93}
- 11-20 18:47:23 台北 `near_ask` YES@0.087 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 6418.93}
- 11-20 18:48:23 台北 `far_below` YES@0.08 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 5529.93}
- 11-20 18:46:23 台北 `at_bid` YES@0.605 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 202.96999999999997}
- 11-20 18:45:23 台北 `bid_plus1` YES@0.606 +8.2 股，依據 {'trades_through': 8.2, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 0.0}
- 11-20 18:46:23 台北 `bid_plus1` YES@0.606 +1.8 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 471.87}
- 11-20 18:44:23 台北 `near_ask` YES@0.609 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 428.0}
- 11-20 18:47:23 台北 `far_below` YES@0.6 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 586.5400000000001}
- 11-20 18:45:23 台北 `no_bid_plus1` NO@0.391 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 6158.93}
- 11-20 18:51:23 台北 `at_bid` YES@0.38 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 1226.0}
- 11-20 18:48:23 台北 `bid_plus1` YES@0.39 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 2434.0}
- 11-20 18:44:23 台北 `near_ask` YES@0.42 +5 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 5.0}
- 11-20 18:46:23 台北 `near_ask` YES@0.42 +5 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 2400.0}
- 11-20 19:11:47 台北 `far_below` YES@0.33 +10 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 0.0, 'book_crossed_depth': 30.0}

## 期間真實成交（taker 側，節錄每市場最近 15 筆）

**ethereum-above-1700-on-november-20-2026**（共 23 筆）

| 台北時間 | outcome | side | price | size |
|---|---|---|---|---|
| 11-20 19:00:56 | Yes | BUY | 0.9112581608 | 53.61 |
| 11-20 19:00:56 | Yes | BUY | 0.911 | 16.4 |
| 11-20 19:01:17 | Yes | SELL | 0.911 | 13.94 |
| 11-20 19:03:08 | Yes | BUY | 0.906 | 21.3 |
| 11-20 19:03:08 | Yes | BUY | 0.908 | 4.46 |
| 11-20 19:03:08 | Yes | BUY | 0.911 | 8.7 |
| 11-20 19:03:08 | Yes | BUY | 0.906 | 4.47 |
| 11-20 19:05:59 | No | SELL | 0.088 | 0.7 |
| 11-20 19:05:59 | Yes | SELL | 0.908 | 13.94 |
| 11-20 19:09:01 | No | BUY | 0.0929250223 | 4311.15 |
| 11-20 19:09:02 | No | SELL | 0.091 | 15.06 |
| 11-20 19:09:08 | No | BUY | 0.1059086129 | 34.93578 |
| 11-20 19:09:34 | No | BUY | 0.1089999969 | 21.834863 |
| 11-20 19:09:44 | No | BUY | 0.1135684162 | 44.026325 |
| 11-20 19:09:47 | Yes | BUY | 0.904122807 | 5.7 |

**bitcoin-above-64k-on-november-20-2026**（共 25 筆）

| 台北時間 | outcome | side | price | size |
|---|---|---|---|---|
| 11-20 18:37:46 | Yes | BUY | 0.0889999948 | 15.730338 |
| 11-20 18:38:55 | No | SELL | 0.9103500476 | 189.26 |
| 11-20 18:39:17 | No | SELL | 0.91 | 26.92 |
| 11-20 18:39:38 | Yes | BUY | 0.0899999987 | 53.222223 |
| 11-20 18:44:17 | Yes | BUY | 0.089 | 50.0 |
| 11-20 18:45:38 | No | BUY | 0.9159999938 | 10.917023 |
| 11-20 18:51:55 | No | BUY | 0.9310381304 | 5.048123 |
| 11-20 18:55:50 | No | SELL | 0.937 | 4.0 |
| 11-20 18:55:58 | No | BUY | 0.9415897636 | 743.423545 |
| 11-20 19:00:53 | Yes | SELL | 0.0567761665 | 851.66 |
| 11-20 19:00:53 | Yes | BUY | 0.0579999977 | 17.24138 |
| 11-20 19:00:58 | No | BUY | 0.95 | 5.2421 |
| 11-20 19:03:25 | No | BUY | 0.9503880452 | 420.880715 |
| 11-20 19:05:25 | No | BUY | 0.95 | 5.0 |
| 11-20 19:07:34 | Yes | BUY | 0.058 | 8.91 |

**bitcoin-above-62k-on-november-20-2026**（共 43 筆）

| 台北時間 | outcome | side | price | size |
|---|---|---|---|---|
| 11-20 18:42:11 | Yes | BUY | 0.6 | 10.0 |
| 11-20 18:43:16 | Yes | BUY | 0.6040288333 | 440.707437 |
| 11-20 18:44:20 | No | BUY | 0.395 | 15.55 |
| 11-20 18:44:25 | Yes | SELL | 0.605 | 8.2 |
| 11-20 18:44:38 | Yes | BUY | 0.607 | 427.96 |
| 11-20 18:44:38 | Yes | BUY | 0.6060016426 | 20.032949 |
| 11-20 18:45:41 | Yes | BUY | 0.6149999849 | 16.260163 |
| 11-20 18:45:58 | Yes | BUY | 0.613 | 19.99 |
| 11-20 18:50:38 | Yes | BUY | 0.5439999391 | 3.676471 |
| 11-20 18:53:25 | Yes | SELL | 0.548 | 3.67 |
| 11-20 19:00:20 | No | BUY | 0.4649999858 | 21.505377 |
| 11-20 19:01:08 | No | BUY | 0.462 | 8.06 |
| 11-20 19:03:17 | Yes | BUY | 0.5199999792 | 3.846154 |
| 11-20 19:07:11 | Yes | BUY | 0.4809999991 | 198.648649 |
| 11-20 19:07:47 | Yes | BUY | 0.4993474289 | 38.31 |

**will-ethereum-reach-1800-on-november-20-2026**（共 1 筆）

| 台北時間 | outcome | side | price | size |
|---|---|---|---|---|
| 11-20 19:06:19 | Yes | BUY | 0.3512194779 | 5.694445 |

## 額外檢查

- 成交紀錄 API 延遲（首次看到時間 − 成交時間戳）：中位數 457 秒，最大 954 秒，>120 秒者 78/92 筆。`sim.apply_fills` 每次從掛單時間重掃並以交易鍵去重，所以晚到的成交不會漏。
- 「mid 碰到限價但沒有真實賣單成交」的測試單：2 張（no_bid_plus1×1次輪詢、no_bid_plus1×1次輪詢）→ 模擬正確地沒有成交，mid 觸及不算成交。
- 排隊量的假設：同價位只在有真實成交消耗時才前進，不計撤單，所以 `at_bid` 類案例偏保守。
- 訂單簿穿價成交：只有輪詢時對手最佳賣價 ≤ 我們限價才算，數量依該檔深度，並先扣掉排在我們前面的買單量；同一批可見流動性只認領一次。
- 以訂單簿穿價成交的測試單 16 張，輪詢中看到穿價的次數：at_bid×11、bid_plus1×13、near_ask×17、at_bid×15、bid_plus1×15、near_ask×15、far_below×14、at_bid×16、bid_plus1×16、near_ask×17、far_below×15、no_bid_plus1×1、at_bid×13、bid_plus1×14、near_ask×17、far_below×2。

## 結論與發現的問題

- 全部 20 張測試單的模擬成交都落在獨立計算的上下界內：**是**。
- 沒有發現成交判斷錯誤。限制：樣本僅限本次驗證的幾個市場與時段；成交量大的市場才有足夠的對照。
- 已知限制：Data API 回報的是 taker 成交，無法看到 maker 端的撤單，排隊位置只能估；成交時間戳為秒級。
