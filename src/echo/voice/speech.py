"""语音输入输出 —— 零外部依赖，优雅降级.

Windows: 使用 SAPI (win32com) 或 pyttsx3
macOS: 使用 say 命令
Linux: 使用 espeak
均不可用时: 静默降级，打印提示
"""

import platform
import subprocess
import sys
from typing import Optional

_available = None


def voice_available() -> bool:
    """检测是否有 TTS 能力."""
    global _available
    if _available is not None:
        return _available

    system = platform.system()
    if system == "Windows":
        try:
            import win32com.client
            _available = True
            return True
        except ImportError:
            pass
    elif system == "Darwin":
        _available = True  # macOS 有内置 say
        return True
    elif system == "Linux":
        try:
            subprocess.run(["which", "espeak"], capture_output=True, check=True)
            _available = True
            return True
        except Exception:
            pass

    _available = False
    return False


def speak(text: str, rate: int = 180) -> None:
    """将文本转换为语音输出.

    Args:
        text: 要朗读的文本
        rate: 语速（仅部分后端支持）
    """
    if not voice_available():
        return

    system = platform.system()
    try:
        if system == "Windows":
            _speak_windows(text, rate)
        elif system == "Darwin":
            _speak_macos(text, rate)
        elif system == "Linux":
            _speak_linux(text, rate)
    except Exception:
        pass  # TTS 失败不应阻断对话


def _speak_windows(text: str, rate: int) -> None:
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Rate = (rate - 180) // 10  # SAPI rate: -10 to 10
        speaker.Speak(text)
    except Exception:
        pass


def _speak_macos(text: str, rate: int) -> None:
    words_per_minute = rate + 60
    subprocess.run(["say", "-r", str(words_per_minute), text],
                   capture_output=True, timeout=30)


def _speak_linux(text: str, rate: int) -> None:
    words_per_minute = rate + 60
    subprocess.run(["espeak", "-s", str(words_per_minute), text],
                   capture_output=True, timeout=30)


def listen(timeout: int = 5) -> Optional[str]:
    """从麦克风捕获语音并转为文本.

    当前返回 None（STT 需要额外依赖如 whisper）。
    作为接口预留。
    """
    return None  # STT 需要 whisper 或 cloud API，暂不实现
