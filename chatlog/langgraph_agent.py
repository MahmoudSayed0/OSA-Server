import os
from urllib.parse import quote_plus
from transformers import pipeline
from langgraph.prebuilt import create_react_agent
from langchain_community.tools import tool
from langchain_community.vectorstores import PGVector
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI


# ----------------------------
# CONFIG
# ----------------------------
# URL-encode the password to handle special characters like @ and !
_postgres_password = quote_plus(os.getenv('POSTGRES_PASSWORD', ''))
CONNECTION_STRING = (
    f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{_postgres_password}@{os.getenv('POSTGRES_HOST', 'db')}:{os.getenv('POSTGRES_PORT', 5432)}/{os.getenv('POSTGRES_DB')}"
)

print("CONNECTION_STRING")
print("CONNECTION_STRING")
print(CONNECTION_STRING)
EMBEDDINGS = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Foundation Knowledge Base collection name (shared by all users)
FOUNDATION_COLLECTION = 'foundation_mining_kb'

# OpenRouter API Key (for Mistral Devstral 2 2512)
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable is not set. Please set it in your .env file or docker-compose environment.")

# ----------------------------
# LLM (Mistral Devstral 2 2512 via OpenRouter - Free Tier)
# ----------------------------
llm = ChatOpenAI(
    model="mistralai/devstral-2512:free",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=0,
    max_tokens=2000
)


# ----------------------------
# AGENT INSTRUCTIONS - Professional Mining Safety AI
# ----------------------------
agent_instructions = """
You are Oinride's Professional Mining Safety & Compliance AI Agent - a specialized assistant for safety managers, supervisors, and environmental compliance officers in the mining industry.

## YOUR IDENTITY
You are a trusted safety expert that helps mining professionals ensure compliance with MSHA, OSHA, and state regulations. You provide authoritative, professional guidance while maintaining a helpful and supportive tone.

## MANDATORY TOOL USAGE
⚠️ CRITICAL: You MUST ALWAYS call the dual_retriever_tool for EVERY question. This searches BOTH:
1. **Official Regulations** (MSHA, OSHA, state mining codes) - authoritative source
2. **User's Documents** (uploaded procedures, SOPs, training materials)

## HOW YOU OPERATE

1. **FIRST STEP (MANDATORY)**: Call dual_retriever_tool to search ALL knowledge sources
2. **SECOND STEP**: Analyze retrieved content from BOTH official regulations AND user documents
3. **THIRD STEP**: Synthesize a professional, structured response
4. **FOURTH STEP**: Identify any conflicts between user docs and official regulations
5. **FIFTH STEP**: Format response with appropriate safety indicators

## RESPONSE FORMATTING GUIDELINES

### Icons & Emojis (USE THESE APPROPRIATELY):
- ⛏️ Mining operations and general mining topics
- 🦺 Safety equipment, PPE, protective measures
- ⚠️ Warnings, hazards, caution items
- 🔴 **CRITICAL** - Immediate action required
- 🟡 **WARNING** - Address within 24-48 hours
- 🟢 **INFO** - Best practice recommendation
- ✅ Requirements met, compliant items
- ❌ Non-compliance, violations
- 📋 Regulations, standards, codes
- 📊 Statistics, data, metrics
- 💡 Tips, recommendations, best practices
- 🔧 Equipment, maintenance, mechanical
- 👷 Personnel, training, workforce
- 🏗️ Construction, operations, infrastructure
- 🚨 Emergency, critical safety alerts
- 📖 Documentation, records, procedures

### Response Structure:
Always structure responses clearly:

1. **Summary** - Brief answer with key icon (1-2 sentences)
2. **Details** - Bullet points with relevant icons
3. **📋 Regulations** - Cite specific codes (e.g., `30 CFR 56.xxx`)
4. **💡 Action Items** - What the user should do

### Highlight Important Items:
- Use **bold** for critical terms and key points
- Use `code blocks` for regulation numbers (e.g., `30 CFR 75.360`)
- Use > blockquotes for direct regulation text
- Add [MSHA] or [OSHA] tags when citing sources

### Safety Priority Levels:
When discussing safety issues, categorize them:
- 🔴 **CRITICAL** - Immediate action required (life-threatening hazards)
- 🟡 **WARNING** - Address within 24-48 hours (significant risks)
- 🟢 **INFO** - Best practice recommendation (improvements)

## CONFLICT DETECTION (REAL-TIME)

When you notice that user's documents contain information that CONFLICTS with official MSHA/OSHA regulations:

1. Answer the user's question first
2. Then add a prominent COMPLIANCE ALERT section:

---
⚠️ **COMPLIANCE ALERT DETECTED**

**Your Document States:** "[quote from user doc]"

**Official Regulation Requires:**
> `[CFR code]`: "[quote from regulation]"

**🔴 Recommendation:** [specific action to fix the conflict]

---

## WHAT YOU CAN DO:
✅ Summarize information from regulations AND user documents
✅ Compare user procedures against official regulations
✅ Identify compliance gaps and non-compliance issues
✅ Explain procedures, regulations, and safety concepts
✅ Provide actionable recommendations based on regulations
✅ Cross-reference different CFR sections
✅ Generate compliance checklists

## WHAT YOU CANNOT DO:
❌ Answer without calling the retrieval tool first
❌ Make up information not in the knowledge base
❌ Provide medical diagnoses or legal judgments
❌ Skip citing regulation codes when they apply
❌ Ignore conflicts between user docs and regulations

## GUARDRAILS:

**Medical/Legal**: Direct users to qualified professionals for medical or legal matters.

**Critical Situations**: If query involves immediate danger:
> 🚨 **IMMEDIATE ACTION REQUIRED**: Follow emergency protocols and contact emergency services/supervisor immediately.

**Professional Tone**: Maintain professional language appropriate for safety managers and compliance officers.

**Confidentiality**: Only discuss information present in the knowledge base.

**Scope**: Focus exclusively on mining safety, compliance, and regulations.

## EXAMPLE RESPONSE FORMAT:

User: "What are our confined space entry requirements?"

---

## ⛏️ Confined Space Entry Requirements

Based on your uploaded procedures and MSHA regulations:

### ✅ Your Procedures Are Compliant With:
- Entry permit requirements match `30 CFR 75.1502`
- Attendant protocols are properly documented
- Rescue equipment staging follows best practices

### 🟡 **WARNING**: Gap Detected
Your SOP states atmospheric testing every 4 hours, but:

> `30 CFR 75.360`: "Before any shift...an examination shall be made for hazardous conditions."

**Recommendation:** Update testing frequency to pre-shift AND continuous monitoring.

### 📋 Relevant Regulations
- `30 CFR 75.1502` - Confined space entry permits [MSHA]
- `30 CFR 75.360` - Pre-shift examination [MSHA]
- `29 CFR 1910.146` - Permit-required confined spaces [OSHA]

### 💡 Action Items
1. 🔧 Review and update SOP-CS-001 testing frequency
2. 👷 Retrain supervisors on pre-shift requirements
3. 📖 Document all atmospheric test results

---
"""


def vector_store(collection_name):
    """Create a vector store connection for a given collection."""
    vectorstore = PGVector(
        connection_string=CONNECTION_STRING,
        embedding_function=EMBEDDINGS,
        collection_name=collection_name,
        use_jsonb=True,
    )
    return vectorstore


def get_foundation_vectorstore():
    """Get the Foundation Knowledge Base vector store (shared by all users)."""
    return vector_store(FOUNDATION_COLLECTION)


def construct_agent_graph(collection_name):
    """
    Construct the LangGraph agent with dual retrieval capability.
    Searches BOTH Foundation KB (official regulations) AND user's documents.
    """
    user_vectorstore = vector_store(collection_name)
    foundation_vectorstore = get_foundation_vectorstore()

    # ----------------------------
    # TOOLS
    # ----------------------------
    @tool
    def dual_retriever_tool(query: str) -> str:
        """
        MANDATORY TOOL: Search BOTH official regulations AND user's documents.

        This tool searches two knowledge sources:
        1. Foundation Knowledge Base - Official MSHA, OSHA, and state mining regulations
        2. User's Documents - Uploaded PDFs, SOPs, procedures, and training materials

        YOU MUST call this tool for EVERY user question before providing any answer.

        Returns: Combined results from official regulations and user documents.
        """
        print(f"[TOOL CALLED] dual_retriever_tool with query: '{query[:50]}...'")

        # Search Foundation KB (official regulations)
        try:
            foundation_results = foundation_vectorstore.similarity_search(query, k=4)
            print(f"[FOUNDATION KB] Found {len(foundation_results)} regulation chunks")
        except Exception as e:
            print(f"[FOUNDATION KB] Error: {e}")
            foundation_results = []

        # Search User's documents
        try:
            user_results = user_vectorstore.similarity_search(query, k=4)
            print(f"[USER DOCS] Found {len(user_results)} document chunks")
        except Exception as e:
            print(f"[USER DOCS] Error: {e}")
            user_results = []

        # Format output with clear source indicators
        output = ""

        # Foundation KB results (official regulations)
        if foundation_results:
            output += "## 📋 FROM OFFICIAL REGULATIONS (MSHA/OSHA):\n\n"
            for i, doc in enumerate(foundation_results, 1):
                reg_code = doc.metadata.get('regulation_code', '')
                category = doc.metadata.get('category', 'regulation').upper()
                filename = doc.metadata.get('filename', 'Unknown')

                if reg_code:
                    output += f"**[{category}] {reg_code}** (Source: {filename})\n"
                else:
                    output += f"**[{category}]** (Source: {filename})\n"
                output += f"{doc.page_content}\n\n---\n\n"
        else:
            output += "## 📋 FROM OFFICIAL REGULATIONS:\nNo matching regulations found in Foundation Knowledge Base.\n\n"

        # User document results
        if user_results:
            output += "## 📄 FROM YOUR DOCUMENTS:\n\n"
            for i, doc in enumerate(user_results, 1):
                filename = doc.metadata.get('filename', 'Unknown Document')
                output += f"**[YOUR DOC]** (Source: {filename})\n"
                output += f"{doc.page_content}\n\n---\n\n"
        else:
            output += "## 📄 FROM YOUR DOCUMENTS:\nNo matching content found in your uploaded documents.\n\n"

        if not foundation_results and not user_results:
            return "No relevant information found in either official regulations or your uploaded documents. Please ensure relevant documents are uploaded."

        return output

    agent_graph = create_react_agent(
        model=llm,
        tools=[dual_retriever_tool],
        prompt=agent_instructions
    )

    return agent_graph


# ----------------------------
# FOUNDATION KB HELPERS
# ----------------------------
def add_to_foundation_kb(chunks, metadata):
    """
    Add document chunks to the Foundation Knowledge Base.
    Used by admin endpoints when uploading official regulations.
    """
    foundation_vs = get_foundation_vectorstore()

    # Add metadata to each chunk
    texts = [chunk for chunk in chunks]
    metadatas = [metadata.copy() for _ in chunks]

    foundation_vs.add_texts(texts=texts, metadatas=metadatas)
    print(f"[FOUNDATION KB] Added {len(chunks)} chunks with metadata: {metadata.get('regulation_code', 'N/A')}")

    return len(chunks)


def search_foundation_kb(query, k=5):
    """
    Search only the Foundation Knowledge Base (for compliance checks).
    """
    foundation_vs = get_foundation_vectorstore()
    results = foundation_vs.similarity_search(query, k=k)
    return results


def search_user_docs(collection_name, query, k=5):
    """
    Search only user's documents (for compliance comparison).
    """
    user_vs = vector_store(collection_name)
    results = user_vs.similarity_search(query, k=k)
    return results
