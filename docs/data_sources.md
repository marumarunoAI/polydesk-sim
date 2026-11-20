# 資料來源實測紀錄

實測環境：Grok Bot 的 box（Linux 雲端機器）。實測時間：2026-11-20 17:3x–17:5x（台北）。
原則：只用免費、免 key 的公開來源；**不使用任何繞過地區限制或 Cloudflare 的手段**；被擋就記 unavailable（DESK_RULES 規則 6 → SKIP）。
每個進 `evidence/` 的數字都帶 `source`（URL）與 `fetched_at`（UTC＋台北）。

| 用途 | 來源（URL） | 實測結果 | 目前使用 |
|---|---|---|---|
| 市場、規則、結算結果 | https://gamma-api.polymarket.com/events/keyset | 200 | 是（offset 分頁已被拒，需 `after_cursor`；limit>50 需 gzip） |
| 訂單簿 | https://clob.polymarket.com/books | 200 | 是 |
| 真實成交 | https://data-api.polymarket.com/v2/trades?condition=… | 200（v1 已退役） | 是（sim.py） |
| 現貨 K 線／現價 | https://data-api.binance.vision/api/v3/klines | 200 | 是 |
| Binance 現貨 | https://api.binance.com/api/v3/klines | **451**（地區限制） | 否 |
| Binance 資金費率／OI | https://fapi.binance.com/fapi/v1/premiumIndex、openInterest | **451** | 嘗試、失敗則 unavailable |
| Binance 幣本位 | https://dapi.binance.com/dapi/v1/premiumIndex | **451** | 否 |
| Binance 期貨（vision 網域） | https://data-api.binance.vision/fapi/v1/premiumIndex | 404（無此路徑） | 否 |
| Hyperliquid 資金費率／OI | POST https://api.hyperliquid.xyz/info `metaAndAssetCtxs` | 200 | 是（funding 為每 1h，程式換算 8h） |
| **OKX 資金費率／OI** | https://www.okx.com/api/v5/public/funding-rate、open-interest | **200** | **是（v1.1 新增）** |
| **Deribit 永續 funding_8h／OI** | https://www.deribit.com/api/v2/public/ticker?instrument_name=BTC-PERPETUAL | **200** | **是（v1.1 新增）** |
| **Bitget 資金費率／OI** | https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=BTCUSDT&productType=USDT-FUTURES、…/open-interest | **200**（BTC、ETH 皆通；2026-11-20 18:45 台北：BTC 資金費率 −0.000031／8h、OI 36,976 BTC） | **是（資料源補強）** |
| **Gate 資金費率／OI** | https://api.gateio.ws/api/v4/futures/usdt/contracts/BTC_USDT（ETH_USDT） | **200**（18:45：BTC −0.0000009／8h、OI＝position_size×0.0001＝29,653 BTC；ETH 乘數 0.01） | **是（資料源補強）** |
| **dYdX v4 資金費率／OI** | https://indexer.dydx.trade/v4/perpetualMarkets?ticker=BTC-USD | **200**（18:45：nextFundingRate 每 1h −0.0000061→×8；OI 194.98 BTC，規模小） | **是（資料源補強，排最後）** |
| **OKX pre_market 永續（S4 v2 用，僅留證據）** | https://www.okx.com/api/v5/public/instruments?instType=SWAP（ruleType=pre_market）＋ /api/v5/market/ticker | 見下「OKX pre_market」 | 只寫 evidence，**不接任何策略** |
| **Hyperliquid 持倉清算價分佈（僅參考）** | https://stats-data.hyperliquid.xyz/Mainnet/leaderboard ＋ POST https://api.hyperliquid.xyz/info `clearinghouseState` | 見下「Hyperliquid 清算價參考」 | **只寫 evidence 參考，不進 `liquidation_clusters`、不當 S1/S2 訊號** |
| Bybit | https://api.bybit.com/v5/market/tickers（及 api.bytick.com） | **403**（CloudFront 地區封鎖） | 否 |
| Coinbase International | https://api.international.coinbase.com/… | 301（Cloudflare 轉址，未再追） | 否 |
| Deribit 隱含波動率 DVOL | https://www.deribit.com/api/v2/public/get_volatility_index_data | **200**（BTC 0.49、ETH 0.62） | 是（quant.py、evidence） |
| **ETF 流量：Farside（BTC／ETH）** | https://farside.co.uk/btc/、https://farside.co.uk/eth/ | **從探測用 box 以一般瀏覽器 UA 的 HTTP GET 可 200**（公開 HTML 表格，單位 US$m）。同一 IP 若遇到 403／Cloudflare challenge 則 unavailable。日本 VPS 實測為 403 challenge，見 `docs/jp_vps_probe.md`。 | **是（正式來源，見下）** |
| ETF 流量：SoSoValue | https://sosovalue.com/…、api.sosovalue.xyz、gw.sosovalue.com | **403**（Cloudflare） | 否 |
| ETF 流量：CoinGlass | https://open-api.coinglass.com/public/v2/… | 500（需 key） | 否 |
| ETF 流量：CryptoQuant／ARK 官網 | cryptoquant.com、ark-funds.com | 403 | 否 |
| ETF 流量：DefiLlama | https://api.llama.fi/etfs | 404；pro-api 需 key | 否 |
| BTC ETF 流量：btcetfdata.com | https://btcetfdata.com/api/v1/current | **200**，免 key，彙整 issuer 持倉變化（單位 BTC，與 Farside US$m 不同） | **否**（函式 `btc_etf_prev_day()` 仍保留，但不寫入 `etf_flow_prev_day`、不作回退，避免兩來源衝突時悄悄選一個） |
| ETH ETF 流量 | 同 Farside `https://farside.co.uk/eth/` | 與 BTC 同一套抓取與嚴格規則 | **是（Farside）** |
| FOMC 日程 | https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm | 200 | 是（解析決議日） |
| BLS 發布日程頁／ics | https://www.bls.gov/schedule/… | **403** | 否 |
| BLS Public Data API | https://api.bls.gov/publicAPI/v2/timeseries/data/… | 200，但只有「已公布數據」，沒有發布日程 | 否 |
| FRED／Treasury | api.stlouisfed.org | 400（需 api_key） | 否 |
| **總經日程（CPI/NFP/PCE/GDP/FOMC…）：Nasdaq 經濟日曆** | https://api.nasdaq.com/api/calendar/economicevents?date=YYYY-MM-DD | **200**，免 key，每日一請求；欄位標 `gmt` 但時間吻合美東發布時刻（例如 08:30 的 Jobless Claims、PCE） | **是（v1.1 新增）** |
| 總經日程：Forex Factory 週檔 | https://nfs.faireconomy.media/ff_calendar_thisweek.json | 200，只有本週；nextweek 404 | 否（備用） |
| 總經日程：TradingEconomics／Investing | tradingeconomics.com、investing.com | 200（HTML，需爬）／403 | 否 |
| **清算熱力圖／清算叢集** | 無免費來源 | — | **unavailable，不用任何代理指標頂替** |
| 交易所流向、盤前價 | 無免費來源 | — | unavailable |

## OKX pre_market（S4 v2 證據，僅記錄）
- 實測 2026-11-20 18:45–18:46（台北）：`/api/v5/public/instruments?instType=SWAP` **200**，546 檔合約，其中 `ruleType=pre_market` 共 3 檔（MOONSHOT、OPENAI、OURA 的 `-USDT-SWAP`，皆 `state=live`）；逐檔 `/api/v5/market/ticker` **200**，例：OPENAI-USDT-SWAP last 120.69／bid 120.59／ask 120.66（USDT／單位標的，**不是 FDV**，換成 FDV 需要供給量，留給 v2）。
- 寫入位置：`evidence/latest.json` 的 `global.okx_premarket`（每檔附 `source` URL 與 `fetched_at`；整體標 `reference_only`）。抓不到或單檔失敗寫 unavailable 與原因。**沒有任何策略／風控程式讀這個鍵**（有測試鎖住）。

## Hyperliquid 清算價參考（僅參考，不是訊號）
- 實測 2026-11-20 18:47–18:50（台北）：leaderboard 檔 https://stats-data.hyperliquid.xyz/Mainnet/leaderboard **200**（約 38 MB）；POST `https://api.hyperliquid.xyz/info`（`metaAndAssetCtxs`、`clearinghouseState`）**200**。前 300 大帳戶共 306 個請求，**遇到 5 次 429**，由退避重試吸收，最終 300/300 成功、0 失敗，耗時 153 秒。
- 限流：固定最小間隔 0.4 秒、不並行；429／5xx／網路錯誤指數退避（2、4、8…秒，上限 60，尊重 `Retry-After`），每次 429 把間隔 ×1.5（上限 3 秒），成功時慢慢降回；重試 6 次仍失敗才放棄該帳戶（帳戶失敗不影響整體，全部失敗才標 unavailable）。
- 實測結果（前 300 大帳戶抽樣）：BTC 46 個持倉、名目 $585M（約為 Hyperliquid BTC OI 的 24%），其中 13 個（$41M）是 cross margin 而 `liquidationPx` 為 null；清算價落在現價 ±10% 內的名目只有約 $7M。ETH 34 個持倉、名目 $247M。**遠低於 S1/S2 規則的 $10B 門檻，也只是抽樣**，所以即使有人想用也不夠格。
- 寫入：`python hl_liq_reference.py [--top N]` → `evidence/hl_liq_reference.json`；或 `python run_day.py --hl-liq-ref N` → `evidence/latest.json` 的 `reference.hl_liquidation_distribution`（預設不抓）。每筆附 `source`、`fetched_at`、`reference_only: true`、涵蓋率 `coverage_of_oi`。
- **硬規定**：不寫進 `liquidation_clusters`（仍永遠 unavailable → S1/S2 在缺資料時照樣 SKIP）、不經 `strategies` 的清算介面、不是任何訊號；有測試掃描 strategies／risk_gate／quant／sim／exits／gate 的原始碼，出現這份資料的鍵名就失敗。

## 使用細節
- **資金費率**取用順序（`strategies.FUNDING_ORDER`）：Binance → OKX → Bitget → Gate → Deribit → Hyperliquid → dYdX，取第一個可用的；**OI** 順序（`OI_ORDER`）：Binance → OKX → Bitget → Gate → Hyperliquid → Deribit → dYdX。所有來源的值都留在 evidence 供對照，每筆帶 `source` URL 與 `fetched_at`。
  換算：OKX 依 `nextFundingTime − fundingTime`；Bitget 依 `fundingRateInterval`；Gate 依 `funding_interval`（秒）；dYdX `nextFundingRate` 為每 1h（×8）；Hyperliquid 為每 1h（×8，存於 `per_8h`）。OI 單位：Bitget／dYdX 為幣；Gate＝`position_size × quanto_multiplier`；Deribit 為 USD（只用於「有沒有 OI」，不跨所加總）。
  注意：本機（box）對 Binance fapi 是 451，所以實際上第一個可用多半是 OKX；Bitget／Gate／dYdX 是 OKX 也掛掉時的備援。都沒有才 unavailable（規則 6 → SKIP）。
- **ETF 流量（Farside，正式來源）**：從本環境（box）用 `requests` 帶一般瀏覽器 UA 讀 https://farside.co.uk/btc/ 與 https://farside.co.uk/eth/（不走 VPS、不裝瀏覽器、不用代理或替代來源）。`run_day` 每次 collect 各抓一次，不另建定時任務。解析公開表格的日期、各基金、Total，單位 US$m；括號為負值，`-` 為無值。只輸出**前一個美東交易日**（週一到週五；美國假日若表上無該日則 unavailable）且**該列各基金與 Total 皆已是數字**的 Total。遇到 HTTP 非 200、Cloudflare challenge、解析失敗、該列為 `-` 或基金未全數更新，就寫 unavailable 與原因（規則 6 → SKIP），**不回退**其他來源。每筆帶 `source` URL、`trading_day`／`data_date`、`fetched_at`（UTC 與台北）。S3 tape 只看正負方向。
- **btcetfdata.com（不再作為 tape 來源）**：先前僅 BTC、單位 BTC、嚴格要求 9 檔 `dt` 對齊前一美東交易日。函式仍在，但 `etf_flow()`／`etf_flow_prev_day` 不再呼叫它，以免與 Farside 數字（單位不同）衝突時悄悄選一個。
- **總經事件**：Nasdaq 端點屬非正式文件的公開端點，可能改版；回傳 `No record found`（code 1002）視為當天無事件，其他異常視為 unavailable。關鍵字：CPI、PPI、Nonfarm/payroll、unemployment rate、PCE、GDP、FOMC、retail sales、ISM、jobless claims（排除 speaks、GDPNow、Dallas Fed）。
- **S3 對 tape 的需求**：funding、OI、ETF 前一日流量、總經日程，四項都要有；BTC 與 ETH 的 ETF 都來自 Farside，缺資料時該資產的 S3 依規則 6 SKIP。
