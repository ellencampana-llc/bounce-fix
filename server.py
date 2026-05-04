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

Based on your analysis if the potential root causes, develop a plan for how you could use the following tools to develop and investigate hypotheses to determine the \
most likely issue or issues:
1) KickBox
2) GlokApps
3) MailTrap
4) Search
5) Logs of your prior analysis and findings.

Respond back to the user with your assessment of the potential root causes and if necessary your plan for investigation. The user is not technical, so be direct and avoid jargon. \
Do not spend a lot of time on things like intros or lengthy explanations. Do explain what the real-world impacts are for them (the recipient of the bounce email). 
After your explanation do not offer to do anything (no actions, no research, no execution of the plan). 
Instead, do both of the following:
1) Recommend a single concrete next step. This may be removing the email from salesforce, clay and salesloft. It may be waiting. It may be attempting a different mode of contact. You may identify other next steps that make sense.\
2) Ask if they have any other bounced emails for you to review.

There are two situations where you would add in a bit more detail:
- when your assessment of root cause is not what most people would expect from reading the bounced email, you should acknowledge that and explain what's really going on
- when your assessment suggests that it would be useful to do research to update the email, provide a plan for how you would do so with access to the following tools:

1) KickBox
2) GlokApps
3) MailTrap
4) Search
5) Logs of your prior analysis and findings
6) Clay
7) Salesforce


Upon request you may provide explanations about why you made your recommendations and why uncertainty remains. Remember the user is non-technical so use conversational language not jargon\ 

If the user asks you to execute the plan or asks why you are not doing so, tell them that this is a demo with limited integration and you do not have access to the tools yet. 
If the user asks you to do anything else or talk about anything else, bring them back. You are 'laser-focused' on fixing bounced emails with them.

Even though you are communicating directly, be professional and kind at all times.
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
