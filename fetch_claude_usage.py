"""
fetch_claude_usage.py
-----------------------
맥(Claude Code CLI가 설치·인증된 기기)에서 실행해서 `claude -p "/usage"` 결과를
파싱하고, LED 매트릭스를 붙인 라즈베리파이로 JSON을 scp한다.

라즈베리파이 자체에는 Claude Code CLI를 설치/인증하지 않는다 — 이 스크립트가
맥에서 주기적으로(cron) 가져와 파일 하나만 Pi로 밀어주고, Pi 쪽은 그 파일을
읽기만 한다.

cron 등록 예:
  */15 * * * * /usr/bin/python3 /Users/banshk/Documents/album-display/fetch_claude_usage.py >> /tmp/fetch_claude_usage.log 2>&1
"""

from __future__ import annotations   # cron이 쓰는 /usr/bin/python3(3.9)엔 `dict | None` 문법이 없음

import datetime
import json
import re
import subprocess
import sys

PI_HOST = "banshk@172.30.1.49"
PI_PATH = "/home/banshk/album-display/claude_usage.json"

# PATH에 기대지 않고 절대경로로 직접 호출한다. cron은 로그인 셸의 PATH 커스터마이징
# (~/.zshrc의 ~/.local/bin 추가)을 안 물려받아서 "claude"만으로는 못 찾는다 —
# zsh -lc로 감싸도 마찬가지였다(비대화형 로그인 셸은 ~/.zprofile만 읽고 ~/.zshrc는 안 읽음).
CLAUDE_BIN = "/Users/banshk/.local/bin/claude"

USAGE_RE = re.compile(
    r"{label}:\s*(\d+)% used · resets (\w+ \d+) at (\d+)(?::(\d+))?(am|pm)"
)


def parse_block(label: str, text: str) -> dict | None:
    m = re.search(USAGE_RE.pattern.format(label=re.escape(label)), text)
    if not m:
        return None

    pct = int(m.group(1))
    month_day, hh, mm, ampm = m.group(2), m.group(3), m.group(4) or "0", m.group(5)

    now = datetime.datetime.now()
    reset_dt = datetime.datetime.strptime(f"{now.year} {month_day} {hh}:{mm}{ampm}", "%Y %b %d %I:%M%p")
    if reset_dt < now:
        reset_dt = reset_dt.replace(year=now.year + 1)

    return {"pct": pct, "resets_in_min": int((reset_dt - now).total_seconds() // 60)}


def fetch_usage() -> dict:
    out = subprocess.run(
        [CLAUDE_BIN, "-p", "/usage", "--output-format", "json"],
        capture_output=True, text=True, timeout=30, check=True,
    )
    text = json.loads(out.stdout)["result"]

    session = parse_block("Current session", text)
    week = parse_block("Current week (all models)", text)
    if session is None or week is None:
        raise ValueError(f"/usage 출력 형식이 바뀐 것 같음 — 파싱 실패\n{text}")

    return {"session": session, "week": week, "fetched_at": now_iso()}


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def main():
    usage = fetch_usage()
    print(json.dumps(usage, ensure_ascii=False))

    tmp_path = "/tmp/claude_usage.json"
    with open(tmp_path, "w") as f:
        json.dump(usage, f)

    subprocess.run(["scp", "-o", "ConnectTimeout=5", tmp_path, f"{PI_HOST}:{PI_PATH}"], check=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[에러] {e}", file=sys.stderr)
        sys.exit(1)
