"""GET /api/provenance: each number on each slide with its sources (deck_studio.provenance).

build_index caches the index and rebuilds it when the .tex, the audit or a slide file changes. A deck whose config
has provenance off (a project made by Deck Studio: no dissertation.tex, no number audit) gets {}."""
from fastapi import APIRouter, Request

from deck_studio.provenance import build_index

router = APIRouter()


@router.get("/api/provenance")
def provenance(request: Request):  # sync: a cold build (about 70 ms) runs in the thread pool, not on the loop
    state = request.app.state.studio
    return build_index(state.kit_root, state.config["slidesDir"]) if state.config["provenance"] else {}
