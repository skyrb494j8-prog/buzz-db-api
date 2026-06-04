"""
buzz_db API — Flask サーバー
================================
buzz_db.json を読み込み、GPT Actions から直接利用できる REST API を提供する。

起動方法（ローカル）:
    pip install flask gunicorn
    python api/main.py

エンドポイント:
    GET /healthz
    GET /buzz/latest        ?emotion_id=loneliness
    GET /buzz/emotions      ?limit=10&min_score=0
    GET /buzz/compositions  ?limit=10&emotion_id=loneliness
    GET /buzz/questions     ?limit=10&placement=ending&emotion_id=loneliness
    GET /buzz/generation
"""

import json
import os
from pathlib import Path
from flask import Flask, jsonify, request, abort

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "buzz_db.json"


def load_db():
    if not DB_PATH.exists():
        abort(503, description=f"buzz_db.json not found at {DB_PATH}")
    with DB_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def top_entry(entries):
    return sorted(entries, key=lambda x: x.get("score", 0), reverse=True)[0]


def filter_by_emotion(entries, emotion_id):
    return [e for e in entries if emotion_id in e.get("best_emotion_ids", [])]


# -----------------------------------------------------------------------
# エンドポイント
# -----------------------------------------------------------------------

@app.route("/healthz")
def health():
    try:
        db = load_db()
        updated_at = db.get("updated_at")
        status = "ok"
    except Exception:
        updated_at = None
        status = "error"
    return jsonify({"status": status, "db_path": str(DB_PATH), "db_updated_at": updated_at})


@app.route("/buzz/latest")
def buzz_latest():
    db = load_db()
    emotion_id = request.args.get("emotion_id")

    emotions     = db.get("ai_emotion_db",     {}).get("entries", [])
    compositions = db.get("ai_composition_db", {}).get("entries", [])
    questions    = db.get("ai_question_db",    {}).get("entries", [])
    rules        = db.get("generation_rules",  {})

    if not emotions or not compositions or not questions:
        abort(503, description="ai_*_db エントリーが空です")

    if emotion_id:
        em_list   = [e for e in emotions if e.get("emotion_id") == emotion_id] or emotions
        comp_list = filter_by_emotion(compositions, emotion_id) or compositions
        q_list    = filter_by_emotion(questions, emotion_id) or questions
    else:
        em_list, comp_list, q_list = emotions, compositions, questions

    return jsonify({
        "updated_at":      db.get("updated_at", ""),
        "top_emotion":     top_entry(em_list),
        "top_composition": top_entry(comp_list),
        "top_question":    top_entry(q_list),
        "generation_rules": rules,
    })


@app.route("/buzz/emotions")
def buzz_emotions():
    db = load_db()
    limit     = min(int(request.args.get("limit", 10)), 50)
    min_score = float(request.args.get("min_score", 0))
    entries   = db.get("ai_emotion_db", {}).get("entries", [])
    filtered  = sorted(
        [e for e in entries if e.get("score", 0) >= min_score],
        key=lambda x: x.get("score", 0), reverse=True
    )[:limit]
    return jsonify({"updated_at": db.get("updated_at", ""), "count": len(filtered), "entries": filtered})


@app.route("/buzz/compositions")
def buzz_compositions():
    db = load_db()
    limit      = min(int(request.args.get("limit", 10)), 50)
    emotion_id = request.args.get("emotion_id")
    entries    = db.get("ai_composition_db", {}).get("entries", [])
    if emotion_id:
        entries = filter_by_emotion(entries, emotion_id) or entries
    sorted_entries = sorted(entries, key=lambda x: x.get("score", 0), reverse=True)[:limit]
    return jsonify({"updated_at": db.get("updated_at", ""), "count": len(sorted_entries), "entries": sorted_entries})


@app.route("/buzz/questions")
def buzz_questions():
    db = load_db()
    limit      = min(int(request.args.get("limit", 10)), 50)
    placement  = request.args.get("placement")
    emotion_id = request.args.get("emotion_id")
    entries    = db.get("ai_question_db", {}).get("entries", [])
    if placement:
        entries = [e for e in entries if placement in e.get("placement", "")]
    if emotion_id:
        entries = filter_by_emotion(entries, emotion_id) or entries
    sorted_entries = sorted(entries, key=lambda x: x.get("score", 0), reverse=True)[:limit]
    return jsonify({"updated_at": db.get("updated_at", ""), "count": len(sorted_entries), "entries": sorted_entries})


@app.route("/buzz/generation")
def buzz_generation():
    db    = load_db()
    rules = db.get("generation_rules", {})
    if not rules:
        abort(404, description="generation_rules が見つかりません")
    return jsonify({"updated_at": db.get("updated_at", ""), "generation_rules": rules})


# -----------------------------------------------------------------------
# エラーハンドラ
# -----------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": str(e)}), 404

@app.errorhandler(503)
def service_unavailable(e):
    return jsonify({"error": str(e)}), 503


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
