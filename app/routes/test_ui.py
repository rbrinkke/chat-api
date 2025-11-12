"""
Test UI Routes - Browser-based testing interface for chat API.

Provides a comprehensive UI for:
- Multi-user WebSocket testing
- RBAC permission validation
- Real-time message exchange
- Connection management
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/test-chat", response_class=HTMLResponse)
async def get_chat_test_ui(request: Request):
    """
    Serve the chat test UI - a browser-based harness for end-to-end testing.

    Features:
    - JWT token authentication
    - Multi-user simulation (open multiple windows)
    - Real-time WebSocket messaging
    - RBAC permission testing
    - Message CRUD operations
    - Connection monitoring

    Usage:
        1. Get JWT tokens from auth-api for different users
        2. Open this page in multiple browser windows
        3. Paste different tokens in each window
        4. Connect to the same group and test messaging

    Example:
        http://localhost:8001/test-chat
    """
    return templates.TemplateResponse("test_chat.html", {"request": request})
