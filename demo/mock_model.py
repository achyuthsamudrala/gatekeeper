"""Mock model server for blog demo.

Two endpoints with different behavior:
  POST /good/v1/chat/completions — returns the correct label (high accuracy)
  POST /bad/v1/chat/completions  — returns wrong labels (low accuracy)

Usage:
  uvicorn demo.mock_model:app --port 9000
"""

from __future__ import annotations

import hashlib
import json

from fastapi import FastAPI, Request

app = FastAPI()

LABELS = ["positive", "negative", "neutral"]


@app.post("/good/v1/chat/completions")
async def good_model(request: Request):
    """High-accuracy model: echoes the expected label from the input."""
    body = await request.json()
    content = body.get("messages", [{}])[0].get("content", "{}")
    try:
        row = json.loads(content.replace("'", '"'))
        label = row.get("expected_label", row.get("label", "positive"))
    except (json.JSONDecodeError, AttributeError):
        label = "positive"
    return {"text": label}


@app.post("/bad/v1/chat/completions")
async def bad_model(request: Request):
    """Low-accuracy model: returns a deterministic but usually wrong label."""
    body = await request.json()
    content = body.get("messages", [{}])[0].get("content", "{}")
    # Hash the input to get a deterministic but wrong answer
    h = int(hashlib.md5(content.encode()).hexdigest(), 16)
    try:
        row = json.loads(content.replace("'", '"'))
        correct = row.get("expected_label", row.get("label", "positive"))
        # Pick a different label ~70% of the time
        wrong_labels = [l for l in LABELS if l != correct]
        if h % 10 < 7:  # 70% wrong
            return {"text": wrong_labels[h % len(wrong_labels)]}
        return {"text": correct}
    except (json.JSONDecodeError, AttributeError):
        return {"text": LABELS[h % len(LABELS)]}


@app.get("/health")
async def health():
    return {"status": "ok"}
