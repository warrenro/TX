# 台指期 1 分鐘 K 線資料自動下載器

[![Python Project CI](https://github.com/weiyuanlo/TX/actions/workflows/python-ci.yml/badge.svg)](https://github.com/weiyuanlo/TX/actions/workflows/python-ci.yml)

---

本專案是一個 Python 腳本，用於自動從永豐金證券 (Sinopac) 的 **Shioaji API** 下載**台灣加權指數期貨 (TXF)** 的 1 分鐘 K 線 (1m OHLCV) 歷史資料。

## 功能特色

*   **連續月資料拼接**: 實作換月邏輯，將多個月份的期貨合約拼接成一筆長期的連續資料。
*   **互動式選單**: 提供簡單易懂的文字選單，讓使用者輕鬆選擇下載區間與儲存方式。
*   **多樣化儲存**: 支援將下載的資料儲存為本地 CSV 檔案，或寫入 Google Cloud Firestore。
*   **安全設定**: 使用 `.env` 檔案來管理敏感的帳號資訊，避免將 API Keys 或密碼直接寫在程式碼中。
*   **自動化測試**: 整合 GitHub Actions，在每次提交時自動執行單元測試，確保程式碼品質。
*   **版本相容性**: 內建版本檢查機制，確保腳本在合適的 `shioaji` 版本下運行。
*   **流量監控**: 登入後自動顯示 API 流量使用狀況，幫助使用者掌握用量。
*   **穩健的資料獲取**: 採用「先下載逐筆成交 (Ticks)，再手動轉換為 K 線」的策略，以應對不同 API 版本的介面差異。

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
    -   `SHIOAJI_API_KEY`: 您的永豐金 API Key。
    -   `SHIOAJI_SECRET_KEY`: 您的永豐金 API Secret。
    -   `SHIOAJI_CERT_PATH`: 您的憑證檔案 (`.pfx`) 的**絕對路徑**。
    -   `SHIOAJI_CERT_PASS`: 您的憑證密碼。

3.  **Google Cloud Firestore 設定**:
    -   若要使用 Firestore 功能，請確保您已經在 Google Cloud Platform 建立了一個專案並啟用了 Firestore。
    -   下載您的服務帳號 JSON 金鑰檔案，並將其命名為 `serviceAccountKey.json` 放置於本專案根目錄下。
    -   (進階) 您也可以在 `.env` 檔案中設定 `GOOGLE_APPLICATION_CREDENTIALS` 變數，指向您的金鑰檔案絕對路徑。

## 如何執行

直接執行 `tx_downloader.py` 腳本，程式將會引導您完成操作。

```bash
python3 tx_downloader.py
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
