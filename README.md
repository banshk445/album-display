# album-display

Spotify에서 재생 중인 곡의 앨범 커버를 64×64 LED 매트릭스에 실시간으로 띄우는
목재 인테리어 디스플레이. 재생 중인 곡이 없으면 시계·마스코트·Claude Code 사용량을
보여주는 대기 화면으로 전환됩니다.

라즈베리파이 4B + HUB75 매트릭스 + 자작나무합판 케이스로 만든 DIY 프로젝트입니다.

> **상태**: 하드웨어 조립 완료, systemd로 상시 운영 중.
> 하드웨어 PWM(GPIO4-18 점퍼)까지 납땜해서 깜빡임을 잡은 상태입니다.

---

## 왜 만들었나

시중에 Tuneshine 같은 완제품이 있지만 $200 선입니다.
부품비를 따져보니 DIY가 크게 불리하지 않았고, 케이스 재질과 비율을 직접 정할 수 있다는
점이 더 컸습니다. 소프트웨어융합 전공 실습 겸 포트폴리오로 진행했습니다.

## 어떻게 동작하나

```
Spotify Web API ──> 곡 변경 감지 ──> 앨범아트 URL
                                        │
                                        ▼
                          다운로드 → 정사각 크롭 → 64×64 리사이즈 → LED 매트릭스

재생 중인 곡 없음/일시정지
    │
    ▼
대기 화면: 우상단 디지털 시계 + Claude Code 사용량 도넛 게이지 2개(5h/주간)
          + 마스코트(가끔 hop/wiggle/look 애니메이션)
```

| 파일 | 역할 |
|---|---|
| `album_display_main.py` | Spotify 폴링, 곡 변경 감지, 대기 화면, 전체 흐름 |
| `album_art_processor.py` | 이미지 다운로드/크롭/리사이즈 (앨범아트·수동 업로드 공용) |
| `show_image.py` | 사진 한 장을 받아 64×64로 처리해 일회성으로 화면에 띄움 |
| `fetch_claude_usage.py` | (맥에서 실행) `claude -p "/usage"` 파싱해서 Pi로 scp |
| `clawd_mascot.png` | 대기 화면 마스코트 픽셀아트 |
| `mac-app/` | 맥 메뉴바 앱(Swift) — 온도 확인/절전모드/재부팅/이미지 업로드 |
| `deploy/` | systemd 유닛, 환경변수 예시 |
| `docs/` | 목재 케이스 도면 (SVG) |

---

## 대기 화면

재생 중인 곡이 없거나 일시정지 상태면 아래를 한 화면에 표시합니다(로테이션 없음).

- **우상단**: 디지털 시계(`HH:MM`, 분 단위 갱신)
- **마스코트**: 평소엔 정지, 10초마다 확률(40%)을 굴려 가끔 hop/wiggle/look 애니메이션
- **하단**: Claude Code 사용량 도넛 게이지 2개 — 세션(5h) / 주간, 색은 시계·마스코트와
  통일한 Claude 브랜드 오렌지

사용량 데이터는 맥에서 `fetch_claude_usage.py`가 1분마다 `claude -p "/usage"`를 파싱해서
`claude_usage.json`을 Pi로 scp합니다. **cron이 아니라 launchd LaunchAgent**로 돌립니다 —
cron은 macOS 로그인 세션 밖에서 실행돼서 `claude`의 키체인 인증에 접근하지 못합니다.
실행 스크립트 자체도 `~/Documents` 밖(`~/.local/share/album-display/`)에 둬야 합니다.
launchd가 실행하는 프로세스는 TCC가 `~/Documents` 접근을 막기 때문입니다.

## 원격 제어

`mac-app/`의 메뉴바 앱(Swift, `MenuBarExtra`)에서 SSH로 Pi를 제어합니다.

- 🌡 온도 확인 (`vcgencmd measure_temp` / `get_throttled`)
- 🖼 이미지 업로드 — 사진을 골라서 scp + `show_image.py` 실행, 10초간 표시 후 자동 복귀
- 🌙 절전모드 — `systemctl stop/start album-display`로 **LED 매트릭스만 끔**.
  케이스 뒷판을 접착해버려서 전원 케이블에 손을 못 대는 상태라, Pi 자체는 계속
  켜둔 채(원격 제어 가능하게) 발열/전력의 대부분을 차지하는 매트릭스만 끄는 방식을 씁니다.
  Pi를 완전히 끄면(`shutdown`) 물리 전원 버튼 없이는 다시 못 켭니다.
- 🔄 재부팅 — `sudo reboot` (전원은 계속 공급되므로 원격으로 다시 살아남, `shutdown`과 다름)

빌드:

```bash
cd mac-app
swiftc -parse-as-library -O main.swift -o AlbumDisplayControl.app/Contents/MacOS/AlbumDisplayControl
codesign --force --sign - AlbumDisplayControl.app
open AlbumDisplayControl.app
```

---

## 구현하면서 짚은 것들

### 곡이 바뀐 걸 언제 알아채는가

폴링 간격을 줄이면 반응은 빨라지지만 API 호출이 그만큼 늘어납니다.
그런데 Spotify는 응답에 `progress_ms`와 `duration_ms`를 같이 주기 때문에,
**곡이 끝나는 시각을 이미 알고 있습니다.**

```python
def next_sleep(info) -> float:
    if info is None or not info["is_playing"] or info["remaining_ms"] is None:
        return POLL_SECONDS
    return max(MIN_SLEEP, min(POLL_SECONDS, info["remaining_ms"] / 1000 + END_MARGIN))
```

남은 시간이 폴링 간격보다 짧으면 그 순간에 맞춰 깨웁니다.
**API를 더 부르지 않고** 반응 속도만 끌어올렸습니다.

예측이 빗나가도 `MIN_SLEEP = 0.5`가 과속 폴링을 막습니다.
이 아래로 줄이는 건 Spotify API 자체의 반영 지연(약 1초)이 벽이라 의미가 없습니다.

### 일시정지는 "곡 없음"이 아니다

`current_playback()`은 일시정지 상태에서도 트랙 정보를 계속 돌려줍니다(`is_playing=False`).
곡 없음만 대기 화면 조건으로 잡으면 일시정지 중엔 화면이 마지막 앨범아트에 멈춰버립니다.
`is_idle = info is None or not info["is_playing"]`로 묶어서 해결했습니다.

### 같은 제목의 다른 곡

처음엔 곡 제목으로 변경을 판정했는데, 이러면 같은 제목의 라이브·리믹스·커버 버전으로
넘어갈 때 앨범아트가 그대로 남습니다. 트랙 ID로 비교하도록 바꿨습니다.

### 상대경로가 깨지는 지점

`rpi-rgb-led-matrix`는 GPIO를 직접 제어해서 root 권한이 필요합니다.
즉 `sudo`로 실행하게 되고, systemd로 자동 실행하면 작업 디렉터리가 `/`가 됩니다.
상대경로로 저장하던 파일과 토큰 캐시가 전부 엉뚱한 곳을 가리키게 되므로,
`BASE_DIR` 기준 절대경로로 정리했습니다.

```python
BASE_DIR = Path(__file__).resolve().parent
```

### systemd에서 print()가 안 보이는 이유

Python stdout은 tty가 아니면 완전 버퍼링됩니다. systemd 아래서 실행하면 `print()`가
journalctl에 거의 안 찍혀서 며칠째 멈춰있는 것처럼 보이는 상황이 실제로 있었습니다.
유닛 파일에 `Environment=PYTHONUNBUFFERED=1` 한 줄이 해결책입니다.

### 인증 정보

Client ID/Secret은 코드에 두지 않고 환경변수로 관리합니다.
spotipy가 `SPOTIPY_*`를 자동으로 읽기 때문에 별도 설정 코드가 필요 없습니다.

한 가지 함정은 **`sudo`가 기본적으로 환경변수를 지운다**는 점입니다.
systemd 유닛에 `EnvironmentFile=`로 명시해야 합니다. 놓치면 인증이 조용히 실패합니다.

---

## 하드웨어

| 부품 | 스펙 |
|---|---|
| Raspberry Pi | 4B (4GB), Wi-Fi 연결 |
| LED 매트릭스 | 64×64, 3mm 피치, HUB75 |
| 인터페이스 | Adafruit RGB Matrix Bonnet |
| 전원 | 5V 4A DC 어댑터 (배럴잭) |
| 케이스 | 자작나무합판 6T/4T + 오일스테인 |
| 고정 | 네오디뮴 자석 Ø8×5mm |

전원은 콘센트 하나로 통합했습니다. 어댑터가 Bonnet 터미널로 들어가고,
Bonnet이 GPIO를 통해 파이에도 전원을 공급합니다(Adafruit 공식 지원).

### 하드웨어 PWM (GPIO4-18 점퍼)

기본값(`adafruit-hat`)은 소프트웨어 PWM이라 깜빡임이 원리적으로 안 없어집니다.
Bonnet 상단 브레이크아웃 행의 `GPIO4`·`18` 라벨 핀을 전선으로 직접 이으면(납땜)
`HARDWARE_MAPPING = "adafruit-hat-pwm"`으로 하드웨어 PWM을 쓸 수 있습니다.
체감 차이가 컸습니다 — 적용 후 깜빡임이 확실히 줄었습니다.
추가로 온보드 사운드(`snd_bcm2835`)를 blacklist 해야 합니다(PWM 하드웨어 충돌).

## 케이스 설계

정면 프레임 없이 측면 4장이 그대로 테두리가 되는 구조입니다.

- 측면 상·하 205×40mm / 좌·우 193×40mm, 6T, 맞대기 접착
- 뒷판 205×205mm, 4T — 자석 4개, 케이블홀 Ø12, 통풍슬롯 3개
- 뒷판은 자석으로 탈부착 (내부 정비용)

처음엔 액자형 정면 프레임을 두려 했지만, 가공 업체가 45도 마이터를 지원하지 않고
사각 홈파기에 최소 여백 20mm 제약이 있어 v1~v5가 전부 폐기됐습니다.
제약에 맞춰 구조를 단순화한 결과가 v6이고, 오히려 더 미니멀해졌습니다.

도면은 `docs/`에 있습니다.

---

## 실행

```bash
pip install spotipy pillow requests
```

[Spotify Developer Dashboard](https://developer.spotify.com/dashboard)에서 앱을 만들고
Redirect URI에 `http://127.0.0.1:8888/callback`을 등록한 뒤:

```bash
export SPOTIPY_CLIENT_ID=...
export SPOTIPY_CLIENT_SECRET=...
export SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback

python album_display_main.py
```

처음 실행하면 브라우저가 열리며 인증을 요청합니다.
이후에는 `.spotify_token_cache`에 저장된 리프레시 토큰으로 자동 로그인됩니다.

로직 검증만 하려면:

```bash
python album_display_main.py --check
```

### 라즈베리파이 상시 실행

```bash
sudo cp deploy/album-display.service /etc/systemd/system/
sudo cp deploy/album-display.env.example /etc/album-display.env
sudo chmod 600 /etc/album-display.env
sudo nano /etc/album-display.env   # SPOTIPY_* 채우기
sudo systemctl enable --now album-display
journalctl -u album-display -f
```

## 앞으로

- [ ] 밝기 자동 조절 (시간대별)
- [ ] journald 재부팅 간 로그 보존 (재부팅 원인 추적용)
- [ ] 곡명·아티스트 텍스트 표시 — 64×64에서 앨범 커버가 화면을 꽉 채우고 3mm 피치에서
      한글이 거의 안 읽혀서 보류 중

완료: ~~라즈베리파이 배선~~ · ~~`rpi-rgb-led-matrix` 연동~~ · ~~케이스 조립~~ ·
~~하드웨어 PWM 전환~~ · ~~대기 화면(시계/사용량/마스코트)~~ · ~~맥 원격 제어 앱~~
