from langchain_google_genai import GoogleGenerativeAIEmbeddings
import os

# Set your Gemini API key
os.environ["GOOGLE_API_KEY"] = "your_api_key"

embedder = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
