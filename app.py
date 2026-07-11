import os
import uuid
import json
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory, abort
from werkzeug.utils import secure_filename

from analyzer import analyze_verilog
from optimizer import generate_optimizations
from report_generator import build_pdf_report

# ─────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
DB_FILE = os.path.join(BASE_DIR, "data", "history.json")

ALLOWED_EXTENSIONS = {".v", ".sv"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB, matches frontend copy

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE


# ─────────────────────────────────────────────────────────
# CORS (manual — avoids requiring flask-cors as a dependency)
# ─────────────────────────────────────────────────────────
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


@app.route("/api/<path:_path>", methods=["OPTIONS"])
def cors_preflight(_path):
    return ("", 204)


# ─────────────────────────────────────────────────────────
# Tiny JSON "database" for history / dashboard stats
# ─────────────────────────────────────────────────────────
def _load_db():
    if not os.path.exists(DB_FILE):
        return {"analyses": []}
    with open(DB_FILE, "r") as f:
        return json.load(f)


def _save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)


def _allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


# ─────────────────────────────────────────────────────────
# Routes — Health check
# ─────────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "vlsi-design-assistant-backend"})


# ─────────────────────────────────────────────────────────
# Routes — Upload + Analyze (the full pipeline)
# ─────────────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def upload_file():
    """
    Accepts a multipart/form-data upload under the field name 'file'.
    Runs analysis + optimization generation immediately and returns
    a single combined result (matches what the dashboard needs to render).
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part in request. Expected field name 'file'."}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not _allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type. Only .v and .sv files are allowed."}), 400

    original_name = secure_filename(file.filename)
    analysis_id = str(uuid.uuid4())[:8]
    stored_name = f"{analysis_id}_{original_name}"
    stored_path = os.path.join(UPLOAD_DIR, stored_name)
    file.save(stored_path)

    file_size_bytes = os.path.getsize(stored_path)
    if file_size_bytes > MAX_FILE_SIZE:
        os.remove(stored_path)
        return jsonify({"error": "File exceeds 5MB limit."}), 400

    with open(stored_path, "r", errors="ignore") as f:
        source_code = f.read()

    # ── Run analysis ──
    analysis_result = analyze_verilog(source_code, original_name)

    # ── Generate optimization suggestions ──
    optimizations = generate_optimizations(source_code, analysis_result)

    record = {
        "id": analysis_id,
        "filename": original_name,
        "stored_path": stored_path,
        "size_kb": round(file_size_bytes / 1024, 1),
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
        "analysis": analysis_result,
        "optimizations": optimizations,
    }

    db = _load_db()
    db["analyses"].insert(0, record)
    db["analyses"] = db["analyses"][:50]  # keep last 50
    _save_db(db)

    return jsonify({
        "id": analysis_id,
        "filename": original_name,
        "size_kb": record["size_kb"],
        "uploaded_at": record["uploaded_at"],
        "analysis": analysis_result,
        "optimizations": optimizations,
    }), 201


# ─────────────────────────────────────────────────────────
# Routes — Fetch a previous analysis by id
# ─────────────────────────────────────────────────────────
@app.route("/api/analysis/<analysis_id>", methods=["GET"])
def get_analysis(analysis_id):
    db = _load_db()
    record = next((a for a in db["analyses"] if a["id"] == analysis_id), None)
    if not record:
        abort(404, description="Analysis not found.")
    return jsonify(record)


# ─────────────────────────────────────────────────────────
# Routes — History / recent files / dashboard stats
# ─────────────────────────────────────────────────────────
@app.route("/api/history", methods=["GET"])
def history():
    db = _load_db()
    limit = int(request.args.get("limit", 10))
    items = [
        {
            "id": a["id"],
            "filename": a["filename"],
            "size_kb": a["size_kb"],
            "uploaded_at": a["uploaded_at"],
            "score": a["analysis"]["score"],
        }
        for a in db["analyses"][:limit]
    ]
    return jsonify(items)


@app.route("/api/stats", methods=["GET"])
def stats():
    """
    Aggregate stats for the dashboard's 5 stat cards
    (Total Analyses, Errors Found, Warnings, Optimizations, Success Rate).
    """
    db = _load_db()
    analyses = db["analyses"]

    total_analyses = len(analyses)
    total_errors = sum(a["analysis"]["counts"]["errors"] for a in analyses)
    total_warnings = sum(a["analysis"]["counts"]["warnings"] for a in analyses)
    total_optimizations = sum(len(a["optimizations"]) for a in analyses)

    if total_analyses > 0:
        avg_score = sum(a["analysis"]["score"] for a in analyses) / total_analyses
        success_rate = round(avg_score)
    else:
        success_rate = 0

    # sparkline-friendly trend (last 7 entries, oldest -> newest)
    recent = list(reversed(analyses[:7]))

    return jsonify({
        "total_analyses": total_analyses,
        "errors_found": total_errors,
        "warnings": total_warnings,
        "optimizations": total_optimizations,
        "success_rate": success_rate,
        "trends": {
            "analyses": [1 for _ in recent],
            "errors": [a["analysis"]["counts"]["errors"] for a in recent],
            "warnings": [a["analysis"]["counts"]["warnings"] for a in recent],
            "optimizations": [len(a["optimizations"]) for a in recent],
            "scores": [a["analysis"]["score"] for a in recent],
        }
    })


# ─────────────────────────────────────────────────────────
# Routes — PDF report generation
# ─────────────────────────────────────────────────────────
@app.route("/api/report/<analysis_id>", methods=["POST", "GET"])
def generate_report(analysis_id):
    db = _load_db()
    record = next((a for a in db["analyses"] if a["id"] == analysis_id), None)
    if not record:
        abort(404, description="Analysis not found.")

    pdf_filename = f"report_{analysis_id}.pdf"
    pdf_path = os.path.join(REPORTS_DIR, pdf_filename)

    build_pdf_report(record, pdf_path)

    return jsonify({
        "report_id": analysis_id,
        "download_url": f"/api/report/{analysis_id}/download",
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }), 201


@app.route("/api/report/<analysis_id>/download", methods=["GET"])
def download_report(analysis_id):
    pdf_filename = f"report_{analysis_id}.pdf"
    pdf_path = os.path.join(REPORTS_DIR, pdf_filename)
    if not os.path.exists(pdf_path):
        abort(404, description="Report not generated yet. POST to /api/report/<id> first.")
    return send_from_directory(REPORTS_DIR, pdf_filename, as_attachment=True)


@app.route("/api/report/last", methods=["GET"])
def download_last_report():
    """Serves the most recently generated report, for the 'Download Last Report' link."""
    files = sorted(
        (f for f in os.listdir(REPORTS_DIR) if f.endswith(".pdf")),
        key=lambda f: os.path.getmtime(os.path.join(REPORTS_DIR, f)),
        reverse=True,
    )
    if not files:
        abort(404, description="No reports generated yet.")
    return send_from_directory(REPORTS_DIR, files[0], as_attachment=True)


# ─────────────────────────────────────────────────────────
# Error handlers (return JSON, not HTML, for API consumers)
# ─────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": str(e.description) if hasattr(e, "description") else "Not found"}), 404


@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": str(e.description) if hasattr(e, "description") else "Bad request"}), 400


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File exceeds 5MB limit."}), 413


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error."}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)