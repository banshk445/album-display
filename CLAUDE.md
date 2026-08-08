# CLAUDE.md — 앨범 커버 디스플레이 프로젝트 인수인계

이 문서는 Claude Code가 세션 시작 시 자동으로 읽는 컨텍스트 파일입니다.
지금까지 Claude(채팅)와 진행한 내용을 그대로 이어받아 작업할 수 있도록 정리했습니다.

## 프로젝트 한 줄 요약

라즈베리파이 + LED 매트릭스(64x64)로 Spotify 현재 재생곡의 앨범 커버를
실시간으로 표시하는 목재 인테리어 디스플레이를 만드는 DIY 프로젝트.
소프트웨어융합 전공 실습 겸 포트폴리오용으로 진행 중.

---

## 0. 프로젝트 폴더 (2026-08-08 확정)

`/Users/banshk/Documents/album-display/`

```
album-display/
├── CLAUDE.md                  # 이 파일
├── album_display_main.py      # 메인 (최신)
├── album_art_processor.py     # 이미지 변환 모듈
├── .spotify_token_cache       # OAuth 리프레시 토큰 — 절대 공유/커밋 금지
├── .gitignore
└── docs/                      # 케이스 도면 SVG, 미리보기 PNG
```

Downloads 폴더에 흩어져 있던 파일을 여기로 모았음. 아직 git 저장소는 아님.

## 1. 개발 장비 / 환경

- **작업 기기**: MacBook Air
- **파이썬 환경**: Anaconda (base 환경)
  - **반드시 이 경로로 실행할 것**: `/opt/anaconda3/bin/python3` (→ python3.13.9, 확인 완료)
  - 시스템 기본 `python3`(`/Library/Frameworks/Python.framework/...`)로 실행하면
    anaconda에 설치된 패키지(spotipy 등)를 못 찾아 `ModuleNotFoundError` 발생함.
    이미 여러 번 겪은 문제이니 스크립트 실행/디버깅 시 항상 anaconda 경로 사용.
- **설치된 패키지**: spotipy, pillow, requests (anaconda base 환경에 설치 완료)
- **최종 타겟 기기**: Raspberry Pi 4B (4GB) — 현재는 맥북에서 로직만 먼저 개발/테스트 중,
  하드웨어 조립 후 RPi로 코드 이전 예정

## 2. 하드웨어 인벤토리

### 도착 완료
| 부품 | 스펙 | 비고 |
|---|---|---|
| Raspberry Pi 4B | 4GB RAM | 디바이스마트 구매, 가이드북+방열판 포함 |
| LED 매트릭스 | 64x64, 3mm 피치, HUB75 | 모델명 P3-64x64-2012-20B-1.2, 실측 확인 완료 |
| GPIO IDC 케이블 | 40핀, 2.54mm | Bonnet-RPi 연결용 |
| 전원 어댑터 | 5V 4A, DC잭(원형 배럴) | Bonnet 터미널 블록용, USB-C 아님 주의 |

### 주문했으나 도착 확인 필요
| 부품 | 스펙 | 구매처 |
|---|---|---|
| RGB Matrix Bonnet | Adafruit 정품 (HAT 아닌 Bonnet 버전) | vctec.co.kr, 26,200원 |
| microSD | Axxen 32GB | 쿠팡 |
| 납땜인두 세트 | 몬스툴 인두+받침대+땜납 | 쿠팡 |
| 목재 케이스 부품 | 자작나무합판 (측면4장+뒷판), 가공 포함 | 아이베란다 |
| 네오디움 자석 | 지름8mm x 5mm, 8개 | 아이베란다 |

### LED 매트릭스 배선 정보 (실물 확인 완료)
- **IN 커넥터**: 16핀, HUB75 신호 입력 — Bonnet에서 오는 IDC 케이블 연결
- **OUT 커넥터**: 매트릭스 체인 연결용 (이 프로젝트는 1장만 쓰므로 미사용)
- **전원 단자**: `+5V` / `GND` 라벨의 4핀 나사식 터미널 블록
- 64x64 전용 보드로 제작되어 있어 **별도 점퍼 납땜 불필요** (E핀이 IN 커넥터에 이미 포함됨)
- 참고: 납땜인두는 Bonnet 쪽에 혹시 필요한 점퍼가 있을 경우를 대비해 준비 중

### 전원 설계
- **전원 콘센트 1개로 통합**: DC잭 5V 4A 어댑터 → Bonnet 터미널 블록에 연결
  → Bonnet이 GPIO를 통해 RPi에도 전원 같이 공급 (Adafruit 공식 지원 기능)
  → RPi용 별도 USB-C 전원 불필요
- 노이즈로 문제 생기면 RPi 전원을 분리하는 것으로 되돌릴 수 있음 (예비 플랜)

## 3. 케이스 설계 최종 스펙 (v6, 확정)

정면 프레임 없이 측면 4장이 곧 테두리 역할을 하는 미니멀 구조.
(설계 과정에서 v1~v5는 아이베란다 시스템 제약으로 폐기됨 — 45도 마이터 가공 미지원,
사각 홈파기 최소여백 20mm 제약 때문에 구조 자체를 변경했음)

- **측면 상·하**: 205 × 40mm, 두께 6T, 2장, 가공 없음(재단만)
- **측면 좌·우**: 193 × 40mm, 두께 6T, 2장, 가공 없음(재단만)
- **뒷판**: 205 × 205mm, 두께 4T, 1장
  - 원형타공(자석용) Ø8 × 4개, 좌표 X/Y = 24mm (네 모서리 기준)
  - 원형타공(케이블홀) Ø12 × 1개, 좌표 X=102.5, Y=30
  - 사각타공(통풍슬롯) 24×5mm × 3개, X=45/102.5/160, Y=102.5
- **조립 방식**: 측면 4장 맞대기(90°) 목공본드 접착 → LED매트릭스 정면 삽입·고정
  → 코너 블록(자투리 목재, 약 20×20mm, 측면 안쪽 상단 모서리 4곳)에 자석 부착
  → 뒷판 자석과 자력으로 탈부착 고정
- **재질**: 자작나무합판 + 오일스테인(월넛/어두운 톤 계열) 도포
- 전체 조립도(2D 도면, 3D 참고 이미지)는 이전 대화에서 생성됨 — 필요시 재생성 요청할 것

## 4. 소프트웨어 진행 현황

### 🔑 인증 정보 취급 (2026-08-08 정리 완료)

**Client ID/Secret은 코드에 적지 않는다.** 환경변수 `SPOTIPY_*`로 관리하며
spotipy가 자동으로 읽는다. `get_spotify_client()`에는 `scope`와 `cache_path`만 넘긴다.

```bash
export SPOTIPY_CLIENT_ID=...
export SPOTIPY_CLIENT_SECRET=...
export SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

- 환경변수가 없으면 `SpotifyOauthError: No client_id...` 로 즉시 중단됨 (동작 확인)
- **sudo는 환경변수를 지운다** — RPi에서 매트릭스를 켤 땐 `sudo -E` 또는
  systemd 유닛의 `Environment=`. 놓치면 인증이 조용히 실패함
- `.spotify_token_cache`(리프레시 토큰)와 위 값들은 절대 커밋/공유 금지.
  `.gitignore`에 이미 등록해둠

**처리 완료**
- 코드에서 하드코딩된 상수 3개 삭제 (`album_display_main.py`)
- `spotify_now_playing.py` 삭제 — 구버전이고 시크릿만 남아 있었음
- `.gitignore` 생성 (토큰 캐시, 실행 산출물 PNG, `__pycache__`)
- 프로젝트 폴더 + Downloads 전체 grep — 남은 시크릿 없음

- [x] developer.spotify.com에서 **Client Secret 재발급 완료** (2026-08-08).
      노출됐던 기존 값은 폐기됨
- [x] `~/.zshrc`에 `export` 3줄 등록 완료. 동작 검증까지 끝남
      (시크릿을 바꿔도 기존 `.spotify_token_cache`는 유효해서 재로그인 없었음)
- [x] GitHub 히스토리 정리 — 불필요. 시크릿이 코드에 박힌 상태로 커밋된 적이 없음
      (git 저장소는 시크릿을 제거한 뒤에 만들었음)

> 시크릿 값은 대화/커밋/코드 어디에도 남기지 말 것. `~/.zshrc`에만 둔다.

### 완성되어 테스트까지 끝난 코드
파일 위치: `/Users/banshk/Documents/album-display/`

1. **`album_art_processor.py`** — 앨범아트 URL을 받아 64x64 이미지로 변환하는 모듈
   - `download_image()`, `crop_to_square()`, `get_matrix_image()`, `save_preview()`
   - 단독 테스트 완료: The Strokes "Reality Awaits" 앨범아트로 64x64 변환 확인됨

2. **`album_display_main.py`** — Spotify 연동 + 이미지 변환 통합 버전 (현재 최신/메인 파일)
   - `album_art_processor.py`를 import해서 사용하므로 **같은 폴더에 있어야 함**
   - 곡이 바뀌면 앨범아트를 64x64로 변환해 파일로 저장
     (`now_playing_64x64.png`, `now_playing_preview.png`)
   - Spotify 인증(OAuth) 정상 작동 확인됨, 실제 재생 정보 정확히 수신됨

   **2026-08-08 수정 내역**

   - **반응 속도 개선 (5초 → 약 0.3초)**: `next_sleep()` 추가.
     Spotify가 주는 `progress_ms`/`duration_ms`로 곡이 끝나는 시각을 계산해
     그 순간에 맞춰 깨어남. **API 추가 호출 없이** 반응 속도만 올림.
     폴링 간격은 5초 → 2초(`POLL_SECONDS`), 시간당 요청은 720 → 약 800으로 거의 그대로.
     - 곡이 끝까지 재생: 약 0.3초 / 수동 스킵: 최대 2초
     - `MIN_SLEEP = 0.5` — 예측이 빗나가도 과속 폴링 방지
     - 이 아래로 줄이는 건 Spotify API 자체 반영 지연(약 1초)이 벽이라 의미 없음
   - **곡 판정 기준: 제목 → 트랙 ID**. 제목으로 비교하면 같은 제목의 다른 버전
     (라이브/리믹스/커버)으로 넘어갈 때 앨범아트가 안 바뀜
   - **모든 경로를 `BASE_DIR` 절대경로로 변경**. 매트릭스 라이브러리는 root 권한이
     필요해 `sudo`로 실행하게 되고, systemd 자동실행 시 cwd가 `/`가 되어
     상대경로가 전부 깨짐. RPi 이전 전에 미리 처리한 것
   - **셀프체크 추가**: `/opt/anaconda3/bin/python3 album_display_main.py --check`
     → `next_sleep()` 계산 검증, `OK` 출력되면 정상

   **TODO**: `show_on_matrix()` 안에 실제 매트릭스 출력 코드가 주석 처리되어 있음
   ```python
   # matrix.SetImage(img.convert('RGB'))
   ```
   하드웨어 조립 후 `rpi-rgb-led-matrix` 설치하고 활성화. **Bonnet을 쓰므로
   `hardware_mapping = 'adafruit-hat'`** (점퍼 직결이 아님).
   활성화할 때 파일 저장 2줄은 지울 것 — SD카드에 매 곡마다 쓸 이유가 없음

3. ~~`spotify_now_playing.py`~~ — 초기 버전, 로직이 `album_display_main.py`에 통합되어
   더 이상 사용 안 함 (삭제해도 무방하다고 안내함)

### Spotify Developer 앱 정보
- 앱 이름: `album-display`
- Redirect URI: `http://127.0.0.1:8888/callback`
- Client ID / Secret: 사용자가 developer.spotify.com dashboard에서 직접 보관 중
  (Claude에게는 공유되지 않음 — 코드 안 변수에 사용자가 직접 입력해야 함)

## 4-1. RPi 이전 시 알려진 함정 (미리 정리, 아직 검증 전)

`rpi-rgb-led-matrix`는 GPIO를 직접 제어하므로 맥북과 환경 전제가 다름.
Pi 4B는 이 라이브러리가 정식 지원하는 모델이라 진행에 문제 없음. (Pi 5는 GPIO가
RP1 칩 뒤로 옮겨져 미지원 — 혹시 나중에 기기를 바꾸게 되면 이 점을 반드시 확인할 것.)

1. **온보드 사운드 비활성화 필수** — 라이브러리가 PWM 하드웨어를 쓰는데 사운드와 충돌.
   `/boot/firmware/config.txt`에 `dtparam=audio=off`,
   `/etc/modprobe.d/blacklist-rgb-matrix.conf`에 `blacklist snd_bcm2835`.
   안 하면 화면이 심하게 깜빡임
2. **`--led-gpio-slowdown`** — Pi 4는 보통 2 또는 4. 값이 낮으면 픽셀이 깨지거나
   색이 튐. 실물 보면서 맞춰야 하는 값이라 코드에 상수로 빼둘 것
3. **환경변수가 안 읽히는 경우가 두 가지** — 둘 다 인증이 조용히 실패함
   - `sudo`는 기본적으로 환경변수를 지움 → `sudo -E`
   - **`~/.zshrc`는 대화형 셸에서만 읽힘.** systemd·cron 같은 비대화형 실행에서는
     `~/.zshrc`에 뭘 적어두든 안 보임 (맥북에서 실제로 확인함)

   → RPi에서 자동 실행할 땐 `~/.zshrc`에 의존하지 말고 systemd 유닛에
     `Environment=` 또는 `EnvironmentFile=`로 직접 넣을 것. 아래 5번 참고
4. **헤드리스 OAuth** — 모니터 없이 SSH로만 붙으면 인증 시 브라우저가 안 열림.
   가장 쉬운 길은 맥북에서 인증을 끝낸 뒤 `.spotify_token_cache`를 RPi로 복사하는 것.
   리프레시 토큰이 들어 있어 그 뒤로는 재로그인 불필요
5. **자동 실행** — systemd 유닛으로 등록. 경로는 이미 `BASE_DIR` 절대경로로 처리해둠.
   인증 정보는 루트만 읽을 수 있는 파일로 분리하는 게 안전함:
   ```ini
   [Service]
   EnvironmentFile=/etc/album-display.env   # chmod 600, SPOTIPY_* 3줄
   ExecStart=/usr/bin/python3 /home/pi/album-display/album_display_main.py
   Restart=always
   ```
6. **전원** — 64x64는 전체 백색 표시 시 순간 전류가 큼. 5V 4A 어댑터가
   Bonnet 터미널로 들어가는 현재 설계가 맞음. USB-C로 파이만 먹이면 안 됨

## 5. 아직 안 한 것 / 다음 작업 후보

- [ ] `~/.zshrc`에 `SPOTIPY_*` 3줄 등록 (§4 인증 정보 항목).
      코드 정리와 Secret 재발급은 완료, 셸 설정만 남음
- [ ] microSD에 Raspberry Pi OS 설치 (Raspberry Pi Imager 사용, microSD 도착 후)
- [ ] Bonnet 도착 확인 및 점퍼 필요 여부 확인
- [ ] RPi + Bonnet + LED매트릭스 실제 배선
- [ ] `rpi-rgb-led-matrix` 라이브러리 RPi에 설치
- [ ] `album_display_main.py`의 `show_on_matrix()` 완성 (실제 매트릭스 출력)
- [ ] 텍스트(곡명/아티스트) 표시 로직 추가 검토 (64x64는 글자가 매우 작아 스크롤 처리 필요할 수 있음)
- [ ] 목재 케이스 조립 (측면 접착 → 자석 부착 → LED 고정 → 뒷판 결합 → 오일스테인 도포)
- [ ] GitHub 공개 + README 작성 (포트폴리오 활용 목적, 설계 의사결정 과정 기록 권장)

## 6. 참고: 설계 결정 히스토리 (왜 이렇게 됐는지)

- 완제품 Tuneshine($200) 대비 DIY가 크게 불리하지 않아 DIY로 진행
- LED 크기: 64x32도 검토했으나 실제 앨범 이미지 리사이즈 비교 테스트 결과 64x64가
  훨씬 선명해서 64x64로 최종 확정 (비용/납땜 부담보다 화질 우선)
- 케이스 목재: 월넛 미취급 → 멀바우(최소 12T라 비율 부적합) → 자작나무합판+오일스테인으로 정착
- 케이스 구조: 정면 프레임 있는 액자형 → 아이베란다 가공 제약(20mm 여백, 45도 미지원)으로
  구조 자체를 단순화하여 정면 프레임을 없앤 v6으로 최종 확정

---

이 프로젝트를 이어받으면, 먼저 사용자에게 **Bonnet/microSD/인두기/목재케이스 도착 여부**를
확인하고, 도착한 부품 기준으로 다음 단계(OS 설치 또는 배선)를 진행하면 됩니다.
