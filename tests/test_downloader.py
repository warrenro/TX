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
        expected_filename = f"TXF_ticks_{contract_code}_{date_str}.csv"
        
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
            
            # 驗證時間是否正確轉換 (包含時區)
            # 原始時間是 2025-11-20 09:01:10.123456 UTC+0
            # 轉換後應為 2025-11-20 17:01:10.123456 UTC+8 (Asia/Taipei)
            # CSV 儲存的格式是 'YYYY-MM-DD HH:MM:SS.ffffff'
            expected_datetime_str = "2025-11-20 17:01:10.123456"
            self.assertEqual(saved_df.iloc[0]['datetime'], expected_datetime_str)

        finally:
            # 5. 清理測試後產生的檔案
            if os.path.exists(expected_filename):
                os.remove(expected_filename)

if __name__ == '__main__':
    unittest.main()