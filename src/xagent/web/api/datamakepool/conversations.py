from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth_dependencies import get_current_user
from ...models.database import get_db
from ...models.user import User
from ...schemas.datamakepool import (
    ConversationMessageRequest,
    ConversationMessageResponse,
    ConversationResponse,
    CreateConversationRequest,
    FlowDraftResponse,
)
from ....core.datamakepool.conversations import ConversationService

router = APIRouter(prefix="/api/datamakepool/conversations", tags=["datamakepool"])


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationResponse:
    """创建探索态会话。

    当前这一版直接复用 Task 作为会话宿主，并同步创建一个空白 FlowDraft。
    """
    try:
        result = ConversationService(db=db).create_conversation(
            user=user,
            title=request.title,
            objective=request.objective,
        )
        return ConversationResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{conversation_id}/messages", response_model=ConversationMessageResponse)
async def post_message(
    conversation_id: int,
    request: ConversationMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationMessageResponse:
    """向探索会话追加一条消息，并刷新当前初版 FlowDraft。"""
    try:
        result = ConversationService(db=db).post_message(
            conversation_id=conversation_id,
            content=request.content,
            user=user,
        )
        return ConversationMessageResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{conversation_id}/flowdraft", response_model=FlowDraftResponse)
async def get_conversation_flowdraft(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FlowDraftResponse:
    """读取某个会话当前关联的 FlowDraft。"""
    try:
        result = ConversationService(db=db).get_conversation_flowdraft(
            conversation_id=conversation_id,
            user=user,
        )
        return FlowDraftResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
