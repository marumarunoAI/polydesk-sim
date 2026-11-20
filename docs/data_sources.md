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
| Bybit | https://api.bybit.com/v5/market/tickers（及 api.bytick.com） | **403**（CloudFront 地區封鎖） | 否 |
| Coinbase International | https://api.international.coinbase.com/… | 301（Cloudflare 轉址，未再追） | 否 |
| Deribit 隱含波動率 DVOL | https://www.deribit.com/api/v2/public/get_volatility_index_data | **200**（BTC 0.49、ETH 0.62） | 是（quant.py、evidence） |
| ETF 流量：Farside | https://farside.co.uk/bitcoin-etf-flow-all-data/ | **403**（Cloudflare 驗證頁） | 否 |
| ETF 流量：SoSoValue | https://sosovalue.com/…、api.sosovalue.xyz、gw.sosovalue.com | **403**（Cloudflare） | 否 |
| ETF 流量：CoinGlass | https://open-api.coinglass.com/public/v2/… | 500（需 key） | 否 |
| ETF 流量：CryptoQuant／ARK 官網 | cryptoquant.com、ark-funds.com | 403 | 否 |
| ETF 流量：DefiLlama | https://api.llama.fi/etfs | 404；pro-api 需 key | 否 |
| **BTC ETF 流量：btcetfdata.com** | https://btcetfdata.com/api/v1/current | **200**，免 key，彙整 9 檔 issuer 官網的持倉變化（BTC 單位） | **是，僅 BTC，嚴格模式（見下）** |
| ETH ETF 流量 | （找不到免 key 且不被擋的來源；ethetfdata.com 連線失敗） | 無 | 否 → unavailable |
| FOMC 日程 | https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm | 200 | 是（解析決議日） |
| BLS 發布日程頁／ics | https://www.bls.gov/schedule/… | **403** | 否 |
| BLS Public Data API | https://api.bls.gov/publicAPI/v2/timeseries/data/… | 200，但只有「已公布數據」，沒有發布日程 | 否 |
| FRED／Treasury | api.stlouisfed.org | 400（需 api_key） | 否 |
| **總經日程（CPI/NFP/PCE/GDP/FOMC…）：Nasdaq 經濟日曆** | https://api.nasdaq.com/api/calendar/economicevents?date=YYYY-MM-DD | **200**，免 key，每日一請求；欄位標 `gmt` 但時間吻合美東發布時刻（例如 08:30 的 Jobless Claims、PCE） | **是（v1.1 新增）** |
| 總經日程：Forex Factory 週檔 | https://nfs.faireconomy.media/ff_calendar_thisweek.json | 200，只有本週；nextweek 404 | 否（備用） |
| 總經日程：TradingEconomics／Investing | tradingeconomics.com、investing.com | 200（HTML，需爬）／403 | 否 |
| **清算熱力圖／清算叢集** | 無免費來源 | — | **unavailable，不用任何代理指標頂替** |
| 交易所流向、盤前價 | 無免費來源 | — | unavailable |

## 使用細節
- **資金費率**取用順序：Binance → OKX → Deribit → Hyperliquid，取第一個可用的；所有來源的值都留在 evidence 供對照。OKX 的 `fundingRate` 依 `nextFundingTime − fundingTime` 換算成每 8h。
- **BTC ETF 流量（嚴格模式）**：btcetfdata.com 的各檔基金 `dt`（issuer 公布日）常常不同步。程式只在 **9 檔全部 dt = 前一個美東交易日且無 error** 時才輸出加總，否則 unavailable 並列出落後基金。這是第三方彙整、單位 BTC，不等於 Farside 的 USD 淨流量；只用於判斷方向（正負）。實測 17:5x 時 FBTC、BITB、HODL 等仍停在 11/18，所以當下是 unavailable。美國假日時 dt 對不上也會 unavailable（保守）。
- **總經事件**：Nasdaq 端點屬非正式文件的公開端點，可能改版；回傳 `No record found`（code 1002）視為當天無事件，其他異常視為 unavailable。關鍵字：CPI、PPI、Nonfarm/payroll、unemployment rate、PCE、GDP、FOMC、retail sales、ISM、jobless claims（排除 speaks、GDPNow、Dallas Fed）。
- **S3 對 tape 的需求**：funding、OI、ETF 前一日流量、總經日程，四項都要有；ETH 因為沒有 ETF 流量來源，S3 的 ETH 部分會一直 SKIP。
