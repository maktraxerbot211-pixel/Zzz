import asyncio
import json
import math
import os
import re
import subprocess
import sys
import time
import random
import string
from typing import List, Optional, Tuple

from sessions import SubtitleLine

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")
WHISPER = os.environ.get("WHISPER_PATH", "whisper-ctranslate2")
TMP_DIR = "/tmp/tgbot"
os.makedirs(TMP_DIR, exist_ok=True)

FONT = "DejaVu Sans"
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def tmp_path(name: str) -> str:
    return os.path.join(TMP_DIR, name)

def random_name(ext: str) -> str:
    rnd = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{int(time.time()*1000)}_{rnd}.{ext}"

def cleanup_file(path: str):
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass

def cleanup_old_files(max_age_seconds: int = 3600):
    now = time.time()
    removed = 0
    try:
        for fname in os.listdir(TMP_DIR):
            fpath = os.path.join(TMP_DIR, fname)
            try:
                if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > max_age_seconds:
                    os.unlink(fpath)
                    removed += 1
            except Exception:
                pass
    except Exception:
        pass
    return removed

async def run_cmd(*args, timeout: int = 600) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"Command timed out: {args[0]}")
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {stderr.decode()[-2000:]}")
    return stdout.decode()

# ─── SRT helpers ─────────────────────────────────────────────────────────────

def srt_time_to_ms(time_str: str) -> int:
    hms, ms = time_str.split(",")
    h, m, s = hms.split(":")
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)

def ms_to_srt_time(ms: int) -> str:
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms_rem = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"

def ms_to_ass_time(ms: int) -> str:
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    cs = (ms % 1000) // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def parse_srt(srt_content: str) -> List[SubtitleLine]:
    blocks = re.split(r'\n\n+', srt_content.strip())
    lines = []
    for block in blocks:
        parts = block.strip().split("\n")
        if len(parts) < 3:
            continue
        try:
            index = int(parts[0])
        except ValueError:
            continue
        m = re.match(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', parts[1])
        if not m:
            continue
        text = " ".join(parts[2:]).strip()
        lines.append(SubtitleLine(
            index=index,
            start_ms=srt_time_to_ms(m.group(1)),
            end_ms=srt_time_to_ms(m.group(2)),
            text=text,
        ))
    return lines

def split_srt_to_words(lines: List[SubtitleLine], words_per_line: int) -> List[SubtitleLine]:
    result = []
    counter = 1
    for line in lines:
        words = line.text.split()
        if len(words) <= words_per_line:
            result.append(SubtitleLine(counter, line.start_ms, line.end_ms, line.text))
            counter += 1
            continue
        duration = line.end_ms - line.start_ms
        chunks = [" ".join(words[i:i+words_per_line]) for i in range(0, len(words), words_per_line)]
        chunk_dur = duration // len(chunks)
        for i, chunk in enumerate(chunks):
            start = line.start_ms + i * chunk_dur
            end = line.end_ms if i == len(chunks) - 1 else line.start_ms + (i + 1) * chunk_dur
            result.append(SubtitleLine(counter, start, end, chunk))
            counter += 1
    return result

def lines_to_srt(lines: List[SubtitleLine]) -> str:
    return "\n\n".join(
        f"{l.index}\n{ms_to_srt_time(l.start_ms)} --> {ms_to_srt_time(l.end_ms)}\n{l.text}"
        for l in lines
    )

def format_srt_for_display(lines: List[SubtitleLine]) -> str:
    parts = []
    for l in lines:
        s_min = l.start_ms // 60000
        s_sec = (l.start_ms % 60000) // 1000
        parts.append(f"{l.index}. [{s_min}:{s_sec:02d}] {l.text}")
    return "\n".join(parts)

# ─── ASS subtitle generation ─────────────────────────────────────────────────

ASS_STYLE_BASE = {
    "classic": lambda a, v, fs: f"{FONT},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,{a},10,10,{v},1",
    "fire":    lambda a, v, fs: f"{FONT},{fs},&H000066FF,&H000000FF,&H00000080,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,{a},10,10,{v},1",
    "neon":    lambda a, v, fs: f"{FONT},{fs},&H0000FFFF,&H000000FF,&H000066FF,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,{a},10,10,{v},1",
    "minimal": lambda a, v, fs: f"{FONT},{fs},&H00E0E0E0,&H000000FF,&H00000000,&HC0000000,0,0,0,0,100,100,0,0,1,1,2,{a},10,10,{v},1",
    "bold":    lambda a, v, fs: f"{FONT},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,3,{a},10,10,{v},1",
}

STYLE_BASE_SIZE = {"classic": 26, "fire": 30, "neon": 28, "minimal": 22, "bold": 36}
SIZE_SCALE = {"small": 0.75, "medium": 1.0, "large": 1.4, "xl": 1.85}

def position_to_alignment(pos: str) -> int:
    return {"top": 8, "center": 5, "bottom": 2}.get(pos, 2)

def position_to_margin_v(pos: str) -> int:
    return {"top": 30, "center": 0, "bottom": 20}.get(pos, 20)

def get_anim_tag(animation: str) -> str:
    return {
        "fade":        r"{\fad(200,200)}",
        "pop":         r"{\fad(80,80)\t(0,250,\fscx115\fscy115)\t(250,450,\fscx100\fscy100)}",
        "zoom_bounce": r"{\fscx150\fscy150\fad(0,200)\t(0,350,\fscx100\fscy100)\t(350,450,\fscx107\fscy107)\t(450,550,\fscx100\fscy100)}",
        "blur_in":     r"{\blur10\fad(350,200)\t(0,420,\blur0)}",
    }.get(animation, "")

def generate_typewriter_events(lines: List[SubtitleLine]) -> str:
    events = []
    for line in lines:
        words = line.text.split()
        if len(words) <= 1:
            events.append(f"Dialogue: 0,{ms_to_ass_time(line.start_ms)},{ms_to_ass_time(line.end_ms)},Default,,0,0,0,,{{\\fad(120,80)}}{line.text}")
            continue
        duration = line.end_ms - line.start_ms
        step_dur = duration // len(words)
        for i, _ in enumerate(words):
            start_ms = line.start_ms + i * step_dur
            end_ms = line.end_ms if i == len(words) - 1 else line.start_ms + (i + 1) * step_dur
            text = " ".join(words[:i+1])
            events.append(f"Dialogue: 0,{ms_to_ass_time(start_ms)},{ms_to_ass_time(end_ms)},Default,,0,0,0,,{{\\fad(100,60)}}{text}")
    return "\n".join(events)

def generate_word_group_events(lines: List[SubtitleLine], group_size: int = 3) -> str:
    events = []
    FADE_IN_FIRST = 220
    FADE_IN_NEXT  = 130
    FADE_OUT      = 320
    APPEAR_RATIO  = 0.62

    for line in lines:
        words = line.text.split()
        if not words:
            continue
        duration = line.end_ms - line.start_ms
        if len(words) == 1:
            events.append(f"Dialogue: 0,{ms_to_ass_time(line.start_ms)},{ms_to_ass_time(line.end_ms)},Default,,0,0,0,,{{\\fad({FADE_IN_FIRST},{FADE_OUT})}}{line.text}")
            continue
        groups = [words[i:i+group_size] for i in range(0, len(words), group_size)]
        for g, group in enumerate(groups):
            is_last_group = g == len(groups) - 1
            group_start = line.start_ms + round((g / len(groups)) * duration)
            group_end = line.end_ms if is_last_group else line.start_ms + round(((g + 1) / len(groups)) * duration)
            group_dur = group_end - group_start
            appear_budget = round(group_dur * APPEAR_RATIO)
            word_slot = round(appear_budget / (len(group) - 1)) if len(group) > 1 else 0
            for w, _ in enumerate(group):
                is_last_in_group = w == len(group) - 1
                frame_start = group_start + w * word_slot
                frame_end = group_end if is_last_in_group else group_start + (w + 1) * word_slot
                display_text = " ".join(group[:w+1])
                fade_in = FADE_IN_FIRST if w == 0 else FADE_IN_NEXT
                fade_out = FADE_OUT if is_last_in_group else 0
                events.append(f"Dialogue: 0,{ms_to_ass_time(frame_start)},{ms_to_ass_time(frame_end)},Default,,0,0,0,,{{\\fad({fade_in},{fade_out})}}{display_text}")
    return "\n".join(events)

def generate_ass_content(lines: List[SubtitleLine], style: str, animation: str, position: str = "bottom", size: str = "medium") -> str:
    align = position_to_alignment(position)
    margin_v = position_to_margin_v(position)
    font_size = round(STYLE_BASE_SIZE[style] * SIZE_SCALE[size])
    style_def = ASS_STYLE_BASE[style](align, margin_v, font_size)

    header = "\n".join([
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1280",
        "PlayResY: 720",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{style_def}",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ])

    if animation == "typewriter":
        events = generate_typewriter_events(lines)
    elif animation == "word_group":
        events = generate_word_group_events(lines, 3)
    else:
        anim_tag = get_anim_tag(animation)
        events = "\n".join(
            f"Dialogue: 0,{ms_to_ass_time(l.start_ms)},{ms_to_ass_time(l.end_ms)},Default,,0,0,0,,{anim_tag}{l.text}"
            for l in lines
        )
    return header + "\n" + events + "\n"

def watermark_filter(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
    return f"drawtext=text='{escaped}':fontfile={FONT_FILE}:fontsize=30:fontcolor=white@0.65:x=(w-text_w)/2:y=h-50:box=1:boxcolor=black@0.35:boxborderw=6"

# ─── Processing functions ─────────────────────────────────────────────────────

async def get_video_duration(path: str) -> float:
    try:
        out = await run_cmd("ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path, timeout=30)
        return float(out.strip()) or 60.0
    except Exception:
        return 60.0

async def burn_subtitles_styled_ass(video_path: str, lines: List[SubtitleLine], style: str, animation: str, position: str = "bottom", watermark: Optional[str] = None, size: str = "medium") -> str:
    ass_content = generate_ass_content(lines, style, animation, position, size)
    ass_path = tmp_path(random_name("ass"))
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    output = tmp_path(random_name("mp4"))
    escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:")
    vf = f"ass={escaped_ass}:fontsdir={FONT_DIR}"
    if watermark:
        vf += f",{watermark_filter(watermark)}"
    try:
        await run_cmd(FFMPEG, "-y", "-i", video_path, "-vf", vf, "-c:v", "libx264", "-c:a", "copy", "-preset", "fast", output, timeout=600)
    finally:
        cleanup_file(ass_path)
    return output

async def generate_subtitle_preview_clip(video_path: str, lines: List[SubtitleLine], style: str, animation: str, position: str = "bottom", watermark: Optional[str] = None, size: str = "medium") -> str:
    ass_content = generate_ass_content(lines, style, animation, position, size)
    ass_path = tmp_path(random_name("ass"))
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    output = tmp_path(random_name("mp4"))
    escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:")
    vf = f"ass={escaped_ass}:fontsdir={FONT_DIR},scale=640:360"
    if watermark:
        vf += f",{watermark_filter(watermark)}"
    try:
        await run_cmd(FFMPEG, "-y", "-i", video_path, "-t", "5", "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", "-r", "15", output, timeout=120)
    finally:
        cleanup_file(ass_path)
    return output

async def cut_video(video_path: str, start: str, end: str) -> str:
    output = tmp_path(random_name("mp4"))
    await run_cmd(FFMPEG, "-y", "-ss", start, "-i", video_path, "-to", end, "-c:v", "libx264", "-c:a", "aac", "-avoid_negative_ts", "make_zero", "-preset", "fast", output, timeout=600)
    return output

async def merge_videos(video_paths: List[str]) -> str:
    list_file = tmp_path(random_name("txt"))
    output = tmp_path(random_name("mp4"))
    with open(list_file, "w") as f:
        f.write("\n".join(f"file '{p}'" for p in video_paths))
    try:
        await run_cmd(FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", output, timeout=600)
    finally:
        cleanup_file(list_file)
    return output

async def merge_videos_with_crossfade(video_paths: List[str], transition_duration: float = 0.5) -> str:
    if len(video_paths) < 2:
        return await merge_videos(video_paths)
    output = tmp_path(random_name("mp4"))
    durations = []
    for p in video_paths[:-1]:
        durations.append(await get_video_duration(p))
    inputs = []
    for p in video_paths:
        inputs += ["-i", p]
    v_filters = []
    a_filters = []
    cumulative_offset = 0.0
    for i in range(len(video_paths) - 1):
        in_v1 = "[0:v]" if i == 0 else f"[vx{i-1}]"
        in_a1 = "[0:a]" if i == 0 else f"[ax{i-1}]"
        in_v2 = f"[{i+1}:v]"
        in_a2 = f"[{i+1}:a]"
        is_last = i == len(video_paths) - 2
        out_v = "[vfinal]" if is_last else f"[vx{i}]"
        out_a = "[afinal]" if is_last else f"[ax{i}]"
        cumulative_offset += durations[i] - transition_duration
        v_filters.append(f"{in_v1}{in_v2}xfade=transition=fade:duration={transition_duration}:offset={cumulative_offset:.3f}{out_v}")
        a_filters.append(f"{in_a1}{in_a2}acrossfade=d={transition_duration}{out_a}")
    filter_complex = ";".join(v_filters + a_filters)
    await run_cmd(FFMPEG, "-y", *inputs, "-filter_complex", filter_complex, "-map", "[vfinal]", "-map", "[afinal]", "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", output, timeout=600)
    return output

async def add_music_to_video(video_path: str, audio_path: str) -> str:
    output = tmp_path(random_name("mp4"))
    await run_cmd(FFMPEG, "-y", "-i", video_path, "-i", audio_path, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", output, timeout=600)
    return output

async def loop_video_to_fit_audio(video_path: str, audio_path: str) -> str:
    output = tmp_path(random_name("mp4"))
    await run_cmd(FFMPEG, "-y", "-stream_loop", "-1", "-i", video_path, "-i", audio_path, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-c:a", "aac", "-shortest", "-avoid_negative_ts", "make_zero", "-preset", "fast", output, timeout=600)
    return output

async def add_text_to_video(video_path: str, text: str, position: str) -> str:
    output = tmp_path(random_name("mp4"))
    y = "50" if position == "top" else "(h-text_h)/2" if position == "center" else "h-80"
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    vf = f"drawtext=text='{escaped}':fontfile={FONT_FILE}:fontsize=40:fontcolor=white:bordercolor=black:borderw=2:x=(w-text_w)/2:y={y}"
    await run_cmd(FFMPEG, "-y", "-i", video_path, "-vf", vf, "-c:v", "libx264", "-c:a", "copy", "-preset", "fast", output, timeout=600)
    return output

async def mute_video(video_path: str) -> str:
    output = tmp_path(random_name("mp4"))
    await run_cmd(FFMPEG, "-y", "-i", video_path, "-c:v", "copy", "-an", output, timeout=600)
    return output

async def extract_audio(video_path: str) -> str:
    output = tmp_path(random_name("mp3"))
    await run_cmd(FFMPEG, "-y", "-i", video_path, "-vn", "-c:a", "libmp3lame", "-q:a", "2", output, timeout=600)
    return output

async def photo_to_video(photo_path: str, audio_path: str) -> str:
    output = tmp_path(random_name("mp4"))
    await run_cmd(FFMPEG, "-y", "-loop", "1", "-i", photo_path, "-i", audio_path, "-c:v", "libx264", "-c:a", "aac", "-shortest", "-pix_fmt", "yuv420p", "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2", output, timeout=600)
    return output

async def auto_subtitles_generate(video_path: str, language: str, words_per_line: int):
    audio_path = tmp_path(random_name("wav"))
    srt_path = tmp_path(random_name("srt"))
    await run_cmd(FFMPEG, "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", audio_path, timeout=300)
    whisper_cmd = [WHISPER, audio_path, "--model", "small", "--output_format", "srt", "--output_dir", TMP_DIR]
    if language != "auto":
        whisper_cmd += ["--language", language]
    await run_cmd(*whisper_cmd, timeout=600)
    base = os.path.splitext(os.path.basename(audio_path))[0]
    generated_srt = os.path.join(TMP_DIR, f"{base}.srt")
    with open(generated_srt, "r", encoding="utf-8") as f:
        srt_content = f.read()
    cleanup_file(audio_path)
    cleanup_file(generated_srt)
    parsed = parse_srt(srt_content)
    srt_lines = split_srt_to_words(parsed, words_per_line)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(lines_to_srt(srt_lines))
    return srt_lines, srt_path

# ─── Video effects ────────────────────────────────────────────────────────────

ZM15 = "t*(t<15)+15*(1-(t<15))"
ZM25 = "t*(t<25)+25*(1-(t<25))"
ZO15 = "(15-t)*(t<15)"
PANR = "trunc(t*8*(t<16)+128*(1-(t<16)))"
PANL = "trunc((128-t*8)*(t<16))"

EFFECT_FILTERS = {
    "rain":        "colorchannelmixer=bb=1.4:gb=0.9:rb=0.8,eq=brightness=-0.05:saturation=0.8,noise=alls=8:allf=t+u",
    "zoom_in":     f"scale=1280:720,scale=trunc((1280+25*({ZM15}))/2)*2:trunc((720+14*({ZM15}))/2)*2:eval=frame,crop=1280:720:(iw-1280)/2:(ih-720)/2",
    "zoom_out":    f"scale=1280:720,scale=trunc((1280+25*({ZO15}))/2)*2:trunc((720+14*({ZO15}))/2)*2:eval=frame,crop=1280:720:(iw-1280)/2:(ih-720)/2",
    "smooth_zoom": f"scale=1280:720,scale=trunc((1280+15*({ZM25}))/2)*2:trunc((720+9*({ZM25}))/2)*2:eval=frame,crop=1280:720:(iw-1280)/2:(ih-720)/2",
    "pan_right":   f"scale=1408:792,crop=1280:720:{PANR}:36",
    "pan_left":    f"scale=1408:792,crop=1280:720:{PANL}:36",
    "cinema":      "drawbox=x=0:y=0:w=iw:h=ih*0.09:color=black:t=fill,drawbox=x=0:y=ih*0.91:w=iw:h=ih*0.09:color=black:t=fill,eq=contrast=1.1:saturation=0.85",
    "vignette":    "vignette=0.785",
    "warm":        "colorchannelmixer=rr=1.15:gg=0.95:bb=0.75,eq=saturation=1.1:brightness=0.02",
    "bw":          "hue=s=0",
    "vivid":       "eq=saturation=1.8:contrast=1.1:brightness=0.03",
    "living":      "scale=1280:720,scale=1320:760,crop=1280:720:20+15*sin(2*PI*t/12):20+10*sin(2*PI*t/15)",
    "glitch":      "noise=alls=15:allf=t+u,colorchannelmixer=rr=1.1:gg=0.95:bb=0.9,hue=h=6*sin(2*PI*t*1.5)",
    "old_film":    "colorchannelmixer=rr=1.2:gg=0.95:bb=0.7,curves=all='0/0 0.5/0.45 1/0.88',noise=alls=12:allf=t+u,vignette=1.047",
    "dream":       "boxblur=3:2,eq=saturation=1.6:brightness=0.07,vignette=0.628",
    "enhance_auto":"hqdn3d=2:1:3:2.5,unsharp=5:5:1.0:5:5:0.0,eq=saturation=1.08:contrast=1.05",
    "enhance_hd":  "scale=1280:-2:flags=lanczos,unsharp=5:5:1.0:5:5:0.0",
    "enhance_fhd": "scale=1920:-2:flags=lanczos,unsharp=5:5:1.2:5:5:0.0",
}

BEAT_DETECT_PY = """
import sys, json, subprocess, math
vp = sys.argv[1]
try:
    r = subprocess.run(['ffprobe','-v','quiet','-f','lavfi',
        '-i',f'amovie={vp},astats=metadata=1:reset=1',
        '-show_frames','-show_entries',
        'frame=best_effort_timestamp_time:frame_tags=lavfi.astats.Overall.RMS_level',
        '-of','json'],capture_output=True,text=True,timeout=90)
    data=json.loads(r.stdout)
except Exception:
    print(json.dumps([]));sys.exit(0)
times,levels=[],[]
for f in data.get('frames',[]):
    t=f.get('best_effort_timestamp_time')
    rms=f.get('tags',{}).get('lavfi.astats.Overall.RMS_level','')
    if t and rms and rms not in('-inf','nan','','inf'):
        try:times.append(float(t));levels.append(float(rms))
        except:pass
if len(levels)<20:print(json.dumps([]));sys.exit(0)
lin=[10**(l/20) for l in levels]
avg=sum(lin)/len(lin)
std=math.sqrt(sum((x-avg)**2 for x in lin)/len(lin))
thr=avg+1.2*std
beats,last=[],- 99
for i in range(2,len(lin)-2):
    if lin[i]>=lin[i-1] and lin[i]>lin[i+1] and lin[i]>thr and times[i]-last>0.2:
        beats.append(round(times[i],3));last=times[i]
print(json.dumps(beats[:50]))
"""

async def detect_beats(video_path: str) -> list:
    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", "-c", BEAT_DETECT_PY, video_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        beats = json.loads(stdout.decode().strip())
        return beats if isinstance(beats, list) else []
    except Exception:
        return []

async def apply_beat_sync_effect(video_path: str, watermark: Optional[str] = None) -> str:
    output = tmp_path(random_name("mp4"))
    beats = await detect_beats(video_path)
    if len(beats) < 3:
        dur = await get_video_duration(video_path)
        beats = [round(t * 1000) / 1000 for t in [i * 0.5 + 0.25 for i in range(int(dur * 2))]]
    selected = beats[:45]
    pulse_expr = "+".join(f"0.14*exp(-60*(t-{t})^2)" for t in selected)
    filt = f"eq=brightness='min({pulse_expr},0.2)'"
    if watermark:
        filt += f",{watermark_filter(watermark)}"
    await run_cmd(FFMPEG, "-y", "-i", video_path, "-vf", filt, "-c:v", "libx264", "-c:a", "copy", "-preset", "fast", output, timeout=600)
    return output

async def preview_beat_sync_effect(video_path: str) -> str:
    output = tmp_path(random_name("mp4"))
    beats = await detect_beats(video_path)
    if len(beats) < 3:
        beats = [round((i * 0.5 + 0.25) * 1000) / 1000 for i in range(20)]
    selected = [t for t in beats if t < 7][:20]
    pulse_expr = "+".join(f"0.14*exp(-60*(t-{t})^2)" for t in selected)
    filt = f"eq=brightness='min({pulse_expr},0.2)'"
    await run_cmd(FFMPEG, "-y", "-i", video_path, "-t", "5", "-vf", f"{filt},scale=640:360", "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", "-r", "15", output, timeout=120)
    return output

async def apply_video_effect(video_path: str, effect: str, watermark: Optional[str] = None) -> str:
    if effect == "beat_sync":
        return await apply_beat_sync_effect(video_path, watermark)
    output = tmp_path(random_name("mp4"))
    if effect == "speed_up":
        vf = "setpts=0.5*PTS"
        if watermark:
            vf += f",{watermark_filter(watermark)}"
        await run_cmd(FFMPEG, "-y", "-i", video_path, "-vf", vf, "-af", "atempo=2.0", "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", output, timeout=600)
        return output
    if effect == "slow_down":
        vf = "setpts=2.0*PTS"
        if watermark:
            vf += f",{watermark_filter(watermark)}"
        await run_cmd(FFMPEG, "-y", "-i", video_path, "-vf", vf, "-af", "atempo=0.5", "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", output, timeout=600)
        return output
    base_filter = EFFECT_FILTERS.get(effect)
    if not base_filter:
        raise ValueError(f"Unknown effect: {effect}")
    vf = base_filter
    if watermark:
        vf += f",{watermark_filter(watermark)}"
    await run_cmd(FFMPEG, "-y", "-i", video_path, "-vf", vf, "-c:v", "libx264", "-c:a", "copy", "-preset", "fast", output, timeout=600)
    return output

async def generate_montage_preview_clip(video_path: str, effect: str) -> str:
    if effect == "beat_sync":
        return await preview_beat_sync_effect(video_path)
    output = tmp_path(random_name("mp4"))
    if effect == "speed_up":
        await run_cmd(FFMPEG, "-y", "-i", video_path, "-t", "10", "-vf", "setpts=0.5*PTS,scale=640:360", "-af", "atempo=2.0", "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", "-r", "15", output, timeout=120)
        return output
    if effect == "slow_down":
        await run_cmd(FFMPEG, "-y", "-i", video_path, "-t", "3", "-vf", "setpts=2.0*PTS,scale=640:360", "-af", "atempo=0.5", "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", "-r", "15", output, timeout=120)
        return output
    base_filter = EFFECT_FILTERS.get(effect)
    if not base_filter:
        raise ValueError(f"Unknown effect: {effect}")
    await run_cmd(FFMPEG, "-y", "-i", video_path, "-t", "5", "-vf", f"{base_filter},scale=640:360", "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", "-r", "15", output, timeout=120)
    return output
