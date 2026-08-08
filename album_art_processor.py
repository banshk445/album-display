"""
album_art_processor.py
-----------------------
Spotify 앨범아트 URL을 받아서 LED 매트릭스(64x64)에 바로 쏠 수 있는
형태로 변환하는 모듈.

[하는 일]
1. 앨범아트 이미지를 인터넷에서 다운로드
2. 정사각형으로 크롭 (혹시 정사각형이 아닌 경우 대비)
3. 64x64로 리사이즈
4. (선택) 확인용으로 크게 확대한 미리보기 이미지도 같이 저장

[나중에 실제 LED 매트릭스에 연결할 때]
- get_matrix_image() 가 반환하는 PIL Image 객체를
  rpi-rgb-led-matrix 라이브러리의 SetImage() 함수에 그대로 넘기면 됩니다.
  (지금은 매트릭스가 없는 맥북에서도 테스트할 수 있도록
   파일로 저장하는 것까지만 구현)
"""

import io
import requests
from PIL import Image


def download_image(url: str) -> Image.Image:
    """URL에서 이미지를 다운로드해 PIL Image로 반환."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content)).convert("RGB")


def crop_to_square(img: Image.Image) -> Image.Image:
    """이미지를 정중앙 기준 정사각형으로 크롭."""
    w, h = img.size
    size = min(w, h)
    left = (w - size) // 2
    top = (h - size) // 2
    return img.crop((left, top, left + size, top + size))


def get_matrix_image(url: str, matrix_size: int = 64) -> Image.Image:
    """
    앨범아트 URL을 받아서 LED 매트릭스에 바로 쏠 수 있는
    64x64(기본값) 정사각 이미지로 변환해 반환.
    """
    img = download_image(url)
    img = crop_to_square(img)
    img = img.resize((matrix_size, matrix_size), Image.LANCZOS)
    return img


def save_preview(img: Image.Image, path: str, scale: int = 6):
    """
    64x64 이미지를 그대로 저장하면 너무 작아서 확인하기 어려우므로,
    NEAREST 방식으로 확대한 미리보기 파일을 따로 저장.
    (실제 LED 느낌과 비슷하게 픽셀이 뭉개지지 않고 또렷하게 보임)
    """
    w, h = img.size
    preview = img.resize((w * scale, h * scale), Image.NEAREST)
    preview.save(path)


if __name__ == "__main__":
    # ── 테스트: spotify_now_playing.py 에서 받은 앨범아트 URL을 여기 붙여넣고 실행 ──
    test_url = "https://i.scdn.co/image/ab67616d0000b2736b458d1409d938dad4e3ba2c"

    print("[1/3] 이미지 다운로드 중...")
    matrix_img = get_matrix_image(test_url, matrix_size=64)

    print("[2/3] 원본 크기 이미지 저장 중... (64x64_raw.png)")
    matrix_img.save("64x64_raw.png")

    print("[3/3] 확인용 확대 이미지 저장 중... (64x64_preview.png)")
    save_preview(matrix_img, "64x64_preview.png", scale=6)

    print("완료! 64x64_preview.png 파일을 열어서 확인해보세요.")
