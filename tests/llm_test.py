from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
load_dotenv()
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",

    temperature=0.5,
    )
# result = llm.invoke("Sing a ballad of LangChain.")
# print(result.content)
from langchain_deepseek import ChatDeepSeek

llm = ChatDeepSeek(
    model="deepseek-chat",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    # other params...
)

response = llm.invoke("Say 'Hello, world!' in JSON format.")
print(response.content)