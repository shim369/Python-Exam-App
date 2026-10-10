import os
import sys
import tempfile
from pathlib import Path

# 受験履歴は一時ファイルに書き込み、results/history.json を汚さない
_TMP = Path(tempfile.mkdtemp(prefix="mock-exam-test-"))
os.environ["MOCK_EXAM_HISTORY"] = str(_TMP / "history.json")

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)
