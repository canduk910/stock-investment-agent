"""OpenAI 임베딩 — RAG 청크·쿼리 벡터화(text-embedding-3-small).

배치 입력(한 호출에 여러 텍스트)으로 효율화. 클라이언트는 infra.config 의 키로 생성(하드코딩 금지).
임베딩은 chat/completions 가 아니므로 reasoning_effort 등 CHAT_MODEL_PARAMS 와 무관.
"""
from __future__ import annotations

import numpy as np

EMBED_MODEL = "text-embedding-3-small"


def _make_client():
    from openai import OpenAI

    from infra.config import openai_api_key

    return OpenAI(api_key=openai_api_key())


def embed_texts(texts, client=None) -> np.ndarray:
    """텍스트 리스트 → (n, dim) float32 임베딩 행렬. 빈 입력은 (0, 0)."""
    items = [t for t in (texts or []) if t]
    if not items:
        return np.zeros((0, 0), dtype="float32")
    if client is None:
        client = _make_client()
    resp = client.embeddings.create(model=EMBED_MODEL, input=items)
    return np.array([d.embedding for d in resp.data], dtype="float32")


def embed_query(text, client=None) -> np.ndarray:
    """단일 쿼리 → (dim,) float32 벡터. 빈 입력은 (0,)."""
    m = embed_texts([text], client=client)
    return m[0] if m.shape[0] else np.zeros((0,), dtype="float32")
