# scripts/test_ai.py
from google import genai
from config import GEMINI_API_KEY

# Initialize the client explicitly targeting the stable v1 API
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1'}
)

model = "gemini-2.5-flash"
prompt = "Give me a 5-word cycling motivation quote."

try:
    response = client.models.generate_content(
        model=model,
        contents=prompt
    )
    print(response.text)
except Exception as e:
    print(f"Error: {e}")