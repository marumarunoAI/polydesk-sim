# polydesk-sim

Polymarket 加密市場**模擬**交易台（BTC/ETH）。**只模擬、不下真單**：沒有錢包、沒有私鑰、沒有簽名或送單程式、不登入 Polymarket。只讀免費公開資料。

策略與風控規則只寫在 [DESK_RULES.md](DESK_RULES.md)，由負責人決定，程式員不改。

## 需求
Python 3.10+，`pip install requests`（其餘只用標準函式庫）。

## 執行
```
python board.py        # 掃 Gamma + CLOB，寫 board/board_<UTC>.json 與 board/latest.json
```

## 輸出
執行輸出（board/ 等）不進 git，見 `.gitignore`；範例檔在 `examples/board_sample.json`。
