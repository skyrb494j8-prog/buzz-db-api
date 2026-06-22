"""
buzz_db API — Flask サーバー
================================
buzz_db.json を読み込み、GPT Actions から直接利用できる REST API を提供する。

起動方法（ローカル）:
    pip install flask gunicorn
    python api/main.py

エンドポイント:
    GET /                   トップページ(UI)
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
from flask import Flask, jsonify, request, abort, render_template_string

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


# HTML テンプレート
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Buzz Generation UI</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --bg-primary: #ffffff;
            --bg-secondary: #f5f5f5;
            --text-primary: #000000;
            --text-secondary: #666666;
            --border-color: #e0e0e0;
            --accent-color: #6366f1;
            --accent-hover: #4f46e5;
            --error-color: #ef4444;
        }

        body.dark-mode {
            --bg-primary: #1a1a1a;
            --bg-secondary: #2d2d2d;
            --text-primary: #ffffff;
            --text-secondary: #cccccc;
            --border-color: #444444;
            --accent-color: #818cf8;
            --accent-hover: #6366f1;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen",
                "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue",
                sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            transition: background-color 0.3s, color 0.3s;
            min-height: 100vh;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
        }

        h1 {
            font-size: 28px;
            font-weight: 700;
            letter-spacing: -0.5px;
        }

        .theme-toggle {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 50%;
            width: 44px;
            height: 44px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s;
        }

        .theme-toggle:hover {
            background: var(--accent-color);
            color: white;
        }

        .form-group {
            margin-bottom: 24px;
        }

        label {
            display: block;
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--text-primary);
        }

        textarea {
            width: 100%;
            padding: 12px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            background-color: var(--bg-secondary);
            color: var(--text-primary);
            font-family: inherit;
            font-size: 14px;
            resize: vertical;
            min-height: 100px;
            transition: border-color 0.2s;
        }

        textarea:focus {
            outline: none;
            border-color: var(--accent-color);
        }

        button {
            width: 100%;
            padding: 12px 20px;
            background-color: var(--accent-color);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        button:hover:not(:disabled) {
            background-color: var(--accent-hover);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
        }

        button:active:not(:disabled) {
            transform: translateY(0);
        }

        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .result-section {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid var(--border-color);
        }

        .result-box {
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 20px;
            margin-top: 16px;
            min-height: 120px;
        }

        .result-box h3 {
            font-size: 14px;
            font-weight: 600;
            margin-top: 16px;
            margin-bottom: 8px;
            color: var(--text-primary);
        }

        .result-item {
            background-color: var(--bg-primary);
            border-left: 3px solid var(--accent-color);
            padding: 12px;
            margin-bottom: 12px;
            border-radius: 4px;
        }

        .result-item p {
            font-size: 14px;
            line-height: 1.6;
            margin-bottom: 4px;
        }

        .result-score {
            display: inline-block;
            background-color: var(--accent-color);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            margin-top: 4px;
        }

        .loading {
            display: none;
            text-align: center;
            padding: 20px;
        }

        .spinner {
            border: 3px solid var(--bg-secondary);
            border-top: 3px solid var(--accent-color);
            border-radius: 50%;
            width: 32px;
            height: 32px;
            animation: spin 0.8s linear infinite;
            margin: 0 auto;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .error {
            background-color: rgba(239, 68, 68, 0.1);
            border: 1px solid var(--error-color);
            color: var(--error-color);
            padding: 12px;
            border-radius: 8px;
            font-size: 14px;
            margin-top: 16px;
            display: none;
        }

        .empty-state {
            text-align: center;
            color: var(--text-secondary);
            padding: 40px 20px;
            font-size: 14px;
        }

        .info-text {
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 8px;
            line-height: 1.5;
        }

        @media (max-width: 600px) {
            .container {
                padding: 16px;
            }

            h1 {
                font-size: 24px;
            }

            header {
                margin-bottom: 32px;
            }

            button {
                padding: 14px 16px;
                font-size: 14px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎬 Buzz Generation</h1>
            <button class="theme-toggle" onclick="toggleTheme()" title="Toggle dark mode">
                <span id="theme-icon">🌙</span>
            </button>
        </header>

        <main>
            <form id="buzzForm" onsubmit="handleSubmit(event)">
                <div class="form-group">
                    <label for="emotion">感情を選択 (オプション)</label>
                    <textarea id="emotion" placeholder="例: 孤独感、依存感、眠れない..." style="min-height: 60px;"></textarea>
                    <p class="info-text">感情を入力するか空欄のままにしてください</p>
                </div>

                <button type="submit" id="generateBtn">🚀 生成を開始</button>
            </form>

            <div id="error" class="error"></div>

            <section class="result-section" id="resultSection" style="display: none;">
                <h2>📊 生成ルール</h2>
                <div id="loading" class="loading">
                    <div class="spinner"></div>
                    <p style="margin-top: 12px; color: var(--text-secondary);">取得中...</p>
                </div>
                <div id="resultBox" class="result-box"></div>
            </section>

            <div id="emptyState" class="empty-state">
                <p>✨ 上のフォームで生成を開始してください</p>
            </div>
        </main>
    </div>

    <script>
        // テーマ切り替え
        function toggleTheme() {
            const body = document.body;
            body.classList.toggle('dark-mode');
            const isDark = body.classList.contains('dark-mode');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            updateThemeIcon();
        }

        function updateThemeIcon() {
            const icon = document.getElementById('theme-icon');
            const isDark = document.body.classList.contains('dark-mode');
            icon.textContent = isDark ? '☀️' : '🌙';
        }

        // 初期化
        document.addEventListener('DOMContentLoaded', () => {
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme === 'dark') {
                document.body.classList.add('dark-mode');
                updateThemeIcon();
            }
        });

        // フォーム送信
        async function handleSubmit(event) {
            event.preventDefault();

            const btn = document.getElementById('generateBtn');
            const errorDiv = document.getElementById('error');
            const resultSection = document.getElementById('resultSection');
            const loadingDiv = document.getElementById('loading');
            const resultBox = document.getElementById('resultBox');
            const emptyState = document.getElementById('emptyState');

            // UI リセット
            errorDiv.style.display = 'none';
            resultBox.innerHTML = '';
            btn.disabled = true;
            loadingDiv.style.display = 'block';
            resultSection.style.display = 'block';
            emptyState.style.display = 'none';

            try {
                const response = await fetch('/buzz/generation');
                if (!response.ok) {
                    throw new Error(`API error: ${response.status}`);
                }

                const data = await response.json();
                loadingDiv.style.display = 'none';

                // 生成ルールを表示
                if (data.generation_rules) {
                    const rules = data.generation_rules;
                    let html = '';

                    if (rules.hook_rule) {
                        html += '<h3>🎯 フックルール</h3>';
                        html += '<div class="result-item"><p>' + escapeHtml(rules.hook_rule) + '</p></div>';
                    }

                    if (rules.script_rule) {
                        html += '<h3>📝 スクリプトルール</h3>';
                        html += '<div class="result-item"><p>' + escapeHtml(rules.script_rule) + '</p></div>';
                    }

                    if (rules.visual_rule) {
                        html += '<h3>🎨 ビジュアルルール</h3>';
                        html += '<div class="result-item"><p>' + escapeHtml(rules.visual_rule) + '</p></div>';
                    }

                    if (rules.ending_rule) {
                        html += '<h3>🎬 エンディングルール</h3>';
                        html += '<div class="result-item"><p>' + escapeHtml(rules.ending_rule) + '</p></div>';
                    }

                    if (rules.emotion_pairing_rule) {
                        html += '<h3>💫 感情ペアリングルール</h3>';
                        html += '<div class="result-item"><p>' + escapeHtml(rules.emotion_pairing_rule) + '</p></div>';
                    }

                    resultBox.innerHTML = html;
                } else {
                    resultBox.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">生成ルールが見つかりませんでした</p>';
                }

            } catch (error) {
                loadingDiv.style.display = 'none';
                errorDiv.textContent = '❌ エラー: ' + error.message;
                errorDiv.style.display = 'block';
            } finally {
                btn.disabled = false;
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
"""


# -----------------------------------------------------------------------
# エンドポイント
# -----------------------------------------------------------------------

@app.route("/")
def index():
    """トップページ(UI)"""
    return render_template_string(HTML_TEMPLATE)


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
