# 真實資料成交模擬驗證報告

- 產生時間：2026-11-20T23:22:39+08:00（台北）／2026-11-20T15:22:39Z
- 驗證期間：2026-11-20T18:44:16+08:00 → 預計結束 2026-11-20T21:44:16+08:00（台北），每 ~60 秒輪詢一次
- 性質：純模擬。測試單（`is_test=true`，放 `tickets/test/`）不進 journal、績效與風控；沒有任何簽名或送單，只讀公開 API。
- 判斷程式：`sim.apply_fills()`（只認 Data API `/v2/trades`；建立時穿價為 `rejected_post_only`）。獨立檢查用 `validation_report.oracle()`（只看掛單後的真實成交，算上下界）。「合理？」欄直接比對模擬成交與上下界，超出即標不合理。

## 規則更正

- 舊版 `sim.apply_fills` 把訂單簿穿價深度（`book_crossed_depth`）當作成交依據，過於樂觀；舊報告的「合理？」把這段深度加進上界，因此會把超出成交紀錄上下界的模擬成交標成合理。
- 舊結論「全部落在上下界內」有誤。典型例子：`will-ethereum-reach-1800-on-november-20-2026` 四張 YES 測試單，獨立上下界為 0/0，舊模擬卻判 10/10 成交（全部來自簿深穿價），期間沒有能成交的真實 taker 紀錄（僅見一筆 Yes BUY，不構成 YES 買單成交）。
- 現行規則：建立時限價穿過或碰到對手最佳價 → 直接拒單，不成交、不改用 taker、不記手續費、不自動改價。掛單後簿面變動不作為成交或拒單依據，只認真實成交（穿過限價，或同價且扣完排隊量）。撤單／結算前從掛單時間再抓一次成交。

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
| will-ethereum-reach-1800-on-november-2 | at_bid | YES@0.38 | 1287 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| will-ethereum-reach-1800-on-november-2 | bid_plus1 | YES@0.39 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| will-ethereum-reach-1800-on-november-2 | near_ask | YES@0.42 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| will-ethereum-reach-1800-on-november-2 | far_below | YES@0.33 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |
| will-ethereum-reach-1800-on-november-2 | no_bid_plus1 | NO@0.58 | 0 | 0 / 0（穿過 0，同價 0） | 0/10 | cancelled | 是 期間沒有任何能成交的真實成交 → 不成交，合理 |

## 成交明細（模擬判斷）

- 11-20 21:44:16 台北 `at_bid` YES@0.915 +10 股，依據 {'trades_through': 4472.646116999998, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `bid_plus1` YES@0.916 +10 股，依據 {'trades_through': 4472.646116999998, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `near_ask` YES@0.921 +10 股，依據 {'trades_through': 4472.646116999998, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `far_below` YES@0.91 +10 股，依據 {'trades_through': 4458.706116999999, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `no_bid_plus1` NO@0.079 +2.31 股，依據 {'trades_through': 0.0, 'trades_at_limit_after_queue': 2.31}
- 11-20 21:44:16 台北 `at_bid` YES@0.085 +10 股，依據 {'trades_through': 2042.1715060000001, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `bid_plus1` YES@0.086 +10 股，依據 {'trades_through': 2042.1715060000001, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `near_ask` YES@0.087 +10 股，依據 {'trades_through': 2042.1715060000001, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `far_below` YES@0.08 +10 股，依據 {'trades_through': 2031.2544830000002, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `at_bid` YES@0.605 +10 股，依據 {'trades_through': 33.235377, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `bid_plus1` YES@0.606 +10 股，依據 {'trades_through': 41.435377, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `near_ask` YES@0.609 +10 股，依據 {'trades_through': 41.435377, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `far_below` YES@0.6 +10 股，依據 {'trades_through': 33.235377, 'trades_at_limit_after_queue': 0.0}
- 11-20 21:44:16 台北 `no_bid_plus1` NO@0.391 +10 股，依據 {'trades_through': 36.250163, 'trades_at_limit_after_queue': 0.0}

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
- 「mid 碰到限價但沒有真實賣單成交」的測試單：6 張（no_bid_plus1×1次輪詢、at_bid×15次輪詢、bid_plus1×15次輪詢、near_ask×17次輪詢、far_below×4次輪詢、no_bid_plus1×1次輪詢）→ 模擬正確地沒有成交，mid 觸及不算成交。
- 排隊量的假設：同價位只在有真實成交消耗時才前進，不計撤單，所以 `at_bid` 類案例偏保守。
- 訂單簿穿價不再是成交依據。輪詢中曾看到對手價穿過限價的測試單：at_bid×11、bid_plus1×13、near_ask×17、far_below×3、at_bid×15、bid_plus1×15、near_ask×15、far_below×14、at_bid×16、bid_plus1×16、near_ask×17、far_below×15、no_bid_plus1×1、at_bid×13、bid_plus1×14、near_ask×17、far_below×2；其中無真實成交、模擬也不成交者 at_bid、bid_plus1、near_ask、far_below。

## 結論與發現的問題

- 全部 20 張測試單的模擬成交都落在獨立計算的上下界內：**是**。
- 沒有發現成交判斷錯誤。限制：樣本僅限本次驗證的幾個市場與時段；成交量大的市場才有足夠的對照。
- 已知限制：Data API 回報的是 taker 成交，無法看到 maker 端的撤單，排隊位置只能估；成交時間戳為秒級。
