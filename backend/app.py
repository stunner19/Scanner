"""
NSE Trading Scanner — Flask REST API with Upstox OAuth2.

Scanning uses a poll-based approach (not SSE) to work reliably on
Render's free tier which kills connections after 90s:
  POST /api/scan/start          → starts background scan, returns job_id
  GET  /api/scan/status/<id>    → poll this every second for progress + results
"""

import os
import json
import logging
import threading
import traceback
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

from strategies import get_strategy, get_strategy_list
from universe import get_universe, get_universe_names
from data_provider import exchange_code_for_token, preload_instruments
from token_manager import get_token_status
from scan_store import (
    create_job,
    get_job,
    update_progress,
    add_match,
    finish_job,
    fail_job,
    cleanup_old_jobs,
)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ── Auth ──────────────────────────────────────────────────────────────────────


@app.route("/api/auth/login-url")
def login_url():
    api_key = os.environ.get("UPSTOX_API_KEY", "").strip()
    redirect_uri = os.environ.get("UPSTOX_REDIRECT_URI", "").strip()
    if not api_key or not redirect_uri:
        return (
            jsonify({"error": "UPSTOX_API_KEY and UPSTOX_REDIRECT_URI must be set"}),
            500,
        )
    url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code&client_id={api_key}&redirect_uri={redirect_uri}"
    )
    return jsonify({"login_url": url})


@app.route("/api/auth/callback")
def auth_callback():
    code = request.args.get("code", "").strip()
    error = request.args.get("error", "").strip()
    if error:
        return jsonify({"error": f"Upstox login error: {error}"}), 400
    if not code:
        return jsonify({"error": "No authorization code received"}), 400
    try:
        exchange_code_for_token(code)
        frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:8080")
        return redirect(f"{frontend_url}?auth=success")
    except Exception as e:
        log.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ── Health ────────────────────────────────────────────────────────────────────


@app.route("/api/health")
def health():
    status = get_token_status()
    return jsonify(
        {
            "status": "ok",
            "token_valid": status["valid"],
            "token_age": status.get("age_hours"),
            "token_saved": status.get("saved_at"),
            "message": status["message"],
        }
    )


# ── Strategies & Universes ────────────────────────────────────────────────────


@app.route("/api/strategies")
def list_strategies():
    return jsonify(get_strategy_list())


@app.route("/api/universes")
def list_universes():
    return jsonify(
        [{"name": n, "count": len(get_universe(n))} for n in get_universe_names()]
    )


# ── Poll-based Scanner ────────────────────────────────────────────────────────


def _run_scan_background(job_id: str, strategy, tickers: list):
    """Runs in a background thread. Updates scan_store as stocks complete."""
    try:
        for event in strategy.run_stream(tickers):
            total = event.get("total", len(tickers))
            completed = event.get("completed", 0)
            update_progress(job_id, completed, total)
            if event.get("type") == "match":
                add_match(job_id, event)
        finish_job(job_id)
        log.info(f"Job {job_id} complete")
        cleanup_old_jobs()
    except Exception as e:
        log.error(traceback.format_exc())
        fail_job(job_id, str(e))


@app.route("/api/scan/start", methods=["POST"])
def scan_start():
    """Start a background scan. Returns job_id immediately."""
    status = get_token_status()
    if not status["valid"] or not status["access_token"]:
        return (
            jsonify({"error": "Not authenticated. Complete Upstox login first."}),
            401,
        )

    body = request.get_json(force=True) or {}
    strategy_name = body.get("strategy", "").strip()
    universe_name = body.get("universe", "").strip()

    if not strategy_name:
        return jsonify({"error": "strategy is required"}), 400
    if not universe_name:
        return jsonify({"error": "universe is required"}), 400

    strategy = get_strategy(strategy_name)
    if not strategy:
        return jsonify({"error": f"Unknown strategy: {strategy_name}"}), 404

    tickers = get_universe(universe_name)
    if not tickers:
        return jsonify({"error": f"Unknown universe: {universe_name}"}), 404

    job_id = create_job()
    thread = threading.Thread(
        target=_run_scan_background,
        args=(job_id, strategy, tickers),
        daemon=True,
    )
    thread.start()

    log.info(
        f"Job {job_id} started — {universe_name} / {strategy_name} / {len(tickers)} stocks"
    )
    return jsonify({"job_id": job_id, "total": len(tickers)})


@app.route("/api/scan/status/<job_id>")
def scan_status(job_id: str):
    """Poll this every second to get scan progress and results so far."""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


# ── Keep old /api/scan for local dev convenience ──────────────────────────────


@app.route("/api/scan", methods=["POST"])
def scan():
    status = get_token_status()
    if not status["valid"] or not status["access_token"]:
        return jsonify({"error": "Not authenticated"}), 401

    body = request.get_json(force=True) or {}
    strategy_name = body.get("strategy", "").strip()
    universe_name = body.get("universe", "").strip()

    strategy = get_strategy(strategy_name)
    tickers = get_universe(universe_name)

    if not strategy or not tickers:
        return jsonify({"error": "Invalid strategy or universe"}), 400

    try:
        results = strategy.run(tickers)
        results.sort(
            key=lambda x: (
                0 if x.get("strength") == "Strong" else 1,
                -abs(x.get("change_pct", 0)),
            )
        )
        return jsonify(
            {
                "strategy": strategy_name,
                "universe": universe_name,
                "total_scanned": len(tickers),
                "matches": len(results),
                "results": results,
            }
        )
    except Exception as e:
        log.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    status = get_token_status()
    log.info(f"Starting on http://localhost:{port}")
    log.info(f"Token status: {status['message']}")
    preload_instruments()
    app.run(host="0.0.0.0", port=port, debug=True)
