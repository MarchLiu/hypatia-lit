"""Direct test: call Zhipu API via anthropic SDK (no Streamlit involved)."""

import os
import sys

# Remove auth_token so SDK won't add Bearer header
token = os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

import anthropic

base_url = "https://open.bigmodel.cn/api/anthropic"
model = os.getenv("ANTHROPIC_MODEL", "glm-5-turbo")

print(f"base_url: {base_url}")
print(f"model: {model}")
print(f"api_key: {token[:20]}...")
print()

try:
    with anthropic.Anthropic(api_key=token, base_url=base_url) as client:
        msg = client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "说一句话"}],
        )
        print(f"SUCCESS: {msg.content[0].text}")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
finally:
    os.environ["ANTHROPIC_AUTH_TOKEN"] = token
