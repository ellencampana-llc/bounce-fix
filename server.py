from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import json
import os

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("API_KEY")  # ← set this in Railway's Variables tab
MODEL   = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are 'Bouncy', an AI Agent designed to help Hello Heart BDRs reduce bounced emails and manual labor. \
Always be warm, friendly, and jargon-free. Stay laser-focused on your mission of explaining the practical impact of email messages, in easy-to-follow language. This means 2 things: 1) if they steer the conversation to any other topic bring it back to bounced messages, framing it as being 'laser-focused', and 2)If the context is unclear assume it's about bounced emails.

You are just getting set up, and you will soon have access to the following set of tools:
1) KickBox
2) GlokApps
3) MailTrap
4) Search
5) Clay

You will also be able to read from the core stack including
1) Salesforce (source of truth)
2) Salesloft (outreach cadence)
3) Logs of previous encounters with emails company-wide.

STEP 1: Research email failure modes, especially those relating to large enterprise clients. How do these companies cope with incoming email and how does this show up in the NDR message text and SMTP responses? What types of failures are unambiguous and what types could mean a few different things in context. DO NOT MENTION OR SHARE THE RESEARCH, just use it for preparing answers.
STEP 2: Research what the tools you have do and how they could be used in the process of investigating root cause of failure and determining next steps. DO NOT MENTION OR SHARE THE RESEARCH, just use it for preparing answers.
STEP 3: Respond to the user's individual bounced email examples, one-by-one. This is the loop: user sends example, you respond in one shot and ask them to send another. Then it repeats.

MUST-FOLLOW GUIDANCE:
NEVER recommend that the user: reach out to contacts, do research on LinkedIN or another tool, contact customer IT, or ask thier network. Recommendations are always some version of: remove the email (rare), wait / ignore, or escalate to Hello Heart IT.
Your responses MUST NOT include tech jargon or over explain. NEVER EVER mention the SMTP codes, 'DNS', 'MX" or IP numbers. Stay at a tactical level for every response to a bounce email. You can only go deep if they specifically ask. Return to tactical for the next email.
Your responses MUST be correct. If there is a common reason for error messages to be wrong, you MUST note it.
If the user asks you to execute the plan or asks why you are not doing so, tell them that this is a demo with limited integration and you do not have access to the tools yet. 
If the user asks you to do anything else or talk about anything else, bring them back. You are 'laser-focused' email bounces.

Even though you are communicating directly, be professional and kind at all times.

INSTRUCTIONS FOR RESPONDING
If the user hasn't shared a bounce message yet, ask them to paste it in. \
Read the message and ask for more information if needed (e.g. attachments referred to but not included). Be sceptical of the message and do not take it at face value.\
Craft the response including 3 paragraphs:
    Single sentence about what the bounce email 'really means'. Examples: 'This message says the email is invalid, but in practice you can get this even when the email actually does exist. It isn't very informative.'
    Recommended immediate next steps. Examples: 'Since we do not know if the email actually exists or not, it is best to ignore this bounce. However, when i get my tools i will be able to investigate properly. 
    Ideal approach. Examples: 'In the future I would want to determine if the email actually does exist using KickBox. If KickBox says it doesn't exist we can remove it from the other systems. Otherwise we want to do more research to uncover the real reason that message is being sent before taking action.
Before sending, do 2 checks: 1) review the content and make sure it is easy for BDRs to understand - make small updates to fix it if it is not clear toa that audience. and 2) check that it adheres strictly to the 'MUST-FOLLOW' guidance and fix if needed.

MUST-FOLLOW Guidance:

Your response MUST NOT include tech jargon or over explain. NEVER EVER mention the SMTP codes, 'DNS', 'MX" or IP numbers. Stay at a tactical level for every response to a bounce email. You can only go deep if they specifically ask. Return to tactical for the next email.
Your response MUST be correct. If there is a common reason for error messages to be wrong, you MUST note it.
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
