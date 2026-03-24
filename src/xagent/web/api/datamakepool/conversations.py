from fastapi import APIRouter

router = APIRouter(prefix="/api/datamakepool/conversations", tags=["datamakepool"])


@router.post("")
async def create_conversation() -> dict:
    """创建探索态会话。

    后续这里会负责初始化 Task 与 FlowDraft 的关联入口。
    """
    return {"status": "not_implemented"}


@router.post("/{conversation_id}/messages")
async def post_message(conversation_id: int) -> dict:
    """向探索会话追加一条消息。"""
    return {"conversation_id": conversation_id, "status": "not_implemented"}


@router.get("/{conversation_id}/flowdraft")
async def get_conversation_flowdraft(conversation_id: int) -> dict:
    """读取某个会话当前关联的 FlowDraft。"""
    return {"conversation_id": conversation_id, "status": "not_implemented"}
