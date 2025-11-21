# 軟體需求規格書 (Software Requirements Specification)
# 專案名稱：台指期資料自動下載器 (Shioaji API)

**版本**: 2.1
**日期**: 2025-11-20
**作者**: Gemini AI Assistant (Collaborated with User)

---

## 1. 專案概述 (Overview)
本專案旨在開發一自動化 Python 程式，利用永豐金證券 (Sinopac) 的 **Shioaji API**，自動登入並抓取 **台灣加權指數期貨 (TXF)** 的 **連續月合約 (TXFR1)** 的歷史資料。

程式核心功能包含下載 **Ticks** 與 **1 分鐘 K 線 (1m OHLCV)**，並提供互動式選單，讓使用者選擇將資料儲存至 **Google Cloud Firestore** 或 **CSV 檔案**。

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
  * `packaging`: 用於版本號比對。
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
* **流量查詢與警告**:
    * 登入成功後，系統需自動呼叫 `api.usage()` 查詢並顯示目前的 API 流量使用狀況。
    * **若 API 已使用流量超過 400MB，系統將在日誌中顯示一條警告訊息**，提醒使用者注意用量。
    * 流量資訊格式範例: `connections=1 bytes=40890319 limit_bytes=524288000 remaining_bytes=483397681`
* **安全規範**: 強烈建議使用 `.env` 檔案管理所有敏感資訊 (Keys/Passwords/Paths)。

### 3.2 合約選取與資料下載 (Contract & Data Retrieval)
* **商品標的**: 台指期連續月合約 (`TXFR1`)。
* **下載機制**: 本系統直接利用 Shioaji API 提供的**連續月合約物件** (`api.Contracts.Futures.TXF.TXFR1`) 進行資料查詢，不需手動進行換月合約的拼接。API 會自動處理合約換月的細節。

* **Ticks 資料下載**:
  * 系統會逐日下載指定區間內的 Ticks 資料。
  * **API 用法範例**:
    ```python
    ticks = api.ticks(
        contract=api.Contracts.Futures.TXF.TXFR1, 
        date="2020-03-22"
    )
    ```

* **K-bars (1分鐘線) 資料下載**:
  * 系統會一次性下載指定起訖日期區間內的 1 分鐘 K 線資料。
  * **API 用法範例**:
    ```python
    kbars = api.kbars(
        contract=api.Contracts.Futures.TXF.TXFR1,
        start="2025-11-18", 
        end="2025-11-19", 
    )
    ```

### 3.3 資料處理 (Data Processing)
* **K-bar 資料**:
    * **時間轉換**: 將 Shioaji 回傳的 `ts` (奈秒) 轉換為 `datetime` 物件。
    * **時區校正**: 確保時間標記為台灣標準時間 (Asia/Taipei, GMT+8)。
    * **欄位篩選**: 僅保留 `datetime`, `Open`, `High`, `Low`, `Close`, `Volume`。
* **Tick 資料**:
    * **時間轉換**: 將 `ts` (奈秒) 轉換為 `datetime` 物件並校正時區。

### 3.4 Token 自動更新 (Token Auto-Refresh)
* **背景**: Shioaji API 的 Token 具有時效性，在長時間執行下載任務時可能會過期。
* **機制**:
    * 系統會在執行 API 請求（如 `api.ticks`, `api.kbars`）時，自動偵測因 Token 失效而引發的錯誤。
    * 當偵測到此類錯誤時，系統將自動執行一次重新登入 (`login`) 程序以獲取新的 Token。
    * 獲取新 Token 後，系統會自動重試剛才失敗的下載請求。
    * 如果重試後仍然失敗，程式將會終止並顯示錯誤訊息。

### 3.5 下載中斷續傳 (Resumable Download)
* **目的**: 避免因網路中斷、程式崩潰等意外情況導致需要從頭重新下載整個批次的資料。
* **機制**:
    * **進度標記**: 在開始下載某一天的 Ticks 資料之前，系統會將該日期記錄到一個進度檔案 (`download_progress.txt`) 中。
    * **完成標記**: 當該天的所有資料（Ticks/K-bar）成功下載並儲存後，系統會將此進度檔案刪除。
    * **啟動檢查**: 程式每次啟動時，會檢查 `download_progress.txt` 檔案是否存在。
        * **若檔案存在**: 系統會讀取檔案中的日期，並將其作為本次下載任務的起始日期，忽略使用者原先的選擇。同時會提示使用者正在從上次中斷的地方繼續。
        * **若檔案不存在**: 則按照使用者選擇的日期區間正常執行。

### 3.6 互動式介面與輸出 (Interactive Interface & Output)
* **啟動選單**: 程式執行時，需提供一個文字介面選單，讓使用者選擇儲存方式與資料區間。
* **儲存選項**:
  1.  **僅儲存至 Firebase**
  2.  **僅儲存為 CSV 檔案**
  3.  **同時儲存**
* **時間區間選項**:
  1.  上一個交易日
  2.  本週至今
  3.  本月至今
  4.  近半年
  5.  近一年
  6.  近五年
  7.  自訂起訖區間 (格式: YYYY-MM-DD)
* **資料類型選項 (新增)**:
    * 在選擇時間區間之後，系統會顯示新的選單讓使用者選擇要下載的資料類型。
    * **選單內容**:
        1.  `a. 下載 Ticks 資料`
        2.  `b. 下載 K-bar 資料`
        3.  `c. 下載 Ticks 與 K-bar 資料`

### 3.7 K-bar 資料儲存 (K-bar Data Storage)
* **CSV 格式**:
  * **編碼**: `utf-8-sig`。
  * **檔名規則**: `TXF_1m_data_{開始日期}_to_{結束日期}.csv`
* **Firestore 寫入**:
  * **集合名稱**: `TXF_1min`。
  * **文件 ID**: 使用 K 線的 `datetime` 作為文件唯一識別碼 (格式: `YYYY-MM-DD HH:MM:SS`)。
  * **批次寫入**: 採用 `batch` 方式分批寫入資料以提升效能。

### 3.8 Tick 資料儲存策略 (Tick Data Storage Strategy)
*   **儲存目錄**:
    *   所有 Tick 資料的 CSV 檔案都應儲存於專案根目錄下的 `tradedata/` 資料夾中。
    *   此 `tradedata/` 資料夾應被加入到 `.gitignore` 檔案中，以避免將大量的資料檔案提交至版本控制。
*   **長週期查詢處理**:
    *   當使用者請求的資料區間**大於 7 天**時，系統會將下載任務**分割成以「週」為單位的區塊**。
    *   每個週區塊的資料會被儲存成一個獨立的 CSV 檔案。
    *   **檔名規則**: `TXF_ticks_weekly_{週開始日期}_to_{週結束日期}.csv` (例如: `TXF_ticks_weekly_2025-11-10_to_2025-11-16.csv`)。
    *   每週的起始日為週一。
*   **短週期查詢處理**:
    *   若請求區間**小於等於 7 天**，則將所有 Ticks 儲存至單一 CSV 檔案。
    *   **檔名規則**: `TXF_ticks_{開始日期}_to_{結束日期}.csv`。

---

## 4. 資料規格 (Data Schema)

### 4.1 輸入參數設定 (.env)
| 參數變數 | 類型 | 描述 |
| :--- | :--- | :--- |
| `SHIOAJI_API_KEY` | String | Shioaji API Key |
| `SHIOAJI_SECRET_KEY` | String | Shioaji Secret Key |
| `SHIOAJI_CERT_PATH` | String | `.pfx` 憑證檔案絕對路徑 |
| `SHIOAJI_CERT_PASS` | String | 憑證密碼 |
| `GOOGLE_APPLICATION_CREDENTIALS` | String | (可選) Google Cloud 服務帳號金鑰 JSON 檔案的絕對路徑 |

### 4.2 K-bar 輸出資料結構 (CSV / Firestore)
| 欄位名稱 | 資料類型 | 範例值 | 說明 |
| :--- | :--- | :--- | :--- |
| **datetime** | DateTime / Timestamp | `2025-11-19 09:00:00` | K 線起始時間 (台北時區) |
| **Open** | Float | `22500.0` | 開盤價 |
| **High** | Float | `22505.0` | 最高價 |
| **Low** | Float | `22495.0` | 最低價 |
| **Close** | Float | `22502.0` | 收盤價 |
| **Volume** | Integer | `1540` | 成交量 (口) |

### 4.3 Tick 原始資料結構 (Raw Tick Data Structure)
| 欄位名稱 | 資料類型 | 範例值 | 說明 |
| :--- | :--- | :--- | :--- |
| **ts** | Integer | `1616166000030000000` | 奈秒時間戳 |
| **close** | Float | `16011.0` | 成交價 |
| **volume** | Integer | `49` | 單筆成交量 |
| **bid_price** | Float | `16011.0` | 買一價 |
| **bid_volume** | Integer | `1` | 買一量 |
| **ask_price** | Float | `16013.0` | 賣一價 |
| **ask_volume** | Integer | `1` | 賣一量 |
| **tick_type** | Integer | `1` | Tick 類型 (1: Deal, 2: Buy, 3: Sell) |

---

## 5. 例外處理 (Exception Handling)
系統需針對下列情況進行錯誤捕捉並提供清晰的提示訊息：
1. **登入/憑證失敗**: 帳密或路徑錯誤。 -> *終止程式並報錯*。
2. **Firebase 金鑰錯誤**: 選擇寫入 Firebase 但找不到金鑰檔案。 -> *提示使用者檢查檔案路徑*。
3. **查無合約**: API 初始化未完成或市場無合約。 -> *提示檢查網路或 API 狀態*。
4. **無歷史資料**: 指定時間範圍內無交易 (如假日)。 -> *輸出警告訊息，不產生空檔案或寫入空資料*。
5. **無效輸入**: 使用者在互動選單輸入非預期選項。 -> *提示重新輸入*。
6. **Token 過期**: 在 API 請求期間 Token 失效。 -> *自動重新登入並重試一次。若再次失敗則終止程式*。

---

## 6. 開發與部署 (Development & Deployment)

### 6.1 Git 輔助腳本 (`git_helper.sh`)
本專案提供 `git_helper.sh` 腳本以簡化 Git 版控流程。
*   **功能**: 自動化 `git init`, `add`, `commit`, `push` 等操作，並協助設定遠端儲存庫。
*   **目的**: 統一團隊成員的提交習慣，降低手動操作的複雜度。

### 6.2 持續整合 (CI)
*   **GitHub Actions**: 每次 `push` 到主要分支時，將自動觸發測試流程，確保程式碼品質。

### 6.3 自動化測試 (Automated Testing)
*   **測試框架**: 本專案採用 Python 內建的 `unittest` 框架來編寫與執行單元測試。
*   **測試範圍**: 測試案例應涵蓋核心商業邏輯，例如資料下載、時間轉換及檔案儲存等功能。
*   **執行方式**:
    *   **本地執行**: 開發者可透過 `python -m unittest discover tests/` 指令在本機環境執行所有測試。
    *   **CI/CD**: GitHub Actions 工作流程已設定在每次 `push` 和 `pull_request` 時自動執行所有單元測試，實現持續整合。
