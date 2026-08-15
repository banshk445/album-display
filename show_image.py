"""
show_image.py
-----------------------
로컬 사진 파일을 받아서 LED 매트릭스용 64x64로 처리한 뒤 override.png로 저장한다.
album_display_main.py의 main() 루프가 이 파일을 감지해서 일회성으로 화면에 띄운다
(OVERRIDE_DISPLAY_SECONDS 동안 보여준 뒤 자동으로 원래 화면으로 복귀).

맥 메뉴바 앱의 "이미지 업로드" 기능이 scp로 사진을 올린 뒤 이 스크립트를 호출한다.

사용법: python3 show_image.py <사진 경로>
"""

import sys
from pathlib import Path

from PIL import Image

from album_art_processor import process_for_matrix

BASE_DIR = Path(__file__).resolve().parent
OVERRIDE_PATH = BASE_DIR / "override.png"


def main():
    if len(sys.argv) != 2:
        print("사용법: python3 show_image.py <사진 경로>", file=sys.stderr)
        sys.exit(1)

    src = Path(sys.argv[1])
    img = Image.open(src).convert("RGB")
    processed = process_for_matrix(img, matrix_size=64)
    processed.save(OVERRIDE_PATH)
    print(f"{OVERRIDE_PATH}에 저장 완료 — 다음 루프에서 화면에 뜸")


if __name__ == "__main__":
    main()
