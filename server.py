from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import json
import os

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("API_KEY")  # ← set this in Railway's Variables tab
MODEL   = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are 'Bouncy', an expert email deliverability assistant. \
Always be warm, friendly, and jargon-free. If the user hasn't shared a bounce message yet, ask them to paste it in. \
Unfortunately you are currently unable to access your tools so you can't solve all of the problems they may encounter\

When you receive a bounced email, review it carefully. Think about all of the issues that could have given rise to the email.\
Consider whether it is a hard or soft reject, whether the server stance may have led to this response, and if the email itself has an obvious error.\

Recommend a simple next step with one sentence -- no long explanation. Acknowledge that to them it may look like the email address is wrong (if that's what the bounce response says).\
Only recommend that they do research if you know that the email address is wrong but you cannot predict what the right one would be. \
It is perfectly fine to say that it needs to be removed without suggesting an alternative. 

Most of the time the answer will be 'do not remove it yet -- i will observe this one and make a recommendation when i have more data.\
Sometimes the recommendation will be to explicitly KEEP it because it is a temporary fail. 

Upon request you may provide explanations about why and you may also provide recommendations for tools to clear up ambiguity.\ 
"""
TOOLS = [
    {
        "type": "web_search_20250305",
        "name": "web_search"
    }
]

@app.route("/")
def index():
    return open("ellen-bounce-handler.html").read()

@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return "", 200

    body = request.get_json()
    messages = body.get("messages", [])

    payload = {
        "model": MODEL,
        "max_tokens": 2048,
        "system": SYSTEM_PROMPT,
        "tools": TOOLS,
        "messages": messages,
    }

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "interleaved-thinking-2025-05-14",
        },
        json=payload,
    )

    data = response.json()

    if not response.ok:
        return jsonify({"error": data.get("error", {}).get("message", "API error")}), response.status_code

    # Agentic loop: keep going if Claude wants to use a tool
    while data.get("stop_reason") == "tool_use":
        # Collect all tool use blocks
        tool_uses = [b for b in data["content"] if b["type"] == "tool_use"]

        # Build tool results
        tool_results = []
        for tool_use in tool_uses:
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use["id"],
                "content": "Search completed.",  # web_search handles its own results internally
            })

        # Add assistant turn + tool results to messages
        messages = messages + [
            {"role": "assistant", "content": data["content"]},
            {"role": "user", "content": tool_results},
        ]

        # Call again
        payload["messages"] = messages
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json=payload,
        )
        data = response.json()

        if not response.ok:
            return jsonify({"error": data.get("error", {}).get("message", "API error")}), response.status_code

    # Extract final text response
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    return jsonify({"text": text})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print(f"🚀 Ellen Campana server running on port {port}")
    app.run(host="0.0.0.0", port=port)
