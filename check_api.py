"""Day1: API connectivity check for Gemini and OpenAI."""

import os
from dotenv import load_dotenv

load_dotenv()


def check_gemini() -> None:
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Reply with exactly: GEMINI_OK",
    )
    text = response.text.strip()
    print(f"[Gemini] {text}")
    assert "GEMINI_OK" in text, f"Unexpected response: {text}"


def check_openai() -> None:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Reply with exactly: OPENAI_OK"}],
        max_tokens=10,
    )
    text = response.choices[0].message.content.strip()
    print(f"[OpenAI] {text}")
    assert "OPENAI_OK" in text, f"Unexpected response: {text}"


if __name__ == "__main__":
    print("=== API Connectivity Check ===")
    try:
        check_gemini()
    except Exception as e:
        print(f"[Gemini] FAILED: {e}")

    try:
        check_openai()
    except Exception as e:
        print(f"[OpenAI] FAILED: {e}")

    print("=== Done ===")
