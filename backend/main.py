"""Data Analysis Agent - CLI entry point."""
import os
from agent.graph_run import build_graph
from agent.graph_run import browse_history
from agent.graph_run import continue_workflow
from agent.graph_run import run_workflow

from utils.thread_check import delete_thread
from utils.path_tool import list_csv_files, get_abs_path


def interactive_run():
    """交互式入口：选择查看历史、开始新对话或继续已有对话"""
    app = build_graph()

    while True:
        print("\n" + "=" * 50)
        print("数据分析智能体")
        print("=" * 50)
        print("  1. 查看会话历史")
        print("  2. 开始新对话")
        print("  3. 继续已有对话")
        print("  4. 删除会话")
        print("  0. 退出")
        choice = input("\n> ").strip()

        if choice == "0":
            print("再见！")
            break

        if choice == "1":
            browse_history(app)
            continue

        if choice == "4":
            from utils.thread_check import list_threads
            threads = list_threads()
            if not threads:
                print("❌ 暂无任何历史记录")
                continue
            print("\n=== 所有会话线程 ===")
            for i, (tid, count) in enumerate(threads, 1):
                print(f"  {i}. {tid}  ({count} 个检查点)")
            print("\n输入编号选择要删除的线程:")
            thread_choice = input("> ").strip()
            if thread_choice.isdigit():
                idx = int(thread_choice) - 1
                if 0 <= idx < len(threads):
                    delete_thread(threads[idx][0], app)
                    continue
            print("❌ 无效选择")
            continue

        if choice == "3":
            from utils.thread_check import list_threads
            threads = list_threads()

            if not threads:
                print("❌ 暂无任何历史记录")
                continue

            print("\n=== 所有会话线程 ===")
            for i, (tid, count) in enumerate(threads, 1):
                print(f"  {i}. {tid}")
                try:
                    config = {"configurable": {"thread_id": tid}}
                    state = app.get_state(config)
                    if state and state.values:
                        file_path = state.values.get("file_path", "未知")
                        print(f"      文件: {file_path}")
                except:
                    pass

            print("\n输入编号选择线程:")
            thread_choice = input("> ").strip()

            if thread_choice.isdigit():
                idx = int(thread_choice) - 1
                if 0 <= idx < len(threads):
                    continue_workflow(threads[idx][0])
                    continue
            print("❌ 无效选择")
            continue

        if choice != "2":
            print("❌ 无效选择")
            continue

        # 开始新对话
        print("\n=== 可用的 CSV 文件 ===")
        csv_files = list_csv_files()
        if not csv_files:
            print("❌ 没有找到 CSV 文件")
            continue

        for i, f in enumerate(csv_files, 1):
            print(f"  {i}. {f}")

        print("\n请选择文件编号或输入完整路径:")
        file_choice = input("> ").strip()

        if file_choice.isdigit():
            idx = int(file_choice) - 1
            if 0 <= idx < len(csv_files):
                file_path = get_abs_path(csv_files[idx])
            else:
                print("❌ 无效编号")
                continue
        else:
            file_path = file_choice

        print("\n请输入分析提示词 (直接回车使用默认):")
        user_prompt = input("> ").strip() or "请分析该数据并生成可视化图表"

        print(f"\n使用文件: {file_path}")
        print(f"提示词: {user_prompt}")

        run_workflow(file_path, user_prompt)

if __name__ == "__main__":
    interactive_run()
