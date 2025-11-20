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

# --- Shioaji 版本檢查 ---
# 這個腳本是針對 shioaji v1.0.0 ~ v1.1.x 開發的，因為不同版本間的 API 差異很大。
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
    台指期 1 分 K 線資料自動下載器
    - 自動登入 Shioaji API
    - 抓取連續月合約
    - 下載 1 分鐘 K 線資料
    - 清洗並儲存為 CSV 或寫入 Firestore
    """
    def __init__(self, api_key: str, secret_key: str, cert_path: str, cert_pass: str):
        """
        初始化 API 客戶端與登入憑證。

        Args:
            api_key (str): Shioaji API Key.
            secret_key (str): Shioaji Secret Key.
            cert_path (str): .pfx 憑證檔案絕對路徑.
            cert_pass (str): 憑證密碼.
        """
        self.api = sj.Shioaji()
        self.api_key = api_key
        self.secret_key = secret_key
        self.cert_path = cert_path
        self.cert_pass = cert_pass
        self.db = None  # Firestore client

    def login(self):
        """執行 API 登入與憑證簽署。成功返回 True，失敗返回 False。"""
        logging.info("正在登入 Shioaji API...")
        try:
            self.api.login(self.api_key, self.secret_key)
            logging.info("API 登入成功。")
            
            # 查詢並顯示 API 流量資訊
            usage = self.api.usage()
            logging.info(f"API 流量狀態: 已查詢 {usage} ")

        except Exception as e:
            logging.error(f"API 登入失敗: {e}")
            return False

        logging.info("正在啟用憑證 (CA)...")
        try:
            self.api.activate_ca(
                ca_path=self.cert_path,
                ca_passwd=self.cert_pass,
            )
            logging.info("憑證啟用成功。")
            return True
        except Exception as e:
            logging.error(f"憑證啟用失敗，請檢查路徑與密碼: {e}")
            self.api.logout() # 登入成功但憑證失敗時，記得登出
            return False

    def init_firestore(self, service_account_key_path: str):
        """
        初始化 Firebase Admin SDK 與 Firestore Client。

        Args:
            service_account_key_path (str): Firebase 服務帳號金鑰 JSON 檔案的路徑。
        """
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
            
    @staticmethod
    def resample_ticks_to_1min_kbars(ticks_df: pd.DataFrame) -> pd.DataFrame:
        """手動將 Ticks 資料重新取樣為 1 分鐘 K 棒。"""
        if ticks_df is None or ticks_df.empty:
            return None

        ticks_df['ts'] = pd.to_datetime(ticks_df['ts'])
        ticks_df.set_index('ts', inplace=True)

        # 使用 pandas resample 功能
        # 由於 tick 資料沒有獨立的開高低價，我們用成交價 (close) 來合成
        ohlc_dict = {
            'close': 'last',
            'volume': 'sum',
            'price_for_ohlc': ['first', 'max', 'min']
        }
        
        ticks_df['price_for_ohlc'] = ticks_df['close']
        
        kbars_df = ticks_df.resample('1Min').apply(ohlc_dict).dropna(subset=[('price_for_ohlc', 'first')])
        kbars_df.columns = ['Close', 'Volume', 'Open', 'High', 'Low'] # 重新命名多層級欄位
        
        # 重設索引，讓時間戳變回一個欄位
        kbars_df.reset_index(inplace=True)
        return kbars_df

    def fetch_continuous_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        下載指定日期區間的連續月資料。
        - Ticks: 逐日下載並儲存。
        - K-bars: 區間下載並回傳。

        Args:
            start_date (str): 開始日期 (YYYY-MM-DD).
            end_date (str): 結束日期 (YYYY-MM-DD).

        Returns:
            pd.DataFrame: 包含 OHLCV 資料的 DataFrame，或在沒有資料時返回 None。
        """
        s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        logging.info(f"已鎖定連續月合約: {self.api.Contracts.Futures.TXF.TXFR1.code} ({self.api.Contracts.Futures.TXF.TXFR1.name})")

        # --- Ticks 下載 ---
        all_ticks_df = []
        logging.info("--- 開始執行 Ticks 下載計畫 ---")
        
        current_date = s_date
        while current_date <= e_date:
            date_str = current_date.strftime("%Y-%m-%d")
            logging.info(f"下載連續月合約 {self.api.Contracts.Futures.TXF.TXFR1.code} 在 {date_str} 的 Ticks 資料...")
            try:
                # 依照使用者規格修改：移除 query_type
                ticks = self.api.ticks(
                    contract=self.api.Contracts.Futures.TXF.TXFR1,
                    date=date_str
                )
                if ticks.ts:
                    ticks_df = pd.DataFrame({**ticks})
                    actual_contract_code = ticks_df['code'][0] if not ticks_df.empty and 'code' in ticks_df.columns else self.api.Contracts.Futures.TXF.TXFR1.code
                    self.save_ticks_to_csv(ticks_df.copy(), actual_contract_code, date_str)
                    all_ticks_df.append(ticks_df)
            except Exception as e:
                logging.warning(f"下載連續月合約在 {date_str} 的 Ticks 時發生錯誤: {e}")
            current_date += timedelta(days=1)

        logging.info("--- Ticks 下載計畫執行完畢 ---\n")

        if all_ticks_df:
            combined_ticks = pd.concat(all_ticks_df, ignore_index=True)
            if (e_date - s_date).days > 7:
                self.save_weekly_ticks_to_csv(combined_ticks.copy())
        else:
            logging.warning("在指定的全區間內未下載到任何 Tick 資料。")

        # --- K-bars 下載 ---
        logging.info(f"--- 開始下載從 {start_date} 到 {end_date} 的 K 線資料 ---")
        try:
            # 依照使用者規格，直接使用 api.kbars
            kbars = self.api.kbars(
                contract=self.api.Contracts.Futures.TXF.TXFR1,
                start=start_date,
                end=end_date,
            )
            if not kbars.ts:
                logging.warning("在指定區間內未下載到任何 K 線資料。")
                return None

            kbars_df = pd.DataFrame({**kbars})
            # api.kbars 回傳的 ts 是 nanoseconds, 需要轉換為 datetime 物件以利後續處理
            kbars_df['ts'] = pd.to_datetime(kbars_df['ts'])
            
            logging.info(f"K 線下載完成，總共 {len(kbars_df)} 筆。")
            return kbars_df

        except Exception as e:
            logging.warning(f"下載連續月合約 K 線時發生錯誤: {e}")
            return None

    @staticmethod
    def process_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        資料清洗、時間轉換與格式整理。
        為了存入 Firestore，我們將時間轉換為台北時區，然後重設索引。

        Args:
            df (pd.DataFrame): 從 API 取得的原始 DataFrame。

        Returns:
            pd.DataFrame: 清洗完成的 DataFrame。
        """
        if df is None or df.empty:
            return None
        
        logging.info("正在進行資料清洗...")
        # 'ts' 欄位是 datetime 物件，將其改名為 'datetime' 並設為索引以進行時區轉換
        df = df.rename(columns={'ts': 'datetime'})
        df.set_index('datetime', inplace=True)
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Taipei')
        df.reset_index(inplace=True) # 將索引轉回欄位

        df = df[['datetime', 'Open', 'High', 'Low', 'Close', 'Volume']] # 確保欄位順序
        
        logging.info("資料清洗完成。")
        return df

    def save_to_csv(self, df: pd.DataFrame, filename: str = None):
        """
        將 DataFrame 儲存為 CSV 檔案。

        Args:
            df (pd.DataFrame): 準備儲存的 DataFrame。
            filename (str, optional): 自訂檔名。若無提供，則依合約代碼自動產生。
        """
        if df is None or df.empty:
            logging.warning("沒有資料可供儲存至 CSV，已跳過。")
            return

        if filename is None:
            if self.contract:
                today_str = datetime.now().strftime('%Y%m%d')
                filename = f"TXF_1m_{self.contract.code}_{today_str}.csv"
            else:
                # Fallback for continuous data where self.contract is not set
                today_str = datetime.now().strftime('%Y%m%d')
                filename = f"TXF_1m_data_{today_str}.csv"

        # 確保檔案儲存在 'tradedata' 資料夾下
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(script_dir, 'tradedata')
        os.makedirs(data_dir, exist_ok=True)  # 確保資料夾存在
        filepath = os.path.join(data_dir, filename)

        logging.info(f"正在將資料儲存至檔案: {filepath}")
        try:
            df.to_csv(filepath, encoding='utf-8-sig', index=False)
            logging.info(f"檔案儲存成功！")
        except Exception as e:
            logging.error(f"儲存 CSV 檔案時發生錯誤: {e}")

    def save_ticks_to_csv(self, df: pd.DataFrame, contract_code: str, date_str: str):
        """
        將 Ticks DataFrame 儲存為 CSV 檔案。

        Args:
            df (pd.DataFrame): 準備儲存的 Ticks DataFrame。
            contract_code (str): 合約代碼.
            date_str (str): 日期字串 (YYYY-MM-DD).
        """
        if df is None or df.empty:
            logging.warning(f"沒有 Ticks 資料可供儲存 ({contract_code} on {date_str})，已跳過。")
            return

        filename = f"TXF_ticks_{contract_code}_{date_str}.csv"

        # 確保檔案儲存在 'tradedata' 資料夾下
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(script_dir, 'tradedata')
        os.makedirs(data_dir, exist_ok=True)  # 確保資料夾存在
        filepath = os.path.join(data_dir, filename)

        logging.info(f"正在將 Ticks 資料儲存至檔案: {filepath}")
        try:
            # 處理時間轉換與欄位篩選
            df['ts'] = pd.to_datetime(df['ts'])
            df.set_index('ts', inplace=True)
            df.index = df.index.tz_localize('UTC').tz_convert('Asia/Taipei')
            df.reset_index(inplace=True)
            df = df.rename(columns={'ts': 'datetime'})

            # 根據規格書篩選並排序欄位
            if 'tick_type' not in df.columns:
                df['tick_type'] = 'Deal'

            # 確保欄位存在
            required_cols = ['datetime', 'close', 'volume', 'tick_type']
            available_cols = [col for col in required_cols if col in df.columns]
            df = df[available_cols]

            df.to_csv(filepath, encoding='utf-8-sig', index=False)
            logging.info(f"Ticks 檔案儲存成功！")
        except Exception as e:
            logging.error(f"儲存 Ticks CSV 檔案 '{filename}' 時發生錯誤: {e}")

    def save_weekly_ticks_to_csv(self, ticks_df: pd.DataFrame):
        """
        將 Ticks DataFrame 按照週來分組，並分別儲存為 CSV 檔案。
        """
        if ticks_df is None or ticks_df.empty:
            logging.warning("沒有 Ticks 資料可供按週儲存，已跳過。")
            return

        logging.info("正在將 Ticks 資料按週儲存...")
        
        # 確保 'ts' 欄位是 datetime 格式
        ticks_df['ts'] = pd.to_datetime(ticks_df['ts'])
        
        # 設定 'ts' 為索引以進行分組
        ticks_df.set_index('ts', inplace=True)
        
        # 按週分組 (W-MON 表示每週從星期一開始)
        weekly_groups = ticks_df.groupby(pd.Grouper(freq='W-MON'))
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(script_dir, 'tradedata')
        os.makedirs(data_dir, exist_ok=True)

        for week_start_ts, group in weekly_groups:
            if group.empty:
                continue
                
            week_start_date = group.index.min().strftime('%Y-%m-%d')
            week_end_date = group.index.max().strftime('%Y-%m-%d')
            
            filename = f"TXF_ticks_weekly_{week_start_date}_to_{week_end_date}.csv"
            filepath = os.path.join(data_dir, filename)

            logging.info(f"正在將 {week_start_date} 到 {week_end_date} 的 Ticks 資料儲存至檔案: {filepath}")
            
            group_to_save = group.reset_index()
            
            try:
                # 處理時間轉換與欄位篩選
                group_to_save['ts'] = pd.to_datetime(group_to_save['ts'])
                group_to_save.set_index('ts', inplace=True)
                group_to_save.index = group_to_save.index.tz_localize('UTC').tz_convert('Asia/Taipei')
                group_to_save.reset_index(inplace=True)
                group_to_save = group_to_save.rename(columns={'ts': 'datetime'})

                if 'tick_type' not in group_to_save.columns:
                    group_to_save['tick_type'] = 'Deal'

                required_cols = ['datetime', 'close', 'volume', 'tick_type']
                available_cols = [col for col in required_cols if col in group_to_save.columns]
                group_to_save = group_to_save[available_cols]

                group_to_save.to_csv(filepath, encoding='utf-8-sig', index=False)
                logging.info(f"週次 Ticks 檔案儲存成功！")
            except Exception as e:
                logging.error(f"儲存週次 Ticks CSV 檔案 '{filename}' 時發生錯誤: {e}")
                
        # 恢復原始 DataFrame 的索引
        ticks_df.reset_index(inplace=True)

    def save_to_firestore(self, df: pd.DataFrame, collection_name: str = "TXF_1min"):
        """
        將 DataFrame 的資料逐筆寫入 Firestore。

        Args:
            df (pd.DataFrame): 準備儲存的 DataFrame。
            collection_name (str): Firestore 上的集合名稱。
        """
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
            # 將 Timestamp 物件轉為 ISO 格式字串，或直接讓 Firestore 處理
            doc_id = row['datetime'].strftime('%Y-%m-%d %H:%M:%S')
            doc_ref = self.db.collection(collection_name).document(doc_id)
            
            data = row.to_dict()
            # 'datetime' 欄位是 pandas Timestamp，Firestore 會自動轉換
            
            batch.set(doc_ref, data)
            count += 1
            
            # 每 500 筆提交一次 batch，避免單一 batch 過大
            if count % 500 == 0:
                logging.info(f"正在提交 {count} 筆資料...")
                batch.commit()
                batch = self.db.batch() # 重新開始一個新的 batch

        # 提交剩餘的資料
        if count % 500 != 0:
            logging.info(f"正在提交最後 {count % 500} 筆資料...")
            batch.commit()
            
        logging.info(f"共 {count} 筆資料成功寫入 Firestore。")


def calculate_date_range(period: str, start: str, end: str) -> (datetime.date, datetime.date):
    """根據使用者選擇的期間，計算開始與結束日期。"""
    today = datetime.now().date()
    
    if period == 'custom':
        if not start or not end:
            raise ValueError("使用自訂區間 'custom' 時，必須同時提供 --start 和 --end 參數。")
        s_date = datetime.strptime(start, "%Y-%m-%d").date()
        e_date = datetime.strptime(end, "%Y-%m-%d").date()
        return s_date, e_date

    e_date = today
    if period == 'last_day':
        # 從昨天開始往前找，找到第一個交易日 (週一到週五)
        s_date = today - timedelta(days=1)
        while s_date.weekday() > 4: # 5:週六, 6:週日
            s_date -= timedelta(days=1)
        return s_date, s_date
    elif period == 'week':
        s_date = today - timedelta(days=today.weekday()) # weekday() 週一為0
    elif period == 'month':
        s_date = today.replace(day=1)
    elif period == '6_months':
        # 簡化計算，直接回溯約 180 天
        s_date = today - timedelta(days=180)
    elif period == 'year':
        s_date = today - timedelta(days=365)
    elif period == '5_years':
        s_date = today - timedelta(days=365*5)
    else:
        # 預設情況，下載近5天
        s_date = today - timedelta(days=5)
        
    return s_date, e_date


def get_period_choice():
    """顯示下載區間選單並取得使用者選擇。"""
    print("\n--- 請選擇要下載的資料區間 ---")
    print("1. 上一個交易日的資料")
    print("2. 本週至今的資料")
    print("3. 本月至今的資料")
    print("4. 近半年的資料")
    print("5. 近一年的資料")
    print("6. 近五年的資料")
    print("7. 自訂起訖區間")
    
    period_map = {
        '1': 'last_day',
        '2': 'week',
        '3': 'month',
        '4': '6_months',
        '5': 'year',
        '6': '5_years',
        '7': 'custom'
    }

    while True:
        choice = input("請輸入您的選擇 (1-7): ").strip()
        normalized_choice = unicodedata.normalize('NFKC', choice)
        
        if normalized_choice in period_map:
            period = period_map[normalized_choice]
            start_date_str = None
            end_date_str = None
            
            if period == 'custom':
                start_date_str = input("請輸入開始日期 (格式: YYYY-MM-DD): ").strip()
                end_date_str = input("請輸入結束日期 (格式: YYYY-MM-DD): ").strip()

            return period, start_date_str, end_date_str
        else:
            logging.warning("無效的輸入，請重新輸入。")


def get_storage_choice():
    """顯示選單並取得使用者儲存偏好。"""
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
        # --- 使用者設定 ---
        # 安全建議：請將您的敏感資訊儲存在環境變數中
        API_KEY = os.getenv("SHIOAJI_API_KEY", "YOUR_API_KEY")
        SECRET_KEY = os.getenv("SHIOAJI_SECRET_KEY", "YOUR_SECRET_KEY")
        CERT_PATH = os.getenv("SHIOAJI_CERT_PATH", "C:/path/to/your/certificate.pfx")
        CERT_PASS = os.getenv("SHIOAJI_CERT_PASS", "YOUR_CERT_PASSWORD")
        
        # **重要**: 程式會從環境變數 'GOOGLE_APPLICATION_CREDENTIALS' 讀取金鑰路徑。
        #           如果未設定，則預設嘗試讀取與腳本相同目錄下的 'serviceAccountKey.json'。
        SERVICE_ACCOUNT_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")

        # --- 取得使用者儲存與區間選擇 ---
        storage_choice = get_storage_choice()
        period, custom_start, custom_end = get_period_choice()

        use_firestore = storage_choice in ['1', '3']
        use_csv = storage_choice in ['2', '3']

        if "YOUR_API_KEY" in API_KEY or "YOUR_SECRET_KEY" in SECRET_KEY:
            logging.critical("請在 .env 檔案中設定您的 SHIOAJI_API_KEY 和 SHIOAJI_SECRET_KEY。")
            return
        if "path/to/your" in CERT_PATH:
            logging.critical("請在 .env 檔案中設定您的 SHIOAJI_CERT_PATH 為您憑證檔案的正確絕對路徑。")
            return
        
        if use_firestore and not os.path.exists(SERVICE_ACCOUNT_KEY_PATH):
            logging.critical(f"找不到 Firebase 服務帳號金鑰檔案 '{SERVICE_ACCOUNT_KEY_PATH}'。")
            logging.critical("您選擇了儲存至 Firebase，但金鑰檔案不存在。")
            logging.critical("請從您的 Firebase 專案下載金鑰，並將其放置在正確的路徑。")
            return

        # 步驟 1: 初始化下載器並登入
        downloader = TXFDownloader( #<-- This was a bug, fixed it.
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            cert_path=CERT_PATH,
            cert_pass=CERT_PASS
        )
        # 執行登入，如果失敗則終止程式
        if not downloader.login():
            logging.critical("\n登入程序失敗，程式已終止。")
            return

        # 步驟 2: 如果需要，初始化 Firestore
        if use_firestore:
            downloader.init_firestore(SERVICE_ACCOUNT_KEY_PATH)

        # 步驟 3: 計算日期區間並下載資料
        start_date, end_date = calculate_date_range(period, custom_start, custom_end)
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        
        logging.info(f"準備下載從 {start_date_str} 到 {end_date_str} 的連續月資料...")
        
        raw_data = downloader.fetch_continuous_data(
            start_date=start_date_str,
            end_date=end_date_str
        )
        
        # 步驟 4: 處理並儲存資料
        processed_data = downloader.process_data(raw_data)
        
        if processed_data is not None:
            logging.info("\n--- 開始儲存資料 ---")
            if use_csv:
                # 儲存至 CSV
                csv_filename = f"TXF_1m_data_{start_date_str}_to_{end_date_str}.csv"
                downloader.save_to_csv(processed_data, filename=csv_filename)
            if use_firestore:
                # 儲存至 Firestore
                downloader.save_to_firestore(processed_data)
        else:
            logging.info("\n最終處理後無有效資料，因此未執行任何儲存操作。")

    except Exception as e:
        logging.critical(f"程式執行過程中發生未預期的錯誤: {e}", exc_info=True)

if __name__ == "__main__":
    main()