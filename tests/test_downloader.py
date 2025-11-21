import unittest
from unittest.mock import patch, MagicMock, call, mock_open
import pandas as pd
from datetime import datetime, date
import sys
import os

# 將專案根目錄加入到 Python 路徑中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 匯入需要被測試的目標
from tx_downloader import TXFDownloader, main, get_resume_date, calculate_date_range

class TestTXDownloaderFeatures(unittest.TestCase):

    def setUp(self):
        """在每個測試前執行，用於準備環境"""
        # 清理可能由其他測試留下的進度檔案
        if os.path.exists('download_progress.txt'):
            os.remove('download_progress.txt')

    def tearDown(self):
        """在每個測試後執行，用於清理環境"""
        if os.path.exists('download_progress.txt'):
            os.remove('download_progress.txt')

    @patch('tx_downloader.os.getenv')
    @patch('tx_downloader.get_storage_choice', return_value='2') # 2: CSV
    @patch('tx_downloader.get_period_choice', return_value=('last_day', None, None))
    @patch('tx_downloader.get_data_type_choice')
    @patch('tx_downloader.TXFDownloader')
    def test_main_flow_select_ticks_only(self, mock_downloader_class, mock_data_type, mock_period, mock_storage, mock_getenv):
        """測試主流程：選擇只下載 Ticks"""
        print("\nRunning test: test_main_flow_select_ticks_only")
        
        # --- 設定模擬 ---
        # 模擬使用者選擇 'a' (僅 Ticks)
        mock_data_type.return_value = 'a'
        
        # 模擬 .env 檔案的返回值
        mock_getenv.return_value = "DUMMY_VALUE"

        # 建立 downloader 的實例 mock
        mock_downloader_instance = MagicMock()
        mock_downloader_class.return_value = mock_downloader_instance
        mock_downloader_instance.login.return_value = True

        # --- 執行 main 函式 ---
        main()

        # --- 驗證 ---
        # 1. 驗證 downloader 被正確初始化和登入
        mock_downloader_class.assert_called_once()
        mock_downloader_instance.login.assert_called_once()

        # 2. 驗證下載函式被呼叫
        mock_downloader_instance.fetch_and_save_ticks.assert_called_once()
        
        # 3. 驗證 K-bar 相關函式未被呼叫
        mock_downloader_instance.fetch_kbars.assert_not_called()
        mock_downloader_instance.save_to_csv.assert_not_called() # save_to_csv 是給 kbar 用的

    @patch('tx_downloader.os.getenv')
    @patch('tx_downloader.get_storage_choice', return_value='2') # 2: CSV
    @patch('tx_downloader.get_period_choice', return_value=('last_day', None, None))
    @patch('tx_downloader.get_data_type_choice')
    @patch('tx_downloader.TXFDownloader')
    def test_main_flow_select_kbars_only(self, mock_downloader_class, mock_data_type, mock_period, mock_storage, mock_getenv):
        """測試主流程：選擇只下載 K-bars"""
        print("\nRunning test: test_main_flow_select_kbars_only")

        # --- 設定模擬 ---
        mock_data_type.return_value = 'b' # 僅 K-bar
        mock_getenv.return_value = "DUMMY_VALUE"
        
        mock_downloader_instance = MagicMock()
        # 模擬 fetch_kbars 回傳一個假的 DataFrame
        mock_kbars_df = pd.DataFrame({'ts': [datetime.now()], 'Open': [1], 'High': [1], 'Low': [1], 'Close': [1], 'Volume': [1]})
        mock_downloader_instance.fetch_kbars.return_value = mock_kbars_df
        mock_downloader_instance.process_data.return_value = mock_kbars_df # 假設 process 後格式不變
        mock_downloader_class.return_value = mock_downloader_instance
        mock_downloader_instance.login.return_value = True

        # --- 執行 main 函式 ---
        main()

        # --- 驗證 ---
        # 1. 驗證 Ticks 相關函式未被呼叫
        mock_downloader_instance.fetch_and_save_ticks.assert_not_called()

        # 2. 驗證 K-bar 相關函式被呼叫
        mock_downloader_instance.fetch_kbars.assert_called_once()
        mock_downloader_instance.process_data.assert_called_once()
        mock_downloader_instance.save_to_csv.assert_called_once()

    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', mock_open(read_data='2025-11-20'))
    def test_get_resume_date_found(self):
        """測試續傳功能：找到進度檔案"""
        print("\nRunning test: test_get_resume_date_found")
        resume_date = get_resume_date()
        self.assertEqual(resume_date, date(2025, 11, 20))

    @patch('os.path.exists', return_value=False)
    def test_get_resume_date_not_found(self, mock_exists):
        """測試續傳功能：找不到進度檔案"""
        print("\nRunning test: test_get_resume_date_not_found")
        resume_date = get_resume_date()
        self.assertIsNone(resume_date)

    @patch('tx_downloader.get_resume_date', return_value=date(2025, 11, 20))
    def test_calculate_date_range_with_resume(self, mock_get_resume):
        """測試日期計算：當有續傳日期時，應使用續傳日期"""
        print("\nRunning test: test_calculate_date_range_with_resume")
        # 即使使用者選了 'last_day'，也應該被續傳日期覆蓋
        start, end = calculate_date_range('last_day', None, None)
        self.assertEqual(start, date(2025, 11, 20))

    @patch('shioaji.Shioaji')
    def test_token_refresh_logic(self, mock_shioaji_class):
        """測試 Token 自動更新與重試邏輯"""
        print("\nRunning test: test_token_refresh_logic")
        
        # --- 設定模擬 ---
        # 模擬 API 第一次呼叫時拋出例外，第二次成功
        mock_api_instance = MagicMock()
        mock_api_instance.ticks.side_effect = [
            Exception("Token expired"), # 第一次呼叫拋出例外
            MagicMock(ts=[12345])      # 第二次呼叫回傳成功
        ]
        
        # 模擬 Shioaji() 返回我們的 mock api instance
        mock_shioaji_class.return_value = mock_api_instance

        # 建立 downloader，但這次傳入的是 mock 過的 api 物件
        downloader = TXFDownloader("key", "secret", "path", "pass")
        downloader.api = mock_api_instance
        
        # 模擬 login 函式，讓它總是成功
        downloader.login = MagicMock(return_value=True)

        # --- 執行 ---
        # 直接呼叫內部帶有重試邏輯的函式
        result = downloader._execute_api_call(downloader.api.ticks, contract="TXF", date="2025-01-01")

        # --- 驗證 ---
        # 1. 驗證 login 函式被呼叫了一次 (在偵測到錯誤後)
        downloader.login.assert_called_once()
        
        # 2. 驗證 api.ticks 總共被呼叫了兩次
        self.assertEqual(downloader.api.ticks.call_count, 2)
        
        # 3. 驗證回傳結果是第二次呼叫的成功結果
        self.assertIsNotNone(result)
        self.assertEqual(result.ts, [12345])

if __name__ == '__main__':
    unittest.main()
