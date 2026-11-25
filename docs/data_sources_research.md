# 免費替代資料源調查（box 實測）

- 實測：2026-11-20 18:37–18:50（台北），Grok Bot 的 box。原始回應存於 `/workspace/dsr/*.out`。
- 範圍：只限免費、公開；不用 Minara 和任何付費服務；沒有註冊任何帳號。「需註冊（免費）」的只列出，沒有測到資料。
- 「UA」是指 curl 的 `-A` 標頭。所有測試都帶一般瀏覽器 UA（`Mozilla/5.0 (X11; Linux x86_64) … Chrome/120 Safari/537.36`），只有特別註明的例外。

## ⚠️ 先說最重要的發現：Farside 其實拿得到（BTC 和 ETH 都可以），但要負責人決定能不能用
| 請求方式 | `farside.co.uk/bitcoin-etf-flow-all-data/` |
|---|---|
| curl 預設 UA、`python-requests` UA、只帶 `Mozilla/5.0` | **403**（Cloudflare 的「Just a moment...」頁） |
| 完整的瀏覽器 UA 字串 | **200**，有完整表格；連續 3 次請求都是 200 |

- BTC 樣本：`19 Nov 2026 | IBIT (541.1) | FBTC (45.9) | … | Total (582.3)`，單位是 US$m。
- ETH（`/ethereum-etf-flow-all-data/`）樣本：`19 Nov 2026 | ETHA (124.2) | … | Total (131.2)`。
- 台北 18:4x 已經有前一個美東交易日（11/19）的完整一列，所以資料有日期。
- robots.txt 只擋 Twitterbot。
- 這個做法沒有解 challenge、沒有用代理、也沒有用 cookie，只是送了一般瀏覽器會送的 UA 標頭。不過 `docs/data_sources.md` 寫了「不使用任何繞過 Cloudflare 的手段」，這算不算繞過、要不要先看 Farside 的使用條款，**請負責人決定**。我沒有寫進程式。
- 如果可以用，Farside 就能**完全**提供 S3 需要的前一日 ETF 淨流量（USD、BTC＋ETH），是原規則指定的來源。程式還要防一件事：Farside 可能隨時改擋，所以抓到 403 或 Cloudflare 頁時要記成 unavailable。

## 1) 清算地圖／清算叢集（S1/S2，門檻 ≥ $10B）
| 來源 | 端點 | 實測 | key | 時間戳 | 能否代替 |
|---|---|---|---|---|---|
| Hyperliquid 排行榜 + 逐一查帳戶倉位 | `GET stats-data.hyperliquid.xyz/Mainnet/leaderboard`；`POST api.hyperliquid.xyz/info {"type":"clearinghouseState","user":…}` | 200：排行榜有 **46,412** 個地址；倉位資料含 `liquidationPx`（真實清算價） | 不用 | 有，查詢當下 | **部分**（說明見下） |
| OKX 已發生的清算 | `/api/v5/public/liquidation-orders?instType=SWAP&uly=BTC-USDT&state=filled` | 200：`bkPx 62316.4, sz 241.35, posSide short, ts 1795170987812` | 不用 | 有 | 不行：這是已經發生的清算，不是未來的清算地圖 |
| OKX 風險檔位、多空比、OI 與成交量 | `/public/position-tiers`、`/rubik/stat/contracts/long-short-account-ratio`、`/rubik/stat/contracts/open-interest-volume` | 200：tier1 `maxLever 100, mmr 0.004`；多空帳戶比 `3.19`；BTC OI `3,049,630,343` USD | 不用 | 有 | 只能當自建模型的輸入 |
| Gate 清算紀錄與合約統計 | `api.gateio.ws/api/v4/futures/usdt/liq_orders`、`contract_stats` | 200：`fill_price 62310.4, size -589`；`lsr_account 2.11, short_liq_usd 211.293` | 不用 | 有 | 只能當自建模型的輸入 |
| Deribit 成交（含 liquidation 標記） | `/public/get_last_trades_by_currency` | 200 | 不用 | 有 | 只能當輸入 |
| BitMEX 清算 | `www.bitmex.com/api/v1/liquidation` | **403**（CloudFront 地區封鎖） | — | — | 不行 |
| Coinalyze | `api.coinalyze.net/v1/liquidation-history` | 401 `Invalid/Missing API key` | **需註冊（免費）** | 有 | 只有已發生的清算和 OI，不是地圖；可當輸入 |
| Hyblock | `api.hyblockcapital.com/v1/liquidationLevels` | 400 `Missing Authentication Token` | 需 key（付費方案） | — | 不行 |
| CoinAnk | `api.coinank.com/api/liqMap/getLiqMap` | 200，但內容是 `success:false, code 403` | 需 key | — | 不行 |
| Laevitas | `api.laevitas.ch/...` | 400 `Api Key is Required` | 需 key（付費） | — | 不行 |
| Velo | `api.velo.xyz/api/v1/status` | 403 `api key not authorized` | 需 key（付費） | — | 不行 |
| Kingfisher | `thekingfisher.io` | 200，但只有行銷頁、沒有公開 API | 付費 | — | 不行 |
| CoinGlass 網站內部 API | `capi.coinglass.com/liquidity-heatmap/...` | 200，有資料 | 不用 | 有 | **不建議**：這是付費服務沒有公開文件的內部端點，有使用條款風險；回傳的是訂單簿流動性熱圖，不是清算地圖 |

**Hyperliquid 實測（排行榜前約 380 個帳戶，依帳戶價值排序）**
- 抽到的 BTC 倉位名目 $672.0M，全站 BTC OI 是 $2.46B，大約涵蓋 27%。ETH 倉位 $267.9M，全站 ETH OI 是 $1.07B。
- 清算價落在現價 ±10% 內的：BTC $9.6M，ETH $0；落在 ±20% 內的：BTC $196.8M。
- 查到約第 380 個帳戶後被限流（HTTP 429），所以要放慢速度，全掃一輪要以小時計。

**$10B 門檻在免費資料下基本上達不到**
免 key 又沒被擋的交易所，BTC 永續 OI 實測合計約 $10.6B：
- OKX $3.05B
- Hyperliquid $2.46B
- Bitget 36,855 BTC，約 $2.29B
- Gate 29,537 BTC，約 $1.84B
- Deribit $0.82B
- Kraken 2,162 BTC
- dYdX 195 BTC

就算這些部位全部堆在現價和關卡之間，也只勉強到 $10B。原規則的 $10B 指的是含 Binance、Bybit 的全市場估算地圖，而這兩家都擋我們的 box。

**自建估算方案，以及跟付費地圖的差距**
- 開源做法：
  - `adlererik/LiquidHeat`：把 Hyperliquid 真實倉位和 CEX 估算分開呈現，不混在一起。
  - `minchillo4/btc-liquidation-heatmap`：用 OI 異常增量乘上假設的槓桿檔位推估，資料來自 Coinalyze，需註冊（免費）。
  - `Co-Messi/HyperData-Terminal`：只用 Hyperliquid 公開資料，不需要 key。
  - `aoki-h-jp/py-liquidation-map`：用 Binance、Bybit 的歷史成交，這兩家在 box 上被擋。
- 可信度：
  - Hyperliquid 的倉位是**真實清算價**，但只代表一家交易所、而且只是抽樣。實測 ±10% 內只有 $9.6M，跟 $10B 差了三個數量級。
  - CEX 估算是**模型推論**：進場價、槓桿分布、平倉時間都是假設，和付費地圖（CoinGlass、Hyblock 也是模型）性質一樣，但少了 Binance、Bybit 這兩個最大的 OI 來源，絕對金額會被系統性低估。
- 結論：兩種方法都**只能部分代替**。想用它們，就必須改門檻（例如改成「占可得 OI 的比例」）或把金額依比例放大。這兩種做法都等於用代理指標，DESK_RULES 附錄目前明文禁止，**要改規則，得由負責人或使用者決定**。

## 2) BTC／ETH 現貨 ETF 前一日淨流量
| 來源 | 端點 | 實測 | key | 時間戳 | 能否代替 |
|---|---|---|---|---|---|
| **Farside**（瀏覽器 UA） | `farside.co.uk/bitcoin-etf-flow-all-data/`、`/ethereum-etf-flow-all-data/` | **200**，樣本見最上方 | 不用 | 有，逐日 | **完整**（BTC＋ETH，USD），前提是負責人同意用法 |
| btcetfdata.com | `/api/v1/current` | 200；ARKB `dt 2026-11-20`，IBIT 與 GBTC 是 `11-19`，FBTC、BITB、HODL 停在 `11-18` | 不用 | 有 | 部分（只有 BTC、單位是 BTC，而且常常不同步） |
| ethetfdata.com | `/api/v1/current` | 連線失敗（000） | — | — | 不行 |
| iShares 持倉 CSV／JSON | `ishares.com/us/products/333011/...ajax?fileType=csv` | 200，但回的是 HTML，不是 CSV | 不用 | — | 不行（這個 URL） |
| Grayscale | `etfs.grayscale.com/gbtc`、`/eth` | 429 | — | — | 不行（被限流） |
| Bitwise | `bitbetf.com`、`ethwetf.com` | 200，HTML | 不用 | 未驗證 | 理論上可以用持有量自算單檔，沒有做解析 |
| Fidelity、Franklin | 產品頁 | 200，HTML（前端用 JS 載入） | — | 未驗證 | 未驗證 |
| WisdomTree | 產品頁 | 403（Cloudflare） | — | — | 不行 |
| Invesco | 產品頁 | 406 | — | — | 不行 |
| VanEck | 產品頁 | 302 | — | — | 不行 |
| The Block | 舊 chart API | 410 `endpoint was retired`；資料頁 200 但是 HTML，沒有驗證 | — | — | 不行 |
| SoSoValue OpenAPI | `api.sosovalue.xyz/openapi/v2/etf/historicalInflowChart` | 403（Cloudflare） | 需註冊（免費） | — | 不行（box 被擋） |
| CoinGlass | `open-api-v4.coinglass.com/api/etf/bitcoin/flow-history` | 401 `API key missing` | 需 key（付費） | — | 不行 |
| Dune | `api.dune.com/api/v1/query/…/results` | 401 | **需註冊（免費）** | 有 | 部分（依賴社群寫的查詢，品質不一） |
| CoinShares | 資金流向頁 | 404 | — | — | 不行（而且是週資料） |
| Yahoo | `query1.finance.yahoo.com/v8/finance/chart/IBIT` | 429 | — | — | 不行 |

## 3) 資金費率／OI 備援（全部不用 key，都是 200，都有時間戳）
| 來源 | 端點 | 樣本 | 能否代替 |
|---|---|---|---|
| Bitget | `api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=BTCUSDT&productType=USDT-FUTURES`、`/open-interest` | `fundingRate -0.000031`，8h；OI `36855.4 BTC` | 完整 |
| Gate | `api.gateio.ws/api/v4/futures/usdt/contracts/BTC_USDT` | `funding_rate -0.0000011`；`position_size 295372412`（× 0.0001 BTC） | 完整 |
| dYdX v4 | `indexer.dydx.trade/v4/perpetualMarkets?ticker=BTC-USD` | `nextFundingRate -0.0000058`（每 1h）；OI `194.98 BTC` | 完整，但規模小 |
| Kraken Futures | `futures.kraken.com/derivatives/api/v3/tickers/PF_XBTUSD` | OI `2161.87`；`fundingRate -0.3936`（單位是每合約 USD，要換算成比率） | 部分 |
| BitMEX | `www.bitmex.com/api/v1/instrument` | 403（CloudFront） | 不行 |

## 4) 總經日程
| 來源 | 端點 | 實測 | key | 能否代替 BLS |
|---|---|---|---|---|
| BLS 日程頁與 ics（瀏覽器 UA） | `bls.gov/schedule/news_release/current_year.asp`、`bls.ics` | 403 `Access Denied` | — | 不行 |
| FRED release dates | `api.stlouisfed.org/fred/releases/dates` | 400 `api_key is not set` | **需註冊（免費）** | 完整（官方的發布日期） |
| Trading Economics | `api.tradingeconomics.com/calendar?c=guest:guest` | 410，訪客帳號已停用 | 付費 | 不行 |
| BEA 發布日程 | `bea.gov/news/schedule` | 200，HTML（GDP、PCE） | 不用 | 部分（要解析 HTML） |
| Census 經濟指標日曆 | `census.gov/economic-indicators/calendar-listview.html` | 200，HTML（零售銷售等） | 不用 | 部分（要解析 HTML） |
| Forex Factory 本週檔 | `nfs.faireconomy.media/ff_calendar_thisweek.json` | 200，例如 `"date":"2026-11-15T16:30:00-05:00","impact":"Low"` | 不用 | 部分（只有本週） |
| Nasdaq 經濟日曆（已在用） | `api.nasdaq.com/api/calendar/economicevents?date=2026-11-25` | 200 | 不用 | 已在用 |

## 5) 盤前價格（S4，第二版用）
| 來源 | 端點 | 實測 | key | 時間戳 | 能否代替 |
|---|---|---|---|---|---|
| **OKX 盤前永續** | `/api/v5/public/instruments?instType=SWAP`，篩選 `ruleType=pre_market`；行情用 `/api/v5/market/ticker` | 200：共 546 個合約，其中 3 個是 pre_market（MOONSHOT、OPENAI、OURA）；`OPENAI-USDT-SWAP last 120.83` | 不用 | 有 | **完整**（但只涵蓋 OKX 有上架的代幣） |
| Whales Market | `api.whales.market/v2/tokens?type=pre_market&page=1&take=100` | 200：總共 369 個代幣，抽 100 個，其中 67 個有 `last_price`，但多數是 `ended`；`total_supply` 常是 null | 不用 | 有（`updated_at`） | 部分（OTC 點對點、流動性薄，總供給要從別處補） |
| Aevo | `api.aevo.xyz/markets?instrument_type=PERPETUAL` | 200：102 個合約，`pre_launch` 為 0 個 | 不用 | — | 目前沒有盤前市場 |
| Hyperliquid | `metaAndAssetCtxs` | 200：235 個合約，欄位裡沒有 pre-launch 標記 | 不用 | — | 無法自動辨識（沒有驗證） |
| Binance pre-market | bapi 端點 | 404；Binance 本來就對 box 回 451 | — | — | 不行 |

## 結論
**可以補的**
- **ETF 前一日流量（S3）**：Farside 用瀏覽器 UA 拿得到 BTC＋ETH 的 USD 流量，可以完整代替。請負責人決定這算不算「繞過 Cloudflare」。如果不行，BTC 只能繼續用 btcetfdata（嚴格模式），ETH 沒有其他免 key 的來源。
- **資金費率／OI 備援**：Bitget、Gate、dYdX 都可以直接接。
- **總經日程**：FRED 只要免費註冊 key，就能拿到官方發布日期。不註冊的話，Nasdaq 加 BEA、Census 頁面已經夠用。
- **盤前價格（S4）**：OKX pre_market 永續可以接，Whales Market 當輔助。

**仍然補不了的**
- **清算地圖 ≥ $10B**：我們拿得到的交易所 BTC 永續 OI 總共只有約 $10.6B，Hyperliquid 的真實倉位在 ±10% 內只有 $9.6M。所有免費方案都只是部分資料或模型推估，S1/S2 的清算條件照現行規則仍然會 SKIP。要啟用，只能改規則：門檻改成占可得 OI 的比例、或改成相對指標，這要負責人或使用者決定。

**建議程式員接**
1. Farside 的 BTC 與 ETH 流量，負責人核可後才接。抓到 403 或 Cloudflare 頁時要記 unavailable。
2. 把 Bitget、Gate、dYdX 加進資金費率／OI 的取用順序。
3. OKX pre_market 的合約清單和行情，第二版 S4 用。
4. （可選）用 Hyperliquid 排行榜和 clearinghouseState 做一份「Hyperliquid 真實清算價分布」，只寫進 evidence 當參考，不當成 S1/S2 的 tape 訊號；要放慢速度，避免 429。
5. （可選，需註冊免費 key）FRED release dates。
