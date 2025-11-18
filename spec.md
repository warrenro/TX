# 軟體需求規格書 (Software Requirements Specification)
# 專案名稱：台指期 1 分 K 線資料自動下載器 (Shioaji API)

**版本**: 1.0  
**日期**: 2025-11-18  
**作者**: Gemini AI Assistant (Collaborated with User)  

---

## 1. 專案概述 (Overview)
本專案旨在開發一自動化 Python 程式，利用永豐金證券 (Sinopac) 的 **Shioaji API**，自動登入並抓取 **台灣加權指數期貨 (TXF)** 的近期合約 **1 分鐘 K 線 (1m OHLCV)** 歷史資料。程式需負責資料下載、時間格式清洗，並最終輸出為 **CSV** 檔案，以利後續量化分析或策略回測。

---

## 2. 系統環境需求 (System Requirements)

### 2.1 硬體與作業系統
* **作業系統**: Windows 10/11, macOS, 或 Linux (需支援 Python 3 環境)。
* **網路連線**: 必須具備穩定網際網路以連接 Shioaji 報價伺服器。
* **磁碟空間**: 足以儲存歷史 CSV 檔案之空間。

### 2.2 軟體依賴 (Dependencies)
* **程式語言**: Python 3.8+
* **必要 Python 套件**:
  * `shioaji`: 核心 API，用於連接券商、行情下載。
  * `pandas`: 用於時間序列處理、資料清洗、CSV 輸出。
* **選用套件**:
  * `python-dotenv` (建議): 用於環境變數管理，避免明文儲存帳密。

### 2.3 帳戶與憑證
* **證券帳戶**: 具備有效之永豐金證券/期貨帳戶且已開通 API 權限。
* **電子憑證**: 需備妥有效之 `.pfx` 憑證檔案及對應密碼 (通常為身分證字號)。

---

## 3. 功能需求 (Functional Requirements)

### 3.1 身份驗證 (Authentication)
* **API 登入**: 系統需接受 `API_KEY` 與 `SECRET_KEY` 進行初始化登入。
* **憑證簽章 (CA)**: 系統需讀取 `.pfx` 檔案路徑與密碼，執行 `activate_ca` 以解鎖歷史資料存取權限。
* **安全規範**: 程式碼架構應將敏感資訊 (Keys/Passwords) 定義為變數或外部設定檔，便於抽離管理。

### 3.2 合約選取 (Contract Selection)
* **商品標的**: 台指期 (TXF)。
* **自動選取邏輯**:
  1. 從 API 取得所有 TXF 期貨合約列表。
  2. 排除跨月價差單 (Spread contracts)。
  3. 自動鎖定列表中的 **首個常規合約** (通常為近月/當月合約)。

### 3.3 資料下載 (Data Retrieval)
* **頻率 (Interval)**: 1 分鐘 (1m)。
* **資料區間**: 預設下載最近 `N` 天 (例如: 5天) 或 API 允許之最大回溯範圍。
* **資料內容**: 包含 Open, High, Low, Close, Volume, Timestamp。

### 3.4 資料處理 (Data Processing)
* **時間轉換**: 將 Shioaji 回傳的 `ts` (奈秒) 轉換為 `datetime` 物件。
* **時區校正**: 確保時間標記為台灣標準時間 (Asia/Taipei, GMT+8)。
* **索引設定**: 使用 `Datetime` 作為 DataFrame 的索引 (Index)。
* **欄位篩選**: 僅保留 OHLCV 相關欄位，剔除 API 內部代碼。

### 3.5 檔案輸出 (Output)
* **格式**: CSV (Comma-Separated Values)。
* **編碼**: `utf-8-sig` (確保 Excel 開啟中文與日期不亂碼)。
* **檔名規則**: `TXF_1m_{合約代碼}_{下載日期}.csv`
  * *範例*: `TXF_1m_TXF202511_20251118.csv`

---

## 4. 資料規格 (Data Schema)

### 4.1 輸入參數設定
| 參數變數 | 類型 | 描述 |
| :--- | :--- | :--- |
| `API_KEY` | String | Shioaji API Key |
| `SECRET_KEY` | String | Shioaji Secret Key |
| `CERT_PATH` | String | `.pfx` 憑證檔案絕對路徑 |
| `CERT_PASS` | String | 憑證密碼 |

### 4.2 輸出 CSV 結構
| 欄位名稱 (Header) | 資料類型 | 範例值 | 說明 |
| :--- | :--- | :--- | :--- |
| **Datetime** | DateTime | `2025-11-18 09:00:00` | 索引欄位，已轉為標準時間 |
| **Open** | Float | `22500.0` | 開盤價 |
| **High** | Float | `22505.0` | 最高價 |
| **Low** | Float | `22495.0` | 最低價 |
| **Close** | Float | `22502.0` | 收盤價 |
| **Volume** | Integer | `1540` | 成交量 (口) |

---

## 5. 例外處理 (Exception Handling)

系統需針對下列情況進行錯誤捕捉 (Try-Except) 並輸出 Log：

1. **登入失敗**: 帳號密碼錯誤或 API 伺服器維護中。 -> *終止程式並報錯*。
2. **憑證錯誤**: `.pfx` 路徑無效或密碼錯誤。 -> *提示使用者檢查路徑*。
3. **查無合約**: 若 API 初始化未完成導致合約列表為空。 -> *提示檢查網路或合約下載狀態*。
4. **無歷史資料**: 指定時間範圍內無交易 (如假日)。 -> *輸出警告訊息，不產生空檔案*。

---

## 6.擴充功能
* **連續月拼接**: 實作換月邏輯，將多個月份的期貨合約拼接為長期連續資料。
* **設定檔分離**: 使用 `config.ini` 或 `.env` 讀取帳號資訊。
* **資料庫串接**: 支援寫入 SQLite/MySQL 資料庫。