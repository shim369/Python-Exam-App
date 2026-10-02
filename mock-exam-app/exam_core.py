"""模擬試験アプリと検証スクリプトで共有する定数・読み込み処理."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
EXAMS_DIR = APP_DIR / "exams"
HISTORY_PATH = Path(os.environ.get("MOCK_EXAM_HISTORY", APP_DIR / "results" / "history.json"))

TIME_LIMIT_SEC = 75 * 60
PASS_RATE = 0.7
QUESTIONS_PER_EXAM = 40

# 章番号: (タイトル, 1回あたりの出題数)
CHAPTERS: dict[int, tuple[str, int]] = {
    1: ("Python の環境", 1),
    2: ("コーディング規約", 2),
    3: ("Python の言語仕様", 7),
    4: ("Python のクラス", 3),
    5: ("型ヒント", 2),
    6: ("テキストの処理", 4),
    8: ("日付と時刻の処理", 2),
    9: ("データ型とアルゴリズム", 5),
    10: ("汎用OS・ランタイムサービス", 2),
    11: ("ファイルとディレクトリへのアクセス", 2),
    13: ("特定のデータフォーマットを扱う", 2),
    14: ("インターネット上のデータを扱う", 2),
    16: ("テスト", 3),
    17: ("デバッグ", 2),
    18: ("暗号関連", 1),
}

REQUIRED_FIELDS = ("id", "chapter", "section", "topic", "question", "choices", "answerIndex", "explanation")


def chapter_label(chapter: int) -> str:
    title = CHAPTERS.get(chapter, ("不明", 0))[0]
    return f"{chapter}章 {title}"


def list_exam_files(exams_dir: Path = EXAMS_DIR) -> list[Path]:
    return sorted(exams_dir.glob("exam-*.json"))


def load_exam(path: Path) -> dict:
    """exam-XX.json を読み込む. トップレベルは {"title", "questions"} または問題の配列."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = {"questions": data}
    data.setdefault("title", path.stem)
    data["key"] = path.stem
    return data


def load_exams(exams_dir: Path = EXAMS_DIR) -> list[dict]:
    return [load_exam(p) for p in list_exam_files(exams_dir)]


def load_history(path: Path = HISTORY_PATH) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def append_history(record: dict, path: Path = HISTORY_PATH) -> None:
    history = load_history(path)
    history.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def last_results(history: list[dict]) -> dict[str, dict]:
    """回(exam key)ごとの最新の受験記録."""
    latest: dict[str, dict] = {}
    for rec in history:
        latest[rec.get("exam")] = rec
    return latest


def now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")
