"""exams/exam-*.json を検査する.

使い方: uv run scripts/validate_exams.py [--textbook DIR]
エラーがあれば終了コード 1.
"""

from __future__ import annotations

import argparse
import difflib
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exam_core import APP_DIR, CHAPTERS, QUESTIONS_PER_EXAM, REQUIRED_FIELDS, list_exam_files, load_exam  # noqa: E402

SIM_WARN = 0.85
POSITION_REF = re.compile(r"選択肢\s*[A-DＡ-Ｄ1-4１-４ア-エ]|[1-4１-４一二三四最]\S{0,2}番目の選択肢|[A-D]\s*(?:が|は|の選択肢)正")


def norm(text: str | None) -> str:
    """重複判定用: 空白をすべて除去する."""
    return re.sub(r"\s+", "", text or "")


def norm_choice(text: str) -> str:
    """選択肢の重複判定用: 空白の違いも意味を持つので行末の空白だけ除く."""
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--textbook", type=Path, default=APP_DIR / "textbook", help="章.節フォルダがある教科書ディレクトリ")
    args = ap.parse_args()

    textbook_sections = {p.name for p in args.textbook.iterdir() if p.is_dir() and re.fullmatch(r"\d+\.\d+", p.name)}
    errors: list[str] = []
    warnings: list[str] = []
    files = list_exam_files()
    if not files:
        print("exams/ に exam-*.json がありません")
        return 1

    seen_ids: dict[str, str] = {}
    all_qs: list[tuple[str, dict]] = []
    section_counts: dict[str, Counter] = defaultdict(Counter)

    for path in files:
        name = path.name
        try:
            exam = load_exam(path)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: JSON を読めません: {e}")
            continue
        qs = exam["questions"]
        if len(qs) != QUESTIONS_PER_EXAM:
            errors.append(f"{name}: 問題数 {len(qs)} (期待値 {QUESTIONS_PER_EXAM})")

        ch_count = Counter(q.get("chapter") for q in qs)
        for ch, (title, n) in CHAPTERS.items():
            if ch_count.get(ch, 0) != n:
                errors.append(f"{name}: {ch}章 {title} の出題数 {ch_count.get(ch, 0)} (期待値 {n})")
        for ch in ch_count.keys() - CHAPTERS.keys():
            errors.append(f"{name}: 出題範囲外の章 {ch}")

        for q in qs:
            qid = q.get("id", "?")
            where = f"{name}:{qid}"
            for f in REQUIRED_FIELDS:
                v = q.get(f)
                if v is None or (isinstance(v, str) and not v.strip()):
                    errors.append(f"{where}: 必須項目 {f} が空")
            if "code" not in q:
                errors.append(f"{where}: code キーがない (なければ null)")
            elif q["code"] is not None and not str(q["code"]).strip():
                errors.append(f"{where}: code が空文字 (なければ null)")
            if qid in seen_ids:
                errors.append(f"{where}: id 重複 ({seen_ids[qid]})")
            seen_ids[qid] = name

            choices = q.get("choices") or []
            if len(choices) != 4:
                errors.append(f"{where}: 選択肢が {len(choices)} 個")
            if len({norm_choice(c) for c in choices}) != len(choices):
                errors.append(f"{where}: 選択肢に重複")
            ai = q.get("answerIndex")
            if not isinstance(ai, int) or isinstance(ai, bool) or not 0 <= ai <= 3:
                errors.append(f"{where}: answerIndex が不正 ({ai})")

            sec = str(q.get("section", ""))
            if not re.fullmatch(r"\d+\.\d+", sec) or sec.split(".")[0] != str(q.get("chapter")):
                errors.append(f"{where}: section {sec} と chapter {q.get('chapter')} が不整合")
            elif sec not in textbook_sections:
                errors.append(f"{where}: section {sec} は教科書フォルダにない (出題範囲外)")
            section_counts[sec][path.stem] += 1

            for f in ("question", "explanation"):
                if POSITION_REF.search(q.get(f) or ""):
                    warnings.append(f"{where}: {f} で選択肢を位置・記号で参照している可能性")
            for c in choices:
                if re.fullmatch(r"(すべて|全て)(正しい|誤り).*|該当なし|いずれでもない", c.strip()):
                    errors.append(f"{where}: 使用禁止の選択肢「{c}」")
            all_qs.append((name, q))

        # 同じ章の中で特定の節に偏っていないか
        for ch in CHAPTERS:
            secs = sorted(s for s in textbook_sections if s.split(".")[0] == str(ch))
            used = Counter(q["section"] for q in qs if q.get("chapter") == ch)
            if secs and used:
                limit = math.ceil(CHAPTERS[ch][1] / len(secs))
                for s, c in used.items():
                    if c > limit:
                        warnings.append(f"{name}: {ch}章で {s} に {c} 問偏っている (目安 {limit} 問以下)")

    # 重複チェック (全回・全問のペア)
    for i, (fa, a) in enumerate(all_qs):
        for fb, b in all_qs[i + 1 :]:
            pair = f"{fa}:{a.get('id')} と {fb}:{b.get('id')}"
            qa, qb = norm(a.get("question")), norm(b.get("question"))
            ca, cb = norm(a.get("code")), norm(b.get("code"))
            if qa == qb and ca == cb:
                errors.append(f"重複: {pair} (問題文・コードが完全一致)")
                continue
            if ca and ca == cb:
                errors.append(f"重複: {pair} (コードが完全一致)")
                continue
            q_sim = difflib.SequenceMatcher(None, qa, qb).ratio()
            c_sim = difflib.SequenceMatcher(None, ca, cb).ratio() if ca and cb else 0.0
            t_sim = difflib.SequenceMatcher(None, norm(a.get("topic")), norm(b.get("topic"))).ratio()
            if (q_sim >= SIM_WARN and (not ca or not cb or c_sim >= 0.6)) or c_sim >= SIM_WARN or t_sim >= SIM_WARN:
                warnings.append(f"類似: {pair} (問題文 {q_sim:.2f} / コード {c_sim:.2f} / topic {t_sim:.2f})")

    # 節ごとの出題済み回数
    stems = [p.stem for p in files]
    print("== 節ごとの出題済み回数 ==")
    print("節     " + " ".join(f"{s[-2:]:>3}" for s in stems) + "  合計")
    for sec in sorted(textbook_sections | set(section_counts), key=lambda s: tuple(map(int, s.split(".")))):
        cnt = section_counts.get(sec, Counter())
        total = sum(cnt.values())
        print(f"{sec:<6} " + " ".join(f"{cnt.get(s, 0):>3}" for s in stems) + f"  {total:>3}" + ("  ← 未出題" if total == 0 else ""))

    print(f"\n== 結果: {len(files)} 回 / {len(all_qs)} 問 ==")
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"エラー {len(errors)} 件 / 警告 {len(warnings)} 件")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
