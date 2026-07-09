"""인텐트 분류기 학습 스크립트 — 계획 §4. (결정적·오프라인, LLM 미호출)

데이터셋 TSV(`질문<TAB>라벨`) → build_pipeline() 학습 → joblib 저장.
우선순위: data/intent_dataset.tsv(intent_gen.py 산출) 있으면 그것으로, 없으면
tests/fixtures/intent_seed.tsv(라벨당 소수 시드)로 학습한다 — 키 없는 환경에서도
동작하는 커밋용 모델을 만들 수 있게(스모크 수준). 실사용 정확도는 실데이터셋 필요.

실행: `uv run python -m chat.intent_train [데이터셋.tsv]`
"""
from __future__ import annotations

import sys
from pathlib import Path

import joblib

from chat.intent import MODEL_PATH, build_pipeline

_ROOT = Path(__file__).resolve().parents[1]
_REAL_DATASET = _ROOT / "data" / "intent_dataset.tsv"
_SEED_DATASET = _ROOT / "tests" / "fixtures" / "intent_seed.tsv"


def load_dataset(path: Path) -> tuple[list[str], list[str]]:
    texts, labels = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue  # 형식 위반 행은 건너뜀(임의 해석 금지)
        q, label = parts
        texts.append(q.strip())
        labels.append(label.strip())
    return texts, labels


def train(dataset_path: Path | None = None) -> Path:
    if dataset_path is None:
        dataset_path = _REAL_DATASET if _REAL_DATASET.exists() else _SEED_DATASET
    texts, labels = load_dataset(dataset_path)
    if not texts:
        raise SystemExit(f"학습 데이터가 비어 있습니다: {dataset_path}")

    pipe = build_pipeline()
    pipe.fit(texts, labels)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, MODEL_PATH)
    print(
        f"학습 완료: {len(texts)}개 샘플({len(set(labels))}라벨) "
        f"← {dataset_path.relative_to(_ROOT)}\n저장: {MODEL_PATH.relative_to(_ROOT)}"
    )
    return MODEL_PATH


if __name__ == "__main__":
    arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    train(arg)
