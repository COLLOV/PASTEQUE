from fastapi import APIRouter, HTTPException
from ....schemas.chat import ChatRequest, ChatResponse
from ....core.config import settings
from ....services.chat_service import ChatService
from ....engines.openai_engine import OpenAIChatEngine
from ....integrations.openai_client import OpenAICompatibleClient

router = APIRouter(prefix="/chat")


@router.post("/completions", response_model=ChatResponse)
def chat_completion(payload: ChatRequest) -> ChatResponse:  # type: ignore[valid-type]
    """Chat completions via moteur OpenAI‑compatible.

    - En mode local (`LLM_MODE=local`): utilise `VLLM_BASE_URL` + `Z_LOCAL_MODEL`.
    - En mode API (`LLM_MODE=api`): utilise `OPENAI_BASE_URL` + `OPENAI_API_KEY` + `LLM_MODEL`.
    """
    if settings.llm_mode not in {"local", "api"}:
        raise HTTPException(status_code=500, detail="Invalid LLM_MODE; expected 'local' or 'api'")

    if settings.llm_mode == "local":
        base_url = settings.vllm_base_url
        model = settings.z_local_model
        api_key = None
    else:
        base_url = settings.openai_base_url
        model = settings.llm_model
        api_key = settings.openai_api_key

    if not base_url or not model:
        raise HTTPException(status_code=500, detail="LLM base_url/model not configured")

    client = OpenAICompatibleClient(base_url=base_url, api_key=api_key)
    engine = OpenAIChatEngine(client=client, model=model)
    service = ChatService(engine)
    return service.completion(payload)
