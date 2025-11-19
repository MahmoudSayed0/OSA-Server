from django.urls import path
from .views import (
    upload_pdf, ask_agent, get_chat_history, clear_chat_history,
    create_user, delete_user, get_all_users, list_pdfs, delete_pdf, get_pdf_file,
    create_session, list_sessions, get_session_messages, update_session, delete_session
)

urlpatterns = [
    # User Management
    path("create-user/", create_user, name="create_user"),
    path("delete-user/", delete_user, name="delete_user"),
    path("get-all-users/", get_all_users, name="get_all_users"),

    # PDF Management
    path("upload-pdf/", upload_pdf, name="upload_pdf"),
    path("list-pdfs/", list_pdfs, name="list_pdfs"),
    path("delete-pdf/", delete_pdf, name="delete_pdf"),
    path("get-pdf/<int:pdf_id>/", get_pdf_file, name="get_pdf_file"),

    # Chat Agent
    path("ask-agent/", ask_agent, name="ask_agent"),

    # Legacy Chat History (backward compatibility)
    path("chat-history/", get_chat_history, name="get_chat_history"),
    path("clear-chat-history/", clear_chat_history, name="clear_chat_history"),

    # Session Management (NEW)
    path("sessions/", create_session, name="create_session"),
    path("sessions/list/", list_sessions, name="list_sessions"),
    path("sessions/<str:session_id>/", update_session, name="update_session"),
    path("sessions/<str:session_id>/delete/", delete_session, name="delete_session"),
    path("sessions/<str:session_id>/messages/", get_session_messages, name="get_session_messages"),

]
