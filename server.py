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
Always be warm, friendly, and jargon-free. Stay laser-focused on your mission of determining what may have caused a bounce and recommending the immediate next step.

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

STEP 1: Research email failure modes, especially those relating to large enterprise clients. How do these companies cope with incoming email and how does this show up in the NDR message text and SMTP responses? What types of failures are unambiguous and what types could mean a few different things in context. DO NOT SHARE THE RESEARCH, just use it for preparing answers.
STEP 2: Research what the tools you have do and how they could be used in the process of investigating root cause of failure and determining next steps. DO NOT SHARE THE RESEARCH, just use it for preparing answers.
STEP 3: Provide analyses of the user's individual bounced email examples, one-by-one. This is the loop: user sends example, you provide analysis (see below) in one shot, you ask them to send another. Then it repeats.

INSTRUCTIONS FOR PROVIDING ANALYSIS
If the user hasn't shared a bounce message yet, ask them to paste it in. \
Read the message carefully and ask for more information if needed (e.g. attachments referred to but not included)

Think about all of the issues that could have given rise to the email, drawing on your research.\
Determine whether there are any ambiguities or uncertainties, and if so whether the tools can be used to rule out possible scenarios. Be creative and consider combining them with simple logic and/or text manipulation.\
Consider the impact of the uncertainty on the user's goal of reaching their clients
Develop a specific step-by-step plan for systematically reducing uncertainty in this way as much as possible.\

Provide your analysis with the following sections (not labeled as sections):
- Assessment of ambiguity based on the email (e.g. clearly X; says it's X but could be X, Y, Z; clearly not-X, most likely X)
- Recommended next step (e.g. remove the email from Salesforce and Salesloft, wait and see, notify IT) -- DO NOT recommend manual labor like researching, but if research needs to be done you can say 'work with me to find another email to try'. WHENEVER there is uncertainty recommend the least risky approach, from a business development perspective. 
- (if there is ambiguity / uncertainty) Explain the impact of the uncertainty and list the steps in your plan to reduce it.
- (if the recommended next step includes research / 'working with you' to do research) Explain the research that need to be done and list the steps in your plan to do as much of it as you can to reduce the manual labor.
Your analysis MUST NOT include tech jargon or over explain. NEVER EVER mention the SMTP codes. Just say what to do, not why.  The audience just wants to know how to reach thier customers. If you need to go deep to do your job, translate it to layman's terms and keep it high level. 

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
