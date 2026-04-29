import asyncio
import json
from pathlib import Path
from typing import Any

from app.core.config import settings


class EmailToolError(RuntimeError):
    pass


class EmailToolAdapter:
    def __init__(self, skill_dir: str, node_command: str, timeout_seconds: int) -> None:
        self.skill_dir = Path(skill_dir)
        self.node_command = node_command
        self.timeout_seconds = timeout_seconds

    def status(self) -> dict[str, Any]:
        imap_script = self.skill_dir / "scripts" / "imap.js"
        smtp_script = self.skill_dir / "scripts" / "smtp.js"
        return {
            "skill_dir": str(self.skill_dir),
            "exists": self.skill_dir.exists(),
            "imap_script": str(imap_script),
            "imap_script_exists": imap_script.exists(),
            "smtp_script": str(smtp_script),
            "smtp_script_exists": smtp_script.exists(),
            "node_command": self.node_command,
        }

    async def _run_script(self, script_name: str, args: list[str]) -> Any:
        script_path = self.skill_dir / "scripts" / script_name

        if not script_path.exists():
            raise EmailToolError(
                f"Email skill script not found: {script_path}. "
                "Please ensure imap-smtp-email plugin is present in workspace."
            )

        try:
            process = await asyncio.create_subprocess_exec(
                self.node_command,
                str(script_path),
                *args,
                cwd=str(self.skill_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise EmailToolError(
                f"Node command not found: {self.node_command}. "
                "Install Node.js and ensure it is in PATH."
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise EmailToolError(
                f"Email tool timed out after {self.timeout_seconds}s"
            ) from exc

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if process.returncode != 0:
            raise EmailToolError(stderr or stdout or f"Script exited with {process.returncode}")

        if not stdout:
            return {}

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            for line in reversed(lines):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
            raise EmailToolError("Email tool returned non-JSON output")

    async def check(
        self,
        limit: int = 10,
        mailbox: str = "INBOX",
        recent: str | None = None,
        unseen: bool = True,
    ) -> Any:
        args = ["check", "--limit", str(limit), "--mailbox", mailbox]
        if recent:
            args.extend(["--recent", recent])
        if unseen:
            args.extend(["--unseen", "true"])
        return await self._run_script("imap.js", args)

    async def fetch(self, uid: str, mailbox: str = "INBOX") -> Any:
        return await self._run_script("imap.js", ["fetch", uid, "--mailbox", mailbox])

    async def search(self, params: dict[str, Any]) -> Any:
        args = ["search", "--mailbox", str(params.get("mailbox", "INBOX"))]

        if params.get("limit"):
            args.extend(["--limit", str(params["limit"])])
        if params.get("unseen"):
            args.append("--unseen")
        if params.get("seen"):
            args.append("--seen")
        if params.get("from_email"):
            args.extend(["--from", str(params["from_email"])])
        if params.get("subject"):
            args.extend(["--subject", str(params["subject"])])
        if params.get("recent"):
            args.extend(["--recent", str(params["recent"])])
        if params.get("since"):
            args.extend(["--since", str(params["since"])])
        if params.get("before"):
            args.extend(["--before", str(params["before"])])

        return await self._run_script("imap.js", args)

    async def send(self, params: dict[str, Any]) -> Any:
        args = ["send", "--to", str(params["to"]), "--subject", str(params["subject"])]

        if params.get("body"):
            args.extend(["--body", str(params["body"])])
        if params.get("html"):
            args.append("--html")
        if params.get("cc"):
            args.extend(["--cc", str(params["cc"])])
        if params.get("bcc"):
            args.extend(["--bcc", str(params["bcc"])])
        if params.get("attach"):
            args.extend(["--attach", str(params["attach"])])
        if params.get("from_addr"):
            args.extend(["--from", str(params["from_addr"])])

        return await self._run_script("smtp.js", args)

    async def verify_smtp(self) -> Any:
        return await self._run_script("smtp.js", ["verify"])


email_tool_adapter = EmailToolAdapter(
    skill_dir=settings.email_skill_dir,
    node_command=settings.email_skill_node_command,
    timeout_seconds=settings.email_tool_timeout_seconds,
)
