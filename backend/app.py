"""
NSE Trading Scanner — Flask REST API with Upstox OAuth2.

One-time setup:
  1. GET  /api/auth/login-url  → open this URL in browser
  2. Upstox redirects to /api/auth/callback?code=xxx automatically
  3. App exchanges code for long-lived token and saves to config.json
  4. All future scans work automatically — no daily login needed
"""

import os
import json
import logging
import traceback
from flask import Flask, jsonify, request, redirect, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

from strategies import get_strategy, get_strategy_list
from universe import get_universe, get_universe_names
from data_provider import exchange_code_for_token, preload_instruments
from token_manager import get_token_status

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ── Auth ──────────────────────────────────────────────────────────────────────


@app.route("/api/auth/login-url")
def login_url():
    api_key = os.environ.get("UPSTOX_API_KEY", "").strip()
    redirect_uri = os.environ.get("UPSTOX_REDIRECT_URI", "").strip()

    if not api_key or not redirect_uri:
        return (
            jsonify(
                {
                    "error": "UPSTOX_API_KEY and UPSTOX_REDIRECT_URI must be set in backend/.env"
                }
            ),
            500,
        )

    url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code"
        f"&client_id={api_key}"
        f"&redirect_uri={redirect_uri}"
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


# ── Scanner — SSE streaming endpoint ─────────────────────────────────────────


def _check_auth():
    status = get_token_status()
    if not status["valid"] or not status["access_token"]:
        return None, "Not authenticated. Complete one-time Upstox login first."
    return status, None


@app.route("/api/scan/stream", methods=["GET"])
def scan_stream():
    """
    Server-Sent Events endpoint — streams results live as each stock completes.
    The frontend receives matches immediately without waiting for all stocks.

    Query params: strategy=RSI Oversold&universe=Nifty 500
    """
    _, auth_err = _check_auth()
    if auth_err:
        return jsonify({"error": auth_err}), 401

    strategy_name = request.args.get("strategy", "").strip()
    universe_name = request.args.get("universe", "").strip()

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

    log.info(
        f"[SSE] Scanning '{universe_name}' ({len(tickers)} stocks) "
        f"with '{strategy_name}'"
    )

    def event_stream():
        try:
            matches = []
            for event in strategy.run_stream(tickers):
                if event["type"] == "match":
                    matches.append(event)

                # Send every event (progress + matches) to frontend
                yield f"data: {json.dumps(event)}\n\n"

            # Final summary event
            yield f"data: {json.dumps({'type': 'done', 'total_scanned': len(tickers), 'matches': len(matches)})}\n\n"

        except Exception as e:
            log.error(traceback.format_exc())
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx buffering on Render
        },
    )


# ── Scanner — classic blocking endpoint (kept for compatibility) ──────────────


@app.route("/api/scan", methods=["POST"])
def scan():
    _, auth_err = _check_auth()
    if auth_err:
        return jsonify({"error": auth_err}), 401

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

    log.info(
        f"Scanning '{universe_name}' ({len(tickers)} stocks) with '{strategy_name}'"
    )

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
    except EnvironmentError as e:
        return jsonify({"error": str(e)}), 401
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
