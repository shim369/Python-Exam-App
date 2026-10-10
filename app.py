"""Python 3 エンジニア認定実践試験 模擬試験アプリ (streamlit run app.py)."""

from __future__ import annotations

import random
import string
import time
import uuid

import streamlit as st

from exam_core import (
    CHAPTERS,
    PASS_RATE,
    TIME_LIMIT_SEC,
    append_history,
    chapter_label,
    load_exams,
    load_history,
    last_results,
    now_str,
)

st.set_page_config(page_title="Python3 実践試験 模擬試験", page_icon="🐍", layout="centered")

LETTERS = "ABCD"
_MD_SPECIAL = set(string.punctuation)


# ---------------------------------------------------------------- helpers
def md_escape(text: str) -> str:
    """ラジオボタンのラベル (Markdown 解釈される) 用に記号をエスケープする."""
    return "".join("\\" + ch if ch in _MD_SPECIAL else ch for ch in text)


def needs_code_block(choices: list[str]) -> bool:
    """改行や連続空白を含む選択肢があれば、すべて st.code で表示する."""
    return any("\n" in c or "  " in c or c != c.strip() for c in choices)


def init_state() -> None:
    st.session_state.setdefault("screen", "start")


def start_exam(exam: dict) -> None:
    questions = exam["questions"]
    st.session_state.update(
        screen="exam",
        exam_key=exam["key"],
        exam_title=exam["title"],
        questions=questions,
        # 選択肢の並び順は開始時に一度だけ決める (表示位置 -> 元の選択肢 index)
        orders=[random.sample(range(len(q["choices"])), len(q["choices"])) for q in questions],
        answers=[None] * len(questions),  # 元の選択肢 index で保持
        current=0,
        deadline=time.time() + TIME_LIMIT_SEC,
        attempt=uuid.uuid4().hex[:8],
        timed_out=False,
        record=None,
    )


def radio_key(i: int) -> str:
    return f"ans_{st.session_state.attempt}_{i}"


def save_current_answer() -> None:
    i = st.session_state.current
    pos = st.session_state.get(radio_key(i))
    if pos is not None:
        st.session_state.answers[i] = st.session_state.orders[i][pos]


def go(delta: int) -> None:
    save_current_answer()
    st.session_state.current += delta


def finish_exam(timed_out: bool = False) -> None:
    if st.session_state.screen != "exam":
        return
    if not timed_out:
        save_current_answer()
    st.session_state.timed_out = timed_out
    st.session_state.screen = "result"
    record = grade()
    append_history(record)
    st.session_state.record = record


def grade() -> dict:
    qs = st.session_state.questions
    answers = st.session_state.answers
    by_chapter: dict[str, dict[str, int]] = {}
    correct = 0
    for q, a in zip(qs, answers):
        ch = by_chapter.setdefault(str(q["chapter"]), {"correct": 0, "total": 0})
        ch["total"] += 1
        if a == q["answerIndex"]:
            ch["correct"] += 1
            correct += 1
    by_chapter = dict(sorted(by_chapter.items(), key=lambda kv: int(kv[0])))
    return {
        "datetime": now_str(),
        "exam": st.session_state.exam_key,
        "title": st.session_state.exam_title,
        "correct": correct,
        "total": len(qs),
        "byChapter": by_chapter,
        "timedOut": st.session_state.timed_out,
        # 結果画面を後から開き直せるよう、問題ごとの解答と選択肢の並び順も保存する
        "answers": [
            {"id": q["id"], "answer": a, "order": order}
            for q, a, order in zip(qs, answers, st.session_state.orders)
        ],
    }


def open_record(record: dict, exams_by_key: dict[str, dict]) -> None:
    """受験履歴の記録から結果画面を復元する. 問題本文は exams/ の JSON から id で引く."""
    exam = exams_by_key.get(record.get("exam"), {"questions": []})
    by_id = {q["id"]: q for q in exam["questions"]}
    questions, answers, orders = [], [], []
    for item in record.get("answers") or []:
        q = by_id.get(item.get("id"))
        if q is None:
            continue
        n = len(q["choices"])
        order = item.get("order")
        if not order or sorted(order) != list(range(n)):
            order = list(range(n))
        questions.append(q)
        answers.append(item.get("answer"))
        orders.append(order)
    st.session_state.update(
        screen="result",
        record=record,
        exam_title=record.get("title", record.get("exam")),
        questions=questions,
        answers=answers,
        orders=orders,
    )


def start_review() -> None:
    """結果画面で表示中の受験記録のうち、間違えた (未解答を含む) 問題だけを解き直す."""
    qs = [q for q, a in zip(st.session_state.questions, st.session_state.answers) if a != q["answerIndex"]]
    st.session_state.update(
        screen="review",
        review_questions=qs,
        review_orders=[random.sample(range(len(q["choices"])), len(q["choices"])) for q in qs],
        review_answers=[None] * len(qs),
        review_checked=[False] * len(qs),
        review_current=0,
        review_attempt=uuid.uuid4().hex[:8],
    )


def review_key(i: int) -> str:
    return f"rev_{st.session_state.review_attempt}_{i}"


def save_review_answer() -> None:
    i = st.session_state.review_current
    pos = st.session_state.get(review_key(i))
    if pos is not None:
        st.session_state.review_answers[i] = st.session_state.review_orders[i][pos]


def review_go(delta: int) -> None:
    save_review_answer()
    st.session_state.review_current += delta


def check_review() -> None:
    save_review_answer()
    st.session_state.review_checked[st.session_state.review_current] = True


def remaining_sec() -> float:
    return max(0.0, st.session_state.deadline - time.time())


# ---------------------------------------------------------------- screens
def render_start() -> None:
    st.title("🐍 Python 3 エンジニア認定実践試験 模擬試験")
    st.caption(f"全40問・制限時間 {TIME_LIMIT_SEC // 60} 分・正答率 {int(PASS_RATE * 100)}% 以上で合格")

    exams = load_exams()
    if not exams:
        st.warning("exams/ に問題ファイル (exam-XX.json) がありません。")
        return
    history = load_history()
    latest = last_results(history)

    def label(exam: dict) -> str:
        rec = latest.get(exam["key"])
        score = f"前回 {rec['correct']}/{rec['total']}" if rec else "未受験"
        return f"{exam['title']}（{len(exam['questions'])}問・{score}）"

    rows = []
    for exam in exams:
        rec = latest.get(exam["key"])
        rows.append(
            {
                "回": exam["title"],
                "問題数": len(exam["questions"]),
                "前回スコア": f"{rec['correct']} / {rec['total']}" if rec else "—",
                "前回正答率": f"{rec['correct'] / rec['total']:.0%}" if rec else "—",
                "受験日時": rec["datetime"].replace("T", " ") if rec else "—",
            }
        )
    st.dataframe(rows, hide_index=True, width="stretch")

    idx = st.selectbox("受験する回", range(len(exams)), format_func=lambda i: label(exams[i]), key="exam_select")
    st.button("試験を開始する", type="primary", on_click=start_exam, args=(exams[idx],))

    if history:
        st.subheader("受験履歴")
        exams_by_key = {e["key"]: e for e in exams}

        def history_label(j: int) -> str:
            rec = history[j]
            note = "" if rec.get("answers") else "（解答の詳細なし）"
            when = rec.get("datetime", "").replace("T", " ")
            return f"{when}　{rec.get('title', rec.get('exam'))}　{rec['correct']}/{rec['total']}{note}"

        j = st.selectbox(
            "振り返る記録（新しい順）",
            range(len(history) - 1, -1, -1),
            format_func=history_label,
            key="history_select",
        )
        st.button("結果を見る", on_click=open_record, args=(history[j], exams_by_key))


@st.fragment(run_every=1)
def render_timer() -> None:
    if st.session_state.get("screen") != "exam":
        return
    rem = remaining_sec()
    if rem <= 0:
        finish_exam(timed_out=True)
        st.rerun(scope="app")
    m, s = divmod(int(rem), 60)
    color = "red" if rem < 5 * 60 else "blue"
    st.markdown(f"⏱ 残り時間 **:{color}[{m:02d}:{s:02d}]**")


def render_choices(q: dict, order: list[int], key: str, current: int | None, on_change, disabled: bool = False) -> None:
    shown = [q["choices"][k] for k in order]
    index = order.index(current) if current is not None else None
    # ウィジェットが一度消えた後 (前へ/次へ) でも保存済みの解答を復元する
    if key not in st.session_state:
        st.session_state[key] = index

    if needs_code_block(shown):
        for pos, text in enumerate(shown):
            st.markdown(f"**{LETTERS[pos]}**")
            st.code(text, language="python")
        fmt = lambda pos: LETTERS[pos]  # noqa: E731
        horizontal = True
    else:
        fmt = lambda pos: f"{LETTERS[pos]}. {md_escape(shown[pos])}"  # noqa: E731
        horizontal = False
    st.radio(
        "解答を選択",
        range(len(shown)),
        format_func=fmt,
        key=key,
        horizontal=horizontal,
        on_change=on_change,
        disabled=disabled,
    )


def render_exam() -> None:
    if remaining_sec() <= 0:
        finish_exam(timed_out=True)
        st.rerun()
    qs = st.session_state.questions
    i = st.session_state.current
    q = qs[i]
    n = len(qs)

    st.subheader(st.session_state.exam_title)
    left, right = st.columns([3, 2])
    with left:
        answered = sum(a is not None for a in st.session_state.answers)
        st.markdown(f"**問題 {i + 1} / {n}**　（解答済み {answered}）")
    with right:
        render_timer()
    st.progress((i + 1) / n)

    st.caption(f"{chapter_label(q['chapter'])} / {q['section']}")
    st.markdown(q["question"])
    if q.get("code"):
        st.code(q["code"], language="python")
    render_choices(q, st.session_state.orders[i], radio_key(i), st.session_state.answers[i], save_current_answer)

    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.button("← 前へ", disabled=i == 0, on_click=go, args=(-1,), width="stretch")
    with c3:
        if i < n - 1:
            st.button("次へ →", type="primary", on_click=go, args=(1,), width="stretch")
        else:
            st.button("採点する", type="primary", on_click=finish_exam, width="stretch")


def render_result() -> None:
    record = st.session_state.record
    qs = st.session_state.questions
    answers = st.session_state.answers
    orders = st.session_state.orders
    rate = record["correct"] / record["total"]

    st.title(f"結果：{record['title']}")
    if record.get("timedOut"):
        st.warning("制限時間に達したため、自動的に採点しました。")
    c1, c2, c3 = st.columns(3)
    c1.metric("正答数", f"{record['correct']} / {record['total']}")
    c2.metric("正答率", f"{rate:.1%}")
    c3.metric("判定", "合格" if rate >= PASS_RATE else "不合格")
    if rate >= PASS_RATE:
        st.success(f"合格です（合格ライン {int(PASS_RATE * 100)}%）")
    else:
        st.error(f"不合格です（合格ライン {int(PASS_RATE * 100)}%）")

    st.subheader("章ごとの正答数")
    st.dataframe(
        [
            {
                "章": chapter_label(int(ch)),
                "正答数": f"{v['correct']} / {v['total']}",
                "正答率": f"{v['correct'] / v['total']:.0%}",
            }
            for ch, v in record["byChapter"].items()
        ],
        hide_index=True,
        width="stretch",
    )

    st.subheader("全問の一覧")
    if not qs:
        st.info("この記録には問題ごとの解答が保存されていません（機能追加前の記録、または問題ファイルが見つかりません）。")
        st.button("開始画面に戻る", on_click=lambda: st.session_state.update(screen="start"))
        return
    n_wrong = sum(a != q["answerIndex"] for q, a in zip(qs, answers))
    st.button(
        f"間違えた問題を解き直す（{n_wrong}問）",
        type="primary",
        disabled=n_wrong == 0,
        on_click=start_review,
    )
    only_wrong = st.toggle("間違えた問題だけ表示する", key="only_wrong")
    shown = 0
    for i, (q, a, order) in enumerate(zip(qs, answers, orders)):
        ok = a == q["answerIndex"]
        if only_wrong and ok:
            continue
        shown += 1
        mark = "✅" if ok else ("⬜ 未解答" if a is None else "❌")
        with st.expander(f"{mark} 問題 {i + 1}（{q['section']}）{q['topic']}"):
            st.markdown(q["question"])
            if q.get("code"):
                st.code(q["code"], language="python")
            for pos, k in enumerate(order):
                tags = []
                if k == q["answerIndex"]:
                    tags.append("正解")
                if k == a:
                    tags.append("あなたの解答")
                head = f"**{LETTERS[pos]}**" + (f"　`{' / '.join(tags)}`" if tags else "")
                st.markdown(head)
                st.code(q["choices"][k], language="python")
            your = "未解答" if a is None else LETTERS[order.index(a)]
            st.markdown(f"**あなたの解答:** {your}　**正解:** {LETTERS[order.index(q['answerIndex'])]}")
            st.info(q["explanation"])
    if shown == 0:
        st.success("間違えた問題はありません。")

    st.button("開始画面に戻る", on_click=lambda: st.session_state.update(screen="start"))


def render_review() -> None:
    qs = st.session_state.review_questions
    i = st.session_state.review_current
    q = qs[i]
    n = len(qs)
    order = st.session_state.review_orders[i]
    checked = st.session_state.review_checked
    answer = st.session_state.review_answers[i]

    st.subheader(f"復習：{st.session_state.exam_title} の間違えた問題")
    n_checked = sum(checked)
    n_ok = sum(c and a == rq["answerIndex"] for rq, a, c in zip(qs, st.session_state.review_answers, checked))
    st.markdown(f"**問題 {i + 1} / {n}**　（答え合わせ済み {n_checked}・正解 {n_ok}）")
    st.progress((i + 1) / n)

    st.caption(f"{chapter_label(q['chapter'])} / {q['section']}")
    st.markdown(q["question"])
    if q.get("code"):
        st.code(q["code"], language="python")
    render_choices(q, order, review_key(i), answer, save_review_answer, disabled=checked[i])

    if checked[i]:
        correct = LETTERS[order.index(q["answerIndex"])]
        if answer == q["answerIndex"]:
            st.success(f"正解です（正解: {correct}）")
        else:
            st.error(f"不正解です（正解: {correct}）")
        st.info(q["explanation"])
    else:
        st.button("答え合わせ", type="primary", disabled=answer is None, on_click=check_review)

    if n_checked == n:
        st.success(f"復習完了：{n} 問中 {n_ok} 問正解しました。")

    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.button("← 前へ", disabled=i == 0, on_click=review_go, args=(-1,), width="stretch")
    with c2:
        st.button("結果画面に戻る", on_click=lambda: st.session_state.update(screen="result"), width="stretch")
    with c3:
        st.button("次へ →", disabled=i == n - 1, on_click=review_go, args=(1,), width="stretch")


# ---------------------------------------------------------------- main
init_state()
{"start": render_start, "exam": render_exam, "result": render_result, "review": render_review}[st.session_state.screen]()
