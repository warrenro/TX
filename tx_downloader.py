import os
import shioaji as sj
import pandas as pd
from datetime import datetime, timedelta

# 建議：使用 python-dotenv 套件來管理您的敏感資訊
# from dotenv import load_dotenv
# load_dotenv()

class TXFDownloader:
    """
    台指期 1 分 K 線資料自動下載器
    - 自動登入 Shioaji API
    - 抓取近月合約
    - 下載 1 分鐘 K 線資料
    - 清洗並儲存為 CSV
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

    @staticmethod
    def process_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        資料清洗、時間轉換與格式整理。

        Args:
            df (pd.DataFrame): 從 API 取得的原始 DataFrame。

        Returns:
            pd.DataFrame: 清洗完成的 DataFrame。
        """
        if df is None or df.empty:
            return None
        
        print("正在進行資料清洗...")
        # 將奈秒時間戳轉換為日期時間格式，並設定為台灣時區
        df['ts'] = pd.to_datetime(df['ts'])
        df = df.rename(columns={'ts': 'Datetime'})
        df.set_index('Datetime', inplace=True)
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Taipei')

        # 篩選並重新命名欄位
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        
        print("資料清洗完成。")
        return df

    def save_to_csv(self, df: pd.DataFrame):
        """
        將 DataFrame 儲存為 CSV 檔案。

        Args:
            df (pd.DataFrame): 準備儲存的 DataFrame。
        """
        if df is None or df.empty:
            print("沒有資料可供儲存，已跳過。")
            return

        today_str = datetime.now().strftime('%Y%m%d')
        filename = f"TXF_1m_{self.contract.code}_{today_str}.csv"
        
        print(f"正在將資料儲存至檔案: {filename}")
        try:
            df.to_csv(filename, encoding='utf-8-sig')
            print(f"檔案儲存成功！路徑: {os.path.abspath(filename)}")
        except Exception as e:
            print(f"儲存 CSV 檔案時發生錯誤: {e}")

def main():
    """主執行函數"""
    try:
        # --- 使用者設定 ---
        # 安全建議：請將您的敏感資訊儲存在環境變數中，並使用 os.getenv 讀取
        # 例如: API_KEY = os.getenv("SHIOAJI_API_KEY")
        API_KEY = "YOUR_API_KEY"
        SECRET_KEY = "YOUR_SECRET_KEY"
        CERT_PATH = "C:/path/to/your/certificate.pfx" # Windows 範例
        # CERT_PATH = "/Users/yourname/certs/certificate.pfx" # macOS/Linux 範例
        CERT_PASS = "YOUR_CERT_PASSWORD" # 通常是身分證字號

        # 檢查使用者是否已替換預設值
        if "YOUR_API_KEY" in API_KEY or "YOUR_SECRET_KEY" in SECRET_KEY:
            print("錯誤：請在程式碼中替換 'YOUR_API_KEY' 和 'YOUR_SECRET_KEY' 為您的真實金鑰。")
            return
        if "path/to/your" in CERT_PATH:
            print("錯誤：請更新 'CERT_PATH' 為您憑證檔案的正確絕對路徑。")
            return

        # 步驟 1: 初始化下載器並登入
        downloader = TXFDownloader(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            cert_path=CERT_PATH,
            cert_pass=CERT_PASS
        )
        downloader.login()

        # 步驟 2: 取得近月合約
        downloader.get_near_future_contract()

        # 步驟 3: 下載 K 線資料 (預設 5 天)
        raw_data = downloader.fetch_data(days_to_fetch=5)

        # 步驟 4: 資料處理
        processed_data = downloader.process_data(raw_data)

        # 步驟 5: 儲存至 CSV
        downloader.save_to_csv(processed_data)

    except Exception as e:
        print(f"程式執行過程中發生未預期的錯誤: {e}")

if __name__ == "__main__":
    main()
