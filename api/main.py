"""
buzz_db API — FastAPI サーバー
================================
buzz_db.json を読み込み、GPT Actions から直接利用できる REST API を提供する。

起動方法:
    pip install fastapi uvicorn
    uvicorn api.main:app --reload --port 8000

エンドポイント一覧:
    GET /buzz/latest        最新の総合サマリー（GPT Actions メイン）
    GET /buzz/emotions      感情DB（ai_emotion_db）
    GET /buzz/compositions  構図DB（ai_composition_db）
    GET /buzz/questions     問いかけDB（ai_question_db）
    GET /buzz/generation    生成ルール（generation_rules）
    GET /healthz            ヘルスチェック
    GET /docs               Swagger UI（自動生成）
    GET /openapi.json       OpenAPI スキーマ
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# -----------------------------------------------------------------------
# パス設定
# -----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent   # プロジェクトルート
DB_PATH  = BASE_DIR / "buzz_db.json"


def load_db() -> dict[str, Any]:
    """buzz_db.json を読み込む。ファイルが見つからない場合は 503 を返す。"""
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail=f"buzz_db.json not found at {DB_PATH}")
    with DB_PATH.open(encoding="utf-8") as f:
        return json.load(f)


# -----------------------------------------------------------------------
# アプリ初期化
# -----------------------------------------------------------------------
app = FastAPI(
    title="Buzz Reel DB API",
    description=(
        "Instagram バズリール分析DBをGPT Actionsから利用するためのAPI。\n\n"
        "buzz_db.json を読み込み、感情・構図・問いかけ・生成ルールを返す。"
    ),
    version="1.0.0",
    contact={"name": "Buzz DB", "url": "https://github.com/your-repo/buzz-db"},
    license_info={"name": "MIT"},
    openapi_tags=[
        {"name": "buzz",   "description": "バズリール分析DB エンドポイント"},
        {"name": "system", "description": "ヘルスチェック"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # GPT Actions / 外部クライアントからのアクセスを許可
    allow_methods=["GET"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------
# レスポンスモデル
# -----------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    db_path: str
    db_updated_at: str | None


class LatestResponse(BaseModel):
    updated_at: str
    top_emotion: dict[str, Any]
    top_composition: dict[str, Any]
    top_question: dict[str, Any]
    generation_rules: dict[str, Any]


class EmotionsResponse(BaseModel):
    updated_at: str
    count: int
    entries: list[dict[str, Any]]


class CompositionsResponse(BaseModel):
    updated_at: str
    count: int
    entries: list[dict[str, Any]]


class QuestionsResponse(BaseModel):
    updated_at: str
    count: int
    entries: list[dict[str, Any]]


class GenerationResponse(BaseModel):
    updated_at: str
    generation_rules: dict[str, Any]


# -----------------------------------------------------------------------
# ユーティリティ
# -----------------------------------------------------------------------
def top_entry(entries: list[dict]) -> dict:
    """score で降順ソートして先頭を返す"""
    return sorted(entries, key=lambda x: x.get("score", 0), reverse=True)[0]


def filter_by_emotion(entries: list[dict], emotion_id: str) -> list[dict]:
    """best_emotion_ids に emotion_id を含むエントリを返す"""
    return [e for e in entries if emotion_id in e.get("best_emotion_ids", [])]


# -----------------------------------------------------------------------
# エンドポイント
# -----------------------------------------------------------------------

@app.get("/healthz", tags=["system"], response_model=HealthResponse, summary="ヘルスチェック")
def health_check() -> HealthResponse:
    """サーバーと buzz_db.json の疎通確認。"""
    try:
        db = load_db()
        updated_at = db.get("updated_at")
    except HTTPException:
        updated_at = None
    return HealthResponse(
        status="ok",
        db_path=str(DB_PATH),
        db_updated_at=updated_at,
    )


@app.get(
    "/buzz/latest",
    tags=["buzz"],
    response_model=LatestResponse,
    summary="最新サマリー（GPT Actions メイン）",
    description=(
        "スコア最上位の感情・構図・問いかけ と 生成ルールをまとめて返す。\n\n"
        "GPT Actions のメインエンドポイント。台本生成・画像生成の起点として使う。"
    ),
)
def get_latest(
    emotion_id: str | None = Query(
        default=None,
        description="絞り込む感情ID（例: loneliness, insomnia）。省略時は全体スコア最上位を返す。",
    )
) -> LatestResponse:
    db = load_db()

    emotion_entries     = db.get("ai_emotion_db",     {}).get("entries", [])
    composition_entries = db.get("ai_composition_db", {}).get("entries", [])
    question_entries    = db.get("ai_question_db",    {}).get("entries", [])
    rules               = db.get("generation_rules",  {})

    if not emotion_entries or not composition_entries or not question_entries:
        raise HTTPException(status_code=503, detail="ai_*_db エントリーが空です")

    # emotion_id 指定時は関連エントリを絞り込む
    if emotion_id:
        comp_filtered = filter_by_emotion(composition_entries, emotion_id) or composition_entries
        q_filtered    = filter_by_emotion(question_entries,    emotion_id) or question_entries
        em_filtered   = [e for e in emotion_entries if e.get("emotion_id") == emotion_id] or emotion_entries
    else:
        comp_filtered = composition_entries
        q_filtered    = question_entries
        em_filtered   = emotion_entries

    return LatestResponse(
        updated_at=db.get("updated_at", ""),
        top_emotion=top_entry(em_filtered),
        top_composition=top_entry(comp_filtered),
        top_question=top_entry(q_filtered),
        generation_rules=rules,
    )


@app.get(
    "/buzz/emotions",
    tags=["buzz"],
    response_model=EmotionsResponse,
    summary="感情DB一覧",
    description=(
        "ai_emotion_db の全エントリをスコア降順で返す。\n\n"
        "各エントリに ai_image_prompt・script_template・caption_template を含む。"
    ),
)
def get_emotions(
    limit: int = Query(default=10, ge=1, le=50, description="返却件数（最大50）"),
    min_score: float = Query(default=0.0, ge=0.0, le=10.0, description="スコアの下限フィルタ"),
) -> EmotionsResponse:
    db = load_db()
    entries = db.get("ai_emotion_db", {}).get("entries", [])
    filtered = [e for e in entries if e.get("score", 0) >= min_score]
    sorted_entries = sorted(filtered, key=lambda x: x.get("score", 0), reverse=True)[:limit]
    return EmotionsResponse(
        updated_at=db.get("updated_at", ""),
        count=len(sorted_entries),
        entries=sorted_entries,
    )


@app.get(
    "/buzz/compositions",
    tags=["buzz"],
    response_model=CompositionsResponse,
    summary="構図DB一覧",
    description=(
        "ai_composition_db の全エントリをスコア降順で返す。\n\n"
        "各エントリに full_prompt・negative_prompt を含む（画像生成AIに直渡し可）。"
    ),
)
def get_compositions(
    limit: int = Query(default=10, ge=1, le=50, description="返却件数（最大50）"),
    emotion_id: str | None = Query(default=None, description="感情IDで絞り込み（例: loneliness）"),
) -> CompositionsResponse:
    db = load_db()
    entries = db.get("ai_composition_db", {}).get("entries", [])
    if emotion_id:
        entries = filter_by_emotion(entries, emotion_id) or entries
    sorted_entries = sorted(entries, key=lambda x: x.get("score", 0), reverse=True)[:limit]
    return CompositionsResponse(
        updated_at=db.get("updated_at", ""),
        count=len(sorted_entries),
        entries=sorted_entries,
    )


@app.get(
    "/buzz/questions",
    tags=["buzz"],
    response_model=QuestionsResponse,
    summary="問いかけDB一覧",
    description=(
        "ai_question_db の全エントリをスコア降順で返す。\n\n"
        "placement（hook / ending）と best_emotion_ids で組み合わせを選択できる。"
    ),
)
def get_questions(
    limit: int = Query(default=10, ge=1, le=50, description="返却件数（最大50）"),
    placement: str | None = Query(
        default=None,
        description="配置場所フィルタ（hook / ending / hook_or_ending）",
    ),
    emotion_id: str | None = Query(default=None, description="感情IDで絞り込み"),
) -> QuestionsResponse:
    db = load_db()
    entries = db.get("ai_question_db", {}).get("entries", [])

    if placement:
        entries = [e for e in entries if placement in e.get("placement", "")]
    if emotion_id:
        entries = filter_by_emotion(entries, emotion_id) or entries

    sorted_entries = sorted(entries, key=lambda x: x.get("score", 0), reverse=True)[:limit]
    return QuestionsResponse(
        updated_at=db.get("updated_at", ""),
        count=len(sorted_entries),
        entries=sorted_entries,
    )


@app.get(
    "/buzz/generation",
    tags=["buzz"],
    response_model=GenerationResponse,
    summary="生成ルール",
    description=(
        "generation_rules を返す。\n\n"
        "GPT が台本・画像・キャプションを生成する際の行動指針として使う。"
    ),
)
def get_generation() -> GenerationResponse:
    db = load_db()
    rules = db.get("generation_rules", {})
    if not rules:
        raise HTTPException(status_code=404, detail="generation_rules が見つかりません")
    return GenerationResponse(
        updated_at=db.get("updated_at", ""),
        generation_rules=rules,
    )
