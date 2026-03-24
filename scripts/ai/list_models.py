# scripts/ai/list_models.py
from google import genai
from config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

print("Available models for your API key:")
for model in client.models.list():
    print(f" - {model.name}")