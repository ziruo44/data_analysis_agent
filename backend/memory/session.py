from config.mock_session import MOCK_SESSION

def get_session_config(thread_id: str = None):
    """
    返回调用 graph.invoke() 所需的 config dict。
    后续 FastAPI 接入时，这里改成从 request headers / Redis / DB 获取。
    """
    if thread_id is None:
        thread_id = MOCK_SESSION["thread_id"]
    return {
        "configurable": {
            "thread_id": thread_id,
            "user_id": MOCK_SESSION["user_id"],
        }
    }
