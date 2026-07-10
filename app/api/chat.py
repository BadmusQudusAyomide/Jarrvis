from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import logging
import json
import re
from app.llm.router import route_model, classify_intent
from app.memory.short_term import get_history, add_message, clear_history
from app.memory.long_term import (
    is_worth_remembering,
    store_memory,
    retrieve_memories,
    build_memory_context
)
from app.memory.profile import (
    extract_name,
    set_profile_name,
    get_profile_name,
    clear_profile,
    get_profile,
    update_profile,
    add_profile_note,
    remove_profile_note,
    extract_profile_updates,
    build_profile_context_for_message,
    build_persona_header,
    build_full_profile_summary,
    set_pending_confirmation,
    get_pending_confirmation,
    clear_pending_confirmation,
    apply_pending_confirmation,
)
from app.memory.context_manager import manage_context
from app.agents.core_agent import Agent
from app.agents.planning import PlanOrchestrator, should_plan_task
from app.agents.confirmation import get_pending_action, clear_pending_action, describe_action
from app.config import DEFAULT_MODEL, CODING_MODEL, get_system_prompt
from app.tools.system_tools import execute_tool

logger = logging.getLogger(__name__)

router = APIRouter()


def _normalize_response_text(value):
    """Normalize agent output to plain text for API and chat history."""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)

class ChatRequest(BaseModel):
    message: str
    session_id: str = "local"  # Default to "local" for testing


class DownloadMediaRequest(BaseModel):
    url: str
    audio_only: bool = False
    quality: str = "best"


class ProfileUpdateRequest(BaseModel):
    session_id: str = "local"
    updates: dict


class ProfileActionRequest(BaseModel):
    session_id: str = "local"
    text: str


@router.post("/chat/clear")
def clear_chat(session_id: str = "local"):
    clear_history(session_id)
    clear_profile(session_id)
    return {"message": f"Cleared chat and profile for session '{session_id}'"}


@router.post("/tools/download_media")
def download_media(req: DownloadMediaRequest):
    result = execute_tool("download_media", {
        "url": req.url,
        "audio_only": req.audio_only,
        "quality": req.quality
    })
    return {"response": _normalize_response_text(result)}


@router.get("/profile/get")
def profile_get(session_id: str = "local"):
    return {"profile": get_profile(session_id)}


@router.post("/profile/update")
def profile_update(req: ProfileUpdateRequest):
    profile = update_profile(req.session_id, req.updates)
    return {"profile": profile}


@router.post("/profile/remember")
def profile_remember(req: ProfileActionRequest):
    profile = add_profile_note(req.session_id, req.text)
    return {"profile": profile}


@router.post("/profile/forget")
def profile_forget(req: ProfileActionRequest):
    profile = remove_profile_note(req.session_id, req.text)
    return {"profile": profile}

@router.post("/chat")
def chat(req: ChatRequest):
    normalized_msg = req.message.strip()

    pending = get_pending_confirmation(req.session_id)
    if pending:
        msg = normalized_msg.lower()
        if msg in {"yes", "y", "confirm", "proceed", "ok", "okay"}:
            success, result = apply_pending_confirmation(req.session_id)
            response_text = result if success else f"Could not apply change: {result}"
            add_message(req.session_id, "user", req.message)
            add_message(req.session_id, "assistant", response_text)
            return {"response": response_text}
        if msg in {"no", "n", "cancel", "stop"}:
            clear_pending_confirmation(req.session_id)
            response_text = "Okay, I cancelled that profile update."
            add_message(req.session_id, "user", req.message)
            add_message(req.session_id, "assistant", response_text)
            return {"response": response_text}

    pending_action = get_pending_action(req.session_id)
    if pending_action:
        msg = normalized_msg.lower()
        if msg in {"yes", "y", "confirm", "proceed", "ok", "okay"}:
            tool_name = pending_action.get("tool")
            tool_args = pending_action.get("args", {})
            clear_pending_action(req.session_id)
            result = execute_tool(tool_name, tool_args)
            response_text = str(result)
            add_message(req.session_id, "user", req.message)
            add_message(req.session_id, "assistant", response_text)
            return {"response": response_text}
        if msg in {"no", "n", "cancel", "stop"}:
            clear_pending_action(req.session_id)
            response_text = f"Okay, I cancelled: {describe_action(pending_action.get('tool'), pending_action.get('args', {}))}"
            add_message(req.session_id, "user", req.message)
            add_message(req.session_id, "assistant", response_text)
            return {"response": response_text}

    # 0. Deterministic profile capture + direct recall
    extracted_name = extract_name(req.message)
    if extracted_name:
        existing_name = get_profile_name(req.session_id)
        if existing_name and existing_name.strip().lower() != extracted_name.strip().lower():
            set_pending_confirmation(req.session_id, "name", extracted_name, existing_name)
            response_text = (
                f"I currently have your name as '{existing_name}'. "
                f"Do you want me to update it to '{extracted_name}'? Reply 'yes' or 'no'."
            )
            add_message(req.session_id, "user", req.message)
            add_message(req.session_id, "assistant", response_text)
            return {"response": response_text, "requires_confirmation": True}
        set_profile_name(req.session_id, extracted_name)
        # Fast path: if this is a direct name declaration, do not run agent/LLM.
        if re.match(r"^\s*(my name is|i am|i'm)\s+.+$", normalized_msg, re.IGNORECASE):
            response_text = f"Nice to meet you, {extracted_name}. I'll remember your name."
            add_message(req.session_id, "user", req.message)
            add_message(req.session_id, "assistant", response_text)
            return {"response": response_text}
    auto_updates = extract_profile_updates(req.message)
    if auto_updates:
        update_profile(req.session_id, auto_updates)

    if re.search(r"\b(what(?:'s| is)\s+my\s+name|my\s+name\s+again)\b", req.message, re.IGNORECASE):
        saved_name = get_profile_name(req.session_id)
        if saved_name:
            response_text = f"Your name is {saved_name}."
            add_message(req.session_id, "user", req.message)
            add_message(req.session_id, "assistant", response_text)
            return {"response": response_text}

    remember_match = re.search(r"^\s*(remember that|remember)\s+(.+)$", req.message, re.IGNORECASE)
    if remember_match:
        note = remember_match.group(2).strip()
        add_profile_note(req.session_id, note)
        response_text = f"Noted. I'll remember: {note}"
        add_message(req.session_id, "user", req.message)
        add_message(req.session_id, "assistant", response_text)
        return {"response": response_text}

    forget_match = re.search(r"^\s*(forget)\s+(.+)$", req.message, re.IGNORECASE)
    if forget_match:
        note = forget_match.group(2).strip()
        remove_profile_note(req.session_id, note)
        response_text = f"Done. I removed that note: {note}"
        add_message(req.session_id, "user", req.message)
        add_message(req.session_id, "assistant", response_text)
        return {"response": response_text}

    if re.search(r"\b(who am i|what do you know about me|show my profile)\b", req.message, re.IGNORECASE):
        profile = get_profile(req.session_id)
        response_text = build_full_profile_summary(profile)
        add_message(req.session_id, "user", req.message)
        add_message(req.session_id, "assistant", response_text)
        return {"response": response_text}

    # 1. Retrieve relevant long-term memories
    memories = retrieve_memories(req.message, req.session_id)
    memory_context = build_memory_context(memories)
    profile_data = get_profile(req.session_id)
    persona_header = build_persona_header(profile_data)
    profile_context = build_profile_context_for_message(profile_data, req.message)

    # 2. Classify intent early so we can choose a lighter prompt profile
    intent = classify_intent(req.message)
    prompt_profile = "coding" if intent == "coding" else "full"

    # 3. Build custom system prompt with persona + memory context
    custom_system_prompt = get_system_prompt(profile=prompt_profile) + persona_header + memory_context + profile_context
    
    # 4. Route to appropriate model based on intent
    chosen_model = route_model(req.message, DEFAULT_MODEL, CODING_MODEL)
    
    # 5. Add user message to history
    add_message(req.session_id, "user", req.message)
    
    # 6. Get conversation history
    history = get_history(req.session_id)

    # 7. Compress context if history is getting long
    original_length = len(history)
    history = manage_context(history, req.session_id)
    if len(history) < original_length:
        logger.info(f"Context compressed: {original_length} -> {len(history)} messages")

    # 8. Create agent and run autonomous loop
    logger.info(f"Processing message with model {chosen_model}, history length: {len(history)}")
    if should_plan_task(req.message):
        logger.info("Planning gate triggered for message")
        orchestrator = PlanOrchestrator()
        response_text = orchestrator.run(
            task=req.message,
            history=history,
            system_prompt=custom_system_prompt,
            model=chosen_model,
        )
    else:
        agent = Agent(model=chosen_model)
        response_text = _normalize_response_text(agent.run(req.message, history, custom_system_prompt, session_id=req.session_id))
    
    # 9. Add final response to history
    add_message(req.session_id, "assistant", response_text)

    # 10. Store in long-term memory if worth remembering
    if is_worth_remembering(req.message):
        store_memory(req.session_id, req.message)

    # A destructive-tool confirmation may have been raised during agent.run() —
    # surface it as a flag so the UI can render it distinctly from a normal answer.
    requires_confirmation = get_pending_action(req.session_id) is not None
    return {"response": response_text, "requires_confirmation": requires_confirmation}


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Streaming chat endpoint backed by the full agent/tool loop."""

    def generate():
        # 0. Resolve any pending destructive-action confirmation first
        normalized_msg = req.message.strip().lower()
        pending_action = get_pending_action(req.session_id)
        if pending_action:
            if normalized_msg in {"yes", "y", "confirm", "proceed", "ok", "okay"}:
                tool_name = pending_action.get("tool")
                tool_args = pending_action.get("args", {})
                clear_pending_action(req.session_id)
                response_text = str(execute_tool(tool_name, tool_args))
                add_message(req.session_id, "user", req.message)
                add_message(req.session_id, "assistant", response_text)
                yield json.dumps({"token": response_text}) + "\n"
                yield json.dumps({"done": True}) + "\n"
                return
            if normalized_msg in {"no", "n", "cancel", "stop"}:
                clear_pending_action(req.session_id)
                response_text = f"Okay, I cancelled: {describe_action(pending_action.get('tool'), pending_action.get('args', {}))}"
                add_message(req.session_id, "user", req.message)
                add_message(req.session_id, "assistant", response_text)
                yield json.dumps({"token": response_text}) + "\n"
                yield json.dumps({"done": True}) + "\n"
                return

        # 1. Retrieve memories and build context
        memories = retrieve_memories(req.message, req.session_id)
        memory_context = build_memory_context(memories)
        profile_data = get_profile(req.session_id)
        persona_header = build_persona_header(profile_data)
        profile_context = build_profile_context_for_message(profile_data, req.message)

        # 2. Classify intent early so we can choose a lighter prompt profile
        intent = classify_intent(req.message)
        prompt_profile = "coding" if intent == "coding" else "full"
        system_prompt = get_system_prompt(profile=prompt_profile) + persona_header + memory_context + profile_context

        # 3. Route to model
        chosen_model = route_model(req.message, DEFAULT_MODEL, CODING_MODEL)

        # 4. Add user message and get history
        add_message(req.session_id, "user", req.message)
        history = get_history(req.session_id)

        # 5. Compress context if needed
        history = manage_context(history, req.session_id)

        # 6. Run full agent loop (tools enabled), then stream back by chunks
        logger.info(f"Streaming agent response with model {chosen_model}, history length: {len(history)}")
        if should_plan_task(req.message):
            logger.info("Planning gate triggered for streaming request")
            orchestrator = PlanOrchestrator()
            complete_text = orchestrator.run(
                task=req.message,
                history=history,
                system_prompt=system_prompt,
                model=chosen_model,
            )
        else:
            agent = Agent(model=chosen_model)
            complete_text = _normalize_response_text(agent.run(req.message, history, system_prompt, session_id=req.session_id))

        # 7. Emit response in chunks so frontend streaming UX still works
        chunk_size = 40
        for i in range(0, len(complete_text), chunk_size):
            chunk = complete_text[i:i + chunk_size]
            yield json.dumps({"token": chunk}) + "\n"

        # 8. Store complete response
        add_message(req.session_id, "assistant", complete_text)

        # 9. Store in long-term memory if worth remembering
        if is_worth_remembering(req.message):
            store_memory(req.session_id, req.message)

        yield json.dumps({"done": True}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
