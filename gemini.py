# To install: pip install -q -U google-genai

from google import genai

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()

context = ""

response = client.models.generate_content(
    model="gemini-2.5-flash", contents=context
)
print(response.text)