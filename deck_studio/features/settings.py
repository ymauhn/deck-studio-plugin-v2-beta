"""Settings: the model and the skills of new chats, kept in data_dir/settings.json (PYTHON.md "Skills").

GET /api/settings gives the model and the skills catalog, each skill with `on`; POST takes {model?, skills?}, where
`skills` lists the skills to turn on: every other skill of the catalog is turned off. Changes apply to the chats
opened after them."""
from fastapi import APIRouter, Request

from deck_studio.agent.sdk import catalog, selected_skills
from deck_studio.server.api import ApiError, json_body
from deck_studio.core.write_guard import DEFAULT_LEVEL, LEVELS
from deck_studio.server.routes.chats import EFFORTS, MODELS

router = APIRouter()


def payload(state):
    on = set(selected_skills(state))
    return {"model": state.settings.get("model", MODELS[0]), "models": MODELS,
            "effort": state.settings.get("effort", ""), "efforts": EFFORTS,
            "autonomy": state.settings.get("autonomy", DEFAULT_LEVEL), "autonomies": list(LEVELS),
            "skills": [{**s, "on": s["name"] in on} for s in catalog(state)]}


@router.get("/api/settings")
def get_settings(request: Request):
    return payload(request.app.state.studio)


@router.post("/api/settings")
async def save_settings(request: Request):
    state = request.app.state.studio
    body = await json_body(request)
    if "model" in body:
        if body["model"] not in MODELS:
            raise ApiError(400, "model", "Modelo desconhecido.")
        state.settings["model"] = body["model"]
    if "effort" in body:
        if body["effort"] not in EFFORTS:
            raise ApiError(400, "effort", "Nível de esforço desconhecido.")
        state.settings["effort"] = body["effort"]
    if "autonomy" in body:  # the chat switch: applies to the next tool call of every chat
        if body["autonomy"] not in LEVELS:
            raise ApiError(400, "autonomy", "Nível de autonomia desconhecido.")
        state.settings["autonomy"] = body["autonomy"]
    if "skills" in body:
        if not isinstance(body["skills"], list) or not all(isinstance(n, str) for n in body["skills"]):
            raise ApiError(400, "skills", "A lista de skills veio num formato inválido.")
        on = set(body["skills"])
        state.settings["skills"] = {s["name"]: s["name"] in on for s in catalog(state)}
    state.save_settings()
    return payload(state)
