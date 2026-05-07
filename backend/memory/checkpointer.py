from langgraph.checkpoint.sqlite import SqliteSaver
from utils.path_tool import get_abs_path

DB_PATH = get_abs_path("checkpoints.db")
_checkpointer_cm = SqliteSaver.from_conn_string(DB_PATH)
checkpointer = _checkpointer_cm.__enter__()
