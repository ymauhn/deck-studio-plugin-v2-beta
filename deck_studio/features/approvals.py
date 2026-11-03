"""Approvals: a tool call the write guard asks about waits for the author (SPEC story 34).

The agent's PreToolUse hook calls ask(): it publishes an `approval` event (the card) and waits for
POST /api/approvals/{id} {decision: "allow" | "deny"}. No answer in time is a denial. Every pending card
is closed by a second `approval` event with its end state; GET /api/approvals lists the open ones, for a page
opened late. As the agent loop's feature module, it also closes the agent's renderer at shutdown."""
import asyncio
import uuid

from fastapi import APIRouter, Request

from deck_studio.server.api import ApiError, json_body

router = APIRouter()


def timeout(state):
    """Seconds an approval waits: 10 min, or the config's approvalTimeout."""
    return state.config.get("approvalTimeout", 600)


def _pending(state):
    return state.extras.setdefault("approvals", {})  # approval id -> (future of the decision, its card)


async def ask(state, chat_id, turn_id, tool, summary, reason):
    """Show the card and wait: "allow", "deny" or "timeout". A cancelled wait (the turn stopped) closes the card."""
    approval_id = str(uuid.uuid4())
    card = {"id": approval_id, "chatId": chat_id, "turnId": turn_id, "tool": tool, "summary": summary,
            "reason": reason, "state": "pending"}
    answer = asyncio.get_running_loop().create_future()
    _pending(state)[approval_id] = answer, card
    await state.events.publish("approval", **card)
    decision = "cancelled"
    try:
        decision = await asyncio.wait_for(answer, timeout(state))
    except TimeoutError:
        decision = "timeout"
    finally:
        _pending(state).pop(approval_id, None)
        await state.events.publish("approval", id=approval_id, chatId=chat_id, turnId=turn_id, state=decision)
    return decision


async def shutdown(state):
    """The agent's renderer (a headless Chromium, started on the first screenshot) goes with the server."""
    if renderer := state.extras.get("renderer"):
        await renderer.close()


@router.get("/api/approvals")
def open_cards(request: Request):
    """The cards still waiting for the author."""
    return [card for _, card in _pending(request.app.state.studio).values()]


@router.post("/api/approvals/{approval_id}")
async def decide(approval_id: str, request: Request):
    state = request.app.state.studio
    decision = (await json_body(request)).get("decision")
    if decision not in ("allow", "deny"):
        raise ApiError(400, "decision", 'A decisão deve ser "allow" ou "deny".')
    answer, _ = _pending(state).get(approval_id, (None, None))
    if answer is None or answer.done():
        raise ApiError(404, "not-found", "Esta aprovação não está mais pendente.")
    answer.set_result(decision)
    return {"id": approval_id, "decision": decision}
