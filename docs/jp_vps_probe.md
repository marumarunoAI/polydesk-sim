# 日本 Sakura VPS 公開資料來源實測

探測主機為日本 Sakura VPS `os3-364-15171`（`ubuntu@133.167.68.175`，egress IP 經 `https://api.ipify.org` 回 `133.167.68.175`，2026-11-20 22:35:23 Asia/Taipei）。報告時間為台北時間（Asia/Taipei, UTC+8）；VPS 系統時鐘為 JST（UTC+9）。這次只測、不接進 `polydesk-sim` 正式流程或規則；未使用帳號、登入、簽名或需註冊的 API key。當時 VPS 產物放在 `~/grok/polydesk-probe/`（系統無 `python3-venv`，未使用 sudo/apt；Python 套件以 `pip install --target ~/grok/polydesk-probe/pydeps` 安裝，未寫入 `~/.local`）。2026-11-25 03:32 Asia/Taipei 已將專案搬到 `~/web3/grok_workspace/polydesk-probe/`，並刪除空的 `~/grok`；腳本改為以檔案自身目錄為根路徑。

## 結論

- **Binance USD-M REST（資金費率、OI、OI 歷史）**：可用。VPS 回 HTTP 200（延遲約 60–80 ms）；同一時刻探測用 box 對 `premiumIndex` 回 HTTP 451（地區封鎖）。差異來自 IP／地區，不是端點本身失效。
- **Binance 強平 REST `GET /fapi/v1/allForceOrders`**：不可用。VPS 回 HTTP 404，body 為 Binance 公開 404 HTML（「網頁不存在」），無 JSON 資料。本次未呼叫需簽名的 `forceOrders`。
- **Binance 強平 WS**（`btcusdt@forceOrder`、`!forceOrder@arr`）：連線可用，但本窗口未看到事件。兩條流皆於約 90 秒內成功連上、0 筆訊息，因此本次無法記錄事件欄位。
- **Bybit v5 REST（tickers 含 fundingRate／openInterest、funding/history、open-interest 歷史）**：可用。VPS 全部 HTTP 200（延遲約 59–134 ms），不是 403。
- **Bybit 強平 WS**（官方主題 `allLiquidation.{symbol}`）：可用。90 秒窗口內 BTCUSDT 收到 5 則清算 snapshot（另 1 則為 subscribe 成功回覆，共 6 則 WS 訊息），ETHUSDT 收到 1 則清算 snapshot（另 1 則 subscribe 回覆）。欄位與官方文件一致：`T, s, S, v, p`。
- **OKX REST（順便測是否 403）**：可用。VPS 對公開 funding-rate、open-interest 回 HTTP 200，不是 403。
- **Farside BTC／ETH**：VPS 上 `curl`＋瀏覽器 UA **不可用**。兩邊皆 HTTP 403，回應標頭 `cf-mitigated: challenge`、`server: cloudflare`，body 標題為 `Just a moment...`（Cloudflare managed challenge）。同一時刻探測用 box 回 HTTP 200，可看到資金流量表格。本輪使用者電腦離線，無法從共用電腦重測；負責人先前亦記錄「VPS 403、共用電腦 200」。已在 `~/grok` 下載 Playwright Chromium，但啟動時缺少系統函式庫（首先是 `libatk-1.0.so.0`），依規則未用 sudo 安裝，**一般瀏覽器載入尚未完成**。未使用 stealth、未解 captcha、未偽造指紋。
- **CoinGlass 清算熱力圖**：公開頁面 HTTP 可載入（200，經一次 301）。`curl` 得到帶標題與「Login」連結的 Next.js HTML；熱力圖頁 HTML 含 `<canvas>`。本次只看可見性，未抓熱力圖或清算數值，也未繞過登入／付費牆。無法單靠 curl 判定互動圖表是否需登入才能完整顯示。Headless 瀏覽器因同樣缺少系統函式庫而未載入。

## 總表

| 來源 | 端點 | 狀態 | 欄位（實測見到） | 頻率限制 | 備註 |
| --- | --- | --- | --- | --- | --- |
| Binance USD-M | `GET /fapi/v1/premiumIndex` BTCUSDT／ETHUSDT | 可用（VPS HTTP 200；box HTTP 451） | `symbol, markPrice, indexPrice, estimatedSettlePrice, lastFundingRate, interestRate, nextFundingTime, time` | 回應標頭 `X-MBX-USED-WEIGHT-1M` 每次 +1（本輪見到 2、3）。官方 USD-M IP `REQUEST_WEIGHT` 2400／分鐘（見 [General API Information](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info)／2026-11 對 `exchangeInfo` 的公開記錄） | VPS 22:35:26–28 Asia/Taipei；box 同時 451，body 引 Binance terms eligibility |
| Binance USD-M | `GET /fapi/v1/fundingRate` BTCUSDT／ETHUSDT `limit=2` | 可用（HTTP 200） | `symbol, fundingTime, fundingRate, markPrice, rateType` | 本輪此端點**未**回 `X-MBX-USED-WEIGHT-1M`。文件另有市場資料權重規則，未再加打以探上限 | 回傳最近兩筆 8h 結算（2026-11-20 00:00 UTC、08:00 UTC） |
| Binance USD-M | `GET /fapi/v1/openInterest` BTCUSDT／ETHUSDT | 可用（HTTP 200） | `symbol, openInterest, time` | `X-MBX-USED-WEIGHT-1M` 見到 4、5（每次 +1） | `time` 與請求時刻一致（即時） |
| Binance USD-M | `GET /futures/data/openInterestHist` `period=5m&limit=2` | 可用（HTTP 200） | `symbol, sumOpenInterest, sumOpenInterestValue, CMCCirculatingSupply, timestamp` | 官方：[Open Interest Statistics](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics) 權重 0、IP 1000 請求／5 分鐘、只保留近 1 個月。本輪無 `X-MBX-USED-WEIGHT-1M` | 兩根 5 分鐘 bar：14:25 與 14:30 UTC |
| Binance USD-M | `GET /fapi/v1/allForceOrders`（未簽名） | 不可用（HTTP 404） | 無資料；HTML 404 | 不適用（端點不存在或已下線） | 2026-11-20 22:35:43 Asia/Taipei |
| Binance USD-M WS | `wss://fstream.binance.com/ws/btcusdt@forceOrder`、`/ws/!forceOrder@arr` | 連線可用；本窗口 0 事件 | 本窗口無事件，欄位未觀察到 | 本次各開一條、聽約 90 秒，未碰到限制。官方連線規範見 [Binance Futures WebSocket](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams) | 22:38:59–22:42:10 Asia/Taipei |
| Bybit v5 | `GET /v5/market/tickers?category=linear` BTCUSDT／ETHUSDT | 可用（HTTP 200，非 403） | 含 `fundingRate, nextFundingTime, openInterest, openInterestValue, markPrice, indexPrice, lastPrice, fundingIntervalHour, fundingCap` 等 | 官方 [Rate Limit Rules](https://bybit-exchange.github.io/docs/v5/rate-limit)：HTTP IP 600 請求／5 秒。本輪公開端點**未**回 `X-Bapi-Limit`／`X-Bapi-Limit-Status` | 延遲約 59–68 ms；CloudFront POP `KIX82-P7` |
| Bybit v5 | `GET /v5/market/funding/history` `limit=2` | 可用（HTTP 200） | `symbol, fundingRate, fundingRateTimestamp` | 同上；本輪無 `X-Bapi-*` 標頭 | 兩筆 8h 結算（08:00、00:00 UTC） |
| Bybit v5 | `GET /v5/market/open-interest` `intervalTime=5min&limit=2` | 可用（HTTP 200） | `openInterest, singleOpenInterest, timestamp`；另有 `nextPageCursor` | 同上 | 兩根 5 分鐘 bar：14:35、14:30 UTC |
| Bybit v5 WS | `wss://stream.bybit.com/v5/public/linear` 主題 `allLiquidation.BTCUSDT`／`ETHUSDT`（[官方文件](https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation)） | 可用（連線成功且收到清算事件） | 訊息：`topic, type, ts, data[]`；每筆 `T`（時間 ms）、`s`（符號）、`S`（Buy/Sell）、`v`（數量）、`p`（價格） | 官方 WS：5 分鐘內不超過 500 連線；行情連線每 IP 每市場 1000。本次未碰到限制 | BTC 22:42:12–22:43:42、ETH 22:43:45–22:45:14 Asia/Taipei |
| OKX | `GET /api/v5/public/funding-rate`、`/public/open-interest` `BTC-USDT-SWAP` | 可用（HTTP 200，非 403） | funding：`fundingRate, fundingTime, nextFundingTime, ...`；OI：`oi, oiCcy, oiUsd, ts` | 本次只做連通性，未專門測 OKX 限頻 | Cloudflare `cf-ray` 節點 `KIX` |
| Farside | `https://farside.co.uk/btc/`、`/eth/` | VPS curl 不可用（HTTP 403 challenge）；box curl 可用（HTTP 200）；VPS 一般瀏覽器載入因缺系統函式庫而未完成 | box 200 時表格欄位見下文。VPS curl 只得到 Cloudflare 挑戰頁，無表格 | 不適用 | VPS `cf-ray` `KIX`；box `EWR`。若要補測瀏覽器，需負責人批准 sudo 安裝套件（見 §2.3） |
| CoinGlass | `https://www.coinglass.com/pro/futures/LiquidationHeatMap` → 301 `/LiquidationHeatMap/BTC`；`https://www.coinglass.com/LiquidationData` → 301 `/liquidations` | 公開 HTML 可載入（最終 HTTP 200）；互動圖是否需登入，curl 無法判定 | 未擷取熱力圖或清算數值。頁面 title／標題存在，有「Login」連結；熱力圖頁 HTML 含 `<canvas>` | 未測 API（依規則不逆向） | 只看可見性；CloudFront POP `KIX56-P2` |

## 環境與方法

- 連線：從探測用 box `ssh -i ~/.ssh/sakura_jp_vps ubuntu@133.167.68.175`。本輪使用者電腦離線，無法從共用電腦重測 Farside／Binance；改以同一時段的 box `curl` 做對照。
- VPS 時間校樣（SSH 登入當下 `date`）：`Fri Nov 20 23:32:13 JST 2026` = `2026-11-20 22:32:13` Asia/Taipei，UTC `2026-11-20 14:32:13`。
- REST 實測窗口：`2026-11-20T14:35:23Z`–`14:36:09Z`（22:35:23–22:36:09 Asia/Taipei）。請求間隔約 2 秒，未連續大量打 API。
- WS 實測窗口：`2026-11-20T14:38:58Z`–`14:45:14Z`（22:38:58–22:45:14 Asia/Taipei）。各主題依序聽約 90 秒。
- 腳本現在位於 VPS：`~/web3/grok_workspace/polydesk-probe/`（`rest_probe.sh`、`ws_probe.py`、`browser_probe.py`、`cg_visibility.py`）。2026-11-20 探測當時放在 `~/grok/polydesk-probe/`。本 repo 只新增本報告。
- 硬規則執行情況：未動 `~/mev-venv`、`~/rh-latency-probe`、`~/robinhood-mev`（這三個路徑在 `$HOME` 下不存在）；未用 sudo 改系統；未改 `polydesk-sim` 程式或規則。完成時 `ls` 確認 `$HOME` 下新增的目錄只有 `grok/`。`~/grok` 占用 **870M**（2026-11-20 22:46:38 Asia/Taipei，`du -sh ~/grok`；主要是 Playwright 下載的 Chromium）。其後刪除無法啟動的 `ms-playwright`，同樹改為 **171M**；2026-11-25 03:32 Asia/Taipei 搬到 `~/web3/grok_workspace/polydesk-probe/` 後 `du -sh` 仍為 **171M**（空的 `~/grok` 已 `rmdir`）。
- 系統套件缺口（需負責人決定是否 sudo 安裝，本次未裝）：
  - `python3-venv`／`ensurepip` 不可用。若要標準 venv：`sudo apt install python3.12-venv`。
  - Playwright Chromium 已下載到 `~/grok/polydesk-probe/ms-playwright`，但啟動失敗，缺少共用函式庫（`ldd`）：`libatk-1.0.so.0`、`libatk-bridge-2.0.so.0`、`libatspi.so.0`、`libXcomposite.so.1`、`libXdamage.so.1`、`libXfixes.so.3`、`libgbm.so.1`、`libasound.so.2`；完整 `chrome` 另外缺 `libcups.so.2`、`libcairo.so.2`、`libpango-1.0.so.0`。Ubuntu 24.04 對應套件（`apt-cache` 查名，未安裝）：`libatk1.0-0t64`、`libatk-bridge2.0-0t64`、`libatspi2.0-0t64`、`libxcomposite1`、`libxdamage1`、`libxfixes3`、`libgbm1`、`libasound2t64`、`libcups2t64`、`libcairo2`、`libpango-1.0-0`。亦可改用官方 `playwright install-deps`（同樣需要 sudo）。

## 1. Binance／Bybit／OKX

### 1.1 Binance REST

關鍵指令（VPS）：

```bash
curl -sS -D - -o /dev/null -w 'http_code=%{http_code} time_total=%{time_total}\n' \
  -A 'polydesk-probe/1.0' \
  'https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT'
```

其餘端點以同樣方式、間隔約 2 秒呼叫。

`GET /fapi/v1/ping`：HTTP 200，`time_total=0.071476`，`X-MBX-USED-WEIGHT-1M: 1`，body `{}`。時刻 `2026-11-20T14:35:24Z`／22:35:24 Asia/Taipei。

`premiumIndex` BTCUSDT（VPS，22:35:26 Asia/Taipei，`time_total=0.079433`，`X-MBX-USED-WEIGHT-1M: 2`）：

```json
{"symbol":"BTCUSDT","markPrice":"61807.56890555","indexPrice":"61870.79260870","estimatedSettlePrice":"61964.53510060","lastFundingRate":"0.00006309","interestRate":"0.00010000","nextFundingTime":1795190400000,"time":1795185326000}
```

`time=1795185326000` = `2026-11-20T14:35:26Z`；`nextFundingTime=1795190400000` = `2026-11-20T16:00:00Z`／2026-11-21 00:00:00 Asia/Taipei。ETHUSDT 同時 HTTP 200，`time_total=0.062602`，權重標頭 3，欄位相同。

同一時刻探測用 box（egress `94.192.72.1`，CloudFront POP `IAD12-P2`，22:35:27 Asia/Taipei，`time_total=0.245107`）回 HTTP 451：

```json
{"code":0,"msg":"Service unavailable from a restricted location according to 'b. Eligibility' in https://www.binance.com/en/terms. Please contact customer service if you believe you received this message in error."}
```

標頭：`server: CloudFront`。因此 Binance 在 VPS 回 200、在 box 回 451，是 IP／地區差異。

`fundingRate` BTCUSDT（22:35:30 Asia/Taipei，`time_total=0.060978`，無 used-weight 標頭）：

```json
[{"symbol":"BTCUSDT","fundingTime":1795132800001,"fundingRate":"0.00002034","markPrice":"61959.30000000","rateType":"Regular"},{"symbol":"BTCUSDT","fundingTime":1795161600000,"fundingRate":"0.00000706","markPrice":"61830.02185157","rateType":"Regular"}]
```

`fundingTime` 分別為 `2026-11-20T00:00:00Z`、`2026-11-20T08:00:00Z`（台北 08:00、16:00）。ETHUSDT 同樣 200，欄位相同。

`openInterest` BTCUSDT（22:35:34 Asia/Taipei，`time_total=0.064502`，`X-MBX-USED-WEIGHT-1M: 4`）：

```json
{"symbol":"BTCUSDT","openInterest":"96060.358","time":1795185328211}
```

ETHUSDT：HTTP 200，權重標頭 5，欄位相同。

`openInterestHist` BTCUSDT `period=5m&limit=2`（22:35:39 Asia/Taipei，`time_total=0.066284`，無 used-weight 標頭）：

```json
[{"symbol":"BTCUSDT","sumOpenInterest":"95753.27000000","sumOpenInterestValue":"5944336167.09271000","CMCCirculatingSupply":"20114434.00000000","timestamp":1795184700000},{"symbol":"BTCUSDT","sumOpenInterest":"95832.58300000","sumOpenInterestValue":"5949627635.74730400","CMCCirculatingSupply":"20114434.00000000","timestamp":1795185000000}]
```

`timestamp` 為 `2026-11-20T14:25:00Z`、`14:30:00Z`（間隔 5 分鐘）。ETHUSDT 同樣 200、欄位相同。官方說明此端點只提供近 1 個月資料；本次只取最近 2 根，未測更舊區間。

`allForceOrders` BTCUSDT（未帶簽名，22:35:43 Asia/Taipei，`time_total=0.079746`）：HTTP 404，`content-type: text/html`，`server: nginx`。正文為 Binance 公開錯誤頁，標題「出错啦！您访问的网页不存在。」／「Sorry! The page you’re looking for cannot be found.」。不是「需要簽名」的 JSON 錯誤，而是端點已不存在或已下線。

### 1.2 Bybit REST（兼測是否 403）

VPS 對 `api.bybit.com` 全部 HTTP 200，沒有 403。公開市場端點本輪回應標頭含 `ret_code: 0`、`server: Openresty`、`x-cache: Miss from cloudfront`、POP `KIX82-P7`，**沒有** `X-Bapi-Limit`、`X-Bapi-Limit-Status`、`X-Bapi-Limit-Reset-Timestamp`。頻率限制因此以官方文件為準：HTTP IP 600 請求／5 秒（[Rate Limit Rules](https://bybit-exchange.github.io/docs/v5/rate-limit)）。

`tickers` BTCUSDT（22:35:45 Asia/Taipei，`time_total=0.058575`）`retCode=0`，重點欄位：

```json
{"symbol":"BTCUSDT","lastPrice":"61833.50","indexPrice":"61865.37","markPrice":"61837.48","openInterest":"70974.952","openInterestValue":"4388912174.80","fundingRate":"0.00004072","nextFundingTime":"1795190400000","fundingIntervalHour":"8","fundingCap":"0.00333"}
```

（完整 list 物件還有 24h 高低、買賣一檔等，見 VPS `out/by_tickers_btc.body`。）ETHUSDT 同樣 200（22:35:47 Asia/Taipei，`time_total=0.068475`），欄位集合相同。

`funding/history` BTCUSDT `limit=2`（22:35:49 Asia/Taipei，`time_total=0.133519`）：

```json
{"retCode":0,"retMsg":"OK","result":{"category":"linear","list":[{"symbol":"BTCUSDT","fundingRate":"-0.00000369","fundingRateTimestamp":"1795161600000"},{"symbol":"BTCUSDT","fundingRate":"0.00002556","fundingRateTimestamp":"1795132800000"}]}}
```

時間戳為 `2026-11-20T08:00:00Z`、`00:00:00Z`。

`open-interest` BTCUSDT `intervalTime=5min&limit=2`（22:35:54 Asia/Taipei，`time_total=0.128485`）：

```json
{"retCode":0,"result":{"symbol":"BTCUSDT","category":"linear","list":[{"openInterest":"70989.90900000","singleOpenInterest":"35494.955","timestamp":"1795185300000"},{"openInterest":"70912.69600000","singleOpenInterest":"35456.348","timestamp":"1795185000000"}],"nextPageCursor":"lastid%3D22352758%26lasttime%3D1795185000"}}
```

`timestamp` 為 `2026-11-20T14:35:00Z`、`14:30:00Z`。ETH 同樣 200。

### 1.3 OKX（只測是否 403）

`GET https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP`：HTTP 200，`time_total=0.065524`，`server: cloudflare`，`cf-ray: ...-KIX`，`code=0`（22:35:58 Asia/Taipei）。

`GET .../public/open-interest?instId=BTC-USDT-SWAP`：HTTP 200，`time_total=0.203059`，同樣非 403（22:36:00 Asia/Taipei）。

### 1.4 強平 WebSocket

VPS 指令（2026-11-20 當時路徑；2026-11-25 起改為 `~/web3/grok_workspace/polydesk-probe/`）：

```bash
PYTHONPATH=~/grok/polydesk-probe/pydeps python3 ~/grok/polydesk-probe/ws_probe.py
```

`websockets==17.4` 當時裝在 `~/grok/polydesk-probe/pydeps`（現隨專案在新路徑的 `pydeps/`）。各連線監聽 90 秒，依序進行，中間間隔 2 秒。

**Binance `wss://fstream.binance.com/ws/btcusdt@forceOrder`**：`2026-11-20T14:38:59Z` 連上（22:38:59 Asia/Taipei），聽到 `14:40:33Z`（22:40:33 Asia/Taipei），`elapsed=95.01s`，`connected=True`，`error=None`，**事件數 0**。

**Binance `wss://fstream.binance.com/ws/!forceOrder@arr`**：`14:40:35Z` 連上（22:40:35 Asia/Taipei），聽到 `14:42:10Z`（22:42:10 Asia/Taipei），`elapsed=95.013s`，同樣連線成功、**事件數 0**。

本窗口無法記錄 Binance 強平事件欄位。0 事件只代表這兩段約 90 秒內沒有推送，不代表該流永遠沒有資料。

**Bybit `wss://stream.bybit.com/v5/public/linear`，subscribe `allLiquidation.BTCUSDT`**：`14:42:12Z` 開始（22:42:12 Asia/Taipei），`elapsed=90.011s`，`connected=True`。共 6 則 WS 訊息：第 1 則為訂閱成功，其後 5 則為清算 snapshot。訂閱回覆（22:42:13 Asia/Taipei）：

```json
{"success":true,"ret_msg":"","conn_id":"dbqqo6mdd3e6godi1fq0-36i8x","req_id":"","op":"subscribe"}
```

第一則清算 snapshot（22:42:19 Asia/Taipei）：

```json
{"topic":"allLiquidation.BTCUSDT","type":"snapshot","ts":1795185739757,"data":[{"T":1795185739377,"s":"BTCUSDT","S":"Buy","v":"0.035","p":"61336.80"},{"T":1795185739486,"s":"BTCUSDT","S":"Buy","v":"0.025","p":"61342.30"}]}
```

`ts=1795185739757` = `2026-11-20T14:42:19.757Z`。其後還有 snapshot（例如 22:42:20、22:43:42 Asia/Taipei），欄位相同。官方文件對 `S` 的說明：`Buy` 表示多單被強平。

**Bybit 同一 host，subscribe `allLiquidation.ETHUSDT`**：`14:43:45Z` 連上（22:43:45 Asia/Taipei），聽到 `14:45:14Z`（22:45:14 Asia/Taipei），`elapsed=90.014s`。2 則訊息：訂閱成功 + 1 則清算 snapshot（22:44:23 Asia/Taipei）：

```json
{"topic":"allLiquidation.ETHUSDT","type":"snapshot","ts":1795185863326,"data":[{"T":1795185863283,"s":"ETHUSDT","S":"Buy","v":"0.08","p":"1725.85"}]}
```

`ts=1795185863326` = `2026-11-20T14:44:23.326Z`。

## 2. Farside BTC／ETH

### 2.1 VPS curl（瀏覽器 UA）

時刻：BTC `2026-11-20T14:36:02Z`／22:36:02 Asia/Taipei，`time_total=0.113172`；ETH `14:36:04Z`／22:36:04 Asia/Taipei，`time_total=0.049294`。

兩邊皆 HTTP 403。關鍵標頭（BTC）：

```
HTTP/2 403
cf-mitigated: challenge
server: cloudflare
cf-ray: a5d82f46adabfc9c-KIX
```

ETH：`cf-ray: a5d82f53bc83b118-KIX`，同樣 `cf-mitigated: challenge`。

Body 開頭（BTC，5597 bytes；ETH 同樣結構）：

```html
<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>
```

頁內腳本含 `window._cf_chl_opt`、`cType: 'managed'`、`cZone: 'farside.co.uk'`。這是 Cloudflare managed challenge，不是一般 403 空頁。依規則不繞過 challenge。

### 2.2 對照：探測用 box curl（同一時段）

本輪使用者電腦離線，無法從共用電腦重測。負責人先前：共用電腦 curl 回 200、VPS 回 403。box 對照如下（瀏覽器 UA 相同）。

- box egress：`https://api.ipify.org` 回 `94.192.72.1`（22:35:26 Asia/Taipei）。Farside 頁尾另印 `Your IP: 104.23.253.143`。`cf-ray` 節點 `EWR`／`IAD`。
- `https://farside.co.uk/btc/`：HTTP 200，`time_total=0.657428`，`server: cloudflare`，`cf-ray: a5d82e6f3fb843d7-EWR`，`cf-cache-status: DYNAMIC`，**沒有** `cf-mitigated`（22:35:28 Asia/Taipei）。`<title>Bitcoin ETF Flow (US$m) – Farside Investors</title>`。
- `https://farside.co.uk/eth/`：HTTP 200，`time_total=0.623893`，`cf-ray: a5d82e799e2ec647-EWR`（22:35:30 Asia/Taipei）。`<title>Ethereum ETF Flow (US$m) – Farside Investors</title>`。

box 看到的表格欄位（僅作為「當 HTTP 200 時頁面有什麼」的對照，**不是** VPS 上可取得的資料）：

- BTC 基金欄：`IBIT, FBTC, BITB, ARKB, BTCO, EZBC, BRRR, HODL, BTCW, MSBT, GBTC, BTC`，另有 `Total`、`Fee`。HTML 表列日期從 `02 Nov 2026` 到 `20 Nov 2026`（週末 7–8、14–15 Nov 無列，符合美股 ETF 交易日）。
- ETH 基金欄：`ETHA, ETHB, FETH, ETHW, TETH, ETHV, QETH, EZET, MSSE, ETHE, ETH`，另有 `Total`、`Fee`、`Staking fee`。日期同樣到 `20 Nov 2026`。
- 完整度（box、22:35 Asia/Taipei）：`19 Nov 2026` 各基金與 Total 皆有數值；`20 Nov 2026`（實測當天）各基金為 `-`，Total 為 `0.0`，當天尚未更新完。

### 2.3 VPS headless Chromium

已在當時的 `~/grok/polydesk-probe` 執行（未用 sudo；2026-11-25 專案已遷至 `~/web3/grok_workspace/polydesk-probe/`）：

```bash
python3 -m pip install --target ~/grok/polydesk-probe/pydeps playwright
PLAYWRIGHT_BROWSERS_PATH=~/grok/polydesk-probe/ms-playwright python3 -m playwright install chromium
```

Playwright 1.65.2、Chrome for Testing 159.0.8154.6 下載到 `~/grok/polydesk-probe/ms-playwright`（未寫入 `~/.cache/ms-playwright`）。腳本只用預設 headless Chromium 載入一次，沒有 stealth 外掛、不解 captcha、不偽造指紋。

啟動失敗時間：`2026-11-20T14:43:22Z`／22:43:22 Asia/Taipei。錯誤為缺少共用函式庫，行程立刻結束，**沒有對 Farside 發出瀏覽器請求**：

```
chrome-headless-shell: error while loading shared libraries: libatk-1.0.so.0: cannot open shared object file: No such file or directory
```

完整 `ldd` 缺套件見上文「系統套件缺口」。依規則停止，不自行 `apt`／sudo。因此 VPS 上「一般瀏覽器能不能通過 Cloudflare challenge」這個問題，本次無法回答。若負責人批准安裝上述函式庫，可以再做一次正常載入；若屆時仍是 challenge，應記錄「過不了」並停止。

## 3. CoinGlass 清算熱力圖（只看可見性）

只做一次 `curl`（瀏覽器 UA、跟隨一次 301）。未擷取熱力圖資料、未呼叫或逆向其 API、未嘗試繞過登入或付費牆。Headless 瀏覽器因 §2.3 同一原因未能載入。

- `https://www.coinglass.com/pro/futures/LiquidationHeatMap`（22:36:07 Asia/Taipei，`time_total=0.197656`）：先 HTTP 301，`location: /LiquidationHeatMap/BTC`，再 HTTP 200，`content-type: text/html; charset=utf-8`，CloudFront POP `KIX56-P2`。HTML 約 604004 bytes。`<title>Crypto & Bitcoin (BTC) Liquidation Heatmap | CoinGlass</title>`。可見標題含「BTC Liquidation Heatmap」。HTML 含 `<canvas>`、`__NEXT_DATA__`（Next.js）。有「Login」連結，無 password 輸入框。頁源出現 login／premium／subscribe／unlock 等字樣（行銷或導向文字；**未**據此打開或繞過任何付費內容）。
- `https://www.coinglass.com/LiquidationData`（22:36:09 Asia/Taipei，`time_total=0.101503`）：先 HTTP 301，`location: /liquidations`，再 HTTP 200。HTML 約 414084 bytes。`<title>Bitcoin & Crypto Liquidations: Real-Time Data & Charts | CoinGlass</title>`。可見標題含「Liquidation Data」「Liquidation Heatmap」「Live LiquidationsConnecting to CoinGlass」。有「Login」連結，無 `<canvas>`。同樣未擷取任何清算數值。

結論：公開頁面對 VPS 不是 Cloudflare 擋掉（與 Farside 不同），一般 HTTP 載入可拿到頁面殼。curl 無法確認互動熱力圖是否需登入後才完整可見。

## 對 polydesk-sim 的含意

以下只陳述事實，不建議改規則，也不把任何來源接進正式流程。是否採用由負責人與使用者決定。

- 從日本 VPS 看，Binance USD-M 公開 REST（資金費率、OI、OI 歷史）與 Bybit v5 對應公開 REST 目前都可在未登入、未帶 key 的情況下取得。這與探測用 box 上 Binance 回 451（地區封鎖）不同，差異在 IP／地區。
- Binance 公開強平 REST `allForceOrders` 本次回 404，不能當作清算證據來源。Binance 強平 WS 可以從該 VPS 連上，但兩個 90 秒窗口都沒有事件，本次無法記錄欄位，也不能從這麼短的窗口判斷它是否穩定可用。
- Bybit 公開強平 WS（`allLiquidation.BTCUSDT`／`ETHUSDT`）從該 VPS 連線成功，且在約 90 秒內收到真實清算事件與欄位。這使它能作為清算證據來源的**候選**。是否違反既有規則 6（資料不可用則 SKIP；且不得用清算代理指標），由負責人決定。
- Bybit／OKX 公開 REST 從該 VPS 不是 403。
- Farside 從該 VPS 的 curl 會碰到 Cloudflare managed challenge（403），同一時段從 box 則可以讀到表格；`20 Nov 2026` 當天列在 box 上看起來尚未更新完，`19 Nov 2026` 已有各基金數值。VPS 上一般瀏覽器能否通過 challenge，因缺少系統函式庫而尚未測成。Farside 是否接入正式流程，仍等使用者決定。
- CoinGlass 公開頁在 VPS 上可以載入 HTML，但本次依規則沒有抓熱力圖資料，也沒有測其非公開 API。
