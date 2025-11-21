# 台指期資料自動下載器

[![Python Tests](https://github.com/weiyuanlo/TX/actions/workflows/python-tests.yml/badge.svg)](https://github.com/weiyuanlo/TX/actions/workflows/python-tests.yml)

---

本專案是一個 Python 腳本，用於自動從永豐金證券 (Sinopac) 的 **Shioaji API** 下載**台灣加權指數期貨 (TXF)** 的 **1 分鐘 K 線 (1m OHLCV)** 與 **逐筆成交 (Ticks)** 歷史資料。

## 功能特色

*   **原生連續月合約**: 直接使用 Shioaji API 的 `TXFR1` 連續月合約物件，無需手動拼接換月資料。
*   **多元資料下載**: 支援下載 **1 分鐘 K 線 (K-bars)** 與 **逐筆成交 (Ticks)** 兩種歷史資料。
*   **彈性資料選擇**: 提供互動選單，讓使用者可自由選擇僅下載 Ticks、僅下載 K-bar，或兩者都下載。
*   **下載中斷續傳**: 在下載 Ticks 資料時，若程式意外中斷，下次執行時會自動從上次失敗的日期續傳，節省時間。
*   **Token 自動更新**: 內建 Token 過期偵測機制。在長時間下載過程中若 Token 失效，系統會自動重新登入並重試，提升執行穩定性。
*   **多元儲存選項**:
    *   K 線資料可儲存至本地 **CSV** 或 **Google Cloud Firestore**。
    *   Ticks 資料則會依日期自動分批儲存為 CSV 檔案於 `tradedata/` 目錄下。
*   **API 流量監控**: 登入後自動查詢並顯示 API 已使用流量。若用量超過 400MB，將發出警告提醒。
*   **安全設定**: 使用 `.env` 檔案管理 API 金鑰、憑證路徑等敏感資訊，確保安全性。
*   **自動化測試**: 整合 GitHub Actions，在程式碼提交時自動執行 `unittest` 單元測試，確保品質。
*   **版本相容性**: 內建版本檢查機制，確保腳本在合適的 `shioaji` 版本下運行。

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
    -   `SHIOAJI_API_KEY`: 您的永豐金 API Key。
    -   `SHIOAJI_SECRET_KEY`: 您的永豐金 API Secret。
    -   `SHIOAJI_CERT_PATH`: 您的憑證檔案 (`.pfx`) 的**絕對路徑**。
    -   `SHIOAJI_CERT_PASS`: 您的憑證密碼。

3.  **Google Cloud Firestore 設定**:
    -   若要使用 Firestore 功能，請確保您已經在 Google Cloud Platform 建立了一個專案並啟用了 Firestore。
    -   下載您的服務帳號 JSON 金鑰檔案，並將其命名為 `serviceAccountKey.json` 放置於本專案根目錄下。
    -   (進階) 您也可以在 `.env` 檔案中設定 `GOOGLE_APPLICATION_CREDENTIALS` 變數，指向您的金鑰檔案絕對路徑。

## 如何執行

直接執行 `tx_downloader.py` 腳本，程式將會透過三層選單引導您完成操作。

```bash
python3 tx_downloader.py
```

### 互動流程

1.  **選擇儲存方式**:
    -   `1. 僅儲存至 Firebase`
    -   `2. 僅儲存為 CSV 檔案`
    -   `3. 同時儲存至 Firebase 和 CSV`

2.  **選擇資料區間**:
    -   `1. 上一個交易日的資料`
    -   `2. 本週至今的資料`
    -   ... (其他選項)
    -   `7. 自訂起訖區間`

3.  **選擇資料類型**:
    -   `a. 下載 Ticks 資料`
    -   `b. 下載 K-bar 資料`
    -   `c. 下載 Ticks 與 K-bar 資料`

完成選擇後，程式將開始執行下載任務。

## 如何執行測試

若要手動執行本專案的單元測試，請在根目錄下運行以下指令：

```bash
python -m unittest discover tests/
```

---

## 開發輔助 (Development Helper)

本專案包含一個 `git_helper.sh` 腳本，旨在簡化開發過程中的 Git 操作與專案初始化。

### 功能

*   **自動化 Git 操作**: 協助執行 `git init`, `git add`, `git commit`, `git push` 等常用指令。
*   **設定遠端儲存庫**: 如果尚未設定 `origin`，腳本會引導您新增遠端 GitHub 儲存庫 URL。
*   **建立 `.gitignore`**: 如果專案中缺少 `.gitignore` 檔案，會自動生成一份適用於 Python 專案的預設版本。
*   **整理工作流程檔案**: 自動將根目錄的 `.yml` 檔案移動到 `.github/workflows/` 目錄下。

### 使用方式

```bash
bash git_helper.sh
```
