import traceback

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.utils.timezone import now

from langchain_core.messages import HumanMessage, AIMessage

import os
import json
import tempfile

from .models import ConversationLog, UserKnowledgeBase
from .langgraph_agent import construct_agent_graph, vector_store

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import PGVector
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings


# ----------------------------
# CONFIG
# ----------------------------
CONNECTION_STRING = (
    "postgresql+psycopg2://pgadmin_z9f3:R7u%21xVw2sKp%403yNq@localhost:6543/oinride"
)
EMBEDDINGS = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


# ----------------------------
# VIEWS
# ----------------------------


@csrf_exempt
@require_POST
def create_user(request):
    try:
        data = json.loads(request.body)
        username = data.get("username")
        collection_name = data.get("collection_name")

        if not username or not collection_name:
            return JsonResponse({"error": "username and collection_name are required"}, status=400)

        # Save to DB
        user_kb = UserKnowledgeBase.objects.create(
            username=username,
            collection_name=collection_name
        )

        return JsonResponse({
            "id": user_kb.id,
            "username": user_kb.username,
            "collection_name": user_kb.collection_name
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_POST
def delete_user(request):
    try:
        data = json.loads(request.body)
        username = data.get("username")

        if not username:
            return JsonResponse({"error": "Username is required"}, status=400)

        try:
            user = UserKnowledgeBase.objects.get(username=username)
        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

        user.delete()

        return JsonResponse({"message": f"✅ User '{username}' and all related data deleted."})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_all_users(request):
    """Return a list of all users with their collection names."""
    try:
        users = UserKnowledgeBase.objects.all().values("id", "username", "collection_name")

        if not users:
            return JsonResponse({"message": "No users found."}, status=200)

        return JsonResponse({"users": list(users)}, safe=False, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_POST
def upload_pdf(request):
    """Handle PDF upload, split into chunks, and save to PGVector DB."""
    try:
        username = request.GET.get("username", "").strip()
        collection_name = None
        if not username:
            return JsonResponse({"error": "Username parameter is required"}, status=400)

        try:
            user_kb = UserKnowledgeBase.objects.get(username=username)
            collection_name = user_kb.collection_name
        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

        if "file" not in request.FILES:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        # Save temp file
        pdf_file = request.FILES["file"]
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            for chunk in pdf_file.chunks():
                tmp_file.write(chunk)
            tmp_file_path = tmp_file.name

        # Load and split PDF
        loader = PyPDFLoader(tmp_file_path)
        documents = loader.load()
        if not documents:
            return JsonResponse({"error": "No text extracted from PDF"}, status=400)

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
        )
        docs = text_splitter.split_documents(documents)

        vectorstore = vector_store(collection_name)
        vectorstore.add_documents(docs)

        return JsonResponse({
            "message": "✅ PDF processed and chunks saved",
            "num_chunks": len(docs),
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_POST
@csrf_exempt
def ask_agent(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_input = data.get("question", "")
            username = request.GET.get("username", "").strip()
            if not username:
                return JsonResponse({"error": "Username parameter is required"}, status=400)

            # Check if user exists
            try:
                user_kb = UserKnowledgeBase.objects.get(username=username)
                collection_name = user_kb.collection_name
            except UserKnowledgeBase.DoesNotExist:
                return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

            # Run agent for that user
            logs = ConversationLog.objects.filter(user_knowledge_base=user_kb).order_by("-created_at")[:5]
            logs = reversed(logs)

            # Format as Human/AI chat style
            chat_history = ""
            for log in logs:
                chat_history += f"Human Message: {log.user_input}\n"
                chat_history += f"AI Response: {log.response}\n\n"

            if chat_history:
                chat_history = "This is the last 5 messages if the conversation:\n" + chat_history


            agent_graph = construct_agent_graph(collection_name)
            messages = agent_graph.invoke({"messages": [("user", user_input), ("system", chat_history)]})
            response = messages["messages"][-1].content

            # Save chat to DB
            ConversationLog.objects.create(
                user_input=user_input,
                response=response,
                created_at=now(),
                is_succeeded=True,
                user_knowledge_base=user_kb,  # FK relation
            )

            return JsonResponse({
                "username": username,
                "answer": response
            })

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Only POST allowed"}, status=405)


@csrf_exempt
def get_chat_history(request):
    if request.method == "GET":
        try:
            username = request.GET.get("username", "").strip()
            if not username:
                return JsonResponse({"error": "Username parameter is required"}, status=400)
                # Check if user exists
            try:
                user_kb = UserKnowledgeBase.objects.get(username=username)
            except UserKnowledgeBase.DoesNotExist:
                return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

            # Get the last 20 messages, newest first
            logs = ConversationLog.objects.filter(user_knowledge_base=user_kb).order_by("-created_at")[:20]

            # Convert them into a list of dicts
            history = [
                {
                    "id": log.id,
                    "question": log.user_input,
                    "answer": log.response,
                    "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "success": log.is_succeeded,
                }
                for log in logs
            ]

            return JsonResponse({"history": history}, safe=False)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Only GET allowed"}, status=405)


@csrf_exempt
@require_http_methods(["POST"])
def clear_chat_history(request):
    try:
        username = request.GET.get("username", "").strip()
        if not username:
            return JsonResponse({"error": "Username parameter is required"}, status=400)
        try:
            user_kb = UserKnowledgeBase.objects.get(username=username)
        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

        with transaction.atomic():
            ConversationLog.objects.filter(user_knowledge_base=user_kb).delete()

        return JsonResponse({"message": "✅ Conversation history cleared successfully."}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)