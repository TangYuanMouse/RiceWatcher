import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import llm_provider_config
from app.core.schemas import MessageIn, RunAccepted, RunEvent, RunInfo
from app.services.email_tool_adapter import EmailToolError, email_tool_adapter


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunState:
    info: RunInfo
    events: list[RunEvent]


class GatewayService:
    """
    OpenClaw-inspired local gateway core.
    - Single service as source of truth
    - Per-session serialized execution lanes
    - Streaming lifecycle/assistant/tool events
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}

    def _lock_for_session(self, session_key: str) -> asyncio.Lock:
        if session_key not in self._session_locks:
            self._session_locks[session_key] = asyncio.Lock()
        return self._session_locks[session_key]

    async def submit_message(self, payload: MessageIn) -> RunAccepted:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        info = RunInfo(
            run_id=run_id,
            session_key=payload.session_key,
            status="accepted",
            created_at=utc_now_iso(),
        )

        self._runs[run_id] = RunState(info=info, events=[])
        self._emit(
            run_id,
            RunEvent(
                run_id=run_id,
                stream="lifecycle",
                phase="start",
                content="Run accepted by gateway.",
            ),
        )

        asyncio.create_task(self._run_agent_loop(run_id=run_id, payload=payload))
        return RunAccepted(run_id=run_id)

    def _emit(self, run_id: str, event: RunEvent) -> None:
        state = self._runs[run_id]
        state.events.append(event)

    @staticmethod
    def _should_trigger_email_fetch(text: str) -> bool:
        keywords = [
            "email",
            "mail",
            "inbox",
            "unread",
            "邮件",
            "邮箱",
            "收件箱",
            "未读",
            "询盘",
        ]
        lowered = text.lower()
        return any(keyword in lowered for keyword in keywords)

    @staticmethod
    def _build_email_snapshot(emails: list[dict]) -> str:
        if not emails:
            return "No unread emails found."

        lines: list[str] = []
        for item in emails[:5]:
            uid = item.get("uid", "N/A")
            sender = item.get("from", "Unknown")
            subject = item.get("subject", "(no subject)")
            snippet = item.get("snippet", "")
            lines.append(f"UID={uid} | From={sender} | Subject={subject} | Snippet={snippet}")
        return "\n".join(lines)

    @staticmethod
    def _masked_key(api_key: str) -> str:
        if not api_key:
            return ""
        if len(api_key) <= 8:
            return "*" * len(api_key)
        return f"{api_key[:4]}***{api_key[-4:]}"

    async def _call_third_party_llm(self, text: str, email_context: str | None = None) -> str:
        endpoint = f"{llm_provider_config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {llm_provider_config.api_key}",
            "Content-Type": "application/json",
        }
        user_content = text
        if email_context:
            user_content = (
                f"User instruction:\n{text}\n\n"
                f"Unread email snapshot:\n{email_context}\n\n"
                "Please include concrete email handling actions in your answer."
            )

        payload = {
            "model": llm_provider_config.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a practical foreign-trade assistant. "
                        "Give concise and actionable suggestions. "
                        "When email context is present, prioritize inbox triage, "
                        "classification, and response draft strategy."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=llm_provider_config.timeout_seconds) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "LLM returned empty content.")
        )

    async def _generate_assistant_reply(
        self,
        payload: MessageIn,
        email_context: str | None = None,
    ) -> str:
        config_ready = (
            llm_provider_config.enabled
            and bool(llm_provider_config.base_url)
            and bool(llm_provider_config.api_key)
            and bool(llm_provider_config.model_name)
        )
        if not config_ready:
            return (
                "LLM config not enabled or incomplete. "
                "Set api_key, base_url, model_name in backend/config/llm_provider.json. "
                "Fallback suggestion: send follow-up within 48h with price ladder and sample lead time."
            )

        return await self._call_third_party_llm(payload.text, email_context=email_context)

    async def _run_agent_loop(self, run_id: str, payload: MessageIn) -> None:
        state = self._runs[run_id]
        state.info.status = "running"
        lock = self._lock_for_session(payload.session_key)
        email_context: str | None = None

        try:
            async with lock:
                self._emit(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        stream="assistant",
                        content=(
                            f"Session {payload.session_key}: start analysis for input."
                        ),
                    ),
                )
                await asyncio.sleep(0.25)

                self._emit(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        stream="tool",
                        tool_name="intent_classifier",
                        content="Classified request into trade-assistant workflow.",
                    ),
                )
                await asyncio.sleep(0.25)

                if self._should_trigger_email_fetch(payload.text):
                    try:
                        unread = await email_tool_adapter.check(limit=5, unseen=True)
                        unread_count = len(unread) if isinstance(unread, list) else 0
                        email_context = self._build_email_snapshot(unread if isinstance(unread, list) else [])
                        self._emit(
                            run_id,
                            RunEvent(
                                run_id=run_id,
                                stream="tool",
                                tool_name="email_fetcher",
                                content=(
                                    f"Fetched unread emails: {unread_count}. "
                                    "Snapshot attached to assistant context."
                                ),
                            ),
                        )
                    except EmailToolError as exc:
                        self._emit(
                            run_id,
                            RunEvent(
                                run_id=run_id,
                                stream="tool",
                                tool_name="email_fetcher",
                                content=f"Email fetch skipped: {exc}",
                            ),
                        )
                    await asyncio.sleep(0.2)

                self._emit(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        stream="tool",
                        tool_name="llm_provider",
                        content=(
                            "Using provider="
                            f"{llm_provider_config.provider}, "
                            f"base_url={llm_provider_config.base_url or 'N/A'}, "
                            f"model={llm_provider_config.model_name or 'N/A'}, "
                            f"api_key={self._masked_key(llm_provider_config.api_key)}"
                        ),
                    ),
                )
                await asyncio.sleep(0.2)

                self._emit(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        stream="tool",
                        tool_name="timeline_writer",
                        content="Timeline checkpoint appended.",
                    ),
                )
                await asyncio.sleep(0.2)

                summary = await self._generate_assistant_reply(
                    payload,
                    email_context=email_context,
                )
                self._emit(
                    run_id,
                    RunEvent(run_id=run_id, stream="assistant", content=summary),
                )

                state.info.status = "done"
                state.info.ended_at = utc_now_iso()
                self._emit(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        stream="lifecycle",
                        phase="end",
                        content="Run finished.",
                    ),
                )
        except Exception as exc:  # pragma: no cover
            state.info.status = "error"
            state.info.ended_at = utc_now_iso()
            self._emit(
                run_id,
                RunEvent(
                    run_id=run_id,
                    stream="lifecycle",
                    phase="error",
                    content=f"Run failed: {exc}",
                ),
            )

    def get_run_info(self, run_id: str) -> RunInfo | None:
        state = self._runs.get(run_id)
        return None if state is None else state.info

    def get_events(self, run_id: str, start_index: int = 0) -> list[RunEvent]:
        state = self._runs.get(run_id)
        if state is None:
            return []
        return state.events[start_index:]

    async def stream_sse(self, run_id: str, start_index: int = 0):
        """Yield Server-Sent Events lines with JSON payload."""
        cursor = start_index

        while True:
            state = self._runs.get(run_id)
            if state is None:
                payload = json.dumps(
                    {
                        "run_id": run_id,
                        "stream": "lifecycle",
                        "phase": "error",
                        "content": "run not found",
                        "created_at": utc_now_iso(),
                    }
                )
                yield f"data: {payload}\n\n"
                break

            if cursor < len(state.events):
                event = state.events[cursor]
                payload = json.dumps(event.model_dump())
                yield f"data: {payload}\n\n"
                cursor += 1
                continue

            if state.info.status in {"done", "error"}:
                break

            await asyncio.sleep(0.2)


gateway_service = GatewayService()
