import os
import shioaji as sj
import pandas as pd
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore

# 建議：使用 python-dotenv 套件來管理您的敏感資訊
# from dotenv import load_dotenv
# load_dotenv()

class TXFDownloader:
    """
    台指期 1 分 K 線資料自動下載器
    - 自動登入 Shioaji API
    - 抓取近月/連續月合約
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
        self.contract = None
        self.db = None  # Firestore client

    def login(self):
        """執行 API 登入與憑證簽署。"""
        print("正在登入 Shioaji API...")
        try:
            self.api.login(self.api_key, self.secret_key)
            print("API 登入成功。")
        except Exception as e:
            print(f"API 登入失敗: {e}")
            raise

        print("正在啟用憑證 (CA)...")
        try:
            self.api.activate_ca(
                ca_path=self.cert_path,
                ca_passwd=self.cert_pass,
            )
            print("憑證啟用成功。")
        except Exception as e:
            print(f"憑證啟用失敗，請檢查路徑與密碼: {e}")
            raise

    def init_firestore(self, service_account_key_path: str):
        """
        初始化 Firebase Admin SDK 與 Firestore Client。

        Args:
            service_account_key_path (str): Firebase 服務帳號金鑰 JSON 檔案的路徑。
        """
        print(f"正在使用金鑰檔案 '{service_account_key_path}' 初始化 Firestore...")
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(service_account_key_path)
                firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            print("Firestore 初始化成功。")
        except Exception as e:
            print(f"Firestore 初始化失敗，請檢查金鑰檔案路徑是否正確: {e}")
            raise

    def get_near_future_contract(self):
        """取得台指期近月合約。"""
        print("正在查詢台指期近月合約...")
        try:
            # 遍歷所有 TXF 合約，找到第一個非價差的常規合約
            for future in self.api.Contracts.Futures.TXF:
                if not future.is_spread:
                    self.contract = future
                    print(f"成功鎖定近月合約: {self.contract.code} ({self.contract.name})")
                    return
            if self.contract is None:
                raise RuntimeError("在合約列表中找不到有效的台指期近月合約。")
        except Exception as e:
            print(f"查詢合約失敗: {e}")
            raise

    def fetch_data(self, days_to_fetch: int = 5) -> pd.DataFrame:
        """
        下載指定天數的 1 分鐘 K 線資料。

        Args:
            days_to_fetch (int): 要回溯下載的天數。預設為 5 天。

        Returns:
            pd.DataFrame: 包含 OHLCV 資料的 DataFrame，若無資料則為 None。
        """
        if not self.contract:
            print("錯誤：尚未指定合約。")
            return None

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days_to_fetch)
        
        print(f"準備下載從 {start_date} 至 {end_date} 的 1 分鐘 K 線資料...")

        try:
            kbars = self.api.kbars(
                contract=self.contract,
                start=str(start_date),
                end=str(end_date),
                freq='1Min'
            )
            
            if not kbars.ts: # 檢查是否有資料回傳
                print(f"警告：在指定時間範圍內 ({start_date} to {end_date}) 查無歷史資料。")
                return None

            df = pd.DataFrame({**kbars})
            print(f"成功下載 {len(df)} 筆資料。")
            return df

        except Exception as e:
            print(f"下載 K 線資料時發生錯誤: {e}")
            return None

    def fetch_continuous_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        下載指定日期區間的連續月 K 線資料。
        透過自動換月邏輯，將不同月份的合約拼接成一筆連續資料。
        此處的拼接邏輯為：一個合約的交易期間，是從上個合約到期日的隔天，到自己到期日當天。

        Args:
            start_date (str): 開始日期 (YYYY-MM-DD).
            end_date (str): 結束日期 (YYYY-MM-DD).

        Returns:
            pd.DataFrame: 包含拼接後 OHLCV 資料的 DataFrame。
        """
        all_contracts = sorted(
            [c for c in self.api.Contracts.Futures.TXF if not c.is_spread],
            key=lambda c: c.delivery_date
        )
        if not all_contracts:
            print("錯誤：找不到任何常規 TXF 合約。")
            return None

        s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        e_date = datetime.strptime(end_date, "%Y-%m-%d").date()

        query_plan = {}  # {contract: (start_range, end_range)}
        
        start_contract_idx = -1
        for i, contract in enumerate(all_contracts):
            delivery_d = datetime.strptime(contract.delivery_date, "%Y%m%d").date()
            if delivery_d >= s_date:
                start_contract_idx = i
                break
        
        if start_contract_idx == -1:
            print(f"錯誤：找不到任何合約的到期日在 {s_date} 或之後。")
            return None

        for i in range(start_contract_idx, len(all_contracts)):
            current_contract = all_contracts[i]
            delivery_d = datetime.strptime(current_contract.delivery_date, "%Y%m%d").date()

            if i == start_contract_idx:
                # 對於第一個相關合約，我們從使用者指定的 start_date 開始
                range_start = s_date
            else:
                prev_contract = all_contracts[i-1]
                prev_delivery_d = datetime.strptime(prev_contract.delivery_date, "%Y%m%d").date()
                range_start = prev_delivery_d + timedelta(days=1)

            range_end = delivery_d

            effective_start = max(s_date, range_start)
            effective_end = min(e_date, range_end)

            if effective_start <= effective_end:
                query_plan[current_contract] = (str(effective_start), str(effective_end))

            if delivery_d >= e_date:
                break
                
        all_kbars_df = []
        print("\n--- 開始執行下載計畫 ---")
        for contract, (start, end) in query_plan.items():
            print(f"下載合約 {contract.code} 從 {start} 到 {end} 的資料...")
            try:
                kbars = self.api.kbars(
                    contract=contract,
                    start=start,
                    end=end,
                    freq='1Min'
                )
                if kbars.ts:
                    df = pd.DataFrame({**kbars})
                    all_kbars_df.append(df)
                    print(f"成功下載 {len(df)} 筆資料。")
                else:
                    print(f"合約 {contract.code} 在此區間 ({start} to {end}) 無資料。")
            except Exception as e:
                print(f"下載合約 {contract.code} 資料時發生錯誤: {e}")
        
        print("--- 下載計畫執行完畢 ---\n")

        if not all_kbars_df:
            print("在指定的全區間內未下載到任何資料。")
            return None

        continuous_df = pd.concat(all_kbars_df, ignore_index=True)
        continuous_df.drop_duplicates(subset=['ts'], inplace=True)
        continuous_df.sort_values(by='ts', inplace=True)
        
        print(f"全部資料拼接完成，總共 {len(continuous_df)} 筆。")
        return continuous_df

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
        
        print("正在進行資料清洗...")
        df['ts'] = pd.to_datetime(df['ts'])
        df = df.rename(columns={'ts': 'datetime'})
        df.set_index('datetime', inplace=True)
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Taipei')
        df.reset_index(inplace=True) # 將索引轉回欄位

        df = df[['datetime', 'Open', 'High', 'Low', 'Close', 'Volume']]
        
        print("資料清洗完成。")
        return df

    def save_to_csv(self, df: pd.DataFrame, filename: str = None):
        """
        將 DataFrame 儲存為 CSV 檔案。

        Args:
            df (pd.DataFrame): 準備儲存的 DataFrame。
            filename (str, optional): 自訂檔名。若無提供，則依合約代碼自動產生。
        """
        if df is None or df.empty:
            print("沒有資料可供儲存至 CSV，已跳過。")
            return

        if filename is None:
            if self.contract:
                today_str = datetime.now().strftime('%Y%m%d')
                filename = f"TXF_1m_{self.contract.code}_{today_str}.csv"
            else:
                # Fallback for continuous data where self.contract is not set
                today_str = datetime.now().strftime('%Y%m%d')
                filename = f"TXF_1m_data_{today_str}.csv"

        print(f"正在將資料儲存至檔案: {filename}")
        try:
            df.to_csv(filename, encoding='utf-8-sig', index=False)
            print(f"檔案儲存成功！路徑: {os.path.abspath(filename)}")
        except Exception as e:
            print(f"儲存 CSV 檔案時發生錯誤: {e}")

    def save_to_firestore(self, df: pd.DataFrame, collection_name: str = "TXF_1min"):
        """
        將 DataFrame 的資料逐筆寫入 Firestore。

        Args:
            df (pd.DataFrame): 準備儲存的 DataFrame。
            collection_name (str): Firestore 上的集合名稱。
        """
        if self.db is None:
            print("錯誤：Firestore 未初始化，無法儲存資料。")
            return
        
        if df is None or df.empty:
            print("沒有資料可供儲存至 Firestore，已跳過。")
            return

        print(f"準備將 {len(df)} 筆資料寫入 Firestore 集合 '{collection_name}'...")
        
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
                print(f"正在提交 {count} 筆資料...")
                batch.commit()
                batch = self.db.batch() # 重新開始一個新的 batch

        # 提交剩餘的資料
        if count % 500 != 0:
            print(f"正在提交最後 {count % 500} 筆資料...")
            batch.commit()
            
        print(f"共 {count} 筆資料成功寫入 Firestore。")


def main():
    """主執行函數"""
    try:
        # --- 使用者設定 ---
        # 安全建議：請將您的敏感資訊儲存在環境變數中
        API_KEY = os.getenv("SHIOAJI_API_KEY", "YOUR_API_KEY")
        SECRET_KEY = os.getenv("SHIOAJI_SECRET_KEY", "YOUR_SECRET_KEY")
        CERT_PATH = os.getenv("SHIOAJI_CERT_PATH", "C:/path/to/your/certificate.pfx")
        CERT_PASS = os.getenv("SHIOAJI_CERT_PASS", "YOUR_CERT_PASSWORD")
        
        # **重要**: 請將您的 Firebase 服務帳號金鑰檔案命名為 'serviceAccountKey.json'
        #           並放置在與此腳本相同的目錄下。
        #           或者，您也可以修改下面的路徑。
        SERVICE_ACCOUNT_KEY_PATH = "serviceAccountKey.json"

        if "YOUR_API_KEY" in API_KEY or "YOUR_SECRET_KEY" in SECRET_KEY:
            print("錯誤：請在程式碼中或環境變數中設定您的 API Key/Secret。")
            return
        if "path/to/your" in CERT_PATH:
            print("錯誤：請更新 'CERT_PATH' 為您憑證檔案的正確絕對路徑。")
            return
        if not os.path.exists(SERVICE_ACCOUNT_KEY_PATH):
            print(f"錯誤：找不到 Firebase 服務帳號金鑰檔案 '{SERVICE_ACCOUNT_KEY_PATH}'。")
            print("請從您的 Firebase 專案下載金鑰，並將其放置在正確的路徑。")
            return

        # 步驟 1: 初始化下載器並登入
        downloader = TXFDownloader(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            cert_path=CERT_PATH,
            cert_pass=CERT_PASS
        )
        downloader.login()
        
        # 步驟 2: 初始化 Firestore
        downloader.init_firestore(SERVICE_ACCOUNT_KEY_PATH)

        # --- 範例 1: 下載近月合約資料並儲存 ---
        print("\n--- 範例 1: 下載近月合約資料 ---")
        downloader.get_near_future_contract()
        raw_data = downloader.fetch_data(days_to_fetch=5)
        processed_data = downloader.process_data(raw_data)
        
        # 儲存至 CSV
        downloader.save_to_csv(processed_data)
        # 儲存至 Firestore
        downloader.save_to_firestore(processed_data)
        
        print("--- 範例 1 結束 ---\n")


        # --- 範例 2: 下載連續月資料並儲存 ---
        print("\n--- 範例 2: 下載連續月資料 ---")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        print(f"準備下載從 {start_date_str} 到 {end_date_str} 的連續月資料...")
        
        continuous_raw_data = downloader.fetch_continuous_data(
            start_date=start_date_str,
            end_date=end_date_str
        )
        
        continuous_processed_data = downloader.process_data(continuous_raw_data)
        
        if continuous_processed_data is not None:
            # 儲存至 CSV
            csv_filename = f"TXF_1m_continuous_{start_date_str}_to_{end_date_str}.csv"
            downloader.save_to_csv(continuous_processed_data, filename=csv_filename)
            # 儲存至 Firestore
            downloader.save_to_firestore(continuous_processed_data)

        print("--- 範例 2 結束 ---")

    except Exception as e:
        print(f"程式執行過程中發生未預期的錯誤: {e}")

if __name__ == "__main__":
    main()
