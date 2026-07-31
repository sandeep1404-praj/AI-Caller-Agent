"""HTTP webhook server for Twilio voice callbacks."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from caller import ClassCallAgentService
from utils import safe_json_dumps


def create_webhook_app(service: ClassCallAgentService, logger) -> Flask:
    """Create a Flask app that handles health checks and Twilio callbacks."""

    app = Flask(__name__)

    @app.get("/health")
    def health() -> Response:
        return jsonify({"status": "ok"})

    @app.post("/voice")
    def voice() -> Response:
        payload = request.form or request.args
        lecture_id = payload.get("lecture_id", "").strip()
        transcript = payload.get("SpeechResult", "").strip() or payload.get("Transcript", "").strip()
        call_sid = payload.get("CallSid", "").strip()
        attempt_number = int(payload.get("attempt_number", "0") or 0) or None

        if not lecture_id:
            logger.warning("Voice webhook missing lecture_id payload=%s", dict(payload))
            return Response(_twiml_say("We could not identify the lecture. Goodbye."), mimetype="application/xml")

        decision = service.process_voice_response(
            lecture_id=lecture_id,
            transcript=transcript,
            call_sid=call_sid,
            attempt_number=attempt_number,
        )
        logger.info("Voice webhook processed lecture_id=%s decision=%s", lecture_id, safe_json_dumps(decision.__dict__))
        return Response(_build_response_twiml(decision.status, decision.reason), mimetype="application/xml")

    return app


def _build_response_twiml(status: str, reason: str) -> str:
    if status in {"Available", "Late"}:
        message = "Thank you for confirming. Goodbye."
    elif status in {"Unavailable", "Leave", "Emergency", "Cancelled"}:
        message = "Thank you for the update. We will notify the department. Goodbye."
    elif status == "Retry Pending":
        message = "We did not get a clear answer. We will try again later. Goodbye."
    else:
        message = reason or "We could not confirm your availability. Goodbye."
    return _twiml_say(message)


def _twiml_say(message: str) -> str:
    return f"<?xml version='1.0' encoding='UTF-8'?><Response><Say>{message}</Say></Response>"
