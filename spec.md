# 軟體需求規格書 (Software Requirements Specification)
# 專案名稱：台指期 1 分 K 線資料自動下載器 (Shioaji API)

**版本**: 1.2
**日期**: 2025-11-19
**作者**: Gemini AI Assistant (Collaborated with User)

---

## 1. 專案概述 (Overview)
本專案旨在開發一自動化 Python 程式，利用永豐金證券 (Sinopac) 的 **Shioaji API**，自動登入並抓取 **台灣加權指數期貨 (TXF)** 的 1 分鐘 K 線 (1m OHLCV) 歷史資料。

程式核心功能包含下載**近月合約**與**連續月合約**，並提供互動式選單，讓使用者選擇將資料儲存至 **Google Cloud Firestore**、**CSV 檔案**，或兩者皆存。

---

## 2. 環境與帳戶需求 (Environment & Credentials)

### 2.1 執行環境
* **作業系統**: Windows 10/11, macOS, 或 Linux。
* **程式語言**: Python 3.8+
* **必要 Python 套件**:
  * `shioaji`: 核心 API，用於連接券商、行情下載。
  * `pandas`: 用於時間序列處理、資料清洗、CSV 輸出。
  * `firebase-admin`: 用于連接 Google Cloud Firestore。
  * `python-dotenv`: 用於環境變數管理，避免明文儲存帳密。
* **網路連線**: 必須具備穩定網際網路連線。

### 2.2 帳戶與憑證
* **證券帳戶**: 具備有效之永豐金證券/期貨帳戶且已開通 API 權限。
* **電子憑證**: 需備妥有效之 Shioaji `.pfx` 憑證檔案及對應密碼。
* **Google Cloud 帳戶**: 若要使用 Firestore，需具備 Google Cloud 專案及服務帳號金鑰 (JSON 檔案)。

---

## 3. 功能需求 (Functional Requirements)

### 3.1 身份驗證 (Authentication)
* **API 登入**: 系統需使用 `API_KEY` 與 `SECRET_KEY` 進行初始化登入。
* **憑證簽章 (CA)**: 系統需讀取 `.pfx` 檔案路徑與密碼，執行 `activate_ca`。
* **安全規範**: 強烈建議使用 `.env` 檔案管理所有敏感資訊 (Keys/Passwords/Paths)。

### 3.2 合約選取與資料下載 (Contract & Data Retrieval)
* **商品標的**: 台指期 (TXF)。
* **近月合約下載**:
  * 自動鎖定當前的近月合約。
  * 透過 `api.ticks` 下載指定天數內的**逐筆成交資料 (Ticks)**。
  * 在本地端使用 `pandas` 將 Ticks **重新取樣 (Resample)** 為 1 分鐘 K 線資料。
* **連續月資料拼接**:
  * 實作換月邏輯，根據合約到期日自動切換標的。
  * 處理邏輯：一個合約的交易期間，是從上個合約到期日的隔天，到自己到期日當天。
  * 依序下載各合約在有效期間內的 Ticks 資料，最後合併並轉換為一筆連續的 1 分鐘 K 線資料。

### 3.3 資料處理 (Data Processing)
* **時間轉換**: 將 Shioaji 回傳的 `ts` (奈秒) 轉換為 `datetime` 物件。
* **時區校正**: 確保時間標記為台灣標準時間 (Asia/Taipei, GMT+8)。
* **資料清洗**: 移除重複數據並依時間排序。
* **欄位篩選**: 僅保留 `datetime`, `Open`, `High`, `Low`, `Close`, `Volume`。

### 3.4 互動式輸出 (Interactive Output)
* **啟動選單**: 程式執行時，需提供一個文字介面選單，讓使用者選擇儲存方式。
* **選項**:
  1.  **僅儲存至 Firebase**: 將資料寫入 Firestore。
  2.  **僅儲存為 CSV 檔案**: 將資料寫入本地 CSV。
  3.  **同時儲存**: 同時執行上述兩種儲存操作。

### 3.5 檔案與資料庫輸出 (Output & Storage)
* **互動式介面 (Interactive Interface)**:
  * 系統需提供一個文字選單，讓使用者可以選擇要下載的資料區間。
  * 支援的選項應包含：
    1.  上一個交易日的資料。
    2.  本週至今的資料。
    3.  本月至今的資料。
    4.  近半年的資料。
    5.  近一年的資料。
    6.  近五年的資料。
    7.  自訂起訖區間。
  * 當使用者選擇「自訂起訖區間」時，系統需能接收使用者輸入的開始與結束日期 (格式: YYYY-MM-DD)。

### 3.6 檔案與資料庫輸出 (Output & Storage)
* **CSV 格式**:
  * **編碼**: `utf-8-sig`。
  * **檔名規則**:
    *   `TXF_1m_data_{開始日期}_to_{結束日期}.csv`
* **Firestore 寫入**:
  * **集合名稱**: 預設為 `TXF_1min`。
  * **文件 ID**: 使用 K 線的 `datetime` 作為文件唯一識別碼 (格式: `YYYY-MM-DD HH:MM:SS`)。
  * **批次寫入**: 為了提升效能，採用 `batch` 方式分批寫入資料。

---

## 4. 資料規格 (Data Schema)

### 4.1 輸入參數設定
| 參數變數 (建議存於 .env) | 類型 | 描述 |
| :--- | :--- | :--- |
| `SHIOAJI_API_KEY` | String | Shioaji API Key |
| `SHIOAJI_SECRET_KEY` | String | Shioaji Secret Key |
| `SHIOAJI_CERT_PATH` | String | `.pfx` 憑證檔案絕對路徑 |
| `SHIOAJI_CERT_PASS` | String | 憑證密碼 |
| `GOOGLE_APPLICATION_CREDENTIALS` | String | Google Cloud 服務帳號金鑰 JSON 檔案的絕對路徑 |

### 4.2 輸出資料結構 (CSV / Firestore)
| 欄位名稱 | 資料類型 | 範例值 | 說明 |
| :--- | :--- | :--- | :--- |
| **datetime** | DateTime / Timestamp | `2025-11-19 09:00:00` | K 線起始時間 (已轉為台北時區) |
| **Open** | Float | `22500.0` | 開盤價 |
| **High** | Float | `22505.0` | 最高價 |
| **Low** | Float | `22495.0` | 最低價 |
| **Close** | Float | `22502.0` | 收盤價 |
| **Volume** | Integer | `1540` | 成交量 (口) |

---

## 5. 例外處理 (Exception Handling)
系統需針對下列情況進行錯誤捕捉並提供清晰的提示訊息：
1. **登入/憑證失敗**: 帳密或路徑錯誤。 -> *終止程式並報錯*。
2. **Firebase 金鑰錯誤**: 選擇寫入 Firebase 但找不到金鑰檔案。 -> *提示使用者檢查檔案路徑*。
3. **查無合約**: API 初始化未完成或市場無合約。 -> *提示檢查網路或 API 狀態*。
4. **無歷史資料**: 指定時間範圍內無交易 (如假日)。 -> *輸出警告訊息，不產生空檔案或寫入空資料*。
5. **無效輸入**: 使用者在互動選單輸入非預期選項。 -> *提示重新輸入*。

---

## 6. 開發與部署 (Development & Deployment)

### 6.1 Git 輔助腳本 (`git_helper.sh`)
本專案提供 `git_helper.sh` 腳本以簡化 Git 版控流程。
*   **功能**: 自動化 `git init`, `add`, `commit`, `push` 等操作，並協助設定遠端儲存庫。
*   **目的**: 統一團隊成員的提交習慣，降低手動操作的複雜度。

### 6.2 持續整合 (CI)
*   **GitHub Actions**: (若有配置) 每次 `push` 到主要分支時，將自動觸發測試流程，確保程式碼品質。
