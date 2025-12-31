import traceback

from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_http_methods
from .decorators import require_staff
from django.db import transaction
from django.utils.timezone import now
from django.conf import settings

from langchain_core.messages import HumanMessage, AIMessage

import os
import json
import tempfile
import shutil
from pathlib import Path

from .models import ConversationLog, UserKnowledgeBase, UploadedPDF, ChatSession, ChatMessage, DocumentSummary, UserFeedback, SavedNote, FoundationDocument
from .langgraph_agent import construct_agent_graph, vector_store, add_to_foundation_kb, get_foundation_vectorstore, FOUNDATION_COLLECTION, get_current_model, AVAILABLE_MODELS

# Subscription utilities for limit checking
from subscriptions.utils import can_use_credits, can_upload_pdf, use_credits, increment_pdf_count, decrement_pdf_count, get_usage_summary

import threading
import logging

logger = logging.getLogger(__name__)

# ----------------------------
# AGENT GRAPH CACHE (prevents cold start on first request)
# ----------------------------
_agent_cache = {}
_agent_cache_lock = threading.Lock()


def get_or_create_agent_graph(collection_name):
    """Get cached agent graph or create new one. Prevents cold start delays."""
    if collection_name in _agent_cache:
        return _agent_cache[collection_name]

    with _agent_cache_lock:
        # Double-check after acquiring lock
        if collection_name in _agent_cache:
            return _agent_cache[collection_name]

        logger.info(f"[Agent] Creating new agent graph for collection: {collection_name}")
        agent_graph = construct_agent_graph(collection_name)
        _agent_cache[collection_name] = agent_graph
        return agent_graph


# ----------------------------
# AUTH HELPER
# ----------------------------

def get_authenticated_user(request):
    """
    Get authenticated User from JWT token in cookies or Authorization header.

    Returns:
        User or None: The authenticated user if token is valid, None otherwise
    """
    from rest_framework_simplejwt.tokens import AccessToken
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
    from accounts.models import User

    # First check if DRF already authenticated the user
    if hasattr(request, 'user') and request.user.is_authenticated:
        return request.user

    # Try to get token from cookies
    access_token = request.COOKIES.get('access_token')

    # Fallback to Authorization header
    if not access_token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            access_token = auth_header[7:]

    if not access_token:
        return None

    try:
        # Validate the token
        token = AccessToken(access_token)
        user_id = token.get('user_id')

        if not user_id:
            return None

        # Get the user
        user = User.objects.get(id=user_id)
        return user

    except (InvalidToken, TokenError, User.DoesNotExist) as e:
        print(f"[AUTH] Token validation failed: {e}")
        return None


def get_user_knowledge_base(request):
    """
    Get UserKnowledgeBase for the authenticated user.

    Priority:
    1. JWT authenticated user (from accounts.User model via cookies/header)
    2. Username from query parameter (backward compatibility)

    For JWT users, auto-creates UserKnowledgeBase if it doesn't exist.

    Returns:
        tuple: (user_kb, error_response)
        - If successful: (UserKnowledgeBase instance, None)
        - If error: (None, JsonResponse with error)
    """
    # Check for JWT authenticated user first
    auth_user = get_authenticated_user(request)
    if auth_user:
        # First, try to find by username
        try:
            user_kb = UserKnowledgeBase.objects.get(username=auth_user.username)
            return user_kb, None
        except UserKnowledgeBase.DoesNotExist:
            pass

        # If not found by username, try to find by collection_name (in case username was updated)
        collection_name = auth_user.collection_name or f"collection_{auth_user.username}"
        try:
            user_kb = UserKnowledgeBase.objects.get(collection_name=collection_name)
            # Update username to match the new username
            if user_kb.username != auth_user.username:
                user_kb.username = auth_user.username
                user_kb.save()
                print(f"[AUTH] Updated UserKnowledgeBase username to: {auth_user.username}")
            return user_kb, None
        except UserKnowledgeBase.DoesNotExist:
            pass

        # Create new UserKnowledgeBase if neither found
        user_kb = UserKnowledgeBase.objects.create(
            username=auth_user.username,
            collection_name=collection_name
        )
        print(f"[AUTH] Created UserKnowledgeBase for JWT user: {auth_user.username}")

        return user_kb, None

    # Fallback to username parameter (backward compatibility)
    username = request.GET.get("username", "").strip()
    if not username:
        # Also check request body for POST requests
        if request.method in ["POST", "PUT"]:
            try:
                data = json.loads(request.body)
                username = data.get("username", "").strip()
            except (json.JSONDecodeError, AttributeError):
                pass

    if not username:
        return None, JsonResponse({"error": "Authentication required"}, status=401)

    try:
        user_kb = UserKnowledgeBase.objects.get(username=username)
        return user_kb, None
    except UserKnowledgeBase.DoesNotExist:
        return None, JsonResponse({"error": f"User '{username}' does not exist"}, status=404)

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import PGVector
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document

# Docling for advanced PDF parsing (better tables, layout understanding)
try:
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
    print("[PDF Parser] Docling available - using advanced PDF parsing")
except ImportError:
    DOCLING_AVAILABLE = False
    print("[PDF Parser] Docling not available - falling back to PyPDFLoader")

# PyMuPDF as fallback for corrupted/malformed PDFs
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
    print("[PDF Parser] PyMuPDF available - fallback for corrupted PDFs")
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("[PDF Parser] PyMuPDF not available")

# OCR support for scanned/image-based PDFs
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
    print("[PDF Parser] OCR available (pytesseract + pdf2image) - for scanned PDFs")
except ImportError:
    OCR_AVAILABLE = False
    print("[PDF Parser] OCR not available - scanned PDFs won't be processed")


# ----------------------------
# CONFIG
# ----------------------------
# Build connection string from environment variables (same as langgraph_agent.py)
CONNECTION_STRING = os.getenv('PGVECTOR_CONNECTION') or (
    f"postgresql+psycopg2://{os.getenv('POSTGRES_USER', 'oinride')}:{os.getenv('POSTGRES_PASSWORD_FLAT', '')}@{os.getenv('POSTGRES_HOST', 'db')}:{os.getenv('POSTGRES_PORT', 5432)}/{os.getenv('POSTGRES_DB', 'oinride')}"
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


import threading

def process_pdf_background(pdf_id, file_path, filename, collection_name):
    """Background task to parse PDF and add to vector store."""
    import django
    django.setup()

    from .models import UploadedPDF

    try:
        print(f"[PDF Processing] Starting background processing for: {filename}")

        # Update status to processing
        uploaded_pdf = UploadedPDF.objects.get(id=pdf_id)
        uploaded_pdf.status = 'processing'
        uploaded_pdf.save()

        documents = []
        parser_used = "pypdf"
        page_count = 0  # Track number of pages in PDF

        # OPTIMIZATION: Try fast parsers first, then Docling for complex PDFs

        # 1. Try PyMuPDF first (fastest)
        if PYMUPDF_AVAILABLE:
            try:
                print(f"[PDF Processing] Trying PyMuPDF (fast) for: {filename}")
                pdf_doc = fitz.open(str(file_path))
                page_count = len(pdf_doc)  # Capture page count
                full_text = ""
                for page_num in range(page_count):
                    page = pdf_doc[page_num]
                    full_text += page.get_text() + "\n\n"
                pdf_doc.close()

                if full_text.strip() and len(full_text.strip()) > 100:
                    documents = [Document(
                        page_content=full_text,
                        metadata={"source": str(file_path), "filename": filename, "parser": "pymupdf"}
                    )]
                    parser_used = "pymupdf"
                    print(f"[PDF Processing] PyMuPDF extracted {len(full_text)} characters")
            except Exception as e:
                print(f"[PDF Processing] PyMuPDF failed: {e}")
                documents = []

        # 2. Fallback to PyPDFLoader
        if not documents:
            try:
                print(f"[PDF Processing] Trying PyPDFLoader for: {filename}")
                loader = PyPDFLoader(str(file_path))
                documents = loader.load()
                if page_count == 0:
                    page_count = len(documents)  # Each document is a page
                parser_used = "pypdf"
                print(f"[PDF Processing] PyPDFLoader extracted {len(documents)} pages")
            except Exception as e:
                print(f"[PDF Processing] PyPDFLoader failed: {e}")
                documents = []

        # 3. Final fallback to Docling (slow but handles complex layouts)
        if not documents and DOCLING_AVAILABLE:
            import concurrent.futures
            DOCLING_TIMEOUT = 30  # Reduced from 60

            def parse_with_docling(fp):
                converter = DocumentConverter()
                result = converter.convert(str(fp))
                return result.document.export_to_markdown()

            try:
                print(f"[PDF Processing] Using Docling (complex PDF) for: {filename}")
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(parse_with_docling, file_path)
                    try:
                        markdown_content = future.result(timeout=DOCLING_TIMEOUT)
                        if markdown_content and len(markdown_content.strip()) > 0:
                            documents = [Document(
                                page_content=markdown_content,
                                metadata={"source": str(file_path), "filename": filename, "parser": "docling"}
                            )]
                            parser_used = "docling"
                            print(f"[PDF Processing] Docling extracted {len(markdown_content)} characters")
                    except concurrent.futures.TimeoutError:
                        print(f"[PDF Processing] Docling timeout after {DOCLING_TIMEOUT}s")
                        documents = []
            except Exception as e:
                print(f"[PDF Processing] Docling failed: {e}")
                documents = []

        # 4. Final fallback: OCR for scanned/image-based PDFs
        if not documents and OCR_AVAILABLE:
            try:
                print(f"[PDF Processing] Using OCR for scanned PDF: {filename}")
                # Convert PDF pages to images
                images = convert_from_path(str(file_path), dpi=200)
                if page_count == 0:
                    page_count = len(images)  # Each image is a page
                print(f"[PDF Processing] Converted {len(images)} pages to images")

                full_text = ""
                for i, image in enumerate(images):
                    # Extract text from each page image
                    page_text = pytesseract.image_to_string(image, lang='eng+ara')  # Support English + Arabic
                    full_text += f"\n--- Page {i+1} ---\n{page_text}\n"
                    print(f"[PDF Processing] OCR page {i+1}: {len(page_text)} chars")

                if full_text.strip() and len(full_text.strip()) > 50:
                    documents = [Document(
                        page_content=full_text,
                        metadata={"source": str(file_path), "filename": filename, "parser": "ocr"}
                    )]
                    parser_used = "ocr"
                    print(f"[PDF Processing] OCR extracted {len(full_text)} characters total")
            except Exception as e:
                print(f"[PDF Processing] OCR failed: {e}")
                documents = []

        if not documents:
            uploaded_pdf.status = 'failed'
            uploaded_pdf.error_message = 'No text could be extracted from this PDF (tried all parsers including OCR)'
            uploaded_pdf.save()
            Path(file_path).unlink(missing_ok=True)
            print(f"[PDF Processing] Failed - no text extracted after all methods: {filename}")
            return

        # Check if documents have actual content
        total_content = sum(len(doc.page_content.strip()) for doc in documents)
        if total_content < 50:  # Less than 50 chars is essentially empty
            uploaded_pdf.status = 'failed'
            uploaded_pdf.error_message = 'PDF appears to be empty or contains no readable text'
            uploaded_pdf.save()
            Path(file_path).unlink(missing_ok=True)
            print(f"[PDF Processing] Failed - PDF content too short ({total_content} chars): {filename}")
            return

        # Split documents
        print(f"[PDF Processing] Splitting documents into chunks...")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        docs = text_splitter.split_documents(documents)
        print(f"[PDF Processing] Created {len(docs)} chunks")

        # Verify we have chunks to add
        if not docs:
            uploaded_pdf.status = 'failed'
            uploaded_pdf.error_message = 'No text chunks could be created from this PDF'
            uploaded_pdf.save()
            Path(file_path).unlink(missing_ok=True)
            print(f"[PDF Processing] Failed - no chunks created: {filename}")
            return

        # Add metadata
        for doc in docs:
            doc.metadata["pdf_id"] = str(pdf_id)
            doc.metadata["pdf_filename"] = filename

        # Add to vector store (this is the slow part - embedding generation)
        print(f"[PDF Processing] Adding {len(docs)} chunks to vector store (embedding)...")
        vectorstore = vector_store(collection_name)
        vectorstore.add_documents(docs)

        # Update PDF record
        uploaded_pdf.chunks_count = len(docs)
        uploaded_pdf.page_count = page_count
        uploaded_pdf.status = 'completed'
        uploaded_pdf.save()

        print(f"[PDF Processing] Completed: {filename} - {len(docs)} chunks, {page_count} pages, parser: {parser_used}")

    except Exception as e:
        print(f"[PDF Processing] Error: {e}")
        try:
            uploaded_pdf = UploadedPDF.objects.get(id=pdf_id)
            uploaded_pdf.status = 'failed'
            uploaded_pdf.error_message = str(e)
            uploaded_pdf.save()
        except:
            pass


@csrf_exempt
@require_POST
def upload_pdf(request):
    """Handle PDF upload - saves file quickly and processes in background."""
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

        collection_name = user_kb.collection_name
        username = user_kb.username

        # Check PDF upload limit (subscription)
        auth_user = get_authenticated_user(request)
        if auth_user:
            can_upload, limit_error = can_upload_pdf(auth_user)
            if not can_upload:
                return JsonResponse({
                    "error": limit_error,
                    "limit_reached": True
                }, status=403)

        if "file" not in request.FILES:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        # Get file and check size limit (10MB)
        pdf_file = request.FILES["file"]
        file_size = pdf_file.size
        filename = pdf_file.name

        # 10MB size limit
        MAX_FILE_SIZE = 10 * 1024 * 1024
        if file_size > MAX_FILE_SIZE:
            return JsonResponse({
                "error": f"File size exceeds 10MB limit. Your file is {file_size / (1024*1024):.1f}MB"
            }, status=400)

        # Create media directory structure
        pdf_dir = Path(settings.MEDIA_ROOT) / 'pdfs' / username
        pdf_dir.mkdir(parents=True, exist_ok=True)

        # Create unique filename
        import uuid
        unique_filename = f"{uuid.uuid4()}_{filename}"
        pdf_file_path = pdf_dir / unique_filename

        # Save PDF file
        with open(pdf_file_path, 'wb') as destination:
            for chunk in pdf_file.chunks():
                destination.write(chunk)

        # Create PDF record with 'processing' status
        relative_path = f"pdfs/{username}/{unique_filename}"
        uploaded_pdf = UploadedPDF.objects.create(
            user_knowledge_base=user_kb,
            filename=filename,
            file_path=relative_path,
            file_size=file_size,
            status='processing'
        )

        # Increment PDF count for subscription tracking
        if auth_user:
            increment_pdf_count(auth_user)

        # Start background processing
        thread = threading.Thread(
            target=process_pdf_background,
            args=(uploaded_pdf.id, pdf_file_path, filename, collection_name)
        )
        thread.daemon = True
        thread.start()

        # Return immediately
        return JsonResponse({
            "message": "File uploaded, processing started",
            "pdf_id": uploaded_pdf.id,
            "filename": filename,
            "file_size": file_size,
            "file_url": f"/media/{relative_path}",
            "status": "processing"
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_pdf_status(request, pdf_id):
    """Get the processing status of a PDF."""
    try:
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

        pdf = UploadedPDF.objects.get(id=pdf_id, user_knowledge_base=user_kb)

        return JsonResponse({
            "pdf_id": pdf.id,
            "filename": pdf.filename,
            "status": pdf.status,
            "chunks_count": pdf.chunks_count,
            "error_message": pdf.error_message,
            "file_url": f"/media/{pdf.file_path}" if pdf.file_path else None
        })

    except UploadedPDF.DoesNotExist:
        return JsonResponse({"error": "PDF not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_POST
@csrf_exempt
def ask_agent(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_input = data.get("question", "")
            session_id = data.get("session_id")  # Get session_id from request

            if not user_input:
                return JsonResponse({"error": "Question is required"}, status=400)

            # Get user from JWT auth or fallback to username param
            user_kb, error_response = get_user_knowledge_base(request)
            if error_response:
                return error_response

            collection_name = user_kb.collection_name

            # Check credit limit (subscription) - estimate minimum credits needed
            auth_user = get_authenticated_user(request)
            if auth_user:
                # Estimate credits: input tokens + expected output (roughly 4 chars = 1 token)
                estimated_input_tokens = len(user_input) // 4 + 50  # +50 for system prompt
                min_credits_needed = max(estimated_input_tokens, 100)  # Minimum 100 credits per request

                can_use, credit_error = can_use_credits(auth_user, min_credits_needed)
                if not can_use:
                    return JsonResponse({
                        "error": credit_error,
                        "credits_required": min_credits_needed,
                        "limit_reached": True
                    }, status=403)

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

            # Run AI agent (using cached agent graph to prevent cold start)
            logger.info(f"[askAgent] Processing request for user {user_kb.username}, collection: {collection_name}")
            agent_graph = get_or_create_agent_graph(collection_name)
            messages = agent_graph.invoke({"messages": [("user", user_input), ("system", chat_history)]})
            ai_response = messages["messages"][-1].content

            # Deduct credits based on actual usage (subscription)
            credits_used = 0
            if auth_user:
                # Calculate tokens: input + output (roughly 4 chars = 1 token)
                input_tokens = len(user_input) // 4 + len(chat_history) // 4 + 50
                output_tokens = len(ai_response) // 4
                credits_used = input_tokens + output_tokens

                success, error, remaining = use_credits(
                    user=auth_user,
                    amount=credits_used,
                    action_type='chat',
                    description=f"Chat: {user_input[:50]}...",
                    metadata={
                        'session_id': str(session.session_id) if session else None,
                        'input_tokens': input_tokens,
                        'output_tokens': output_tokens
                    }
                )
                if not success:
                    print(f"[Credits] Warning: Could not deduct credits for user {auth_user.username}: {error}")

            # Save user message to ChatMessage
            user_message = ChatMessage.objects.create(
                session=session,
                role='user',
                content=user_input
            )

            # Get current model info for metadata
            current_model_id = get_current_model()
            model_config = AVAILABLE_MODELS.get(current_model_id, {})

            # Save AI response to ChatMessage with model info
            ai_message = ChatMessage.objects.create(
                session=session,
                role='assistant',
                content=ai_response,
                metadata={
                    'model_id': current_model_id,
                    'model_name': model_config.get('name', 'Unknown'),
                    'provider': model_config.get('provider', 'unknown')
                }
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

            response_data = {
                "username": user_kb.username,
                "answer": ai_response,
                "id": log.id,
                "session_id": str(session.session_id),
                "message_id": str(ai_message.message_id),
                "model_info": {
                    "model_id": current_model_id,
                    "model_name": model_config.get('name', 'Unknown'),
                    "provider": model_config.get('provider', 'unknown')
                }
            }

            # Add credits info if authenticated
            if auth_user and credits_used > 0:
                response_data["credits_used"] = credits_used

            return JsonResponse(response_data)

        except Exception as e:
            logger.error(f"[askAgent] Error: {type(e).__name__}: {str(e)}", exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Only POST allowed"}, status=405)


@csrf_exempt
def get_chat_history(request):
    if request.method == "GET":
        try:
            # Get user from JWT auth or fallback to username param
            user_kb, error_response = get_user_knowledge_base(request)
            if error_response:
                return error_response

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
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

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
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

        username = user_kb.username

        # Get all PDFs for this user
        pdfs = UploadedPDF.objects.filter(user_knowledge_base=user_kb)

        documents = [{
            'id': pdf.id,
            'filename': pdf.filename,
            'size': f"{pdf.file_size / (1024*1024):.1f} MB",
            'file_size': pdf.file_size,
            'page_count': pdf.page_count,
            'chunks_count': pdf.chunks_count,
            'upload_date': pdf.uploaded_at.isoformat(),
            'file_url': f"/chatlog/get-pdf/{pdf.id}/?username={username}",
            'status': pdf.status,
            'error_message': pdf.error_message
        } for pdf in pdfs]

        return JsonResponse({
            'documents': documents,
            'count': len(documents)
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_user_stats(request):
    """
    Get user's knowledge base statistics.
    Returns document count, page count, storage used, and chunk count.
    GET /chatlog/user/stats/
    """
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

        # Get all completed PDFs for this user
        pdfs = UploadedPDF.objects.filter(
            user_knowledge_base=user_kb,
            status='completed'
        )

        # Calculate statistics
        total_documents = pdfs.count()
        total_pages = sum(pdf.page_count for pdf in pdfs)
        total_storage_bytes = sum(pdf.file_size for pdf in pdfs)
        total_chunks = sum(pdf.chunks_count for pdf in pdfs)

        # Format storage size
        if total_storage_bytes >= 1024 * 1024 * 1024:  # GB
            storage_display = f"{total_storage_bytes / (1024**3):.2f} GB"
        elif total_storage_bytes >= 1024 * 1024:  # MB
            storage_display = f"{total_storage_bytes / (1024**2):.1f} MB"
        elif total_storage_bytes >= 1024:  # KB
            storage_display = f"{total_storage_bytes / 1024:.1f} KB"
        else:
            storage_display = f"{total_storage_bytes} bytes"

        # Get processing stats
        processing_count = UploadedPDF.objects.filter(
            user_knowledge_base=user_kb,
            status='processing'
        ).count()
        failed_count = UploadedPDF.objects.filter(
            user_knowledge_base=user_kb,
            status='failed'
        ).count()

        # Get first and last upload dates
        first_upload = pdfs.order_by('uploaded_at').first()
        last_upload = pdfs.order_by('-uploaded_at').first()

        return JsonResponse({
            "stats": {
                "total_documents": total_documents,
                "total_pages": total_pages,
                "total_storage_bytes": total_storage_bytes,
                "storage_display": storage_display,
                "total_chunks": total_chunks,
                "processing_count": processing_count,
                "failed_count": failed_count,
                "first_upload": first_upload.uploaded_at.isoformat() if first_upload else None,
                "last_upload": last_upload.uploaded_at.isoformat() if last_upload else None,
            },
            "collection_name": user_kb.collection_name,
            "username": user_kb.username
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
def delete_pdf(request):
    """Delete a PDF from user's list AND remove its vector chunks from database."""
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

        # Get pdf_id from request body or query params
        if request.method == "POST":
            data = json.loads(request.body)
            pdf_id = data.get("pdf_id")
        else:  # DELETE method
            pdf_id = request.GET.get("pdf_id")

        if not pdf_id:
            return JsonResponse({"error": "pdf_id is required"}, status=400)

        # Find the PDF and verify it belongs to this user
        try:
            pdf = UploadedPDF.objects.get(id=pdf_id, user_knowledge_base=user_kb)
        except UploadedPDF.DoesNotExist:
            return JsonResponse({"error": "PDF not found or does not belong to this user"}, status=404)

        filename = pdf.filename
        chunks_count = pdf.chunks_count

        # Delete the physical file if it exists
        if pdf.file_path:
            file_full_path = Path(settings.MEDIA_ROOT) / pdf.file_path
            if file_full_path.exists():
                file_full_path.unlink()

        # IMPORTANT: Delete vector chunks from pgvector database
        # This prevents orphaned chunks from appearing in search results
        vectors_deleted = 0
        try:
            from django.db import connection

            # First, try to delete by pdf_id metadata (for PDFs uploaded after metadata tracking)
            delete_by_metadata_query = """
                DELETE FROM langchain_pg_embedding
                WHERE collection_id = (
                    SELECT uuid FROM langchain_pg_collection
                    WHERE name = %s
                )
                AND cmetadata->>'pdf_id' = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(delete_by_metadata_query, [user_kb.collection_name, str(pdf_id)])
                vectors_deleted = cursor.rowcount
                print(f"[DELETE_PDF] Deleted {vectors_deleted} vector chunks for PDF ID {pdf_id}")

                # Fallback: If no vectors were deleted (old PDFs without metadata),
                # and this is the ONLY PDF for this user, clean the entire collection
                if vectors_deleted == 0:
                    remaining_pdfs = UploadedPDF.objects.filter(user_knowledge_base=user_kb).exclude(id=pdf_id).count()
                    if remaining_pdfs == 0:
                        # This is the last PDF - safe to delete all vectors for this user
                        delete_all_query = """
                            DELETE FROM langchain_pg_embedding
                            WHERE collection_id = (
                                SELECT uuid FROM langchain_pg_collection
                                WHERE name = %s
                            )
                        """
                        cursor.execute(delete_all_query, [user_kb.collection_name])
                        vectors_deleted = cursor.rowcount
                        print(f"[DELETE_PDF] Fallback cleanup: Deleted {vectors_deleted} orphaned chunks (last PDF for user)")
        except Exception as vector_error:
            print(f"[DELETE_PDF] Warning: Could not clean vectors: {vector_error}")
            # Continue with deletion even if vector cleanup fails

        # Delete the PDF record from Django database
        pdf.delete()

        # Invalidate DocumentSummary cache (delete old summary so it regenerates)
        try:
            DocumentSummary.objects.filter(user_knowledge_base=user_kb).delete()
            print(f"[DELETE_PDF] Invalidated DocumentSummary cache for user {user_kb.username}")
        except Exception as cache_error:
            print(f"[DELETE_PDF] Warning: Could not invalidate summary cache: {cache_error}")

        # Decrement PDF count for subscription tracking
        auth_user = get_authenticated_user(request)
        if auth_user:
            decrement_pdf_count(auth_user)

        return JsonResponse({
            "message": f"✅ PDF '{filename}' deleted successfully",
            "deleted_pdf_id": int(pdf_id),
            "chunks_deleted": chunks_count,
            "vectors_deleted": vectors_deleted
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_pdf_file(request, pdf_id):
    """
    Serve PDF file for preview.
    GET /chatlog/get-pdf/<pdf_id>/ (uses JWT auth or ?username=<username>)
    """
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

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
    Body: {"title": "New Chat"} (username from JWT auth or query param)
    """
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

        # Get title from body
        title = "New Chat"
        try:
            data = json.loads(request.body)
            title = data.get("title", "New Chat")
        except (json.JSONDecodeError, AttributeError):
            pass

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
    GET /chatlog/sessions/ (uses JWT auth or ?username=ahmed)
    """
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

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
    GET /chatlog/sessions/<session_id>/messages/ (uses JWT auth or ?username=ahmed)
    """
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

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
    Body: {"title": "New Title"} (uses JWT auth or username in body)
    """
    try:
        data = json.loads(request.body)
        title = data.get("title")

        if not title:
            return JsonResponse({"error": "Title is required"}, status=400)

        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

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
    DELETE /chatlog/sessions/<session_id>/ (uses JWT auth or ?username=ahmed)
    OR
    POST /chatlog/sessions/<session_id>/delete/ (uses JWT auth or body)
    """
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

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


# ===================================
# DOCUMENT SUMMARY & FEEDBACK ENDPOINTS
# ===================================

# Emoji mapping for different document topics
TOPIC_EMOJIS = {
    'safety': '🛡️', 'security': '🔒', 'emergency': '🚨', 'fire': '🔥',
    'health': '🏥', 'medical': '⚕️', 'construction': '🏗️', 'engineering': '⚙️',
    'environment': '🌍', 'chemical': '🧪', 'electrical': '⚡', 'machine': '🔧',
    'vehicle': '🚗', 'transport': '🚚', 'aviation': '✈️', 'maritime': '🚢',
    'food': '🍽️', 'agriculture': '🌾', 'mining': '⛏️', 'oil': '🛢️',
    'nuclear': '☢️', 'radiation': '☢️', 'hazard': '⚠️', 'risk': '📊',
    'compliance': '✅', 'regulation': '📋', 'policy': '📜', 'procedure': '📝',
    'training': '📚', 'manual': '📖', 'guide': '📕', 'report': '📑',
    'audit': '🔍', 'inspection': '🔎', 'assessment': '📈', 'analysis': '📉',
    'finance': '💰', 'business': '💼', 'legal': '⚖️', 'contract': '📄',
    'technology': '💻', 'software': '🖥️', 'data': '📊', 'network': '🌐',
    'default': '📄'
}


def get_topic_emoji(text: str) -> str:
    """Determine the most relevant emoji based on document content."""
    text_lower = text.lower()
    for keyword, emoji in TOPIC_EMOJIS.items():
        if keyword in text_lower:
            return emoji
    return TOPIC_EMOJIS['default']


@csrf_exempt
@require_http_methods(["GET", "POST"])
def get_document_summary(request):
    """
    Generate or retrieve a NotebookLM-style summary of user's documents.
    GET /chatlog/summary/ - Get existing summary or generate new one
    POST /chatlog/summary/ - Force regenerate summary
    """
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

        collection_name = user_kb.collection_name
        force_regenerate = request.method == "POST"

        # Get user's uploaded PDFs - ONLY completed ones
        pdfs = UploadedPDF.objects.filter(
            user_knowledge_base=user_kb,
            status='completed'  # Only count successfully processed PDFs
        ).order_by('uploaded_at')

        pdf_count = pdfs.count()

        if pdf_count == 0:
            # Check if there are any processing PDFs
            processing_count = UploadedPDF.objects.filter(
                user_knowledge_base=user_kb,
                status='processing'
            ).count()

            if processing_count > 0:
                return JsonResponse({
                    "has_summary": False,
                    "message": f"{processing_count} document(s) still processing..."
                })

            return JsonResponse({
                "has_summary": False,
                "message": "No documents uploaded yet"
            })

        pdf_filenames = sorted([pdf.filename for pdf in pdfs])

        # Create a document fingerprint based on filenames and IDs
        # This ensures we detect ANY change in documents
        import hashlib
        doc_fingerprint = hashlib.md5(
            '|'.join([f"{pdf.id}:{pdf.filename}" for pdf in pdfs]).encode()
        ).hexdigest()[:16]

        print(f"[Summary] Checking cache for user {user_kb.username}, {pdf_count} docs, fingerprint: {doc_fingerprint}")

        # Check for existing summary with matching fingerprint
        existing_summary = DocumentSummary.objects.filter(
            user_knowledge_base=user_kb
        ).first()

        if existing_summary and not force_regenerate:
            from django.utils import timezone
            from datetime import timedelta

            # Get stored fingerprint (we'll add this check)
            stored_filenames = sorted(existing_summary.source_filenames) if existing_summary.source_filenames else []
            current_filenames = pdf_filenames

            # Check if documents have changed
            docs_match = stored_filenames == current_filenames and existing_summary.source_count == pdf_count
            is_recent = existing_summary.updated_at > timezone.now() - timedelta(hours=1)

            print(f"[Summary] Cache check: docs_match={docs_match}, is_recent={is_recent}")
            print(f"[Summary] Stored: {stored_filenames}")
            print(f"[Summary] Current: {current_filenames}")

            if docs_match and is_recent:
                print(f"[Summary] Returning cached summary")
                return JsonResponse({
                    "has_summary": True,
                    "summary_id": existing_summary.id,
                    "title": existing_summary.title,
                    "emoji": existing_summary.emoji,
                    "summary": existing_summary.summary,
                    "key_topics": existing_summary.key_topics,
                    "suggested_questions": existing_summary.suggested_questions,
                    "source_count": existing_summary.source_count,
                    "source_filenames": existing_summary.source_filenames,
                    "created_at": existing_summary.created_at.isoformat(),
                    "cached": True
                })
            else:
                # Documents changed - delete old summary to force regeneration
                print(f"[Summary] Documents changed, deleting old summary and regenerating")
                existing_summary.delete()
                existing_summary = None

        # Generate new summary using AI
        summary_prompt = f"""Analyze all the documents in my knowledge base and create a comprehensive summary.

Instructions:
1. Generate a concise, descriptive TITLE (max 10 words) that captures the main theme
2. Write a SUMMARY paragraph (150-250 words) that:
   - Describes what the documents cover
   - Highlights key findings, methods, or concepts
   - Uses **bold** for important terms (3-5 key terms)
3. List 3-5 KEY_TOPICS as single words or short phrases
4. Generate 3 QUESTIONS that would help someone understand the documents better

Format your response EXACTLY as JSON:
{{
    "title": "Your Title Here",
    "summary": "Your summary with **bold** key terms...",
    "key_topics": ["topic1", "topic2", "topic3"],
    "questions": ["Question 1?", "Question 2?", "Question 3?"]
}}

Documents to analyze: {', '.join(pdf_filenames)}"""

        # Run AI agent to generate summary (using cached agent graph)
        agent_graph = get_or_create_agent_graph(collection_name)
        messages = agent_graph.invoke({"messages": [("user", summary_prompt)]})
        ai_response = messages["messages"][-1].content

        # Parse AI response
        import re

        # Try to extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', ai_response)

        title = "Document Summary"
        summary = ai_response
        key_topics = []
        questions = []

        if json_match:
            try:
                parsed = json.loads(json_match.group())
                title = parsed.get('title', title)
                summary = parsed.get('summary', summary)
                key_topics = parsed.get('key_topics', [])
                questions = parsed.get('questions', [])
            except json.JSONDecodeError:
                # If JSON parsing fails, extract info manually
                pass

        # If we couldn't parse, try to extract title from first line
        if title == "Document Summary" and '\n' in ai_response:
            first_line = ai_response.split('\n')[0].strip()
            if len(first_line) < 100 and not first_line.startswith('{'):
                title = first_line.replace('#', '').strip()

        # Get emoji based on content
        emoji = get_topic_emoji(title + ' ' + summary)

        # Generate fallback questions if none parsed
        if not questions:
            questions = [
                f"What are the main topics covered in these {pdf_count} document(s)?",
                "What are the key findings or recommendations?",
                "How can this information be applied practically?"
            ]

        # Save new summary (old one was deleted if it existed)
        print(f"[Summary] Saving new summary for {pdf_count} documents")
        summary_obj = DocumentSummary.objects.create(
            user_knowledge_base=user_kb,
            title=title,
            emoji=emoji,
            summary=summary,
            key_topics=key_topics,
            suggested_questions=questions,
            source_count=pdf_count,
            source_filenames=pdf_filenames
        )

        return JsonResponse({
            "has_summary": True,
            "summary_id": summary_obj.id,
            "title": title,
            "emoji": emoji,
            "summary": summary,
            "key_topics": key_topics,
            "suggested_questions": questions,
            "source_count": pdf_count,
            "source_filenames": pdf_filenames,
            "created_at": summary_obj.created_at.isoformat(),
            "cached": False
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_POST
def submit_feedback(request):
    """
    Submit user feedback on summaries or chat responses.
    POST /chatlog/feedback/
    Body: {
        "feedback_type": "thumbs_up" | "thumbs_down" | "save_note" | "copy",
        "content_type": "summary" | "chat_response",
        "content_id": "optional_id",
        "content_preview": "optional preview text",
        "comment": "optional user comment"
    }
    """
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

        data = json.loads(request.body)
        feedback_type = data.get('feedback_type')
        content_type = data.get('content_type')
        content_id = data.get('content_id')
        content_preview = data.get('content_preview', '')
        comment = data.get('comment', '')

        if not feedback_type or not content_type:
            return JsonResponse({
                "error": "feedback_type and content_type are required"
            }, status=400)

        # Validate feedback_type
        valid_types = ['thumbs_up', 'thumbs_down', 'save_note', 'copy']
        if feedback_type not in valid_types:
            return JsonResponse({
                "error": f"Invalid feedback_type. Must be one of: {', '.join(valid_types)}"
            }, status=400)

        # Create feedback record
        feedback = UserFeedback.objects.create(
            user_knowledge_base=user_kb,
            feedback_type=feedback_type,
            content_type=content_type,
            content_id=content_id,
            content_preview=content_preview[:500] if content_preview else None,
            comment=comment
        )

        return JsonResponse({
            "message": "Feedback submitted successfully",
            "feedback_id": feedback.id,
            "feedback_type": feedback_type
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_POST
def save_note(request):
    """
    Save content to user's notes.
    POST /chatlog/notes/
    Body: {
        "title": "Note title",
        "content": "Note content",
        "source_type": "summary" | "chat_response",
        "source_id": "optional_id"
    }
    """
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

        data = json.loads(request.body)
        title = data.get('title', 'Untitled Note')
        content = data.get('content')
        source_type = data.get('source_type', 'summary')
        source_id = data.get('source_id')

        if not content:
            return JsonResponse({"error": "content is required"}, status=400)

        note = SavedNote.objects.create(
            user_knowledge_base=user_kb,
            title=title,
            content=content,
            source_type=source_type,
            source_id=source_id
        )

        # Also create feedback record for analytics
        UserFeedback.objects.create(
            user_knowledge_base=user_kb,
            feedback_type='save_note',
            content_type=source_type,
            content_id=source_id,
            content_preview=content[:200]
        )

        return JsonResponse({
            "message": "Note saved successfully",
            "note_id": note.id,
            "title": note.title
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_notes(request):
    """
    Get all saved notes for user.
    GET /chatlog/notes/
    """
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

        notes = SavedNote.objects.filter(user_knowledge_base=user_kb)

        notes_data = [{
            'id': note.id,
            'title': note.title,
            'content': note.content,
            'source_type': note.source_type,
            'created_at': note.created_at.isoformat()
        } for note in notes]

        return JsonResponse({
            'notes': notes_data,
            'count': len(notes_data)
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_feedback_stats(request):
    """
    Get feedback statistics for admin/analytics.
    GET /chatlog/feedback/stats/
    """
    try:
        # Get user from JWT auth or fallback to username param
        user_kb, error_response = get_user_knowledge_base(request)
        if error_response:
            return error_response

        from django.db.models import Count

        # Get feedback counts by type
        feedback_stats = UserFeedback.objects.filter(
            user_knowledge_base=user_kb
        ).values('feedback_type').annotate(count=Count('id'))

        stats = {item['feedback_type']: item['count'] for item in feedback_stats}

        # Calculate satisfaction rate
        thumbs_up = stats.get('thumbs_up', 0)
        thumbs_down = stats.get('thumbs_down', 0)
        total_votes = thumbs_up + thumbs_down

        satisfaction_rate = (thumbs_up / total_votes * 100) if total_votes > 0 else None

        return JsonResponse({
            'stats': stats,
            'total_feedback': sum(stats.values()),
            'satisfaction_rate': round(satisfaction_rate, 1) if satisfaction_rate else None,
            'total_votes': total_votes
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ===================================
# FOUNDATION KNOWLEDGE BASE ADMIN ENDPOINTS
# ===================================

def is_admin_user(request):
    """
    Check if the authenticated user is an admin.
    Returns (is_admin, user, error_response)
    """
    auth_user = get_authenticated_user(request)
    if not auth_user:
        return False, None, JsonResponse({"error": "Authentication required"}, status=401)

    # Check if user is superuser or staff
    if not (auth_user.is_superuser or auth_user.is_staff):
        return False, auth_user, JsonResponse({"error": "Admin access required"}, status=403)

    return True, auth_user, None


def smart_chunk_regulation(text, filename, metadata=None):
    """
    Intelligent chunking for regulation documents.
    Uses larger chunks and smarter separators for legal/regulatory text.
    """
    import re

    if metadata is None:
        metadata = {}

    # For regulations: Use larger chunks with semantic separators
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,  # Larger chunks for regulations
        chunk_overlap=300,
        separators=[
            "\n§",           # CFR section marker
            "\nSection ",    # Section headers
            "\nPart ",       # Part headers
            "\nSubpart ",    # Subpart headers
            "\n\n\n",        # Triple newline (major breaks)
            "\n\n",          # Paragraphs
            "\n",
            ". ",            # Sentences
            " "
        ]
    )

    chunks = splitter.split_text(text)

    # Extract regulation metadata from each chunk
    enriched_chunks = []
    for chunk in chunks:
        chunk_metadata = metadata.copy()

        # Extract CFR references
        cfr_pattern = r'(\d+ CFR [\d\.]+)'
        cfr_matches = re.findall(cfr_pattern, chunk)
        if cfr_matches:
            chunk_metadata['cfr_codes'] = cfr_matches

        # Extract section numbers
        section_pattern = r'§\s*([\d\.]+)'
        section_matches = re.findall(section_pattern, chunk)
        if section_matches:
            chunk_metadata['sections'] = section_matches

        # Identify topic keywords for mining safety
        safety_keywords = ['hazard', 'ppe', 'training', 'inspection',
                           'ventilation', 'ground control', 'electrical',
                           'explosive', 'blasting', 'dust', 'noise',
                           'fire', 'emergency', 'rescue', 'methane',
                           'roof', 'rib', 'haulage', 'hoisting']
        found_keywords = [kw for kw in safety_keywords if kw in chunk.lower()]
        if found_keywords:
            chunk_metadata['topics'] = found_keywords

        enriched_chunks.append({
            'content': chunk,
            'metadata': chunk_metadata
        })

    return enriched_chunks


def process_foundation_pdf_background(doc_id, file_path, filename, category, regulation_code):
    """Background task to parse Foundation PDF and add to Foundation KB vector store."""
    import django
    django.setup()

    from .models import FoundationDocument

    try:
        print(f"[Foundation KB] Starting background processing for: {filename}")

        # Update status to processing
        foundation_doc = FoundationDocument.objects.get(id=doc_id)
        foundation_doc.status = 'processing'
        foundation_doc.save()

        documents = []
        parser_used = "pypdf"

        # 1. Try PyMuPDF first (fastest)
        if PYMUPDF_AVAILABLE:
            try:
                print(f"[Foundation KB] Trying PyMuPDF for: {filename}")
                pdf_doc = fitz.open(str(file_path))
                full_text = ""
                for page_num in range(len(pdf_doc)):
                    page = pdf_doc[page_num]
                    full_text += page.get_text() + "\n\n"
                pdf_doc.close()

                if full_text.strip() and len(full_text.strip()) > 100:
                    documents = [Document(
                        page_content=full_text,
                        metadata={"source": str(file_path), "filename": filename, "parser": "pymupdf"}
                    )]
                    parser_used = "pymupdf"
                    print(f"[Foundation KB] PyMuPDF extracted {len(full_text)} characters")
            except Exception as e:
                print(f"[Foundation KB] PyMuPDF failed: {e}")
                documents = []

        # 2. Fallback to PyPDFLoader
        if not documents:
            try:
                print(f"[Foundation KB] Trying PyPDFLoader for: {filename}")
                loader = PyPDFLoader(str(file_path))
                documents = loader.load()
                parser_used = "pypdf"
                print(f"[Foundation KB] PyPDFLoader extracted {len(documents)} pages")
            except Exception as e:
                print(f"[Foundation KB] PyPDFLoader failed: {e}")
                documents = []

        # 3. Fallback to Docling for complex layouts
        if not documents and DOCLING_AVAILABLE:
            import concurrent.futures
            DOCLING_TIMEOUT = 60

            def parse_with_docling(fp):
                converter = DocumentConverter()
                result = converter.convert(str(fp))
                return result.document.export_to_markdown()

            try:
                print(f"[Foundation KB] Using Docling for: {filename}")
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(parse_with_docling, file_path)
                    try:
                        markdown_content = future.result(timeout=DOCLING_TIMEOUT)
                        if markdown_content and len(markdown_content.strip()) > 0:
                            documents = [Document(
                                page_content=markdown_content,
                                metadata={"source": str(file_path), "filename": filename, "parser": "docling"}
                            )]
                            parser_used = "docling"
                            print(f"[Foundation KB] Docling extracted {len(markdown_content)} characters")
                    except concurrent.futures.TimeoutError:
                        print(f"[Foundation KB] Docling timeout")
                        documents = []
            except Exception as e:
                print(f"[Foundation KB] Docling failed: {e}")
                documents = []

        if not documents:
            foundation_doc.status = 'failed'
            foundation_doc.error_message = 'No text could be extracted from this PDF'
            foundation_doc.save()
            print(f"[Foundation KB] Failed - no text extracted: {filename}")
            return

        # Combine all document content
        full_text = "\n\n".join([doc.page_content for doc in documents])

        if len(full_text.strip()) < 50:
            foundation_doc.status = 'failed'
            foundation_doc.error_message = 'PDF appears to be empty or contains no readable text'
            foundation_doc.save()
            print(f"[Foundation KB] Failed - content too short: {filename}")
            return

        # Smart chunking for regulations
        base_metadata = {
            'filename': filename,
            'category': category,
            'regulation_code': regulation_code,
            'foundation_doc_id': str(doc_id),
            'parser': parser_used,
            'is_foundation': True
        }

        print(f"[Foundation KB] Smart chunking regulation document...")
        enriched_chunks = smart_chunk_regulation(full_text, filename, base_metadata)
        print(f"[Foundation KB] Created {len(enriched_chunks)} enriched chunks")

        # Add to Foundation KB vector store
        texts = [chunk['content'] for chunk in enriched_chunks]
        metadatas = [chunk['metadata'] for chunk in enriched_chunks]

        foundation_vs = get_foundation_vectorstore()
        foundation_vs.add_texts(texts=texts, metadatas=metadatas)

        # Update document record
        foundation_doc.chunks_count = len(enriched_chunks)
        foundation_doc.status = 'completed'
        foundation_doc.save()

        print(f"[Foundation KB] Completed: {filename} - {len(enriched_chunks)} chunks, parser: {parser_used}")

    except Exception as e:
        print(f"[Foundation KB] Error: {e}")
        traceback.print_exc()
        try:
            foundation_doc = FoundationDocument.objects.get(id=doc_id)
            foundation_doc.status = 'failed'
            foundation_doc.error_message = str(e)
            foundation_doc.save()
        except:
            pass


@csrf_exempt
@require_staff
@require_POST
def upload_foundation_pdf(request):
    """
    Admin endpoint: Upload PDF to Foundation Knowledge Base.
    POST /chatlog/admin/foundation/upload/

    Body (multipart/form-data):
    - file: PDF file
    - title: Document title
    - category: msha|osha|state|best_practice|training
    - regulation_code: e.g., "30 CFR 56" (optional)
    - description: Brief description (optional)
    """
    try:

        if "file" not in request.FILES:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        pdf_file = request.FILES["file"]
        file_size = pdf_file.size
        filename = pdf_file.name

        # Get metadata
        title = request.POST.get('title', filename.replace('.pdf', ''))
        category = request.POST.get('category', 'msha')
        regulation_code = request.POST.get('regulation_code', '')
        description = request.POST.get('description', '')

        # Validate category
        valid_categories = ['msha', 'osha', 'state', 'best_practice', 'training']
        if category not in valid_categories:
            return JsonResponse({
                "error": f"Invalid category. Must be one of: {', '.join(valid_categories)}"
            }, status=400)

        # 20MB size limit for foundation docs
        MAX_FILE_SIZE = 20 * 1024 * 1024
        if file_size > MAX_FILE_SIZE:
            return JsonResponse({
                "error": f"File size exceeds 20MB limit. Your file is {file_size / (1024*1024):.1f}MB"
            }, status=400)

        # Create foundation directory
        foundation_dir = Path(settings.MEDIA_ROOT) / 'foundation_kb'
        foundation_dir.mkdir(parents=True, exist_ok=True)

        # Create unique filename
        import uuid
        unique_filename = f"{uuid.uuid4()}_{filename}"
        pdf_file_path = foundation_dir / unique_filename

        # Save PDF file
        with open(pdf_file_path, 'wb') as destination:
            for chunk in pdf_file.chunks():
                destination.write(chunk)

        # Create FoundationDocument record
        relative_path = f"foundation_kb/{unique_filename}"
        foundation_doc = FoundationDocument.objects.create(
            title=title,
            filename=filename,
            file_path=relative_path,
            category=category,
            regulation_code=regulation_code,
            description=description,
            file_size=file_size,
            status='processing'
        )

        # Start background processing
        thread = threading.Thread(
            target=process_foundation_pdf_background,
            args=(foundation_doc.id, pdf_file_path, filename, category, regulation_code)
        )
        thread.daemon = True
        thread.start()

        return JsonResponse({
            "message": "Foundation document uploaded, processing started",
            "document_id": foundation_doc.id,
            "title": title,
            "filename": filename,
            "category": category,
            "regulation_code": regulation_code,
            "file_size": file_size,
            "status": "processing"
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["GET"])
def list_foundation_documents(request):
    """
    Admin endpoint: List all Foundation Knowledge Base documents with pagination.
    GET /chatlog/admin/foundation/list/
    Query params: page, page_size, search, category
    """
    try:
        # Get pagination params
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        search = request.GET.get('search', '').strip()
        category_filter = request.GET.get('category', '').strip()

        # Base queryset
        documents = FoundationDocument.objects.filter(is_active=True)

        # Apply search filter
        if search:
            from django.db.models import Q
            documents = documents.filter(
                Q(title__icontains=search) |
                Q(filename__icontains=search) |
                Q(description__icontains=search)
            )

        # Apply category filter
        if category_filter:
            documents = documents.filter(category=category_filter)

        # Order by most recent first
        documents = documents.order_by('-created_at')

        # Get total count before pagination
        total_count = documents.count()
        total_pages = (total_count + page_size - 1) // page_size

        # Apply pagination
        start = (page - 1) * page_size
        end = start + page_size
        paginated_docs = documents[start:end]

        docs_data = [{
            'id': doc.id,
            'title': doc.title,
            'filename': doc.filename,
            'category': doc.category,
            'category_display': doc.get_category_display(),
            'regulation_code': doc.regulation_code,
            'description': doc.description,
            'file_size': doc.file_size,
            'chunks_count': doc.chunks_count,
            'status': doc.status,
            'error_message': doc.error_message,
            'is_active': doc.is_active,
            'uploaded_at': doc.created_at.isoformat(),
            'updated_at': doc.updated_at.isoformat()
        } for doc in paginated_docs]

        # Get summary stats (from all documents, not just paginated)
        all_docs = FoundationDocument.objects.filter(is_active=True)
        total_chunks = sum(doc.chunks_count for doc in all_docs if doc.status == 'completed')
        categories_count = {}
        for doc in all_docs:
            if doc.status == 'completed':
                categories_count[doc.category] = categories_count.get(doc.category, 0) + 1

        return JsonResponse({
            'documents': docs_data,
            'count': len(docs_data),
            'total_chunks': total_chunks,
            'categories': categories_count,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["DELETE", "POST"])
def delete_foundation_document(request, doc_id):
    """
    Admin endpoint: Delete Foundation document and its vectors.
    DELETE /chatlog/admin/foundation/delete/<doc_id>/
    OR POST /chatlog/admin/foundation/<doc_id>/delete/
    """
    try:
        try:
            foundation_doc = FoundationDocument.objects.get(id=doc_id)
        except FoundationDocument.DoesNotExist:
            return JsonResponse({"error": "Document not found"}, status=404)

        title = foundation_doc.title
        filename = foundation_doc.filename
        chunks_count = foundation_doc.chunks_count

        # Delete vectors from pgvector
        vectors_deleted = 0
        try:
            from django.db import connection

            delete_query = """
                DELETE FROM langchain_pg_embedding
                WHERE collection_id = (
                    SELECT uuid FROM langchain_pg_collection
                    WHERE name = %s
                )
                AND cmetadata->>'foundation_doc_id' = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(delete_query, [FOUNDATION_COLLECTION, str(doc_id)])
                vectors_deleted = cursor.rowcount
                print(f"[Foundation KB] Deleted {vectors_deleted} vector chunks for doc ID {doc_id}")
        except Exception as e:
            print(f"[Foundation KB] Warning: Could not clean vectors: {e}")

        # Delete physical file
        if foundation_doc.file_path:
            file_full_path = Path(settings.MEDIA_ROOT) / foundation_doc.file_path
            if file_full_path.exists():
                file_full_path.unlink()

        # Delete record
        foundation_doc.delete()

        return JsonResponse({
            "message": f"✅ Foundation document '{title}' deleted successfully",
            "deleted_doc_id": doc_id,
            "filename": filename,
            "chunks_deleted": chunks_count,
            "vectors_deleted": vectors_deleted
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["GET"])
def get_foundation_document_status(request, doc_id):
    """
    Admin endpoint: Get processing status of a Foundation document.
    GET /chatlog/admin/foundation/status/<doc_id>/
    """
    try:
        try:
            doc = FoundationDocument.objects.get(id=doc_id)
        except FoundationDocument.DoesNotExist:
            return JsonResponse({"error": "Document not found"}, status=404)

        return JsonResponse({
            "document_id": doc.id,
            "title": doc.title,
            "filename": doc.filename,
            "category": doc.category,
            "status": doc.status,
            "chunks_count": doc.chunks_count,
            "error_message": doc.error_message
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["GET"])
def get_foundation_document_chunks(request, doc_id):
    """
    Admin endpoint: Get chunks for a Foundation document.
    GET /chatlog/admin/foundation/<doc_id>/chunks/?limit=10
    """
    try:
        try:
            doc = FoundationDocument.objects.get(id=doc_id)
        except FoundationDocument.DoesNotExist:
            return JsonResponse({"error": "Document not found"}, status=404)

        limit = int(request.GET.get('limit', 10))
        limit = min(limit, 50)  # Cap at 50 chunks

        chunks = []
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                # Use file_path for more accurate matching
                file_path = doc.file_path or doc.filename

                # Get chunks that match this document's file_path or filename
                # Search across ALL foundation collections (foundation_kb, foundation_mining_kb, etc.)
                cursor.execute("""
                    SELECT e.uuid, e.document, e.cmetadata
                    FROM langchain_pg_embedding e
                    JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                    WHERE c.name LIKE %s
                    AND (
                        e.cmetadata->>'source' = %s
                        OR e.cmetadata->>'source' LIKE %s
                        OR e.cmetadata->>'source_file' LIKE %s
                    )
                    ORDER BY (e.cmetadata->>'page')::int NULLS LAST
                    LIMIT %s
                """, ['foundation%', file_path, f'%{doc.filename}%', f'%{doc.filename}%', limit])

                for row in cursor.fetchall():
                    chunk_id, content, metadata = row
                    page = None
                    if metadata:
                        page = metadata.get('page') or metadata.get('page_number')
                    chunks.append({
                        "id": str(chunk_id),
                        "content_preview": content[:500] if content else "",
                        "full_content": content if content else "",
                        "source_file": doc.filename,
                        "page": page
                    })
        except Exception as db_err:
            print(f"[Foundation Chunks] DB query error: {db_err}")
            import traceback
            traceback.print_exc()

        # Get file type from filename
        file_ext = doc.filename.split('.')[-1].lower() if '.' in doc.filename else 'unknown'

        return JsonResponse({
            "document_id": doc.id,
            "filename": doc.filename,
            "file_path": doc.file_path,
            "file_type": file_ext,
            "file_size": doc.file_size,
            "category": doc.category,
            "category_display": doc.get_category_display(),
            "total_chunks": doc.chunks_count,
            "chunks": chunks,
            "showing": len(chunks),
            "uploaded_at": doc.created_at.isoformat() if doc.created_at else None,
            "status": doc.status
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["GET"])
def get_foundation_document_file(request, doc_id):
    """
    Admin endpoint: Get actual file content for a Foundation document.
    For TXT files: returns the text content
    For PDF files: returns the file for download/viewing

    GET /chatlog/admin/foundation/<doc_id>/file/
    """
    try:
        try:
            doc = FoundationDocument.objects.get(id=doc_id)
        except FoundationDocument.DoesNotExist:
            return JsonResponse({"error": "Document not found"}, status=404)

        file_path = doc.file_path
        if not file_path:
            return JsonResponse({"error": "File path not available"}, status=404)

        # Check if file exists
        if not os.path.exists(file_path):
            # File might be on VPS in kb_builder directory
            # Try alternative paths
            alt_paths = [
                f"/app/kb_builder/downloads/{doc.filename}",
                f"/opt/kb_builder/downloads/{doc.filename}",
            ]
            file_found = False
            for alt_path in alt_paths:
                if os.path.exists(alt_path):
                    file_path = alt_path
                    file_found = True
                    break

            if not file_found:
                # Return file info even if file not accessible
                file_ext = doc.filename.split('.')[-1].lower() if '.' in doc.filename else 'unknown'
                return JsonResponse({
                    "error": "File not accessible on server",
                    "file_info": {
                        "filename": doc.filename,
                        "file_path": doc.file_path,
                        "file_type": file_ext,
                        "file_size": doc.file_size,
                        "chunks_count": doc.chunks_count
                    }
                }, status=404)

        file_ext = doc.filename.split('.')[-1].lower() if '.' in doc.filename else 'unknown'

        # For TXT files, return content as JSON
        if file_ext == 'txt':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return JsonResponse({
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "file_type": "txt",
                    "content": content,
                    "file_size": len(content),
                    "chunks_count": doc.chunks_count
                })
            except Exception as read_err:
                return JsonResponse({"error": f"Could not read file: {str(read_err)}"}, status=500)

        # For PDF files, return the file
        elif file_ext == 'pdf':
            try:
                return FileResponse(
                    open(file_path, 'rb'),
                    content_type='application/pdf',
                    as_attachment=False,
                    filename=doc.filename
                )
            except Exception as read_err:
                return JsonResponse({"error": f"Could not serve PDF: {str(read_err)}"}, status=500)

        else:
            return JsonResponse({
                "error": f"Unsupported file type: {file_ext}",
                "supported_types": ["txt", "pdf"]
            }, status=400)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_foundation_stats(request):
    """
    Get Foundation Knowledge Base statistics (public endpoint).
    GET /chatlog/foundation/stats/
    """
    try:
        # Get all completed Foundation documents (uploaded via admin)
        documents = FoundationDocument.objects.filter(status='completed', is_active=True)

        admin_docs = documents.count()
        admin_chunks = sum(doc.chunks_count for doc in documents)

        # Category breakdown from admin uploads
        categories = {}
        for doc in documents:
            cat_display = doc.get_category_display()
            if cat_display not in categories:
                categories[cat_display] = {'count': 0, 'chunks': 0}
            categories[cat_display]['count'] += 1
            categories[cat_display]['chunks'] += doc.chunks_count

        # Get ACTUAL chunk count from vector database (includes KB builder uploads)
        db_chunks = 0
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM langchain_pg_embedding e
                    JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                    WHERE c.name = %s
                """, [FOUNDATION_COLLECTION])
                result = cursor.fetchone()
                db_chunks = result[0] if result else 0
        except Exception as db_err:
            print(f"[Foundation Stats] DB query error: {db_err}")
            db_chunks = admin_chunks  # Fallback to admin count

        return JsonResponse({
            "total_documents": admin_docs,
            "total_chunks": db_chunks,  # Use actual DB count
            "admin_uploaded_chunks": admin_chunks,
            "categories": categories,
            "collection_name": FOUNDATION_COLLECTION
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ===================================
# DATABASE STATISTICS (ADMIN)
# ===================================

@csrf_exempt
@require_http_methods(["GET"])
def get_db_stats(request):
    """
    Admin endpoint: Get vector database statistics.
    GET /chatlog/admin/db-stats/

    Returns:
    - total_chunks: Total number of vector chunks in database
    - db_size: Human-readable database size
    - collections: List of all vector collections
    - recent_chunks: Sample of recent chunks for debugging
    """
    try:
        # Check admin access
        is_admin, auth_user, error_response = is_admin_user(request)
        if error_response:
            return error_response

        from django.db import connection

        stats = {
            "total_chunks": 0,
            "db_size": "Unknown",
            "collections": [],
            "recent_chunks": [],
            "user_stats": {}
        }

        with connection.cursor() as cursor:
            # 1. Total chunks in vector store
            try:
                cursor.execute("SELECT count(*) FROM langchain_pg_embedding")
                stats["total_chunks"] = cursor.fetchone()[0]
            except Exception as e:
                stats["total_chunks_error"] = str(e)

            # 2. Database size
            try:
                cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
                stats["db_size"] = cursor.fetchone()[0]
            except Exception as e:
                stats["db_size_error"] = str(e)

            # 3. Collections list with chunk counts
            try:
                cursor.execute("""
                    SELECT c.name, c.uuid, COUNT(e.id) as chunk_count
                    FROM langchain_pg_collection c
                    LEFT JOIN langchain_pg_embedding e ON c.uuid = e.collection_id
                    GROUP BY c.name, c.uuid
                    ORDER BY chunk_count DESC
                """)
                stats["collections"] = [
                    {"name": r[0], "uuid": str(r[1]), "chunk_count": r[2]}
                    for r in cursor.fetchall()
                ]
            except Exception as e:
                stats["collections_error"] = str(e)

            # 4. Sample of recent chunks (for debugging)
            try:
                cursor.execute("""
                    SELECT document, cmetadata
                    FROM langchain_pg_embedding
                    ORDER BY id DESC
                    LIMIT 5
                """)
                for r in cursor.fetchall():
                    content = r[0] if r[0] else ""
                    stats["recent_chunks"].append({
                        "content": content[:200] + "..." if len(content) > 200 else content,
                        "metadata": r[1]
                    })
            except Exception as e:
                stats["recent_chunks_error"] = str(e)

        # 5. User statistics from Django models
        total_users = UserKnowledgeBase.objects.count()
        total_pdfs = UploadedPDF.objects.count()
        completed_pdfs = UploadedPDF.objects.filter(status='completed').count()
        failed_pdfs = UploadedPDF.objects.filter(status='failed').count()

        stats["user_stats"] = {
            "total_users": total_users,
            "total_pdfs": total_pdfs,
            "completed_pdfs": completed_pdfs,
            "failed_pdfs": failed_pdfs,
            "processing_pdfs": UploadedPDF.objects.filter(status='processing').count()
        }

        # 6. Foundation KB stats
        foundation_docs = FoundationDocument.objects.filter(is_active=True)
        stats["foundation_stats"] = {
            "total_documents": foundation_docs.count(),
            "total_chunks": sum(doc.chunks_count for doc in foundation_docs.filter(status='completed')),
            "completed": foundation_docs.filter(status='completed').count(),
            "failed": foundation_docs.filter(status='failed').count()
        }

        return JsonResponse(stats)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


# ===================================
# RAG EVALUATION (ADMIN)
# ===================================

# Evaluation test dataset
RAG_EVAL_DATA = [
    {
        "id": 1,
        "question": "What PPE is required for underground mining?",
        "expected_topics": ["hard hat", "helmet", "safety glasses", "boots", "vest", "gloves"],
        "category": "PPE",
        "is_summary": False
    },
    {
        "id": 2,
        "question": "What are the MSHA requirements for mine inspections?",
        "expected_topics": ["inspection", "cfr", "msha", "quarterly", "hazard", "compliance"],
        "category": "Regulations",
        "is_summary": False
    },
    {
        "id": 3,
        "question": "Give me a summary of all fire safety procedures",
        "expected_topics": ["fire", "evacuation", "extinguisher", "alarm", "emergency", "escape"],
        "category": "Fire Safety",
        "is_summary": True
    },
    {
        "id": 4,
        "question": "What are the ventilation requirements in underground mines?",
        "expected_topics": ["ventilation", "air", "methane", "cfr", "oxygen", "dust"],
        "category": "Ventilation",
        "is_summary": False
    },
    {
        "id": 5,
        "question": "Summarize the key points about electrical safety in mining",
        "expected_topics": ["electrical", "grounding", "lockout", "tagout", "shock", "cable"],
        "category": "Electrical Safety",
        "is_summary": True
    },
    {
        "id": 6,
        "question": "What should I do in case of a roof fall emergency?",
        "expected_topics": ["roof", "fall", "emergency", "evacuate", "rescue", "support"],
        "category": "Emergency Response",
        "is_summary": False
    },
    {
        "id": 7,
        "question": "Provide an overview of training requirements for new miners",
        "expected_topics": ["training", "hours", "certification", "annual", "refresher", "msha"],
        "category": "Training",
        "is_summary": True
    },
]

# Intent detection test cases
INTENT_TEST_CASES = [
    ("What is PPE?", False),
    ("Give me a summary", True),
    ("Summarize the documents", True),
    ("What are the key points?", True),
    ("Explain the regulation", False),
    ("Provide an overview", True),
    ("Tell me about fire safety", False),
    ("Tell me about all safety procedures", True),
]


def _calculate_topic_coverage(answer: str, expected_topics: list) -> tuple:
    """Calculate what percentage of expected topics are mentioned in the answer."""
    answer_lower = answer.lower()
    found_topics = []
    missing_topics = []

    for topic in expected_topics:
        if topic.lower() in answer_lower:
            found_topics.append(topic)
        else:
            missing_topics.append(topic)

    coverage = len(found_topics) / len(expected_topics) if expected_topics else 0
    return coverage, found_topics, missing_topics


def _calculate_semantic_similarity(query: str, answer: str, expected_topics: list) -> dict:
    """Calculate semantic similarity using sentence-transformers."""
    try:
        from sentence_transformers import SentenceTransformer, util

        # Use the same model as embeddings
        model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

        # Create reference text from expected topics
        reference_text = f"The answer should cover: {', '.join(expected_topics)}"

        # Encode texts
        query_embedding = model.encode(query, convert_to_tensor=True)
        answer_embedding = model.encode(answer, convert_to_tensor=True)
        reference_embedding = model.encode(reference_text, convert_to_tensor=True)

        # Calculate similarities
        query_answer_sim = float(util.cos_sim(query_embedding, answer_embedding)[0][0])
        answer_reference_sim = float(util.cos_sim(answer_embedding, reference_embedding)[0][0])

        # Combined semantic score (relevance to query + coverage of expected topics)
        semantic_score = (query_answer_sim * 0.4) + (answer_reference_sim * 0.6)

        return {
            "query_relevance": round(query_answer_sim * 100, 1),
            "topic_alignment": round(answer_reference_sim * 100, 1),
            "semantic_score": round(semantic_score * 100, 1),
            "available": True
        }
    except Exception as e:
        return {
            "query_relevance": 0,
            "topic_alignment": 0,
            "semantic_score": 0,
            "available": False,
            "error": str(e)
        }


def _evaluate_response_quality(answer: str) -> dict:
    """Evaluate response quality based on structure and content."""
    quality = {
        "has_structure": False,
        "has_citations": False,
        "has_action_items": False,
        "appropriate_length": False,
        "score": 0.0
    }

    # Check for structured formatting
    if any(marker in answer for marker in ["##", "**", "1.", "- ", "* "]):
        quality["has_structure"] = True
        quality["score"] += 0.25

    # Check for regulation citations
    if any(marker in answer.upper() for marker in ["CFR", "MSHA", "OSHA", "30 CFR"]):
        quality["has_citations"] = True
        quality["score"] += 0.25

    # Check for action items or recommendations
    if any(marker in answer.lower() for marker in ["recommend", "action", "should", "must", "required"]):
        quality["has_action_items"] = True
        quality["score"] += 0.25

    # Check for appropriate length (not too short, not too long)
    word_count = len(answer.split())
    if 50 <= word_count <= 1500:
        quality["appropriate_length"] = True
        quality["score"] += 0.25

    quality["word_count"] = word_count
    return quality


@csrf_exempt
@require_http_methods(["GET", "POST"])
def run_rag_evaluation(request):
    """
    Admin endpoint: Run RAG evaluation framework.
    GET /chatlog/admin/rag-evaluation/ - Get evaluation status/info
    POST /chatlog/admin/rag-evaluation/ - Run full evaluation

    Optional POST body:
    {
        "collection": "foundation_mining_kb",  // Collection to test against
        "test_ids": [1, 2, 3]  // Specific tests to run (optional, runs all if not provided)
    }

    Returns comprehensive evaluation results for dashboard display.
    """
    from datetime import datetime
    from .langgraph_agent import is_summary_request

    try:
        # Check admin access
        is_admin_check, auth_user, error_response = is_admin_user(request)
        if error_response:
            return error_response

        # GET request - return evaluation info
        if request.method == "GET":
            return JsonResponse({
                "status": "ready",
                "available_tests": len(RAG_EVAL_DATA),
                "test_categories": list(set(t["category"] for t in RAG_EVAL_DATA)),
                "intent_test_cases": len(INTENT_TEST_CASES),
                "description": "RAG Evaluation Framework for Safety Agent",
                "endpoints": {
                    "GET": "Get evaluation info",
                    "POST": "Run evaluation (optional: collection, test_ids)"
                }
            })

        # POST request - run evaluation
        # Parse request body
        try:
            body = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            body = {}

        collection_name = body.get("collection", FOUNDATION_COLLECTION)
        test_ids = body.get("test_ids", None)  # None means run all

        # Initialize results structure
        results = {
            "timestamp": datetime.now().isoformat(),
            "collection": collection_name,
            "intent_detection": {
                "tests": [],
                "passed": 0,
                "total": 0,
                "status": "pending"
            },
            "rag_tests": {
                "tests": [],
                "passed": 0,
                "total": 0,
                "avg_coverage": 0,
                "avg_quality": 0,
                "avg_semantic": 0,
                "status": "pending"
            },
            "overall": {
                "status": "pending",
                "passed": False
            }
        }

        # ===================================
        # PHASE 1: Intent Detection Tests
        # ===================================
        intent_passed = 0
        for query, expected in INTENT_TEST_CASES:
            actual = is_summary_request(query)
            passed = actual == expected
            if passed:
                intent_passed += 1

            results["intent_detection"]["tests"].append({
                "query": query,
                "expected": expected,
                "actual": actual,
                "passed": passed
            })

        results["intent_detection"]["passed"] = intent_passed
        results["intent_detection"]["total"] = len(INTENT_TEST_CASES)
        results["intent_detection"]["status"] = "pass" if intent_passed == len(INTENT_TEST_CASES) else "fail"

        # ===================================
        # PHASE 2: RAG Quality Tests
        # ===================================
        try:
            # Initialize agent
            agent = construct_agent_graph(collection_name)

            # Filter tests if specific IDs requested
            test_data = RAG_EVAL_DATA
            if test_ids:
                test_data = [t for t in RAG_EVAL_DATA if t["id"] in test_ids]

            total_coverage = 0
            total_quality = 0
            total_semantic = 0
            rag_passed = 0

            for test_case in test_data:
                test_result = {
                    "id": test_case["id"],
                    "category": test_case["category"],
                    "question": test_case["question"],
                    "is_summary": test_case["is_summary"],
                    "status": "pending"
                }

                try:
                    # Invoke agent with timeout consideration
                    response = agent.invoke({
                        "messages": [HumanMessage(content=test_case["question"])]
                    })
                    answer = response["messages"][-1].content

                    # Calculate metrics
                    coverage, found, missing = _calculate_topic_coverage(
                        answer, test_case["expected_topics"]
                    )
                    quality = _evaluate_response_quality(answer)

                    # Calculate semantic similarity (DeepEval-style metric)
                    semantic = _calculate_semantic_similarity(
                        test_case["question"], answer, test_case["expected_topics"]
                    )

                    # Combined score (40% coverage, 30% quality, 30% semantic)
                    semantic_factor = (semantic["semantic_score"] / 100) if semantic["available"] else 0
                    combined_score = (coverage * 0.4) + (quality["score"] * 0.3) + (semantic_factor * 0.3)
                    passed = combined_score >= 0.5

                    if passed:
                        rag_passed += 1

                    total_coverage += coverage
                    total_quality += quality["score"]
                    total_semantic += semantic["semantic_score"] if semantic["available"] else 0

                    test_result.update({
                        "status": "pass" if passed else "fail",
                        "coverage": {
                            "score": round(coverage * 100, 1),
                            "found": found,
                            "missing": missing,
                            "expected": test_case["expected_topics"]
                        },
                        "quality": {
                            "score": round(quality["score"] * 100, 1),
                            "has_structure": quality["has_structure"],
                            "has_citations": quality["has_citations"],
                            "has_action_items": quality["has_action_items"],
                            "appropriate_length": quality["appropriate_length"],
                            "word_count": quality["word_count"]
                        },
                        "semantic": semantic,  # DeepEval-style semantic similarity
                        "combined_score": round(combined_score * 100, 1),
                        "answer_preview": answer[:500] + "..." if len(answer) > 500 else answer
                    })

                except Exception as e:
                    test_result.update({
                        "status": "error",
                        "error": str(e)
                    })

                results["rag_tests"]["tests"].append(test_result)

            # Calculate averages
            num_tests = len(test_data)
            results["rag_tests"]["passed"] = rag_passed
            results["rag_tests"]["total"] = num_tests
            results["rag_tests"]["avg_coverage"] = round((total_coverage / num_tests) * 100, 1) if num_tests > 0 else 0
            results["rag_tests"]["avg_quality"] = round((total_quality / num_tests) * 100, 1) if num_tests > 0 else 0
            results["rag_tests"]["avg_semantic"] = round(total_semantic / num_tests, 1) if num_tests > 0 else 0
            results["rag_tests"]["status"] = "pass" if rag_passed >= (num_tests * 0.7) else "fail"

        except Exception as e:
            results["rag_tests"]["status"] = "error"
            results["rag_tests"]["error"] = str(e)

        # ===================================
        # OVERALL STATUS
        # ===================================
        intent_ok = results["intent_detection"]["status"] == "pass"
        rag_ok = results["rag_tests"]["status"] == "pass"

        results["overall"]["status"] = "pass" if (intent_ok and rag_ok) else "fail"
        results["overall"]["passed"] = intent_ok and rag_ok
        results["overall"]["summary"] = {
            "intent_detection": f"{results['intent_detection']['passed']}/{results['intent_detection']['total']} passed",
            "rag_tests": f"{results['rag_tests']['passed']}/{results['rag_tests']['total']} passed",
            "avg_coverage": f"{results['rag_tests']['avg_coverage']}%",
            "avg_quality": f"{results['rag_tests']['avg_quality']}%",
            "avg_semantic": f"{results['rag_tests']['avg_semantic']}%"
        }

        return JsonResponse(results)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)