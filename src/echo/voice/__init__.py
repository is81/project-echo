"""声音模块 —— TTS + STT 零外部依赖."""

from .speech import speak, listen, voice_available

__all__ = ["speak", "listen", "voice_available"]
