import unittest
import pandas as pd
from datetime import datetime
import sys
import os

# 將專案根目錄加入到 Python 路徑中，這樣才能 import tx_downloader
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tx_downloader import TXFDownloader

class TestTXFDownloader(unittest.TestCase):

    def test_resample_ticks_to_1min_kbars_normal(self):
        """測試正常情況下的 Ticks 轉換功能"""
        print("\nRunning test: test_resample_ticks_to_1min_kbars_normal")
        
        # 準備模擬的 Ticks 輸入資料 (橫跨兩分鐘)
        mock_ticks_data = {
            'ts': [
                datetime(2025, 11, 20, 9, 1, 10).timestamp() * 1e9,  # 09:01:10
                datetime(2025, 11, 20, 9, 1, 25).timestamp() * 1e9,  # 09:01:25
                datetime(2025, 11, 20, 9, 1, 50).timestamp() * 1e9,  # 09:01:50
                datetime(2025, 11, 20, 9, 2, 5).timestamp() * 1e9,   # 09:02:05 (只有一筆)
            ],
            'close': [100, 120, 110, 115],
            'volume': [10, 5, 8, 20]
        }
        mock_df = pd.DataFrame(mock_ticks_data)

        # 執行要測試的函式
        result_df = TXFDownloader.resample_ticks_to_1min_kbars(mock_df)

        # --- 開始驗證 ---
        
        # 1. 驗證輸出不是 None 且有 2 筆資料 (09:01 和 09:02)
        self.assertIsNotNone(result_df)
        self.assertEqual(len(result_df), 2)

        # 2. 驗證欄位名稱是否正確
        expected_columns = {'datetime', 'Open', 'High', 'Low', 'Close', 'Volume'}
        self.assertEqual(set(result_df.columns), expected_columns)

        # 3. 詳細驗證第一分鐘 (09:01) 的 K 棒資料
        first_k_bar = result_df.iloc[0]
        self.assertEqual(first_k_bar['datetime'], pd.Timestamp('2025-11-20 09:01:00'))
        self.assertEqual(first_k_bar['Open'], 100)   # 第一次的價格
        self.assertEqual(first_k_bar['High'], 120)   # 最高的價格
        self.assertEqual(first_k_bar['Low'], 100)    # 最低的價格
        self.assertEqual(first_k_bar['Close'], 110)  # 最後一次的價格
        self.assertEqual(first_k_bar['Volume'], 23)  # 10 + 5 + 8

        # 4. 詳細驗證第二分鐘 (09:02) 的 K 棒資料 (只有一筆 tick)
        second_k_bar = result_df.iloc[1]
        self.assertEqual(second_k_bar['datetime'], pd.Timestamp('2025-11-20 09:02:00'))
        self.assertEqual(second_k_bar['Open'], 115)
        self.assertEqual(second_k_bar['High'], 115)
        self.assertEqual(second_k_bar['Low'], 115)
        self.assertEqual(second_k_bar['Close'], 115)
        self.assertEqual(second_k_bar['Volume'], 20)

    def test_resample_ticks_edge_cases(self):
        """測試邊界情況：空的或 None 的輸入"""
        print("\nRunning test: test_resample_ticks_edge_cases")

        # 1. 測試輸入為 None
        result_none = TXFDownloader.resample_ticks_to_1min_kbars(None)
        self.assertIsNone(result_none)

        # 2. 測試輸入為空的 DataFrame
        empty_df = pd.DataFrame({'ts': [], 'close': [], 'volume': []})
        result_empty = TXFDownloader.resample_ticks_to_1min_kbars(empty_df)
        self.assertIsNone(result_empty)

    def test_save_ticks_to_csv(self):
        """測試將 Ticks 儲存至 CSV 的功能"""
        print("\nRunning test: test_save_ticks_to_csv")

        # 1. 準備測試資料和物件
        # 我們不需要真的登入，所以 API Key 給假資料即可
        downloader = TXFDownloader(api_key="DUMMY", secret_key="DUMMY", cert_path="", cert_pass="")
        
        mock_ticks_data = {
            'ts': [
                datetime(2025, 11, 20, 9, 1, 10, 123456).timestamp() * 1e9,
                datetime(2025, 11, 20, 9, 1, 25, 654321).timestamp() * 1e9,
            ],
            'close': [100.5, 101.0],
            'volume': [10, 5],
            'tick_type': ['Deal', 'Deal']
        }
        mock_df = pd.DataFrame(mock_ticks_data)
        
        contract_code = "TXF202512"
        date_str = "2025-11-20"
        # 修正檔案路徑，確保它在 tradedata 資料夾內
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'tradedata')
        os.makedirs(data_dir, exist_ok=True)
        expected_filename = os.path.join(data_dir, f"TXF_ticks_{contract_code}_{date_str}.csv")

        # 確保測試前檔案不存在
        if os.path.exists(expected_filename):
            os.remove(expected_filename)

        try:
            # 2. 執行要測試的函式
            downloader.save_ticks_to_csv(mock_df, contract_code, date_str)

            # 3. 驗證檔案是否成功建立
            self.assertTrue(os.path.exists(expected_filename))

            # 4. 讀取檔案並驗證內容
            saved_df = pd.read_csv(expected_filename)
            
            # 驗證欄位
            self.assertEqual(list(saved_df.columns), ['datetime', 'close', 'volume', 'tick_type'])
            
            # 驗證筆數
            self.assertEqual(len(saved_df), 2)
            
            # 驗證第一筆資料的價格和量
            self.assertEqual(saved_df.iloc[0]['close'], 100.5)
            self.assertEqual(saved_df.iloc[0]['volume'], 10)
            
            # 驗證時間戳的日期部分
            # 原始時間是 UTC，儲存時會轉為 Asia/Taipei
            # 2025-11-20 09:01:10 UTC -> 2025-11-20 17:01:10 Asia/Taipei
            self.assertTrue(saved_df.iloc[0]['datetime'].startswith("2025-11-20 17:01:10"))

        finally:
            # 5. 清理測試後產生的檔案
            if os.path.exists(expected_filename):
                os.remove(expected_filename)

    def test_save_weekly_ticks_to_csv(self):
        """測試將 Ticks 按照週次儲存至 CSV 的功能"""
        print("\nRunning test: test_save_weekly_ticks_to_csv")

        # 1. 準備測試資料和物件
        downloader = TXFDownloader(api_key="DUMMY", secret_key="DUMMY", cert_path="", cert_pass="")
        
        # 準備橫跨兩週的 Ticks 資料
        # 第一週: 2025-11-13 (週四)
        # 第二週: 2025-11-17 (週一)
        mock_ticks_data = {
            'ts': [
                datetime(2025, 11, 13, 10, 0, 0).timestamp() * 1e9,
                datetime(2025, 11, 13, 11, 0, 0).timestamp() * 1e9,
                datetime(2025, 11, 17, 10, 0, 0).timestamp() * 1e9,
            ],
            'close': [22000, 22010, 22100],
            'volume': [2, 3, 5]
        }
        mock_df = pd.DataFrame(mock_ticks_data)
        
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'tradedata')
        os.makedirs(data_dir, exist_ok=True)

        # 預期產生的檔案名稱
        # 第一週是從 2025-11-10 (週一) 開始
        expected_file1 = os.path.join(data_dir, "TXF_ticks_weekly_2025-11-13_to_2025-11-13.csv")
        # 第二週是從 2025-11-17 (週一) 開始
        expected_file2 = os.path.join(data_dir, "TXF_ticks_weekly_2025-11-17_to_2025-11-17.csv")

        # 清理舊檔案
        if os.path.exists(expected_file1): os.remove(expected_file1)
        if os.path.exists(expected_file2): os.remove(expected_file2)

        try:
            # 2. 執行函式
            downloader.save_weekly_ticks_to_csv(mock_df)

            # 3. 驗證檔案是否都已建立
            self.assertTrue(os.path.exists(expected_file1), f"檔案 {expected_file1} 未建立")
            self.assertTrue(os.path.exists(expected_file2), f"檔案 {expected_file2} 未建立")

            # 4. 驗證第一個檔案的內容
            df1 = pd.read_csv(expected_file1)
            self.assertEqual(len(df1), 2)
            self.assertEqual(df1.iloc[0]['close'], 22000)
            self.assertEqual(df1.iloc[1]['volume'], 3)

            # 5. 驗證第二個檔案的內容
            df2 = pd.read_csv(expected_file2)
            self.assertEqual(len(df2), 1)
            self.assertEqual(df2.iloc[0]['close'], 22100)

        finally:
            # 6. 清理測試檔案
            if os.path.exists(expected_file1): os.remove(expected_file1)
            if os.path.exists(expected_file2): os.remove(expected_file2)

if __name__ == '__main__':
    unittest.main()