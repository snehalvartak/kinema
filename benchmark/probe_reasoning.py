import sys, os, json, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmark.run_benchmark import load_key

key = load_key()


def ask(model, extra):
    body = {"model": model,
            "messages": [{"role": "user", "content": "What is 17*23? Reply with just the number."}],
            "max_tokens": 500}
    body.update(extra)
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=120).read())
    m = d["choices"][0]["message"]
    u = d.get("usage", {}).get("completion_tokens_details", {})
    return f"content={str(m.get('content'))[:40]!r} reasoning_tokens={u.get('reasoning_tokens')}"


for model, extra in [
    ("z-ai/glm-5.3-flash", {"reasoning": {"enabled": False}}),
    ("z-ai/glm-5.3-flash", {"reasoning": {"effort": "low"}}),
    ("z-ai/glm-5.2", {"reasoning": {"enabled": False}}),
    ("z-ai/glm-4.5-air", {"reasoning": {"enabled": False}}),
    ("z-ai/glm-4.6", {"reasoning": {"enabled": False}}),
]:
    try:
        print(model, extra, "->", ask(model, extra))
    except Exception as e:
        print(model, extra, "-> FAIL", str(e)[:120])
