from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ....core.database import get_session
from ....core.security import get_current_user, user_is_admin
from ....models.user import User
from ....repositories.conversation_repository import ConversationRepository
from ....repositories.feedback_repository import FeedbackRepository
from ....schemas.feedback import (
    FeedbackCreateRequest,
    FeedbackResponse,
    AdminFeedbackResponse,
)

router = APIRouter(prefix="/feedback")


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def create_feedback(  # type: ignore[valid-type]
    payload: FeedbackCreateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FeedbackResponse:
    conv_repo = ConversationRepository(session)
    fb_repo = FeedbackRepository(session)
    is_admin = user_is_admin(current_user)
    conv = conv_repo.get_by_id(payload.conversation_id) if is_admin else conv_repo.get_by_id_for_user(payload.conversation_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")

    msg = conv_repo.get_message_by_id(payload.message_id)
    if not msg or msg.conversation_id != conv.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message introuvable pour cette conversation")
    if msg.role != "assistant":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Feedback uniquement sur une réponse assistant")

    try:
        feedback = fb_repo.upsert(
            user_id=current_user.id,
            conversation_id=conv.id,
            message_id=msg.id,
            value=payload.value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    session.commit()
    session.refresh(feedback)
    return FeedbackResponse.from_model(feedback)


@router.get("", response_model=list[FeedbackResponse])
def list_my_feedback(  # type: ignore[valid-type]
    conversation_id: int = Query(..., ge=1),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[FeedbackResponse]:
    conv_repo = ConversationRepository(session)
    fb_repo = FeedbackRepository(session)
    is_admin = user_is_admin(current_user)
    conv = conv_repo.get_by_id(conversation_id) if is_admin else conv_repo.get_by_id_for_user(conversation_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    items = fb_repo.list_for_conversation_user(conversation_id=conversation_id, user_id=current_user.id)
    return [FeedbackResponse.from_model(item) for item in items]


@router.delete("/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feedback(  # type: ignore[valid-type]
    feedback_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    repo = FeedbackRepository(session)
    fb = repo.get_by_id(feedback_id)
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback introuvable")
    if fb.user_id != current_user.id and not user_is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Suppression non autorisée")
    repo.delete(fb)
    session.commit()


@router.post("/{feedback_id}/archive", response_model=AdminFeedbackResponse)
def archive_feedback(  # type: ignore[valid-type]
    feedback_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AdminFeedbackResponse:
    if not user_is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    repo = FeedbackRepository(session)
    fb = repo.get_by_id(feedback_id)
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback introuvable")
    repo.archive(fb)
    session.commit()
    session.refresh(fb)
    return AdminFeedbackResponse.from_model(fb)


@router.get("/admin", response_model=list[AdminFeedbackResponse])
def list_admin_feedback(  # type: ignore[valid-type]
    limit: int = Query(200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[AdminFeedbackResponse]:
    if not user_is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    repo = FeedbackRepository(session)
    items = repo.list_latest(limit=limit)
    return [AdminFeedbackResponse.from_model(item) for item in items]
