# album-display

Spotify에서 재생 중인 곡의 앨범 커버를 64×64 LED 매트릭스에 실시간으로 띄우는
목재 인테리어 디스플레이.

라즈베리파이 4B + HUB75 매트릭스 + 자작나무합판 케이스로 만드는 DIY 프로젝트입니다.

> **상태**: 소프트웨어 로직 완성, 하드웨어 조립 대기 중.
> 현재는 매트릭스 대신 PNG 파일로 출력해 맥북에서 검증하고 있습니다.

---

## 왜 만들었나

시중에 Tuneshine 같은 완제품이 있지만 $200 선입니다.
부품비를 따져보니 DIY가 크게 불리하지 않았고, 케이스 재질과 비율을 직접 정할 수 있다는
점이 더 컸습니다. 소프트웨어융합 전공 실습 겸 포트폴리오로 진행 중입니다.

## 어떻게 동작하나

```
Spotify Web API ──> 곡 변경 감지 ──> 앨범아트 URL
                                        │
                                        ▼
                          다운로드 → 정사각 크롭 → 64×64 리사이즈
                                        │
                                        ▼
                        (현재) PNG 저장  /  (예정) LED 매트릭스 출력
```

| 파일 | 역할 |
|---|---|
| `album_display_main.py` | Spotify 폴링, 곡 변경 감지, 전체 흐름 |
| `album_art_processor.py` | 이미지 다운로드 / 크롭 / 리사이즈 |
| `docs/` | 목재 케이스 도면 (SVG) |

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

| | 이전 | 이후 |
|---|---|---|
| 곡이 끝까지 재생 | 최대 5초 | 약 0.3초 |
| 수동 스킵 | 최대 5초 | 최대 2초 |
| 시간당 API 요청 | 720 | 약 800 |

예측이 빗나가도 `MIN_SLEEP = 0.5`가 과속 폴링을 막습니다.
이 아래로 줄이는 건 Spotify API 자체의 반영 지연(약 1초)이 벽이라 의미가 없습니다.

### 같은 제목의 다른 곡

처음엔 곡 제목으로 변경을 판정했는데, 이러면 같은 제목의 라이브·리믹스·커버 버전으로
넘어갈 때 앨범아트가 그대로 남습니다. 트랙 ID로 비교하도록 바꿨습니다.

### 상대경로가 깨지는 지점

`rpi-rgb-led-matrix`는 GPIO를 직접 제어해서 root 권한이 필요합니다.
즉 `sudo`로 실행하게 되고, systemd로 자동 실행하면 작업 디렉터리가 `/`가 됩니다.
상대경로로 저장하던 파일과 토큰 캐시가 전부 엉뚱한 곳을 가리키게 되므로,
하드웨어 이전 전에 미리 `BASE_DIR` 기준 절대경로로 정리했습니다.

```python
BASE_DIR = Path(__file__).resolve().parent
```

### 인증 정보

Client ID/Secret은 코드에 두지 않고 환경변수로 관리합니다.
spotipy가 `SPOTIPY_*`를 자동으로 읽기 때문에 별도 설정 코드가 필요 없습니다.

한 가지 함정은 **`sudo`가 기본적으로 환경변수를 지운다**는 점입니다.
라즈베리파이에서 매트릭스를 켤 때는 `sudo -E`를 쓰거나 systemd 유닛에
`Environment=`로 명시해야 합니다. 놓치면 인증이 조용히 실패합니다.

---

## 하드웨어

| 부품 | 스펙 |
|---|---|
| Raspberry Pi | 4B (4GB) |
| LED 매트릭스 | 64×64, 3mm 피치, HUB75 |
| 인터페이스 | Adafruit RGB Matrix Bonnet |
| 전원 | 5V 4A DC 어댑터 (배럴잭) |
| 케이스 | 자작나무합판 6T/4T + 오일스테인 |
| 고정 | 네오디뮴 자석 Ø8×5mm |

전원은 콘센트 하나로 통합했습니다. 어댑터가 Bonnet 터미널로 들어가고,
Bonnet이 GPIO를 통해 파이에도 전원을 공급합니다(Adafruit 공식 지원).
노이즈 문제가 생기면 파이 전원을 분리하는 것으로 되돌릴 수 있습니다.

## 케이스 설계

정면 프레임 없이 측면 4장이 그대로 테두리가 되는 구조입니다.

- 측면 상·하 205×40mm / 좌·우 193×40mm, 6T, 맞대기 접착
- 뒷판 205×205mm, 4T — 자석 4개, 케이블홀 Ø12, 통풍슬롯 3개
- 뒷판은 자석으로 탈부착 (내부 정비용)

처음엔 액자형 정면 프레임을 두려 했지만, 가공 업체가 45도 마이터를 지원하지 않고
사각 홈파기에 최소 여백 20mm 제약이 있어 v1~v5가 전부 폐기됐습니다.
제약에 맞춰 구조를 단순화한 결과가 지금의 v6이고, 오히려 더 미니멀해졌습니다.

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

## 앞으로

- [ ] 라즈베리파이 OS 설치 및 배선
- [ ] `rpi-rgb-led-matrix` 연동 — Bonnet이므로 `hardware_mapping='adafruit-hat'`
- [ ] 목재 케이스 조립 및 오일스테인 도포
- [ ] 밝기 자동 조절 (야간 조도 낮추기)

곡명·아티스트 텍스트 표시도 후보였지만, 64×64에서는 앨범 커버가 화면을 꽉 채우고
3mm 피치에서 한글이 거의 읽히지 않아 보류했습니다. 실물을 보고 판단할 예정입니다.
