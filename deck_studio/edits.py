"""EditService: the author's direct edits as undoable history turns, one at a time with the agent's turns."""
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from deck_studio.core import plataforma
from deck_studio.server.api import ApiError


class EditService:
    def __init__(self, state):
        self.state = state

    @asynccontextmanager
    async def _turn_lock(self):
        """The studio's turn lock, or 409 while an agent turn (or another edit) holds it."""
        state = self.state
        if state.turn_lock.locked():
            raise ApiError(409, "busy", "Outro pedido está em andamento. Tente de novo quando ele terminar.")
        await state.turn_lock.acquire()
        try:
            await state.publish_status()
            yield
        finally:
            state.turn_lock.release()
            await state.publish_status()

    def _writable(self, rel):
        """The absolute path of a kit file a direct edit may write: only where the write guard allows."""
        decision = self.state.guard.check("Edit", {"file_path": rel})
        if decision.behavior != "allow":
            reason = decision.reason if decision.behavior == "deny" else "A edição direta vale só na área liberada do deck."
            raise ApiError(403, "denied", reason)
        # the guard compares Windows-style strings (core/write_guard.py): on POSIX its \tmp\kit is /tmp/kit
        path = Path(decision.paths[0] if plataforma.WINDOWS else decision.paths[0].replace("\\", "/"))
        if not path.is_file():
            raise ApiError(404, "no-file", f"Arquivo não encontrado: {rel}")
        return path

    async def apply(self, label, changes):
        """Run one direct edit as an undoable turn and return its id.

        changes maps kit-relative paths to fn(old text) -> new text. A fn may raise ApiError to refuse the
        edit: then nothing is written and no turn is recorded. Files are read and written as exact UTF-8
        bytes, so their line endings stay as they are. The lock covers the writes only: the deck builder
        serializes builds itself, and the next edit or undo need not wait for this one's full build."""
        state = self.state
        async with self._turn_lock():
            paths = {rel: self._writable(rel) for rel in changes}
            texts = {rel: fn(paths[rel].read_bytes().decode("utf-8")) for rel, fn in changes.items()}
            turn_id = str(uuid.uuid4())
            state.history.begin(turn_id, {"kind": "edit", "label": label})
            try:
                for rel, text in texts.items():
                    state.history.before_write(turn_id, paths[rel])
                    paths[rel].write_bytes(text.encode("utf-8"))
            finally:  # after a failed write too: the turn records what is on disk now, and its card can undo it
                state.history.end(turn_id)
                await state.events.publish("edit", turnId=turn_id, label=label, files=state.history.get(turn_id).files)
        await state.builder.sources_changed([str(p) for p in paths.values()])
        return turn_id

    async def undo(self, turn_id):
        """Undo one known turn, a direct edit or an agent's, and rebuild the deck. Returns history's UndoResult:
        not ok when a file changed after the turn. 409 while another turn runs and once the turn is undone."""
        state = self.state
        async with self._turn_lock():
            if state.history.get(turn_id).undone:
                raise ApiError(409, "undone", "Este pedido já foi desfeito.")
            result = state.history.undo(turn_id)
        changed = [*result.restored, *result.removed]
        if changed:
            await state.builder.sources_changed([state.guard.write_path("Edit", {"file_path": f}) for f in changed])
        return result
