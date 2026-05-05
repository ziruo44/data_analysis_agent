"""交互式查看 SqliteSaver checkpoint 内容"""
from memory.checkpointer import checkpointer
from memory.session import get_session_config


def list_checkpoints(config):
    return list(checkpointer.list(config))


def print_checkpoint_summary(cps):
    print(f"\n{'='*60}")
    print(f"共 {len(cps)} 个 checkpoint：")
    print(f"{'='*60}")
    for i, cp in enumerate(cps):
        step = cp.metadata.get("step", "?")
        ts = cp.checkpoint["ts"]
        values = cp.checkpoint.get("channel_values", {})
        keys = list(values.keys())
        print(f"  [{i}] step={step:>2} | {ts} | keys={keys}")


def view_checkpoint(cp):
    print(f"\n{'-'*60}")
    print(f"Step: {cp.metadata.get('step')}")
    print(f"ID: {cp.checkpoint['id']}")
    print(f"时间: {cp.checkpoint['ts']}")
    print(f"{'-'*60}")

    values = cp.checkpoint.get("channel_values", {})
    print(f"\n共 {len(values)} 个状态字段：")

    for key, val in values.items():
        val_preview = repr(val)
        if isinstance(val, str) and len(val) > 100:
            val_preview = repr(val[:100]) + "..."
        elif isinstance(val, list) and len(val) > 3:
            val_preview = repr(val[:3]) + f" [...x{len(val)-3}]"
        elif isinstance(val, dict):
            val_preview = repr({k: v for k, v in list(val.items())[:3]}) + f" ...x{len(val)}"
        print(f"  {key}: {val_preview}")


def interactive_view():
    config = get_session_config()
    thread_id = config["configurable"]["thread_id"]
    print(f"\n线程 ID: {thread_id}")

    cps = list_checkpoints(config)
    if not cps:
        print("没有找到任何 checkpoint！")
        return

    print_checkpoint_summary(cps)

    while True:
        choice = input("\n输入编号查看详情 (q退出): ").strip()
        if choice.lower() == "q":
            break
        try:
            idx = int(choice)
            if 0 <= idx < len(cps):
                view_checkpoint(cps[idx])
            else:
                print(f"编号范围: 0 ~ {len(cps)-1}")
        except ValueError:
            print("请输入有效编号")


if __name__ == "__main__":
    interactive_view()
