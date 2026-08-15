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
from PIL import Image, ImageEnhance, ImageFilter

# LED 매트릭스는 64x64로 축소되며 디테일이 뭉개지고, 소프트웨어 PWM(adafruit-hat) 모드라
# 실물로 보면 색이 옅게 느껴진다. 리사이즈 후 선명화 + 채도/대비를 살짝 올려서 보정한다.
# ponytail: 여기서 더 올리면 선명해지기보다 테두리에 노이즈성 윤곽(할로)이 생기기 시작하는
# 지점에 가까워짐 — 64x64/3mm 피치라는 물리적 해상도 한계 자체는 소프트웨어로 못 넘음.
# 이 이상 또렷하게 하려면 GPIO4-18 하드웨어 점퍼(색 표현 비트수 개선)가 더 유효함
SHARPEN_RADIUS = 1.5   # 픽셀이 작을수록(64x64) 큰 반경은 오히려 뭉개지니 1~2 권장
SHARPEN_PERCENT = 350  # UnsharpMask 강도. 100=약함, 250=강함, 350=매우 강함(한계 근처)
SATURATION = 1.3    # 1.0 = 원본. 실물 보면서 1.2~1.5 사이로 조정할 것
CONTRAST = 1.25      # 1.0 = 원본


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


def process_for_matrix(img: Image.Image, matrix_size: int = 64) -> Image.Image:
    """이미 로드된 이미지를 LED 매트릭스용 정사각 이미지로 변환. get_matrix_image/show_image.py가 공유."""
    img = crop_to_square(img)
    img = img.resize((matrix_size, matrix_size), Image.LANCZOS)
    img = img.filter(ImageFilter.UnsharpMask(radius=SHARPEN_RADIUS, percent=SHARPEN_PERCENT, threshold=2))
    img = ImageEnhance.Color(img).enhance(SATURATION)
    img = ImageEnhance.Contrast(img).enhance(CONTRAST)
    return img


def get_matrix_image(url: str, matrix_size: int = 64) -> Image.Image:
    """
    앨범아트 URL을 받아서 LED 매트릭스에 바로 쏠 수 있는
    64x64(기본값) 정사각 이미지로 변환해 반환.
    """
    return process_for_matrix(download_image(url), matrix_size)


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
