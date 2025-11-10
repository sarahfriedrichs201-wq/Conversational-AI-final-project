# To install: pip install -q -U google-genai

from google import genai
from google.genai import types

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()

context = ""

response = client.models.generate_content(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(
        system_instruction="You are a large-scale code generation tool. When passed repository context and an instruction, please generate code to match the request."
    ),
    contents="Generate me a bubble sort algorithm"
)
print(response.text)