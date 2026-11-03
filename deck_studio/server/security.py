"""Per-launch token, Host and Origin checks in front of every route (SPEC "HTTP contract", Security)."""
from secrets import compare_digest

from starlette.requests import HTTPConnection
from starlette.responses import PlainTextResponse, RedirectResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class Security:
    """ASGI middleware: app.add_middleware(Security, state=studio_state)."""

    def __init__(self, app, state):
        self.app = app
        self.state = state

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        await (self.refusal(HTTPConnection(scope)) or self.app)(scope, receive, send)

    def refusal(self, conn):
        token, port = self.state.token, self.state.port
        is_token = lambda value: compare_digest((value or "").encode(), token.encode())  # noqa: E731
        host = conn.headers.get("host", "").lower()
        # DNS rebinding: only our own host names reach the routes
        if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return PlainTextResponse("Host não permitido.", 403)
        cookie = f"studio_{port}"
        if conn.url.path == "/" and is_token(conn.query_params.get("t")):
            response = RedirectResponse("/", 302)
            response.set_cookie(cookie, token, httponly=True, samesite="strict", path="/")
            return response
        header_client = is_token(conn.headers.get("x-studio-token"))
        if not header_client and not is_token(conn.cookies.get(cookie)):
            return PlainTextResponse("Abra o Deck Studio pelo endereço que ele mostrou no terminal.", 401)
        # other web pages in the browser carry the cookie too: a write must come from the studio's own origin
        if conn.scope["method"] not in SAFE_METHODS and not header_client and conn.headers.get("origin") != f"http://{host}":
            return PlainTextResponse("Origem não permitida.", 403)
        return None
