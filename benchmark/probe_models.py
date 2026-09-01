"""Probe which OpenRouter models work with this key (never prints the key)."""
import json
import urllib.request

key = None
for line in open(".env"):
    line = line.strip()
    if line.startswith("OPENROUTER_API_KEY=") and len(line) > 20:
        key = line.split("=", 1)[1].strip()
assert key, "OPENROUTER_API_KEY missing in .env"


def ask(model, prompt="Reply with exactly: OK", max_tokens=400):
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps({"model": model,
                         "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": max_tokens}).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=90)
        d = json.loads(r.read())
        c = d["choices"][0]["message"]["content"]
        usage = d.get("usage", {})
        return f"OK reply={c[:20]!r} tokens={usage.get('total_tokens')}"
    except Exception as e:
        msg = str(e)
        try:
            body = e.read().decode()[:200]
        except Exception:
            body = ""
        return f"FAIL {msg[:60]} {body if 'body' in dir() else ''}"


if __name__ == "__main__":
    for m in ["z-ai/glm-5.3-flash", "z-ai/glm-5.2", "z-ai/glm-4.6", "z-ai/glm-4.5-air"]:
        print(m, "->", ask(m))
