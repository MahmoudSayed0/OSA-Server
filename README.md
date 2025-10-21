# 🧠 AI PDF Chat Assistant

An intelligent document assistant built with **Django**, **LangGraph**, and **Hugging Face models**.  
Each user can upload their own PDFs, and the system creates searchable vector embeddings in PostgreSQL using the **pgvector** extension.  
The user can then chat with the AI agent to get accurate, context-aware answers based on their uploaded documents.

---

## 🚀 Features

✅ **User-Specific Knowledge Bases**  
Each user uploads their own documents, and the system stores embeddings separately to ensure privacy and data isolation.

✅ **PDF Upload & Processing**  
PDFs are automatically split into text chunks, embedded using a Hugging Face model, and stored in PostgreSQL.

✅ **Conversational AI Agent**  
A LangGraph-powered agent retrieves relevant text from the user’s documents and provides context-based answers.

✅ **Conversation History**  
All user questions and AI responses are stored in a log for auditing or display in the frontend.

✅ **APIs for User & Data Management**
- Create/Delete user (POST)
- Get all users (GET)
- Upload PDF (POST)
- Ask agnet (POST)
- Retrieve chat history (GET)
- Clear chat history (POST)

---

## 🧩 Tech Stack

| Component | Technology |
|------------|-------------|
| **Backend** | Django (Python) |
| **AI Framework** | LangGraph |
| **Embeddings Model** | Hugging Face Sentence Transformers |
| **Vector Database** | PostgreSQL + pgvector |
| **Frontend (optional)** | Can connect via Postman, React, or any API consumer |

---

## Prerequisites

Make sure these are installed:
* Python 3.10+
* Docker Desktop

--

## Start The Server
Run the following commands in this order: 

```
docker-compose -f ./docker-compose/docker-compose.yml build
```

```
docker-compose -f ./docker-compose/docker-compose.yml up
```

