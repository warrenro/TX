# 台指期 1 分 K 線資料自動下載器

本專案是一個 Python 程式，用於自動從永豐金證券 (Sinopac) 的 **Shioaji API** 下載**台灣加權指數期貨 (TXF)** 的 1 分鐘 K 線 (1m OHLCV) 歷史資料。

程式會執行以下操作：
1.  登入 Shioaji API。
2.  抓取期貨資料。
3.  將資料儲存到 Google Cloud Firestore。
4.  同時也支援將資料輸出為 CSV 檔案。

## 功能特色

*   **下載近期合約資料**: 自動抓取近月合約的 K 線資料。
*   **連續月資料拼接**: 實作換月邏輯，將多個月份的期貨合約拼接成一筆長期的連續資料。
*   **設定檔分離**: 建議使用 `.env` 檔案來管理敏感的帳號資訊，避免將 API Keys 或密碼直接寫在程式碼中。
*   **資料庫整合**: 支援將下載的資料寫入 Google Cloud Firestore，方便後續的雲端應用與分析。

## 系統需求

*   Python 3.8+
*   相關套件請見 `requirements.txt`

## 設定步驟

1.  **安裝依賴套件**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **設定環境變數**:
    複製 `.env.example` 檔案並重新命名為 `.env`。
    ```bash
    cp .env.example .env
    ```
    接著，編輯 `.env` 檔案，填入您的真實資訊：
    *   `SHIOAJI_API_KEY`: 您的永豐金 API Key。
    *   `SHIOAJI_SECRET_KEY`: 您的永豐金 API Secret。
    *   `SHIOAJI_CERT_PATH`: 您的憑證檔案 (`.pfx`) 的**絕對路徑**。
    *   `SHIOAJI_CERT_PASS`: 您的憑證密碼。
    *   `GOOGLE_APPLICATION_CREDENTIALS`: 您的 Google Cloud 服務帳號金鑰 JSON 檔案的**絕對路徑**。

3.  **Google Cloud Firestore 設定**:
    *   確保您已經在 Google Cloud Platform 建立了一個專案，並啟用了 Firestore。
    *   下載服務帳號的 JSON 金鑰檔案，並將其路徑填入 `.env` 檔案的 `GOOGLE_APPLICATION_CREDENTIALS` 變數中。

## 如何執行

直接執行 `tx_downloader.py` 腳本即可開始下載資料。

```bash
python tx_downloader.py
```

程式預設會執行兩個範例：
1.  下載近 5 天的**近月合約**資料。
2.  下載近 30 天的**連續月**資料。

下載的資料會同時儲存到您設定的 **Firestore** 資料庫以及本地的 **CSV** 檔案中。
