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

import time
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth

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
BRIGHTNESS = 70           # 0~100. 인테리어용이라 100은 대체로 너무 밝음
HARDWARE_MAPPING = "adafruit-hat"   # Bonnet 사용. 점퍼 직결이면 "regular"

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
        _matrix = RGBMatrix(options=options)
    return _matrix


def show_on_matrix(track_info: dict):
    """
    앨범아트를 64x64로 변환해서 표시한다.

    라즈베리파이에서는 LED 매트릭스로, 그 외(맥북 등)에서는 PNG 파일로 나간다.
    rgbmatrix 설치 여부로 자동 판별하므로 기기에 따라 코드를 고칠 필요가 없다.
    """
    if track_info["album_art_url"] is None:
        print("앨범아트가 없는 곡입니다. 건너뜁니다.")
        return

    img = get_matrix_image(track_info["album_art_url"], matrix_size=MATRIX_SIZE)

    if RGBMatrix is None:
        # 매트릭스가 없는 환경 — 파일로 저장해서 눈으로 확인
        img.save(BASE_DIR / "now_playing_64x64.png")
        save_preview(img, BASE_DIR / "now_playing_preview.png", scale=6)
        where = "PNG 저장"
    else:
        get_matrix().SetImage(img.convert("RGB"))
        where = "LED"

    print(f"[표시 완료/{where}] {track_info['title']} - {track_info['artist']}")


def main():
    sp = get_spotify_client()
    last_id = None

    print(f"[시작] 최대 {POLL_SECONDS}초 간격으로 확인합니다. (Ctrl+C로 종료)")

    while True:
        try:
            info = get_now_playing(sp)

            if info is None:
                if last_id is not None:
                    print("재생 중인 곡 없음")
                last_id = None

            elif info["id"] != last_id:
                print("─" * 40)
                print(f"곡명   : {info['title']}")
                print(f"아티스트: {info['artist']}")
                show_on_matrix(info)
                last_id = info["id"]

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
