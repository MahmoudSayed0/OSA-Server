import traceback

from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.utils.timezone import now
from django.conf import settings

from langchain_core.messages import HumanMessage, AIMessage

import os
import json
import tempfile
import shutil
from pathlib import Path

from .models import ConversationLog, UserKnowledgeBase, UploadedPDF, ChatSession, ChatMessage
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

        # Get file and check size limit (10MB)
        pdf_file = request.FILES["file"]
        file_size = pdf_file.size
        filename = pdf_file.name

        # 10MB size limit
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes
        if file_size > MAX_FILE_SIZE:
            return JsonResponse({
                "error": f"File size exceeds 10MB limit. Your file is {file_size / (1024*1024):.1f}MB"
            }, status=400)

        # Create media directory structure
        pdf_dir = Path(settings.MEDIA_ROOT) / 'pdfs' / username
        pdf_dir.mkdir(parents=True, exist_ok=True)

        # Create unique filename to avoid conflicts
        import uuid
        unique_filename = f"{uuid.uuid4()}_{filename}"
        pdf_file_path = pdf_dir / unique_filename

        # Save PDF file permanently
        with open(pdf_file_path, 'wb') as destination:
            for chunk in pdf_file.chunks():
                destination.write(chunk)

        # Load and split PDF using the saved file
        loader = PyPDFLoader(str(pdf_file_path))
        documents = loader.load()
        if not documents:
            # Clean up saved file if processing fails
            pdf_file_path.unlink(missing_ok=True)
            return JsonResponse({"error": "No text extracted from PDF"}, status=400)

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
        )
        docs = text_splitter.split_documents(documents)

        vectorstore = vector_store(collection_name)
        vectorstore.add_documents(docs)

        # Save PDF metadata to database with file path
        relative_path = f"pdfs/{username}/{unique_filename}"
        uploaded_pdf = UploadedPDF.objects.create(
            user_knowledge_base=user_kb,
            filename=filename,
            file_path=relative_path,
            file_size=file_size,
            chunks_count=len(docs)
        )

        return JsonResponse({
            "message": "✅ PDF processed and chunks saved",
            "num_chunks": len(docs),
            "pdf_id": uploaded_pdf.id,
            "filename": filename,
            "file_size": file_size,
            "file_url": f"/media/{relative_path}"
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
            session_id = data.get("session_id")  # NEW: Get session_id from request

            if not username:
                return JsonResponse({"error": "Username parameter is required"}, status=400)

            if not user_input:
                return JsonResponse({"error": "Question is required"}, status=400)

            # Check if user exists
            try:
                user_kb = UserKnowledgeBase.objects.get(username=username)
                collection_name = user_kb.collection_name
            except UserKnowledgeBase.DoesNotExist:
                return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

            # Get or verify session
            session = None
            if session_id:
                try:
                    session = ChatSession.objects.get(
                        session_id=session_id,
                        user_knowledge_base=user_kb
                    )
                except ChatSession.DoesNotExist:
                    return JsonResponse({"error": "Session not found or does not belong to this user"}, status=404)
            else:
                # If no session_id provided, create a new session
                session = ChatSession.objects.create(
                    user_knowledge_base=user_kb,
                    title="New Chat"
                )

            # Get chat history from session messages (last 10 messages)
            previous_messages = session.messages.order_by('-created_at')[:10]
            previous_messages = reversed(list(previous_messages))

            # Format chat history
            chat_history = ""
            for msg in previous_messages:
                if msg.role == 'user':
                    chat_history += f"Human Message: {msg.content}\n"
                elif msg.role == 'assistant':
                    chat_history += f"AI Response: {msg.content}\n\n"

            if chat_history:
                chat_history = "This is the last conversation history:\n" + chat_history

            # Run AI agent
            agent_graph = construct_agent_graph(collection_name)
            messages = agent_graph.invoke({"messages": [("user", user_input), ("system", chat_history)]})
            ai_response = messages["messages"][-1].content

            # Save user message to ChatMessage
            user_message = ChatMessage.objects.create(
                session=session,
                role='user',
                content=user_input
            )

            # Save AI response to ChatMessage
            ai_message = ChatMessage.objects.create(
                session=session,
                role='assistant',
                content=ai_response,
                metadata={}
            )

            # Update session timestamp (triggers auto-update of updated_at)
            session.save()

            # Also save to ConversationLog for backward compatibility
            log = ConversationLog.objects.create(
                user_input=user_input,
                response=ai_response,
                created_at=now(),
                is_succeeded=True,
                user_knowledge_base=user_kb,
            )

            return JsonResponse({
                "username": username,
                "answer": ai_response,
                "id": log.id,
                "session_id": str(session.session_id),
                "message_id": str(ai_message.message_id)
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


@csrf_exempt
@require_http_methods(["GET"])
def list_pdfs(request):
    """List all PDFs uploaded by a user."""
    try:
        username = request.GET.get("username", "").strip()

        if not username:
            return JsonResponse({"error": "Username parameter is required"}, status=400)

        try:
            user_kb = UserKnowledgeBase.objects.get(username=username)
        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

        # Get all PDFs for this user
        pdfs = UploadedPDF.objects.filter(user_knowledge_base=user_kb)

        documents = [{
            'id': pdf.id,
            'filename': pdf.filename,
            'size': f"{pdf.file_size / (1024*1024):.1f} MB",
            'file_size': pdf.file_size,
            'chunks_count': pdf.chunks_count,
            'upload_date': pdf.uploaded_at.isoformat(),
            'file_url': f"/chatlog/get-pdf/{pdf.id}/?username={username}"
        } for pdf in pdfs]

        return JsonResponse({
            'documents': documents,
            'count': len(documents)
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
def delete_pdf(request):
    """Delete a PDF from user's list."""
    try:
        username = request.GET.get("username", "").strip()

        if not username:
            return JsonResponse({"error": "Username parameter is required"}, status=400)

        # Get pdf_id from request body or query params
        if request.method == "POST":
            data = json.loads(request.body)
            pdf_id = data.get("pdf_id")
        else:  # DELETE method
            pdf_id = request.GET.get("pdf_id")

        if not pdf_id:
            return JsonResponse({"error": "pdf_id is required"}, status=400)

        try:
            user_kb = UserKnowledgeBase.objects.get(username=username)
        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

        # Find the PDF and verify it belongs to this user
        try:
            pdf = UploadedPDF.objects.get(id=pdf_id, user_knowledge_base=user_kb)
        except UploadedPDF.DoesNotExist:
            return JsonResponse({"error": "PDF not found or does not belong to this user"}, status=404)

        filename = pdf.filename

        # Delete the physical file if it exists
        if pdf.file_path:
            file_full_path = Path(settings.MEDIA_ROOT) / pdf.file_path
            if file_full_path.exists():
                file_full_path.unlink()

        pdf.delete()

        return JsonResponse({
            "message": f"✅ PDF '{filename}' deleted successfully",
            "deleted_pdf_id": int(pdf_id)
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_pdf_file(request, pdf_id):
    """
    Serve PDF file for preview.
    GET /chatlog/get-pdf/<pdf_id>/?username=<username>
    """
    try:
        username = request.GET.get("username", "").strip()

        if not username:
            return JsonResponse({"error": "Username parameter is required"}, status=400)

        try:
            user_kb = UserKnowledgeBase.objects.get(username=username)
        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

        # Find the PDF and verify it belongs to this user
        try:
            pdf = UploadedPDF.objects.get(id=pdf_id, user_knowledge_base=user_kb)
        except UploadedPDF.DoesNotExist:
            return JsonResponse({"error": "PDF not found or does not belong to this user"}, status=404)

        # Construct the file path
        if not pdf.file_path:
            return JsonResponse({"error": "PDF file path not found in database"}, status=404)

        file_full_path = Path(settings.MEDIA_ROOT) / pdf.file_path

        if not file_full_path.exists():
            return JsonResponse({"error": "PDF file not found on server"}, status=404)

        # Return the file
        response = FileResponse(
            open(file_full_path, 'rb'),
            content_type='application/pdf'
        )
        response['Content-Disposition'] = f'inline; filename="{pdf.filename}"'
        return response

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ===================================
# CHAT SESSION MANAGEMENT ENDPOINTS
# ===================================

@csrf_exempt
@require_POST
def create_session(request):
    """
    Create a new chat session.
    POST /chatlog/sessions/
    Body: {"username": "ahmed", "title": "New Chat"}
    """
    try:
        data = json.loads(request.body)
        username = data.get("username")
        title = data.get("title", "New Chat")

        if not username:
            return JsonResponse({"error": "Username is required"}, status=400)

        try:
            user_kb = UserKnowledgeBase.objects.get(username=username)
        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

        # Create new session
        session = ChatSession.objects.create(
            user_knowledge_base=user_kb,
            title=title
        )

        return JsonResponse({
            "session_id": str(session.session_id),
            "title": session.title,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat()
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def list_sessions(request):
    """
    List all chat sessions for a user.
    GET /chatlog/sessions/?username=ahmed
    """
    try:
        username = request.GET.get("username", "").strip()

        if not username:
            return JsonResponse({"error": "Username parameter is required"}, status=400)

        try:
            user_kb = UserKnowledgeBase.objects.get(username=username)
        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

        # Get all sessions for this user
        sessions = ChatSession.objects.filter(
            user_knowledge_base=user_kb,
            is_archived=False
        ).prefetch_related('messages')

        sessions_data = []
        for session in sessions:
            messages = session.messages.all()
            last_user_message = messages.filter(role='user').last()

            sessions_data.append({
                'session_id': str(session.session_id),
                'title': session.title,
                'message_count': messages.count(),
                'last_message_preview': last_user_message.content[:100] if last_user_message else '',
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat()
            })

        return JsonResponse({
            'sessions': sessions_data,
            'count': len(sessions_data)
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_session_messages(request, session_id):
    """
    Get all messages in a chat session.
    GET /chatlog/sessions/<session_id>/messages/?username=ahmed
    """
    try:
        username = request.GET.get("username", "").strip()

        if not username:
            return JsonResponse({"error": "Username parameter is required"}, status=400)

        try:
            user_kb = UserKnowledgeBase.objects.get(username=username)
        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

        # Get session and verify ownership
        try:
            session = ChatSession.objects.get(
                session_id=session_id,
                user_knowledge_base=user_kb
            )
        except ChatSession.DoesNotExist:
            return JsonResponse({"error": "Session not found or does not belong to this user"}, status=404)

        # Get all messages in session
        messages = session.messages.all()

        messages_data = [{
            'message_id': str(msg.message_id),
            'role': msg.role,
            'content': msg.content,
            'metadata': msg.metadata,
            'created_at': msg.created_at.isoformat()
        } for msg in messages]

        return JsonResponse({
            'session_id': str(session.session_id),
            'title': session.title,
            'messages': messages_data,
            'message_count': len(messages_data)
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT"])
def update_session(request, session_id):
    """
    Update session title.
    PUT /chatlog/sessions/<session_id>/
    Body: {"username": "ahmed", "title": "New Title"}
    """
    try:
        data = json.loads(request.body)
        username = data.get("username")
        title = data.get("title")

        if not username:
            return JsonResponse({"error": "Username is required"}, status=400)

        if not title:
            return JsonResponse({"error": "Title is required"}, status=400)

        try:
            user_kb = UserKnowledgeBase.objects.get(username=username)
        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

        # Get session and verify ownership
        try:
            session = ChatSession.objects.get(
                session_id=session_id,
                user_knowledge_base=user_kb
            )
        except ChatSession.DoesNotExist:
            return JsonResponse({"error": "Session not found or does not belong to this user"}, status=404)

        # Update title
        session.title = title
        session.save()

        return JsonResponse({
            "message": "Session title updated successfully",
            "session_id": str(session.session_id),
            "title": session.title,
            "updated_at": session.updated_at.isoformat()
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE", "POST"])
def delete_session(request, session_id):
    """
    Delete a chat session.
    DELETE /chatlog/sessions/<session_id>/?username=ahmed
    OR
    POST /chatlog/sessions/<session_id>/delete/ with {"username": "ahmed"}
    """
    try:
        # Get username from query params or body
        if request.method == "DELETE":
            username = request.GET.get("username", "").strip()
        else:  # POST
            data = json.loads(request.body)
            username = data.get("username")

        if not username:
            return JsonResponse({"error": "Username is required"}, status=400)

        try:
            user_kb = UserKnowledgeBase.objects.get(username=username)
        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

        # Get session and verify ownership
        try:
            session = ChatSession.objects.get(
                session_id=session_id,
                user_knowledge_base=user_kb
            )
        except ChatSession.DoesNotExist:
            return JsonResponse({"error": "Session not found or does not belong to this user"}, status=404)

        session_title = session.title
        session.delete()

        return JsonResponse({
            "message": f"✅ Session '{session_title}' deleted successfully",
            "deleted_session_id": str(session_id)
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)