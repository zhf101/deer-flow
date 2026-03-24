from fastapi import APIRouter

router = APIRouter(prefix="/api/datamakepool/conversations", tags=["datamakepool"])


@router.post("")
async def create_conversation() -> dict:
    return {"status": "not_implemented"}


@router.post("/{conversation_id}/messages")
async def post_message(conversation_id: int) -> dict:
    return {"conversation_id": conversation_id, "status": "not_implemented"}


@router.get("/{conversation_id}/flowdraft")
async def get_conversation_flowdraft(conversation_id: int) -> dict:
    return {"conversation_id": conversation_id, "status": "not_implemented"}
