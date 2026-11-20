# polydesk-sim

Polymarket 加密市場（BTC/ETH）**模擬**交易台。**只模擬、不下真單**：沒有錢包、沒有私鑰、沒有簽名或送單程式、不登入 Polymarket，只讀免費公開資料，不建定時任務。

策略與風控規則只寫在 [DESK_RULES.md](DESK_RULES.md)，**由負責人決定，程式員不改**。方法參考 Argona〈How to Build Your Own Polymarket Trading Desk〉（https://x.com/Argona0x/status/2121600686374699125），不用文中的付費工具。

第一版範圍：S1 觸價、S2 賣樂透、S3 同日梯子與鏡像。S4 盤前 FDV、S5 已公布事實排在第二版。

## 安裝與執行
```
pip install requests          # 其餘只用標準函式庫，Python 3.10+
python run_day.py             # 跑完一天（交易員每天台北 13:30 手動執行）
python run_day.py --dry-run   # 完整跑一遍但不動真實 fair/tickets/journal（複製到暫存資料夾，結束即刪）
python run_day.py --outdir D  # 全部輸出改放資料夾 D
python brier.py [2026-W47]    # 每週彙總（不帶參數＝全部）
python -m unittest discover -s tests
```
單獨步驟：`python board.py`（掃市場＋訂單簿）、`python evidence.py`、`python settle.py`。

## run_day.py 的順序
1. `settle.py`：到期市場用 Gamma 結算結果回填 journal 的 result、brier_desk、brier_market、虛擬損益。
2. `board.scan_markets()`：Gamma `/events/keyset`（tag bitcoin=235、ethereum=39）找開放中的觸價（reach/hit/dip）與同日 above 市場；排除短於日線（5m/15m/1h/4h）、體育、選舉、政治。
3. `blind.write_blind()` → `blind/<slug>.json`：只有規則原文、關卡、到期、結算來源，**不含任何價格**。
4. `quant.run()`：只讀 `blind/`，用 Binance 公開 K 線（`data-api.binance.vision`）算 σ（1h×30 天實現波動率），窗口內有 FOMC 決議日改用 Deribit DVOL；觸價 `2·N(−|ln(X/S)|/(σ√T))`（上架後已觸價 → 1），above 用 `N(d2)`；寫 `fair/<slug>.json`（UTC＋台北時間戳），並記歷史基準率供參考。
5. 盲算之後才抓價：`board.snapshot()`（CLOB `/books`：YES token 最佳買賣、mid、前 5 檔深度）→ `board/`；`evidence.collect()` → `evidence/`。
6. 讀價只走 `gate.read_board()` / `gate.read_evidence()`：fair 檔必須存在、時間戳早於讀價時間且早於該份 board/evidence 的抓取時間，否則 `BlindOrderError`。
7. `sim.check_all()`：檢查先前 tickets 成交。
8. `risk_gate`：當日損益 ≤ −2% → 當日停機。
9. `exits.run()`：對已有成交的部位檢查出場（邊際 < 0.5pp、S1/S2 到期前 24h、S2 否決出現），掛 maker 賣單（`sim.place_exit`，不假設以 mid 成交），紀錄在 `journal/exits.csv`。
10. `strategies.decide_s1/s2/s3()` → `risk_gate.size_order()` → `sim.place()`（只掛 maker 限價買單）→ `journal/journal.csv`。
任一階段或單一市場出錯不會中斷整天（印出原因、journal 記 SKIP/gate rejected）；每個市場各自過 `gate.read_board()`＋`gate.read_evidence()`。

冪等：同一台北日重跑，fair 不重算、journal 以（日期, 策略, 市場）為鍵不重記、ticket id 固定不重建。

## 驗證與資料來源文件
- 各資料來源的實測結果（可用／被擋／HTTP 碼）：[docs/data_sources.md](docs/data_sources.md)
- 真實資料成交模擬驗證（背景跑數小時的一次性驗證程序）：`python validate_fills.py --hours 3`，報告 [docs/fill_validation.md](docs/fill_validation.md)。測試單 `is_test=true`，放 `tickets/test/`，不進 journal、績效與風控。

## 成交模擬（sim.py）
- 只掛 maker：限價若會碰到對手最佳賣價就拒絕。
- 成交只看真實資料（不假設以 mid 成交）：Polymarket Data API `/v2/trades`（taker 側）中，掛單後有人以 **低於** 限價賣出 → 該量可成交；**等於** 限價 → 先扣掉掛單當時同價位排在前面的量；目前訂單簿已有賣單 ≤ 限價 → 依深度成交。上限為剩餘股數，所以會部分成交。
- S1/S2 到期前 24 小時未成交部分撤單；S3 持有到中午結算。
- 簿深穿價成交：先扣排在我們前面的買單量；同一批可見流動性只認領一次（穿價消失後再出現才重新認領）；與成交紀錄證據取較大值，不相加（避免把同一筆流動性算兩次）。
- 成交紀錄 API 有索引延遲：每次從掛單時間重掃、以交易鍵去重；API 失敗時該張單本輪完全不更新（不推進檢查時間、不撤單）；翻頁時每頁都重送 condition。
- 中途出場同樣用這套判定：賣出等同在統一簿裡掛「相反 outcome 的買單」。

## 手續費（依官方文件核實，依下單／事件時間切換；見 `fees.py`）
公式（切換前後相同）：`fee = shares × feeRate × price × (1 − price)`；**maker 不收平台費（0）**。

| 時間 | Crypto 日線市場 taker 係數 | maker | maker 返佣 | 來源 |
|---|---|---|---|---|
| 到 2026-11-20 23:59 UTC 前 | 0.07 | 0 | 每日返佣池（無法預估，記 0） | https://docs.polymarket.com/trading/fees |
| 2026-11-20 23:59 UTC 起（台北 11/21 07:59） | **0.01**（BTC 5/15 分鐘 up/down 為 0.05，本台不碰） | 0 | 依 30 天 maker 加權量分級（<$20 萬 0%、3%、7%、10%、15%）；本台虛擬帳號量遠低 → 0 | https://docs.polymarket.com/programs/fee-and-rebate-changes-november-2026 |

兩頁內容於 2026-11-20 17:5x（台北）親自讀取核實。進場門檻 `|fair − mid| > fee + 2 pp`，fee 用**決策當下**時間的 taker 公式（保守）：切換前 mid=0.5 時門檻 3.75pp，切換後 2.25pp；模擬成交實收 maker 費 0。測試 `tests/test_fees.py` 跨過切換點驗證。

## 資料來源與目前限制
| 資料 | 來源 | 狀態 |
|---|---|---|
| 市場、規則、結算 | Gamma API | OK |
| 訂單簿、mid | CLOB `/books` | OK |
| 成交紀錄 | Data API `/v2/trades` | OK |
| K 線、現價 | Binance `data-api.binance.vision` | OK（`api.binance.com` 在部分地區回 451） |
| Binance 資金費率、OI | `fapi.binance.com` | 在受限地區回 HTTP 451 → unavailable |
| Hyperliquid 資金費率、OI | `api.hyperliquid.xyz/info` | OK |
| 隱含波動率 | Deribit DVOL | OK |
| FOMC 日程 | federalreserve.gov | OK |
| ETF 流量 | Farside `https://farside.co.uk/btc/`、`/eth/`（box，瀏覽器 UA） | 前一美東交易日 US$m；403／challenge／該日未齊 → unavailable（不回退） |
| 總經發布日程 | BLS | 403 → unavailable |
| 清算地圖、交易所流向、盤前價 | 無免費來源 | unavailable |

依 DESK_RULES 第 6 條，用到 unavailable 的交易一律 SKIP，但 fair 與 mid 照記 journal。

## 輸出
`blind/ fair/ board/ evidence/ tickets/ journal/` 的執行輸出不進 git（見 `.gitignore`）；範例在 `examples/`（`board_sample.json`、`journal_sample.csv`）。

## 程式員的操作定義（負責人可改）
- S2「遠檔位」：fair_touch ≤ 10%（`strategies.FAR_STRIKE_MAX_FAIR`）。
- S3 tape 否決：資金費率與前一日 ETF 流量同時與方向相反。
- Kelly 倍數 0.10（`risk_gate.KELLY_MULT`，允許 0.10–0.25）。
- 「BTC barrier 合計 ≤ 6%」：同資產的觸價與 above 部位合併計（保守）。


## 資料源補強（v1.2）
- 資金費率／OI 取用順序加入 Bitget、Gate、dYdX（見 `docs/data_sources.md`；一律換成每 8h，取第一個可用）。
- `evidence.global.okx_premarket`：OKX pre_market 永續價格，S4（v2）用，**目前沒有任何策略讀取**。
- `hl_liq_reference.py` / `run_day.py --hl-liq-ref N`：Hyperliquid 清算價分佈，**僅參考**，不進 `liquidation_clusters`、不是 S1/S2 訊號。

## 正式紀錄進版本控制（v1.3）
- `journal/`、`fair/`、`tickets/`（`tickets/test/` 除外）是正式紀錄，納入 git；`board/`、`evidence/`、`blind/` 快照與驗證暫存仍被忽略。
- `python run_day.py` 跑完會自己 commit 這三個資料夾並 push main，訊息固定為 `run_day YYYY-MM-DD`（台北日期）；沒有變化就不產生空 commit；push 失敗只印一行 `[git] 警告`，不中斷、本機 commit 保留。
- `--dry-run` 和 `--outdir` 一律不 commit 到 repo。
- **不要在正式工作目錄跑 `git clean -fdx`**（也不要 `git clean -x`／`git stash -u` 之類會清掉未追蹤檔的指令）：它會刪掉還沒 commit 的 `blind/`、`board/`、`evidence/` 快照與正在跑的驗證暫存，曾經因此讓背景驗證程序中途崩潰。要清理請在另一份 clone 裡做。
