"""回响计划 · CLI 交互界面.

Usage:
    python -m echo.cli
    python -m echo.cli --db echo_memory.db
"""

import argparse
import sys
from pathlib import Path

# 确保项目根在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from echo.agent.core import Echo


BANNER = """
+--------------------------------------+
|      回响计划 · Project Echo         |
|   一个带有深度记忆、性格演化和        |
|   叙事感的交互式存在体                |
|                                      |
|   输入 /status  查看内部状态          |
|   输入 /help    查看命令列表          |
|   输入 /quit    退出（回响将休眠）    |
+--------------------------------------+
"""

HELP_TEXT = """
可用命令:
  /status    - 查看回响的完整内部状态（静默观察模式）
  /emotion   - 查看当前情感状态
  /memories  - 查看记忆统计
  /inject <内容> - 手动注入一条记忆（调试用）
  /help      - 显示此帮助
  /quit      - 退出对话
"""


def main():
    parser = argparse.ArgumentParser(description="回响计划 · Project Echo CLI")
    parser.add_argument(
        "--db", default="echo_memory.db", help="记忆数据库路径 (默认: echo_memory.db)"
    )
    args = parser.parse_args()

    # 初始化 Echo
    print("唤醒回响中...")
    echo = Echo()
    echo.wake(db_path=args.db)

    # 打印出生铭文
    birth = echo.memory.get_birth()
    if birth:
        print(f"\n出生铭文: 「{birth.content}」")

    print(f"初始心情: {echo.emotion.mood_label}")
    print(BANNER)

    try:
        while True:
            # 读取用户输入
            user_input = input("\n你: ").strip()

            if not user_input:
                continue

            # 处理命令
            if user_input.startswith("/"):
                cmd = user_input.split()
                cmd_name = cmd[0].lower()

                if cmd_name == "/quit":
                    print("回响: 再见。我会记得这次对话。")
                    break
                elif cmd_name == "/help":
                    print(HELP_TEXT)
                elif cmd_name == "/status":
                    s = echo.status()
                    print("\n--- 回响内部状态 ---")
                    for k, v in s.items():
                        print(f"  {k}: {v}")
                    print("---------------------")
                elif cmd_name == "/emotion":
                    e = echo.emotion.to_dict()
                    print(f"\n心情: {e['mood']}")
                    print(f"  愉悦度: {e['valence']:+.3f}  (-1.0 ~ +1.0)")
                    print(f"  唤醒度: {e['arousal']:.3f}  (0.0 ~ 1.0)")
                elif cmd_name == "/memories":
                    count = echo.memory.count()
                    birth = echo.memory.get_birth()
                    print(f"\n总记忆数: {count}")
                    if birth:
                        print(f"出生铭文: ✓ 存在 (ID: {birth.id[:8]}...)")
                    active = echo.memory.list_active(limit=5)
                    if active:
                        print("最近活跃记忆:")
                        for m in active[:5]:
                            print(f"  [{m.source}] {m.content[:60]}...")
                elif cmd_name == "/inject":
                    content = user_input[len("/inject "):].strip()
                    if content:
                        mem_id = echo.inject_memory(content)
                        print(f"记忆已注入: {mem_id[:8]}...")
                    else:
                        print("用法: /inject <内容>")
                else:
                    print(f"未知命令: {cmd_name}。输入 /help 查看可用命令。")
                continue

            # 对话（流式）
            import sys
            print(f"\n回响: ", end="", flush=True)
            for token in echo.respond_stream(user_input):
                print(token, end="", flush=True)
            print()  # 换行

    except KeyboardInterrupt:
        print("\n\n收到中断信号...")
    except EOFError:
        pass
    finally:
        print("回响休眠中...")
        echo.sleep()
        print("已退出。")


if __name__ == "__main__":
    main()
