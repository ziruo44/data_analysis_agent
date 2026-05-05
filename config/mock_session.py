"""
Mock user session config for development testing.
Replace these values with real database/Redis queries in production.
"""

MOCK_USER_ID = "user_001"

MOCK_SESSION = {
    "thread_id": "mock_thread_001",
    "user_id": MOCK_USER_ID,
    "created_at": "2026-04-22T21:00:00",
    "status": "active",
    "file_path": "storage/earthquake_data_tsunami.csv",
    "user_prompt": "请分析该数据并生成可视化报告"
}

# Map of thread_id -> session data
SESSIONS = {"mock_thread_001": MOCK_SESSION}