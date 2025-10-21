from django.urls import path
from .views import upload_pdf, ask_agent, get_chat_history, clear_chat_history, create_user, delete_user, get_all_users

urlpatterns = [
    path("upload-pdf/", upload_pdf, name="upload_pdf"),
    path("ask-agent/", ask_agent, name="ask_agent"),
    path("chat-history/", get_chat_history, name="get_chat_history"),
    path("clear-chat-history/", clear_chat_history, name="clear_chat_history"),
    path("create-user/", create_user, name="create_user"),
    path("delete-user/", delete_user, name="delete_user"),
    path("get-all-users/", get_all_users, name="get_all_users"),

]
