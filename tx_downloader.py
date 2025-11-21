import os
import shioaji as sj
import numpy as np
import logging
import argparse
import pandas as pd
import unicodedata
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore

# 為了處理版本號比較，引入 packaging 套件
try:
    from packaging import version
except ImportError:
    logging.critical("找不到 'packaging' 套件。請執行 'pip install -r requirements.txt' 進行安裝。")
    exit(1)

# 建議：使用 python-dotenv 套件來管理您的敏感資訊
from dotenv import load_dotenv
load_dotenv()

# --- 常數設定 ---
API_USAGE_WARNING_THRESHOLD_MB = 400
PROGRESS_FILE = 'download_progress.txt'  # 中斷續傳進度檔案

# --- Shioaji 版本檢查 ---
REQUIRED_MIN_VERSION = "1.0.0"
REQUIRED_MAX_VERSION = "1.2.0"

current_version_str = sj.__version__
current_version = version.parse(current_version_str)

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

if not (version.parse(REQUIRED_MIN_VERSION) <= current_version < version.parse(REQUIRED_MAX_VERSION)):
    logging.critical(f"偵測到您的 Shioaji 版本 ({current_version_str}) 與本腳本不相容。")
    logging.critical(f"本腳本需要 Shioaji 版本介於 {REQUIRED_MIN_VERSION} (含) 與 {REQUIRED_MAX_VERSION} (不含) 之間。")
    logging.critical(f"建議執行指令: pip install \"shioaji>={REQUIRED_MIN_VERSION},<{REQUIRED_MAX_VERSION}\"")
    

class TXFDownloader:
    """
    台指期資料自動下載器
    - 自動登入 Shioaji API 並在 Token 過期時自動重新登入
    - 支援中斷續傳
    - 可選擇下載 Ticks, K-bars 或兩者
    - 清洗並儲存為 CSV 或寫入 Firestore
    """
    def __init__(self, api_key: str, secret_key: str, cert_path: str, cert_pass: str):
        self.api = sj.Shioaji()
        self.api_key = api_key
        self.secret_key = secret_key
        self.cert_path = cert_path
        self.cert_pass = cert_pass
        self.db = None

    def login(self):
        """執行 API 登入與憑證簽署。成功返回 True，失敗返回 False。"""
        logging.info("正在登入 Shioaji API...")
        try:
            self.api.logout() # 先登出，確保連線是乾淨的
        except Exception:
            pass # 忽略尚未登入時的登出錯誤

        try:
            self.api.login(self.api_key, self.secret_key)
            logging.info("API 登入成功。")
            
            usage_info = self.api.usage()
            logging.info(f"API 流量狀態: {usage_info}")

            try:
                parts = str(usage_info).split()
                usage_bytes = 0
                for part in parts:
                    if 'bytes=' in part:
                        usage_bytes = int(part.split('=')[1])
                        break
                usage_mb = usage_bytes / (1024 * 1024)
                if usage_mb > API_USAGE_WARNING_THRESHOLD_MB:
                    logging.warning(f"API 用量警告: 目前已使用 {usage_mb:.2f} MB，已超過 {API_USAGE_WARNING_THRESHOLD_MB} MB 的閾值。")
            except Exception as e:
                logging.warning(f"無法解析 API 流量資訊: '{usage_info}'。錯誤: {e}")

        except Exception as e:
            logging.error(f"API 登入失敗: {e}")
            return False

        logging.info("正在啟用憑證 (CA)...")
        try:
            self.api.activate_ca(ca_path=self.cert_path, ca_passwd=self.cert_pass)
            logging.info("憑證啟用成功。")
            return True
        except Exception as e:
            logging.error(f"憑證啟用失敗，請檢查路徑與密碼: {e}")
            self.api.logout()
            return False

    def _execute_api_call(self, api_func, *args, **kwargs):
        """
        包裝 API 呼叫，加入自動重試與 Token 更新機制。
        """
        try:
            # 第一次嘗試
            return api_func(*args, **kwargs)
        except Exception as e:
            # 檢查是否為 Token 相關錯誤 (這裡用一個比較通用的例外捕捉，實際應用可能需要更精確的錯誤類型)
            logging.warning(f"API 呼叫失敗: {e}。嘗試重新登入並重試...")
            if self.login():
                try:
                    # 第二次嘗試
                    logging.info("重新登入成功，正在重試 API 呼叫...")
                    return api_func(*args, **kwargs)
                except Exception as final_e:
                    logging.error(f"重試 API 呼叫後再次失敗: {final_e}")
                    raise final_e # 重試失敗，拋出例外
            else:
                logging.error("重新登入失敗，無法繼續執行。")
                raise e # 登入失敗，拋出原始例外

    def init_firestore(self, service_account_key_path: str):
        logging.info(f"正在使用金鑰檔案 '{service_account_key_path}' 初始化 Firestore...")
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(service_account_key_path)
                firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            logging.info("Firestore 初始化成功。")
        except Exception as e:
            logging.error(f"Firestore 初始化失敗，請檢查金鑰檔案路徑是否正確: {e}")
            raise

    def fetch_and_save_ticks(self, start_date: str, end_date: str):
        """逐日下載 Ticks 資料並儲存。"""
        s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        logging.info("--- 開始執行 Ticks 下載計畫 ---")
        
        current_date = s_date
        while current_date <= e_date:
            date_str = current_date.strftime("%Y-%m-%d")
            
            # 寫入進度檔案
            with open(PROGRESS_FILE, 'w') as f:
                f.write(date_str)
            
            logging.info(f"下載連續月合約 {self.api.Contracts.Futures.TXF.TXFR1.code} 在 {date_str} 的 Ticks 資料...")
            try:
                ticks = self._execute_api_call(
                    self.api.ticks,
                    contract=self.api.Contracts.Futures.TXF.TXFR1,
                    date=date_str
                )
                if ticks.ts:
                    ticks_df = pd.DataFrame({**ticks})
                    actual_contract_code = ticks_df['code'][0] if not ticks_df.empty and 'code' in ticks_df.columns else self.api.Contracts.Futures.TXF.TXFR1.code
                    self.save_ticks_to_csv(ticks_df.copy(), actual_contract_code, date_str)
            except Exception as e:
                logging.warning(f"下載 {date_str} 的 Ticks 時最終失敗: {e}。請檢查後續續傳。")
                # 下載失敗，保留進度檔並中斷
                return

            current_date += timedelta(days=1)

        logging.info("--- Ticks 下載計畫執行完畢 ---\n")
        # 所有日期成功後，刪除進度檔
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)

    def fetch_kbars(self, start_date: str, end_date: str) -> pd.DataFrame:
        """區間下載 K-bars 資料並回傳。"""
        logging.info(f"--- 開始下載從 {start_date} 到 {end_date} 的 K 線資料 ---")
        try:
            kbars = self._execute_api_call(
                self.api.kbars,
                contract=self.api.Contracts.Futures.TXF.TXFR1,
                start=start_date,
                end=end_date,
            )
            if not kbars.ts:
                logging.warning("在指定區間內未下載到任何 K 線資料。")
                return None

            kbars_df = pd.DataFrame({**kbars})
            kbars_df['ts'] = pd.to_datetime(kbars_df['ts'])
            
            logging.info(f"K 線下載完成，總共 {len(kbars_df)} 筆。")
            return kbars_df

        except Exception as e:
            logging.error(f"下載 K 線時最終失敗: {e}")
            return None

    @staticmethod
    def process_data(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return None
        
        logging.info("正在進行 K-bar 資料清洗...")
        df = df.rename(columns={'ts': 'datetime'})
        df.set_index('datetime', inplace=True)
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Taipei')
        df.reset_index(inplace=True)
        df = df[['datetime', 'Open', 'High', 'Low', 'Close', 'Volume']]
        logging.info("資料清洗完成。")
        return df

    def save_to_csv(self, df: pd.DataFrame, filename: str):
        if df is None or df.empty:
            logging.warning("沒有 K-bar 資料可供儲存至 CSV，已跳過。")
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(script_dir, 'tradedata')
        os.makedirs(data_dir, exist_ok=True)
        filepath = os.path.join(data_dir, filename)

        logging.info(f"正在將 K-bar 資料儲存至檔案: {filepath}")
        try:
            df.to_csv(filepath, encoding='utf-8-sig', index=False)
            logging.info(f"檔案儲存成功！")
        except Exception as e:
            logging.error(f"儲存 K-bar CSV 檔案時發生錯誤: {e}")

    def save_ticks_to_csv(self, df: pd.DataFrame, contract_code: str, date_str: str):
        if df is None or df.empty:
            logging.warning(f"沒有 Ticks 資料可供儲存 ({contract_code} on {date_str})，已跳過。")
            return

        filename = f"TXF_ticks_{contract_code}_{date_str}.csv"
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(script_dir, 'tradedata')
        os.makedirs(data_dir, exist_ok=True)
        filepath = os.path.join(data_dir, filename)

        logging.info(f"正在將 Ticks 資料儲存至檔案: {filepath}")
        try:
            df['ts'] = pd.to_datetime(df['ts'])
            df.set_index('ts', inplace=True)
            df.index = df.index.tz_localize('UTC').tz_convert('Asia/Taipei')
            df.reset_index(inplace=True)
            df = df.rename(columns={'ts': 'datetime'})

            if 'tick_type' not in df.columns:
                df['tick_type'] = 'Deal'
            
            required_cols = ['datetime', 'close', 'volume', 'tick_type']
            available_cols = [col for col in required_cols if col in df.columns]
            df = df[available_cols]

            df.to_csv(filepath, encoding='utf-8-sig', index=False)
            logging.info(f"Ticks 檔案儲存成功！")
        except Exception as e:
            logging.error(f"儲存 Ticks CSV 檔案 '{filename}' 時發生錯誤: {e}")

    def save_to_firestore(self, df: pd.DataFrame, collection_name: str = "TXF_1min"):
        if self.db is None:
            logging.error("Firestore 未初始化，無法儲存資料。")
            return
        
        if df is None or df.empty:
            logging.warning("沒有資料可供儲存至 Firestore，已跳過。")
            return

        logging.info(f"準備將 {len(df)} 筆資料寫入 Firestore 集合 '{collection_name}'...")
        batch = self.db.batch()
        count = 0
        
        for _, row in df.iterrows():
            doc_id = row['datetime'].strftime('%Y-%m-%d %H:%M:%S')
            doc_ref = self.db.collection(collection_name).document(doc_id)
            data = row.to_dict()
            batch.set(doc_ref, data)
            count += 1
            
            if count % 500 == 0:
                logging.info(f"正在提交 {count} 筆資料...")
                batch.commit()
                batch = self.db.batch()

        if count % 500 != 0:
            logging.info(f"正在提交最後 {count % 500} 筆資料...")
            batch.commit()
            
        logging.info(f"共 {count} 筆資料成功寫入 Firestore。")


def get_resume_date():
    """檢查是否存在進度檔案，若存在則返回續傳日期。"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            resume_date_str = f.read().strip()
        try:
            resume_date = datetime.strptime(resume_date_str, "%Y-%m-%d").date()
            logging.warning(f"偵測到上次下載中斷，將從 {resume_date_str} 開始續傳。")
            return resume_date
        except ValueError:
            logging.error(f"進度檔案 '{PROGRESS_FILE}' 內容格式錯誤，將忽略並正常執行。")
            os.remove(PROGRESS_FILE)
            return None
    return None

def calculate_date_range(period: str, start: str, end: str) -> (datetime.date, datetime.date):
    today = datetime.now().date()
    
    # 檢查是否有續傳日期
    resume_date = get_resume_date()
    if resume_date:
        # 如果有續傳日期，則以此為開始日期，結束日期維持不變
        if period == 'custom' and end:
            e_date = datetime.strptime(end, "%Y-%m-%d").date()
        else:
            _, e_date = calculate_date_range(period, start, end) # 取得原始的結束日期
        return resume_date, e_date

    if period == 'custom':
        if not start or not end:
            raise ValueError("使用自訂區間 'custom' 時，必須同時提供 --start 和 --end 參數。")
        s_date = datetime.strptime(start, "%Y-%m-%d").date()
        e_date = datetime.strptime(end, "%Y-%m-%d").date()
        return s_date, e_date

    e_date = today
    if period == 'last_day':
        s_date = today - timedelta(days=1)
        while s_date.weekday() > 4:
            s_date -= timedelta(days=1)
        return s_date, s_date
    elif period == 'week':
        s_date = today - timedelta(days=today.weekday())
    elif period == 'month':
        s_date = today.replace(day=1)
    elif period == '6_months':
        s_date = today - timedelta(days=180)
    elif period == 'year':
        s_date = today - timedelta(days=365)
    elif period == '5_years':
        s_date = today - timedelta(days=365*5)
    else:
        s_date = today - timedelta(days=5)
    return s_date, e_date


def get_period_choice():
    print("\n--- 請選擇要下載的資料區間 ---")
    print("1. 上一個交易日的資料")
    print("2. 本週至今的資料")
    print("3. 本月至今的資料")
    print("4. 近半年的資料")
    print("5. 近一年的資料")
    print("6. 近五年的資料")
    print("7. 自訂起訖區間")
    
    period_map = {'1': 'last_day', '2': 'week', '3': 'month', '4': '6_months', '5': 'year', '6': '5_years', '7': 'custom'}

    while True:
        choice = input("請輸入您的選擇 (1-7): ").strip()
        normalized_choice = unicodedata.normalize('NFKC', choice)
        
        if normalized_choice in period_map:
            period = period_map[normalized_choice]
            start_date_str, end_date_str = None, None
            if period == 'custom':
                start_date_str = input("請輸入開始日期 (格式: YYYY-MM-DD): ").strip()
                end_date_str = input("請輸入結束日期 (格式: YYYY-MM-DD): ").strip()
            return period, start_date_str, end_date_str
        else:
            logging.warning("無效的輸入，請重新輸入。")

def get_data_type_choice():
    """顯示下載資料類型選單並取得使用者選擇。"""
    print("\n--- 請選擇要下載的資料類型 ---")
    print("a. 下載 Ticks 資料")
    print("b. 下載 K-bar 資料")
    print("c. 下載 Ticks 與 K-bar 資料")
    
    while True:
        choice = input("請輸入您的選擇 (a/b/c): ").strip().lower()
        if choice in ['a', 'b', 'c']:
            return choice
        else:
            logging.warning("無效的輸入，請重新輸入。")

def get_storage_choice():
    print("\n--- 請選擇資料儲存方式 ---")
    print("1. 僅儲存至 Firebase")
    print("2. 僅儲存為 CSV 檔案")
    print("3. 同時儲存至 Firebase 和 CSV")
    
    while True:
        choice = input("請輸入您的選擇 (1/2/3): ").strip()
        normalized_choice = unicodedata.normalize('NFKC', choice)
        if normalized_choice in ['1', '2', '3']:
            return choice
        else:
            logging.warning("無效的輸入，請重新輸入。")


def main():
    """主執行函數"""
    try:
        API_KEY = os.getenv("SHIOAJI_API_KEY", "YOUR_API_KEY")
        SECRET_KEY = os.getenv("SHIOAJI_SECRET_KEY", "YOUR_SECRET_KEY")
        CERT_PATH = os.getenv("SHIOAJI_CERT_PATH", "C:/path/to/your/certificate.pfx")
        CERT_PASS = os.getenv("SHIOAJI_CERT_PASS", "YOUR_CERT_PASSWORD")
        SERVICE_ACCOUNT_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")

        storage_choice = get_storage_choice()
        period, custom_start, custom_end = get_period_choice()
        data_type_choice = get_data_type_choice()

        use_firestore = storage_choice in ['1', '3']
        use_csv = storage_choice in ['2', '3']
        download_ticks = data_type_choice in ['a', 'c']
        download_kbars = data_type_choice in ['b', 'c']

        if "YOUR_API_KEY" in API_KEY or "YOUR_SECRET_KEY" in SECRET_KEY:
            logging.critical("請在 .env 檔案中設定您的 SHIOAJI_API_KEY 和 SHIOAJI_SECRET_KEY。")
            return
        if "path/to/your" in CERT_PATH:
            logging.critical("請在 .env 檔案中設定您的 SHIOAJI_CERT_PATH 為您憑證檔案的正確絕對路徑。")
            return
        
        if use_firestore and not os.path.exists(SERVICE_ACCOUNT_KEY_PATH):
            logging.critical(f"找不到 Firebase 服務帳號金鑰檔案 '{SERVICE_ACCOUNT_KEY_PATH}'。")
            return

        downloader = TXFDownloader(
            api_key=API_KEY, secret_key=SECRET_KEY, cert_path=CERT_PATH, cert_pass=CERT_PASS
        )
        if not downloader.login():
            logging.critical("\n登入程序失敗，程式已終止。")
            return

        if use_firestore:
            downloader.init_firestore(SERVICE_ACCOUNT_KEY_PATH)

        start_date, end_date = calculate_date_range(period, custom_start, custom_end)
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        
        logging.info(f"準備下載從 {start_date_str} 到 {end_date_str} 的資料...")
        
        if download_ticks:
            downloader.fetch_and_save_ticks(start_date=start_date_str, end_date=end_date_str)
        
        if download_kbars:
            raw_kbars = downloader.fetch_kbars(start_date=start_date_str, end_date=end_date_str)
            processed_kbars = downloader.process_data(raw_kbars)
            
            if processed_kbars is not None:
                logging.info("\n--- 開始儲存 K-bar 資料 ---")
                if use_csv:
                    csv_filename = f"TXF_1m_data_{start_date_str}_to_{end_date_str}.csv"
                    downloader.save_to_csv(processed_kbars, filename=csv_filename)
                if use_firestore:
                    downloader.save_to_firestore(processed_kbars)
            else:
                logging.info("\n最終處理後無有效 K-bar 資料，因此未執行任何儲存操作。")

        # 如果只下載 Ticks 且成功完成，也要刪除進度檔
        if download_ticks and not download_kbars:
            if os.path.exists(PROGRESS_FILE):
                os.remove(PROGRESS_FILE)
                logging.info("Ticks 下載完成，進度檔案已移除。")

    except Exception as e:
        logging.critical(f"程式執行過程中發生未預期的錯誤: {e}", exc_info=True)

if __name__ == "__main__":
    main()