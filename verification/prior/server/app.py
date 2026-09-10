from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import DBAPIError, IntegrityError

from server.analysis import (
    ActivateAnalysis,
    AnalysisService,
    Availability,
    Declaration,
    Expected,
    Mapping,
    Preference,
)
from server.auth import Auth
from server.completion import Alternatives, ApplyCandidate, CompletionService
from server.config import Settings
from server.contest import RULE_PROFILE, Activation, DraftCommand, SetupInput
from server.decision import DecisionService, DisputeInput, EnteredInput, OddsInput, ReconcileInput
from server.persistence import engine_for, many, one, run
from server.workspace import WorkspaceService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = engine_for(settings.database_url)
    auth, service = Auth(settings, engine), WorkspaceService(engine)
    analysis, completion = AnalysisService(service), CompletionService(service)
    decision = DecisionService(service)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        completion.close()
        engine.dispose()

    app = FastAPI(
        title="DFS pre-lock development build",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.engine, app.state.service, app.state.auth = engine, service, auth
    app.state.analysis, app.state.completion = analysis, completion

    @app.middleware("http")
    async def headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(DBAPIError)
    async def database_error(request: Request, exc: DBAPIError) -> JSONResponse:
        # Do not echo SQL, provider bytes, database URLs or credentials.
        code = 409 if isinstance(exc, IntegrityError) else 503
        return JSONResponse(
            {"detail": "Database conflict or busy; attempted change was not confirmed saved"},
            status_code=code,
        )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/auth/login")
    def login() -> Response:
        return auth.login()

    @app.get("/auth/callback")
    def callback(request: Request) -> Response:
        return auth.callback(request)

    @app.post("/auth/logout")
    def logout(session: dict = Depends(auth.require)) -> Response:
        with engine.begin() as db:
            run(
                db,
                "UPDATE session SET revoked=true WHERE token_hash=:hash",
                hash=session["token_hash"],
            )
        response = Response(status_code=204)
        response.delete_cookie("dfs_session")
        return response

    @app.get("/api/session")
    def session_info(session: dict = Depends(auth.require)) -> dict:
        return {
            "csrf": session["csrf"],
            "expires_at": session["expires_at"],
            "test_identity": settings.local_test,
        }

    @app.get("/api/rules")
    def rules(session: dict = Depends(auth.require)) -> dict:
        return RULE_PROFILE

    @app.get("/api/workspaces")
    def workspaces(session: dict = Depends(auth.require)) -> list[dict]:
        with engine.connect() as db:
            return many(
                db,
                "SELECT w.id,c.name FROM workspace w JOIN contest c ON c.id=w.contest_id "
                "WHERE c.owner_id=:owner ORDER BY c.name",
                owner=session["owner_id"],
            )

    @app.post("/api/workspaces")
    def setup(
        data: SetupInput, idempotency_key: UUID = Header(), session: dict = Depends(auth.require)
    ) -> dict:
        return service.setup(str(session["owner_id"]), str(idempotency_key), data)

    @app.put("/api/workspaces/{wid}/setup")
    def revise_setup(
        wid: UUID,
        data: SetupInput,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return service.setup(str(session["owner_id"]), str(idempotency_key), data, str(wid))

    @app.get("/api/workspaces/{wid}")
    def workspace(wid: UUID, session: dict = Depends(auth.require)) -> dict:
        return service.read(str(wid), str(session["owner_id"]))

    @app.post("/api/workspaces/{wid}/imports")
    def upload(wid: UUID, file: UploadFile, session: dict = Depends(auth.require)) -> dict:
        raw = file.file.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(413, "File exceeds 10 MiB")
        return service.stage(str(wid), str(session["owner_id"]), raw, file.filename or "Yahoo.csv")

    @app.get("/api/workspaces/{wid}/imports/{bid}")
    def preview(wid: UUID, bid: UUID, session: dict = Depends(auth.require)) -> dict:
        return service.preview(str(wid), str(session["owner_id"]), str(bid))

    @app.get("/api/workspaces/{wid}/imports/{bid}/raw")
    def raw(wid: UUID, bid: UUID, session: dict = Depends(auth.require)) -> Response:
        service.preview(str(wid), str(session["owner_id"]), str(bid))
        with engine.connect() as db:
            blob = one(
                db,
                "SELECT r.bytes FROM import_batch b JOIN source_capture c ON c.id=b.capture_id "
                "JOIN raw_blob r ON r.sha256=c.blob_hash WHERE b.id=:id",
                id=bid,
            )
        return Response(
            bytes(blob["bytes"]),
            media_type="application/octet-stream",
            headers={"Content-Disposition": 'attachment; filename="yahoo-original.csv"'},
        )

    @app.post("/api/workspaces/{wid}/activate")
    def activate(
        wid: UUID,
        data: Activation,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return service.activate(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.post("/api/workspaces/{wid}/draft")
    def save(
        wid: UUID,
        data: DraftCommand,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return service.save(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.get("/api/workspaces/{wid}/analysis")
    def analysis_state(wid: UUID, session: dict = Depends(auth.require)) -> dict:
        return analysis.state(str(wid), str(session["owner_id"]))

    @app.post("/api/workspaces/{wid}/projections")
    def projection_upload(
        wid: UUID,
        files: list[UploadFile],
        positions: str = Form(),
        declaration: str = Form(),
        session: dict = Depends(auth.require),
    ) -> dict:
        import json

        from pydantic import ValidationError

        try:
            context = Declaration.model_validate_json(declaration)
            labels = json.loads(positions)
            if (
                not isinstance(labels, list)
                or len(labels) != len(files)
                or len(set(labels)) != len(labels)
                or not set(labels) <= {"QB", "RB", "WR", "TE", "DST"}
            ):
                raise ValueError("Choose one file for each supported position")
        except (ValueError, TypeError, ValidationError) as exc:
            raise HTTPException(
                422, "Invalid projection declaration or positional file list"
            ) from exc
        uploaded = {}
        for label, file in zip(labels, files, strict=True):
            raw = file.file.read(10 * 1024 * 1024 + 1)
            if len(raw) > 10 * 1024 * 1024:
                raise HTTPException(413, "File exceeds 10 MiB")
            uploaded[label] = (file.filename or label + ".csv", raw)
        return analysis.stage(str(wid), str(session["owner_id"]), uploaded, context)

    @app.post("/api/workspaces/{wid}/projections/{bid}/review")
    def projection_review(wid: UUID, bid: UUID, session: dict = Depends(auth.require)) -> dict:
        return analysis.review(str(wid), str(session["owner_id"]), str(bid))

    @app.post("/api/workspaces/{wid}/analysis/activate")
    def analysis_activate(
        wid: UUID,
        data: ActivateAnalysis,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return analysis.activate(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.post("/api/workspaces/{wid}/preferences")
    def preference(
        wid: UUID,
        data: Preference,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return analysis.preference(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.post("/api/workspaces/{wid}/mappings")
    def mapping(
        wid: UUID,
        data: Mapping,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return analysis.resolve(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.post("/api/workspaces/{wid}/availability")
    def availability(
        wid: UUID,
        data: Availability,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return analysis.resolve(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.get("/api/workspaces/{wid}/decision-history")
    def decision_history(wid: UUID, session: dict = Depends(auth.require)) -> dict:
        with engine.connect() as db:
            service.owned(db, str(wid), str(session["owner_id"]))
            return {
                "odds": many(
                    db,
                    "SELECT * FROM odds_revision WHERE workspace_id=:id "
                    "ORDER BY created_at DESC LIMIT 100",
                    id=wid,
                ),
                "entered": many(
                    db,
                    "SELECT * FROM entered_revision WHERE workspace_id=:id "
                    "ORDER BY created_at DESC LIMIT 100",
                    id=wid,
                ),
            }

    @app.post("/api/workspaces/{wid}/odds")
    def odds(
        wid: UUID,
        data: OddsInput,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return decision.odds(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.post("/api/workspaces/{wid}/undo")
    def undo(
        wid: UUID,
        data: Expected,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return decision.undo(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.post("/api/workspaces/{wid}/entered")
    def entered(
        wid: UUID,
        data: EnteredInput,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return decision.entered(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.post("/api/workspaces/{wid}/entered-dispute")
    def entered_dispute(
        wid: UUID,
        data: DisputeInput,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return decision.dispute(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.post("/api/workspaces/{wid}/reconcile")
    def reconcile(
        wid: UUID,
        data: ReconcileInput,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return decision.reconcile(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.post("/api/workspaces/{wid}/reconcile-preview")
    def reconcile_preview(
        wid: UUID,
        data: ReconcileInput,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return decision.reconcile(
            str(wid), str(session["owner_id"]), str(idempotency_key), data, preview=True
        )

    @app.post("/api/workspaces/{wid}/alternatives", status_code=202)
    def alternatives(
        wid: UUID,
        data: Alternatives,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return completion.submit(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.post("/api/workspaces/{wid}/complete", status_code=202)
    def complete(
        wid: UUID,
        data: Expected,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return completion.submit(str(wid), str(session["owner_id"]), str(idempotency_key), data)

    @app.get("/api/workspaces/{wid}/completions/{rid}")
    def completed(wid: UUID, rid: UUID, session: dict = Depends(auth.require)) -> dict:
        return completion.read(str(wid), str(session["owner_id"]), str(rid))

    @app.post("/api/workspaces/{wid}/completions/{rid}/apply")
    def apply_completed(
        wid: UUID,
        rid: UUID,
        data: ApplyCandidate,
        idempotency_key: UUID = Header(),
        session: dict = Depends(auth.require),
    ) -> dict:
        return completion.apply(
            str(wid), str(session["owner_id"]), str(idempotency_key), str(rid), data
        )

    dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(dist / "index.html")

    return app
