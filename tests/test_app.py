import json
import os
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from exam_core import load_exams

HISTORY = Path(os.environ["MOCK_EXAM_HISTORY"])
N = len(load_exams()[0]["questions"])


def button(at, label):
    matches = [b for b in at.button if b.label == label]
    assert matches, f"button {label!r} not found: {[b.label for b in at.button]}"
    return matches[0]


def has_text(at, text):
    return any(text in m.value for m in at.markdown)


@pytest.fixture
def at():
    if HISTORY.exists():
        HISTORY.unlink()
    app = AppTest.from_file("../app.py", default_timeout=30)
    app.run()
    assert not app.exception
    return app


def start(at):
    button(at, "試験を開始する").click().run()
    assert not at.exception
    assert at.session_state.screen == "exam"


def test_start_screen_lists_exams(at):
    assert at.selectbox[0].options  # exams/ の JSON が一覧になっている
    assert "未受験" in at.selectbox[0].options[0]


def test_full_run_to_result(at):
    start(at)
    assert at.radio[0].value is None  # 初期状態は未選択
    for i in range(N):
        assert has_text(at, f"問題 {i + 1} / {N}")
        assert has_text(at, "残り時間")
        at.radio[0].set_value(i % 4).run()
        if i < N - 1:
            assert not [b for b in at.button if b.label == "採点する"]
            button(at, "次へ →").click().run()
        else:
            assert not [b for b in at.button if b.label == "次へ →"]
            button(at, "採点する").click().run()
        assert not at.exception

    assert at.session_state.screen == "result"
    assert at.title[0].value.startswith("結果")
    assert [m.label for m in at.metric] == ["正答数", "正答率", "判定"]
    assert len(at.expander) == N  # 全問の一覧

    record = at.session_state.record
    expected = sum(
        q["answerIndex"] == order[i % 4]
        for i, (q, order) in enumerate(zip(at.session_state.questions, at.session_state.orders))
    )
    assert record["correct"] == expected
    assert sum(v["total"] for v in record["byChapter"].values()) == N

    # 間違えた問題だけに絞り込む
    at.toggle[0].set_value(True).run()
    assert len(at.expander) == N - record["correct"]

    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    assert len(history) == 1
    assert {"datetime", "exam", "correct", "total", "byChapter"} <= history[0].keys()

    # 開始画面に戻ると前回スコアが表示される
    button(at, "開始画面に戻る").click().run()
    assert at.session_state.screen == "start"
    assert f"前回 {record['correct']}/{N}" in at.selectbox[0].options[0]


def test_back_keeps_answer(at):
    start(at)
    at.radio[0].set_value(2).run()
    button(at, "次へ →").click().run()
    assert at.radio[0].value is None  # 2問目は未解答
    at.radio[0].set_value(1).run()
    button(at, "← 前へ").click().run()
    assert has_text(at, f"問題 1 / {N}")
    assert at.radio[0].value == 2  # 1問目の解答が残っている

    at.radio[0].set_value(3).run()  # 選び直し
    button(at, "次へ →").click().run()
    assert at.radio[0].value == 1  # 2問目の解答も残っている
    button(at, "← 前へ").click().run()
    assert at.radio[0].value == 3
    q0 = at.session_state.questions[0]
    assert at.session_state.answers[0] == at.session_state.orders[0][3]
    assert at.session_state.answers[0] in range(len(q0["choices"]))


def test_choice_order_fixed_during_exam(at):
    start(at)
    orders = [list(o) for o in at.session_state.orders]
    assert all(sorted(o) == [0, 1, 2, 3] for o in orders)
    for _ in range(3):
        button(at, "次へ →").click().run()
        button(at, "← 前へ").click().run()
    assert at.session_state.orders == orders


def test_timeout_moves_to_result(at):
    start(at)
    at.radio[0].set_value(0).run()
    at.session_state.deadline = time.time() - 1
    at.run()
    assert not at.exception
    assert at.session_state.screen == "result"
    assert at.session_state.record["timedOut"] is True
    assert len(json.loads(HISTORY.read_text(encoding="utf-8"))) == 1


def finish_with(at, pick):
    """全問を pick(i) 番目の表示位置で解答して採点する."""
    start(at)
    for i in range(N):
        at.radio[0].set_value(pick(i)).run()
        button(at, "次へ →" if i < N - 1 else "採点する").click().run()
    assert at.session_state.screen == "result"
    return at.session_state.record


def test_reopen_result_from_history(at):
    record = finish_with(at, lambda i: i % 4)
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    assert [item["id"] for item in history[0]["answers"]] == [q["id"] for q in at.session_state.questions]

    button(at, "開始画面に戻る").click().run()
    assert at.selectbox(key="history_select").options  # 受験履歴が選べる
    button(at, "結果を見る").click().run()
    assert not at.exception
    assert at.session_state.screen == "result"
    assert at.metric[0].value == f"{record['correct']} / {N}"
    assert len(at.expander) == N
    at.toggle[0].set_value(True).run()
    assert len(at.expander) == N - record["correct"]


def test_old_record_without_answers(at):
    HISTORY.write_text(
        json.dumps([{"datetime": "2026-01-01T00:00:00", "exam": "exam-01", "title": "第1回",
                     "correct": 20, "total": N, "byChapter": {}, "timedOut": False}]),
        encoding="utf-8",
    )
    at.run()
    assert "詳細なし" in at.selectbox(key="history_select").options[0]
    button(at, "結果を見る").click().run()
    assert not at.exception
    assert at.session_state.screen == "result"
    assert len(at.expander) == 0
    assert any("保存されていません" in m.value for m in at.info)


def test_review_wrong_questions(at):
    record = finish_with(at, lambda i: i % 4)
    n_wrong = N - record["correct"]
    assert n_wrong > 0
    button(at, f"間違えた問題を解き直す（{n_wrong}問）").click().run()
    assert at.session_state.screen == "review"
    qs = at.session_state.review_questions
    assert len(qs) == n_wrong
    assert history_len() == 1  # 復習は履歴に記録しない

    for i, q in enumerate(qs):
        assert has_text(at, f"問題 {i + 1} / {n_wrong}")
        assert button(at, "答え合わせ").disabled  # 未選択では答え合わせできない
        order = at.session_state.review_orders[i]
        at.radio[0].set_value(order.index(q["answerIndex"])).run()  # 正解を選ぶ
        button(at, "答え合わせ").click().run()
        assert not at.exception
        assert at.radio[0].disabled
        assert any("正解です" in m.value for m in at.success)
        if i < n_wrong - 1:
            button(at, "次へ →").click().run()
    assert any(f"{n_wrong} 問中 {n_wrong} 問正解" in m.value for m in at.success)

    # 前へ戻っても答え合わせ済みの状態が残る
    if n_wrong > 1:
        button(at, "← 前へ").click().run()
        assert at.radio[0].disabled

    button(at, "結果画面に戻る").click().run()
    assert at.session_state.screen == "result"
    assert at.session_state.record == record


def history_len():
    return len(json.loads(HISTORY.read_text(encoding="utf-8")))
