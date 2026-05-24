from dataclasses import dataclass, field
from typing import Optional, List
import threading

@dataclass
class SubtitleLine:
    index: int
    start_ms: int
    end_ms: int
    text: str

@dataclass
class UserSession:
    action: str = "idle"
    videos: List[str] = field(default_factory=list)
    music: Optional[str] = None
    cut_start: Optional[str] = None
    cut_end: Optional[str] = None
    text_content: Optional[str] = None
    last_video_path: Optional[str] = None
    last_photo_path: Optional[str] = None
    pending_new_video: Optional[str] = None
    pending_music_path: Optional[str] = None
    srt_lines: Optional[List[SubtitleLine]] = None
    srt_path: Optional[str] = None
    subtitle_style: Optional[str] = None
    subtitle_animation: Optional[str] = None
    subtitle_position: Optional[str] = None
    subtitle_size: Optional[str] = None
    words_per_line: int = 2
    pending_montage_effect: Optional[str] = None
    watermark_text: Optional[str] = None
    last_menu_message_id: Optional[int] = None
    chat_id: Optional[int] = None
    editing_line_num: Optional[int] = None

_sessions: dict = {}
_lock = threading.Lock()

def get_session(user_id: int) -> UserSession:
    with _lock:
        if user_id not in _sessions:
            _sessions[user_id] = UserSession()
        return _sessions[user_id]

def set_session(user_id: int, **kwargs):
    with _lock:
        if user_id not in _sessions:
            _sessions[user_id] = UserSession()
        sess = _sessions[user_id]
        for k, v in kwargs.items():
            setattr(sess, k, v)

def reset_session(user_id: int):
    with _lock:
        old = _sessions.get(user_id)
        _sessions[user_id] = UserSession(
            watermark_text=old.watermark_text if old else None,
            chat_id=old.chat_id if old else None,
            last_menu_message_id=old.last_menu_message_id if old else None,
        )

def soft_reset_session(user_id: int, new_video_path: Optional[str] = None):
    with _lock:
        old = _sessions.get(user_id)
        _sessions[user_id] = UserSession(
            action="idle",
            videos=[new_video_path] if new_video_path else (old.videos if old else []),
            last_video_path=new_video_path if new_video_path else (old.last_video_path if old else None),
            watermark_text=old.watermark_text if old else None,
            chat_id=old.chat_id if old else None,
            last_menu_message_id=old.last_menu_message_id if old else None,
        )
