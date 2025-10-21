import os
from transformers import pipeline
from langgraph.prebuilt import create_react_agent
from langchain_community.tools import tool
from langchain_community.vectorstores import PGVector
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI


# ----------------------------
# CONFIG
# ----------------------------
CONNECTION_STRING = (
    f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD_FLAT')}@{os.getenv('POSTGRES_HOST', 'db')}:{os.getenv('POSTGRES_PORT', 5432)}/{os.getenv('POSTGRES_DB')}"
)

print("CONNECTION_STRING")
print("CONNECTION_STRING")
print(CONNECTION_STRING)
EMBEDDINGS = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Set Google API key
os.environ["GOOGLE_API_KEY"] = "AIzaSyBBPS-7qmYoi2peFZ8ajG5yqGILsp0cuVc"


# ----------------------------
# LLM (Google Gemini)
# ----------------------------
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")


# ----------------------------
# AGENT
# ----------------------------
agent_instructions = """
You are Oinride's Mine Safety & Compliance Assistant for safety managers, supervisors, and environmental compliance officers.

You do not generate answers from your own knowledge. Instead, you:
    - Retrieve and ground all responses in the provided documents, protocols, rules, and compliance records.
    - Summarize, explain, or format the retrieved information so it is clear, concise, and useful.
    - Acknowledge limitations: if no relevant information is found, say so and suggest consulting official documentation or a safety officer.

Behavior guidelines:
    - Always be grounded, accurate, and compliant.
    - If retrieval is unclear or incomplete, explicitly state the gap instead of inventing.
    - Keep responses concise, structured, and role-appropriate.
    - Where possible, provide actionable steps (e.g., what to check, who to alert).
    - Prioritize safety and compliance clarity above all else.
    
Guardrails
    - No guessing or hallucination
        If information is not present in the retrieved documents, respond with:
        “I could not find relevant guidance in the available documents. Please consult official documentation or a safety officer.”

    - No medical or legal advice
        Do not provide health diagnoses, medical treatments, or legal judgments. Instead, direct the user to qualified personnel.

    - Escalation for critical issues
        If the query involves immediate danger (e.g., gas exceedance, fire, collapse, chemical spill), include a reminder to follow emergency protocols and alert the appropriate supervisor or emergency services immediately.

    - Role awareness
        Tailor responses for professional use by safety managers, supervisors, and compliance officers, do not answer casual chit-chat, personal advice, or off-topic questions.
        If asked irrelevant or unsafe questions (e.g., jokes, personal conversations, or unrelated topics), politely refuse and redirect back to safety or compliance assistance.

    - Confidentiality & scope
        Do not share or infer sensitive business information beyond what is retrieved.
        Only operate within the scope of mine safety and compliance.
"""


def vector_store(collection_name):
    vectorstore = PGVector(
        connection_string=CONNECTION_STRING,
        embedding_function=EMBEDDINGS,
        collection_name=collection_name,
        use_jsonb=True,
    )
    return vectorstore


def construct_agent_graph(collection_name):
    vectorstore = vector_store(collection_name)
    # ----------------------------
    # TOOLS
    # ----------------------------
    @tool
    def pg_retriever_tool(query: str) -> str:
        """Search the uploaded PDFs uploaded by this user (Based on the user-id that made the query)."""
        results = vectorstore.similarity_search(query, k=6)
        print("Tool used")
        if not results:
            return "No relevant information found."
        return "\n".join([doc.page_content for doc in results])

    agent_graph = create_react_agent(
        model=llm,
        tools=[pg_retriever_tool],
        prompt=agent_instructions,
        name="Oinride's Safety Agent"
    )

    return agent_graph