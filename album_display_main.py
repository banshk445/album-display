"""
album_display_main.py
-----------------------
spotify_now_playing.py + album_art_processor.py 를 하나로 합친 통합 버전.

곡이 바뀔 때마다 자동으로:
1. Spotify에서 현재 곡 정보 확인
2. 앨범아트를 64x64로 변환
3. 표시 — 라즈베리파이(rgbmatrix 설치됨)에서는 LED 매트릭스로,
   그 외 환경에서는 PNG 파일로. 자동 판별하므로 기기별로 코드를 고칠 필요 없음

[준비물]
1. pip install spotipy pillow requests
2. Spotify 앱 정보를 환경변수로 설정 (코드에 직접 적지 말 것)

   export SPOTIPY_CLIENT_ID=...
   export SPOTIPY_CLIENT_SECRET=...
   export SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback

   spotipy가 이 세 개를 자동으로 읽는다.
   주의: sudo는 기본적으로 환경변수를 지우므로 RPi에서 매트릭스를 켤 땐
   `sudo -E` 를 쓰거나 systemd 유닛에 Environment= 로 명시할 것.
"""

import json
import random
import socket
import time
from pathlib import Path

import spotipy
from PIL import Image, ImageDraw, ImageFont
from spotipy.oauth2 import SpotifyOAuth

# 네트워크가 잠깐 끊긴 순간에 재시작되면 스포티파이 인증이 새로 필요하다고 판단해서
# 헤드리스 서버에서는 절대 안 열리는 브라우저 콜백을 무한 대기하는 경우가 있었다
# (한 번 빠지면 재시작 전까지 영원히 멈춤). 소켓에 타임아웃을 걸어 예외로 바꿔서
# main()의 재시도 루프가 자동으로 복구하게 한다.
socket.setdefaulttimeout(10)

# sudo / systemd로 실행하면 작업 디렉터리가 달라지므로 항상 이 파일 기준 절대경로를 쓴다
BASE_DIR = Path(__file__).resolve().parent

from album_art_processor import get_matrix_image, save_preview

# Client ID/Secret/Redirect URI는 환경변수(SPOTIPY_*)에서 읽는다. 위 [준비물] 참고.
SCOPE = "user-read-currently-playing user-read-playback-state"

POLL_SECONDS = 2          # 평소 확인 간격 (스킵/일시정지 감지용)
MIN_SLEEP = 0.5           # 곡 끝 예측이 빗나갔을 때 재확인 최소 간격
END_MARGIN = 0.3          # 다음 곡이 Spotify에 반영될 여유 시간(초)
MATRIX_SIZE = 64          # LED 매트릭스 크기 (64x64)

# ── 매트릭스 튜닝 값 (실물 보면서 맞춰야 하는 것들) ────────────────────
GPIO_SLOWDOWN = 4         # Pi 4는 보통 2~4. 픽셀이 깨지거나 색이 튀면 올릴 것
BRIGHTNESS = 45           # 0~100. 인테리어용이라 100은 대체로 너무 밝음.
                          # 너무 낮추면(30 이하) 소프트웨어 PWM 특성상 깜빡임이 오히려 심해짐(하드웨어 PWM엔 해당 없음)
HARDWARE_MAPPING = "adafruit-hat-pwm"   # GPIO4-18 점퍼 납땜 완료(2026-08-11) — 하드웨어 PWM으로 전환

# 대기 화면(재생 중인 곡 없음)에 쓰는 폰트. 라즈베리파이 OS에 기본 포함된 DejaVu.
# 없는 환경(맥북 등)에서는 PIL 기본 비트맵 폰트로 자동 대체된다.
CLOCK_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DIGITAL_FONT_SIZE = 8      # 우상단 구석에 작게 들어가야 해서 작게

CLAUDE_ORANGE = (217, 119, 87)     # Claude 브랜드 색 — 시계·사용량 전부 이 색으로 통일
CLAUDE_USAGE_PATH = BASE_DIR / "claude_usage.json"   # fetch_claude_usage.py(맥)가 scp로 채워둠

MASCOT_PATH = BASE_DIR / "clawd_mascot.png"   # 16x10 픽셀아트, 미리 다운샘플해둔 자산
MASCOT_POS = (11, 12)      # 원래 (1,1)에서 오른쪽·아래로 살짝 이동
MASCOT_CHECK_INTERVAL = 10   # 초 — 이 주기마다 마스코트가 움직일지 확률을 굴림(분 갱신과 무관)
MASCOT_ACTION_CHANCE = 0.4   # 굴릴 때마다 이 확률로 실제 애니메이션 재생 (평균 약 25초에 한 번꼴)

# 맥 메뉴바 앱 등에서 "지금 이 사진 띄워줘"용 일회성 오버레이.
# show_image.py가 이 경로에 64x64로 미리 처리해서 떨궈두면 main() 루프가 감지해서 보여준다.
OVERRIDE_IMAGE_PATH = BASE_DIR / "override.png"
OVERRIDE_DISPLAY_SECONDS = 10

# rgbmatrix는 라즈베리파이에만 설치된다. 맥북에서는 import가 실패하는 게 정상이고,
# 그때는 매트릭스 대신 PNG로 저장해서 눈으로 확인한다.
try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
except ImportError:
    RGBMatrix = RGBMatrixOptions = None

_matrix = None            # 첫 출력 때 한 번만 초기화한다


def get_spotify_client() -> spotipy.Spotify:
    auth_manager = SpotifyOAuth(
        scope=SCOPE,
        cache_path=str(BASE_DIR / ".spotify_token_cache"),
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def get_now_playing(sp: spotipy.Spotify) -> dict | None:
    current = sp.current_playback()
    if current is None or current.get("item") is None:
        return None

    item = current["item"]
    images = item["album"]["images"]

    progress = current.get("progress_ms")
    duration = item.get("duration_ms")

    return {
        "id": item["id"],
        "title": item["name"],
        "artist": ", ".join(a["name"] for a in item["artists"]),
        "album": item["album"]["name"],
        "album_art_url": images[0]["url"] if images else None,
        "is_playing": current["is_playing"],
        # 곡이 끝나기까지 남은 시간 (모르면 None)
        "remaining_ms": None if progress is None or duration is None else duration - progress,
    }


def next_sleep(info: dict | None) -> float:
    """
    다음 확인까지 잠들 시간.
    재생 중이면 '곡이 끝나는 순간'을 이미 알고 있으므로 그때 딱 깨어난다.
    (API를 더 부르지 않고 반응 속도만 올리는 방법)
    """
    if info is None or not info["is_playing"] or info["remaining_ms"] is None:
        return POLL_SECONDS
    return max(MIN_SLEEP, min(POLL_SECONDS, info["remaining_ms"] / 1000 + END_MARGIN))


def get_matrix():
    """매트릭스를 처음 쓸 때 한 번만 초기화한다. (초기화가 GPIO를 잡으므로 재사용)"""
    global _matrix
    if _matrix is None:
        options = RGBMatrixOptions()
        options.rows = MATRIX_SIZE
        options.cols = MATRIX_SIZE
        options.chain_length = 1
        options.parallel = 1
        options.hardware_mapping = HARDWARE_MAPPING
        options.gpio_slowdown = GPIO_SLOWDOWN
        options.brightness = BRIGHTNESS
        # 라이브러리 기본값은 GPIO 초기화 후 root -> daemon으로 권한을 자동으로 낮춘다.
        # 그러면 이후 폴링에서 root 권한으로만 읽을 수 있는 .spotify_token_cache를
        # 못 읽게 되어 매 곡 전환 시도가 조용히 실패한다. root로 계속 실행해야 하므로 끈다.
        options.drop_privileges = False
        _matrix = RGBMatrix(options=options)
    return _matrix


def _display_image(img: Image.Image, label: str):
    """
    이미지를 매트릭스(또는 PNG)로 출력한다. show_on_matrix/show_idle_screen이 공유.

    라즈베리파이에서는 LED 매트릭스로, 그 외(맥북 등)에서는 PNG 파일로 나간다.
    rgbmatrix 설치 여부로 자동 판별하므로 기기에 따라 코드를 고칠 필요가 없다.
    """
    if RGBMatrix is None:
        # 매트릭스가 없는 환경 — 파일로 저장해서 눈으로 확인
        img.save(BASE_DIR / "now_playing_64x64.png")
        save_preview(img, BASE_DIR / "now_playing_preview.png", scale=6)
        where = "PNG 저장"
    else:
        get_matrix().SetImage(img.convert("RGB"))
        where = "LED"

    print(f"[표시 완료/{where}] {label}")


def show_on_matrix(track_info: dict):
    """앨범아트를 64x64로 변환해서 표시한다."""
    if track_info["album_art_url"] is None:
        print("앨범아트가 없는 곡입니다. 건너뜁니다.")
        return

    img = get_matrix_image(track_info["album_art_url"], matrix_size=MATRIX_SIZE)
    _display_image(img, f"{track_info['title']} - {track_info['artist']}")


def _mascot_image(x_offset: int = 0, y_offset: int = 0, angle: int = 0) -> tuple[Image.Image, int, int]:
    """마스코트 원본을 주어진 자세(이동/회전)로 그려서 (이미지, x, y) 반환."""
    mascot = Image.open(MASCOT_PATH).convert("RGB")
    if angle:
        mascot = mascot.rotate(angle, resample=Image.NEAREST, fillcolor=(0, 0, 0))
    return mascot, x_offset, y_offset


# 각 값은 (x_offset, y_offset, 회전각) — 순서대로 재생하면 실제로 움직이는 것처럼 보인다.
# 마지막 프레임은 항상 (0,0,0)으로 돌아와 다음 대기 화면과 자연스럽게 이어진다.
MASCOT_ANIMATIONS = {
    "hop": [(0, 2, 0), (0, -2, 0), (0, -6, 0), (0, -2, 0), (0, 1, 0), (0, 0, 0)],
    "wiggle": [(-3, 0, 0), (3, 0, 0), (-3, 0, 0), (3, 0, 0), (-1, 0, 0), (0, 0, 0)],
    "look": [(0, 0, 10), (0, 0, 16), (0, 0, 10), (0, 0, -10), (0, 0, -16), (0, 0, -10), (0, 0, 0)],
}
MASCOT_FRAME_DELAY = 0.12   # 초 — 너무 짧으면 매트릭스가 못 따라오고 너무 길면 굼떠 보임


def _draw_ring(draw: ImageDraw.ImageDraw, center: tuple, radius: int, pct: int, font):
    cx, cy = center
    bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.ellipse(bbox, outline=(60, 60, 60), width=3)

    if pct > 0:
        draw.arc(bbox, start=-90, end=-90 + 360 * min(pct, 100) / 100, fill=CLAUDE_ORANGE, width=3)

    pct_text = f"{pct}%"
    left, top, right, bottom = draw.textbbox((0, 0), pct_text, font=font)
    w, h = right - left, bottom - top
    draw.text((cx - w / 2 - left, cy - h / 2 - top), pct_text, fill=CLAUDE_ORANGE, font=font)


def render_idle_screen(matrix_size: int = MATRIX_SIZE, mascot_pose: tuple = (0, 0, 0)) -> Image.Image:
    """
    대기 화면(재생 중인 곡 없음), 한 화면에 전부: 우상단 디지털 시간 + 마스코트 +
    Claude Code 사용량(세션 5h % / 주간 %) 도넛 게이지 2개.
    claude_usage.json은 맥에서 fetch_claude_usage.py가 주기적으로 scp해 채운다.
    mascot_pose=(x_offset, y_offset, 회전각) — show_idle_screen()이 애니메이션 프레임마다 넘겨준다.
    """
    img = Image.new("RGB", (matrix_size, matrix_size), "black")
    draw = ImageDraw.Draw(img)

    try:
        time_font = ImageFont.truetype(CLOCK_FONT_PATH, DIGITAL_FONT_SIZE)
    except OSError:
        time_font = ImageFont.load_default()
    text = time.strftime("%H:%M")
    left, top, right, bottom = draw.textbbox((0, 0), text, font=time_font)
    w = right - left
    draw.text((matrix_size - w - 2 - left, 5 - top), text, fill=CLAUDE_ORANGE, font=time_font)

    try:
        mascot, x_offset, y_offset = _mascot_image(*mascot_pose)
        img.paste(mascot, (MASCOT_POS[0] + x_offset, MASCOT_POS[1] + y_offset))
    except OSError:
        pass

    try:
        with open(CLAUDE_USAGE_PATH) as f:
            usage = json.load(f)
    except (OSError, json.JSONDecodeError):
        return img

    try:
        pct_font = ImageFont.truetype(CLOCK_FONT_PATH, 7)     # "100%"가 링(반경13) 안에 들어가는 최대 크기
    except OSError:
        pct_font = ImageFont.load_default()

    _draw_ring(draw, center=(17, 37), radius=13, pct=usage["session"]["pct"], font=pct_font)
    _draw_ring(draw, center=(47, 37), radius=13, pct=usage["week"]["pct"], font=pct_font)

    return img


def show_idle_screen():
    """대기 화면(재생 중인 곡 없음)을 그대로(마스코트 정지 자세) 표시한다."""
    _display_image(render_idle_screen(), f"대기 화면 {time.strftime('%H:%M')}")


def maybe_animate_mascot():
    """
    분/시간 갱신과 무관하게, 대기 중일 때 주기적으로 호출되어 확률적으로(MASCOT_ACTION_CHANCE)
    마스코트가 여러 프레임에 걸쳐 실제로 움직이는 짧은 동작을 한다. 확률에 안 걸리면 아무것도 안 함
    (화면을 다시 그리지 않음 — 불필요한 매트릭스 갱신을 피한다).
    """
    if random.random() >= MASCOT_ACTION_CHANCE:
        return

    label = f"대기 화면 {time.strftime('%H:%M')}"
    action = random.choice(list(MASCOT_ANIMATIONS))
    frames = MASCOT_ANIMATIONS[action]
    for i, pose in enumerate(frames):
        _display_image(render_idle_screen(mascot_pose=pose), f"{label} (마스코트 {action} {i + 1}/{len(frames)})")
        if i < len(frames) - 1:
            time.sleep(MASCOT_FRAME_DELAY)


def main():
    sp = get_spotify_client()
    last_id = None
    last_idle_minute = None   # 대기 화면을 마지막으로 그린 "HH:MM" — 분이 바뀔 때만 다시 그린다
    last_mascot_check = 0.0   # 분 갱신과 무관하게 주기적으로 마스코트 움직임 여부를 굴림

    print(f"[시작] 최대 {POLL_SECONDS}초 간격으로 확인합니다. (Ctrl+C로 종료)")

    while True:
        try:
            if OVERRIDE_IMAGE_PATH.exists():
                try:
                    img = Image.open(OVERRIDE_IMAGE_PATH).convert("RGB")
                    _display_image(img, "수동 오버레이 사진")
                    time.sleep(OVERRIDE_DISPLAY_SECONDS)
                finally:
                    OVERRIDE_IMAGE_PATH.unlink(missing_ok=True)
                last_idle_minute = None   # 오버레이 끝나면 원래 화면을 강제로 다시 그리게
                continue

            info = get_now_playing(sp)
            is_idle = info is None or not info["is_playing"]   # 완전히 없음 + 일시정지 둘 다 대기 화면

            if is_idle:
                if last_id is not None:
                    print("재생 중인 곡 없음/일시정지")
                last_id = None

                now_str = time.strftime("%H:%M")
                if now_str != last_idle_minute:
                    show_idle_screen()
                    last_idle_minute = now_str

                if time.monotonic() - last_mascot_check >= MASCOT_CHECK_INTERVAL:
                    last_mascot_check = time.monotonic()
                    maybe_animate_mascot()

            elif info["id"] != last_id:
                print("─" * 40)
                print(f"곡명   : {info['title']}")
                print(f"아티스트: {info['artist']}")
                show_on_matrix(info)
                last_id = info["id"]
                last_idle_minute = None   # 다음에 다시 대기 상태가 되면 화면을 새로 그리게
                last_mascot_check = 0.0

            time.sleep(next_sleep(info))

        except KeyboardInterrupt:
            print("\n[종료]")
            break
        except Exception as e:
            print(f"[에러] {e} — {POLL_SECONDS}초 후 재시도")
            time.sleep(POLL_SECONDS)


def _selfcheck():
    """next_sleep() 계산 확인: python album_display_main.py --check"""
    def info(remaining_ms, is_playing=True):
        return {"is_playing": is_playing, "remaining_ms": remaining_ms}

    assert next_sleep(None) == POLL_SECONDS                      # 재생 없음
    assert next_sleep(info(180_000)) == POLL_SECONDS             # 곡 중간 → 평소 간격
    assert next_sleep(info(500, is_playing=False)) == POLL_SECONDS  # 일시정지 → 카운트다운 무의미
    assert next_sleep(info(None)) == POLL_SECONDS                # 정보 없음
    assert next_sleep(info(700)) == 0.7 + END_MARGIN             # 곡 끝 직전 → 끝나는 순간 기상
    assert next_sleep(info(-5_000)) == MIN_SLEEP                 # 예측 빗나감 → 과속 방지

    mode = "PNG 저장 (rgbmatrix 없음)" if RGBMatrix is None else \
           f"LED 매트릭스 ({HARDWARE_MAPPING}, slowdown={GPIO_SLOWDOWN}, 밝기={BRIGHTNESS})"
    print(f"출력 모드: {mode}")
    print("OK")


if __name__ == "__main__":
    import sys

    _selfcheck() if "--check" in sys.argv else main()
