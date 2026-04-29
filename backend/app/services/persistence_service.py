import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator

from app.core.config import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_domain_as_name(domain: str) -> str:
    base = domain.split(".")[0]
    return base.replace("-", " ").replace("_", " ").title() or "Unknown Customer"


class PersistenceService:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    country TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS customer_identities (
                    email_domain TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                );

                CREATE TABLE IF NOT EXISTS timeline_events (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_price REAL,
                    currency TEXT NOT NULL,
                    total_amount REAL,
                    status TEXT NOT NULL,
                    payload_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS email_records (
                    id TEXT PRIMARY KEY,
                    mailbox TEXT NOT NULL,
                    uid TEXT NOT NULL,
                    sender TEXT,
                    subject TEXT,
                    date_text TEXT,
                    snippet TEXT,
                    customer_id TEXT,
                    intent TEXT,
                    processed INTEGER NOT NULL DEFAULT 0,
                    raw_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(mailbox, uid)
                );

                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    max_retries INTEGER NOT NULL,
                    retry_count INTEGER NOT NULL,
                    next_run_at TEXT NOT NULL,
                    last_run_at TEXT,
                    last_status TEXT,
                    last_error TEXT,
                    payload_json TEXT
                );

                CREATE TABLE IF NOT EXISTS production_schedule (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL UNIQUE,
                    customer_id TEXT NOT NULL,
                    line_name TEXT NOT NULL,
                    planned_start TEXT NOT NULL,
                    planned_end TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS email_reply_drafts (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    mailbox TEXT NOT NULL,
                    uid TEXT,
                    recipient TEXT,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    context_json TEXT,
                    suggestions_json TEXT,
                    status TEXT NOT NULL,
                    approved_by TEXT,
                    approved_at TEXT,
                    sent_at TEXT,
                    rejection_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS review_queue (
                    id TEXT PRIMARY KEY,
                    mailbox TEXT NOT NULL,
                    uid TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    classification_confidence REAL NOT NULL,
                    extraction_confidence REAL NOT NULL,
                    reasons_json TEXT,
                    status TEXT NOT NULL,
                    note TEXT,
                    resolver TEXT,
                    resolved_at TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(mailbox, uid)
                );
                """
            )

    def seed_demo_data(self) -> None:
        with self._connect() as conn:
            cnt = conn.execute("SELECT COUNT(1) FROM customers").fetchone()[0]
            if cnt == 0:
                now = utc_now_iso()
                rows = [
                    ("c001", "Greenline Trade GmbH", "Germany", "inquiry", json.dumps(["priority", "sample-phase"]), now, now),
                    ("c002", "Pacific Home Goods", "USA", "negotiation", json.dumps(["price-sensitive"]), now, now),
                    ("c003", "Nordic Retail AB", "Sweden", "order", json.dumps(["repeat-buyer"]), now, now),
                ]
                conn.executemany(
                    "INSERT INTO customers (id,name,country,stage,tags_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                    rows,
                )

            tcnt = conn.execute("SELECT COUNT(1) FROM timeline_events").fetchone()[0]
            if tcnt == 0:
                items = [
                    ("t001", "c001", "2026-04-01T09:30:00Z", "manual", "LinkedIn first contact", "Reached purchasing manager with product intro.", utc_now_iso()),
                    ("t002", "c001", "2026-04-05T11:20:00Z", "email", "New inquiry", "Asked quote for rice moisture sensor, qty 2000.", utc_now_iso()),
                ]
                conn.executemany(
                    "INSERT INTO timeline_events (id,customer_id,timestamp,source,title,summary,created_at) VALUES (?,?,?,?,?,?,?)",
                    items,
                )

    def list_customers(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM customers ORDER BY id").fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "country": row["country"],
                "stage": row["stage"],
                "tags": json.loads(row["tags_json"]),
            }
            for row in rows
        ]

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "country": row["country"],
            "stage": row["stage"],
            "tags": json.loads(row["tags_json"]),
        }

    def list_timeline_events(self, customer_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if customer_id:
                rows = conn.execute(
                    "SELECT id,customer_id,timestamp,source,title,summary FROM timeline_events WHERE customer_id=? ORDER BY timestamp DESC",
                    (customer_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id,customer_id,timestamp,source,title,summary FROM timeline_events ORDER BY timestamp DESC"
                ).fetchall()
        return [dict(row) for row in rows]

    def add_timeline_event(
        self,
        customer_id: str,
        source: str,
        title: str,
        summary: str,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        event_id = f"t_{uuid.uuid4().hex[:10]}"
        ts = timestamp or utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO timeline_events (id,customer_id,timestamp,source,title,summary,created_at) VALUES (?,?,?,?,?,?,?)",
                (event_id, customer_id, ts, source, title, summary, utc_now_iso()),
            )
        return {
            "id": event_id,
            "customer_id": customer_id,
            "timestamp": ts,
            "source": source,
            "title": title,
            "summary": summary,
        }

    def list_orders(self, customer_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM orders WHERE 1=1"
        args: list[Any] = []
        if customer_id:
            query += " AND customer_id=?"
            args.append(customer_id)
        if status:
            query += " AND status=?"
            args.append(status)
        query += " ORDER BY updated_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, tuple(args)).fetchall()

        return [
            {
                "id": row["id"],
                "customer_id": row["customer_id"],
                "product_name": row["product_name"],
                "quantity": row["quantity"],
                "unit_price": row["unit_price"],
                "currency": row["currency"],
                "total_amount": row["total_amount"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def create_order(
        self,
        customer_id: str,
        product_name: str,
        quantity: int,
        unit_price: float | None,
        currency: str,
        status: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        order_id = f"o_{uuid.uuid4().hex[:10]}"
        total_amount = None if unit_price is None else unit_price * quantity
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    id,customer_id,product_name,quantity,unit_price,currency,total_amount,status,payload_json,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    order_id,
                    customer_id,
                    product_name,
                    quantity,
                    unit_price,
                    currency,
                    total_amount,
                    status,
                    json.dumps(payload or {}),
                    now,
                    now,
                ),
            )

        return {
            "id": order_id,
            "customer_id": customer_id,
            "product_name": product_name,
            "quantity": quantity,
            "unit_price": unit_price,
            "currency": currency,
            "total_amount": total_amount,
            "status": status,
            "created_at": now,
            "updated_at": now,
        }

    def update_latest_order_status(self, customer_id: str, status: str) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM orders WHERE customer_id=? ORDER BY updated_at DESC LIMIT 1",
                (customer_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE orders SET status=?, updated_at=? WHERE id=?", (status, now, row["id"]))
            updated = conn.execute("SELECT * FROM orders WHERE id=?", (row["id"],)).fetchone()

        return {
            "id": updated["id"],
            "customer_id": updated["customer_id"],
            "product_name": updated["product_name"],
            "quantity": updated["quantity"],
            "unit_price": updated["unit_price"],
            "currency": updated["currency"],
            "total_amount": updated["total_amount"],
            "status": updated["status"],
            "created_at": updated["created_at"],
            "updated_at": updated["updated_at"],
        }

    def upsert_customer_stage(self, customer_id: str, stage: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE customers SET stage=?, updated_at=? WHERE id=?",
                (stage, utc_now_iso(), customer_id),
            )

    def resolve_customer_from_sender(self, sender: str) -> dict[str, Any]:
        email_match = re.search(r"[\w.+-]+@[\w.-]+", sender or "")
        domain = email_match.group(0).split("@", 1)[1].lower() if email_match else "unknown.local"

        with self._connect() as conn:
            link = conn.execute(
                "SELECT customer_id FROM customer_identities WHERE email_domain=?",
                (domain,),
            ).fetchone()

            if link is not None:
                customer = conn.execute("SELECT * FROM customers WHERE id=?", (link["customer_id"],)).fetchone()
                return {
                    "id": customer["id"],
                    "name": customer["name"],
                    "country": customer["country"],
                    "stage": customer["stage"],
                    "tags": json.loads(customer["tags_json"]),
                }

            customer_id = f"c_{uuid.uuid4().hex[:8]}"
            now = utc_now_iso()
            name = _sanitize_domain_as_name(domain)
            conn.execute(
                "INSERT INTO customers (id,name,country,stage,tags_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                (customer_id, name, "Unknown", "lead", json.dumps(["auto-created"]), now, now),
            )
            conn.execute(
                "INSERT INTO customer_identities (email_domain,customer_id,created_at) VALUES (?,?,?)",
                (domain, customer_id, now),
            )

        return {
            "id": customer_id,
            "name": name,
            "country": "Unknown",
            "stage": "lead",
            "tags": ["auto-created"],
        }

    def is_email_processed(self, mailbox: str, uid: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT processed FROM email_records WHERE mailbox=? AND uid=?",
                (mailbox, uid),
            ).fetchone()
        return bool(row and row["processed"] == 1)

    def save_email_record(
        self,
        mailbox: str,
        uid: str,
        sender: str,
        subject: str,
        date_text: str | None,
        snippet: str,
        customer_id: str,
        intent: str,
        processed: bool,
        raw_payload: dict[str, Any],
    ) -> None:
        now = utc_now_iso()
        record_id = f"e_{uuid.uuid4().hex[:10]}"
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM email_records WHERE mailbox=? AND uid=?",
                (mailbox, uid),
            ).fetchone()

            if existing is None:
                conn.execute(
                    """
                    INSERT INTO email_records (
                        id, mailbox, uid, sender, subject, date_text, snippet,
                        customer_id, intent, processed, raw_json, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record_id,
                        mailbox,
                        uid,
                        sender,
                        subject,
                        date_text,
                        snippet,
                        customer_id,
                        intent,
                        1 if processed else 0,
                        json.dumps(raw_payload),
                        now,
                        now,
                    ),
                )

    def create_reply_draft(
        self,
        customer_id: str,
        mailbox: str,
        uid: str | None,
        recipient: str | None,
        subject: str,
        body: str,
        context_used: list[str],
        suggestions: list[str],
    ) -> dict[str, Any]:
        draft_id = f"d_{uuid.uuid4().hex[:10]}"
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO email_reply_drafts (
                    id, customer_id, mailbox, uid, recipient, subject, body,
                    context_json, suggestions_json, status,
                    approved_by, approved_at, sent_at, rejection_reason,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    draft_id,
                    customer_id,
                    mailbox,
                    uid,
                    recipient,
                    subject,
                    body,
                    json.dumps(context_used),
                    json.dumps(suggestions),
                    "draft",
                    None,
                    None,
                    None,
                    None,
                    now,
                    now,
                ),
            )
        return self.get_reply_draft(draft_id) or {}

    def get_reply_draft(self, draft_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM email_reply_drafts WHERE id=?", (draft_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "customer_id": row["customer_id"],
            "mailbox": row["mailbox"],
            "uid": row["uid"],
            "recipient": row["recipient"],
            "subject": row["subject"],
            "body": row["body"],
            "context_used": json.loads(row["context_json"] or "[]"),
            "suggestions": json.loads(row["suggestions_json"] or "[]"),
            "status": row["status"],
            "approved_by": row["approved_by"],
            "approved_at": row["approved_at"],
            "sent_at": row["sent_at"],
            "rejection_reason": row["rejection_reason"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_reply_drafts(
        self,
        customer_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM email_reply_drafts WHERE 1=1"
        args: list[Any] = []
        if customer_id:
            query += " AND customer_id=?"
            args.append(customer_id)
        if status:
            query += " AND status=?"
            args.append(status)
        query += " ORDER BY updated_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, tuple(args)).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "customer_id": row["customer_id"],
                    "mailbox": row["mailbox"],
                    "uid": row["uid"],
                    "recipient": row["recipient"],
                    "subject": row["subject"],
                    "body": row["body"],
                    "context_used": json.loads(row["context_json"] or "[]"),
                    "suggestions": json.loads(row["suggestions_json"] or "[]"),
                    "status": row["status"],
                    "approved_by": row["approved_by"],
                    "approved_at": row["approved_at"],
                    "sent_at": row["sent_at"],
                    "rejection_reason": row["rejection_reason"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

    def update_reply_draft_content(
        self,
        draft_id: str,
        subject: str | None,
        body: str | None,
    ) -> dict[str, Any] | None:
        current = self.get_reply_draft(draft_id)
        if current is None:
            return None
        next_subject = subject if subject is not None else current["subject"]
        next_body = body if body is not None else current["body"]
        with self._connect() as conn:
            conn.execute(
                "UPDATE email_reply_drafts SET subject=?, body=?, status='draft', updated_at=? WHERE id=?",
                (next_subject, next_body, utc_now_iso(), draft_id),
            )
        return self.get_reply_draft(draft_id)

    def set_reply_draft_status(
        self,
        draft_id: str,
        status: str,
        actor: str,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        current = self.get_reply_draft(draft_id)
        if current is None:
            return None

        approved_by = current["approved_by"]
        approved_at = current["approved_at"]
        rejection_reason = current["rejection_reason"]
        sent_at = current["sent_at"]

        now = utc_now_iso()
        if status == "approved":
            approved_by = actor
            approved_at = now
            rejection_reason = None
        elif status == "rejected":
            rejection_reason = reason
        elif status == "sent":
            sent_at = now

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE email_reply_drafts
                SET status=?, approved_by=?, approved_at=?, sent_at=?, rejection_reason=?, updated_at=?
                WHERE id=?
                """,
                (status, approved_by, approved_at, sent_at, rejection_reason, now, draft_id),
            )
        return self.get_reply_draft(draft_id)

    def upsert_review_queue_item(
        self,
        mailbox: str,
        uid: str,
        customer_id: str,
        intent: str,
        classification_confidence: float,
        extraction_confidence: float,
        reasons: list[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        now = utc_now_iso()
        item_id = f"rq_{uuid.uuid4().hex[:10]}"

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM review_queue WHERE mailbox=? AND uid=?",
                (mailbox, uid),
            ).fetchone()

            if existing is None:
                conn.execute(
                    """
                    INSERT INTO review_queue (
                        id, mailbox, uid, customer_id, intent,
                        classification_confidence, extraction_confidence,
                        reasons_json, status, note, resolver, resolved_at,
                        payload_json, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        item_id,
                        mailbox,
                        uid,
                        customer_id,
                        intent,
                        classification_confidence,
                        extraction_confidence,
                        json.dumps(reasons),
                        "pending",
                        None,
                        None,
                        None,
                        json.dumps(payload),
                        now,
                        now,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE review_queue
                    SET customer_id=?, intent=?, classification_confidence=?, extraction_confidence=?,
                        reasons_json=?, status='pending', payload_json=?, updated_at=?
                    WHERE mailbox=? AND uid=?
                    """,
                    (
                        customer_id,
                        intent,
                        classification_confidence,
                        extraction_confidence,
                        json.dumps(reasons),
                        json.dumps(payload),
                        now,
                        mailbox,
                        uid,
                    ),
                )

        return self.get_review_queue_item(mailbox, uid) or {}

    def get_review_queue_item(self, mailbox: str, uid: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_queue WHERE mailbox=? AND uid=?",
                (mailbox, uid),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "mailbox": row["mailbox"],
            "uid": row["uid"],
            "customer_id": row["customer_id"],
            "intent": row["intent"],
            "classification_confidence": row["classification_confidence"],
            "extraction_confidence": row["extraction_confidence"],
            "reasons": json.loads(row["reasons_json"] or "[]"),
            "status": row["status"],
            "note": row["note"],
            "resolver": row["resolver"],
            "resolved_at": row["resolved_at"],
            "payload": json.loads(row["payload_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_review_queue(self, status: str | None = "pending") -> list[dict[str, Any]]:
        query = "SELECT * FROM review_queue"
        args: list[Any] = []
        if status:
            query += " WHERE status=?"
            args.append(status)
        query += " ORDER BY created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, tuple(args)).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "mailbox": row["mailbox"],
                    "uid": row["uid"],
                    "customer_id": row["customer_id"],
                    "intent": row["intent"],
                    "classification_confidence": row["classification_confidence"],
                    "extraction_confidence": row["extraction_confidence"],
                    "reasons": json.loads(row["reasons_json"] or "[]"),
                    "status": row["status"],
                    "note": row["note"],
                    "resolver": row["resolver"],
                    "resolved_at": row["resolved_at"],
                    "created_at": row["created_at"],
                }
            )
        return result

    def resolve_review_queue_item(
        self,
        item_id: str,
        action: str,
        resolver: str,
        note: str | None,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT mailbox, uid FROM review_queue WHERE id=?", (item_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE review_queue
                SET status=?, resolver=?, note=?, resolved_at=?, updated_at=?
                WHERE id=?
                """,
                (action, resolver, note, utc_now_iso(), utc_now_iso(), item_id),
            )

        return self.get_review_queue_item(str(row["mailbox"]), str(row["uid"]))
            else:
                conn.execute(
                    """
                    UPDATE email_records
                    SET sender=?, subject=?, date_text=?, snippet=?, customer_id=?, intent=?,
                        processed=?, raw_json=?, updated_at=?
                    WHERE mailbox=? AND uid=?
                    """,
                    (
                        sender,
                        subject,
                        date_text,
                        snippet,
                        customer_id,
                        intent,
                        1 if processed else 0,
                        json.dumps(raw_payload),
                        now,
                        mailbox,
                        uid,
                    ),
                )

    def ensure_default_jobs(self) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM scheduled_jobs WHERE job_type=?",
                ("process_unread_emails",),
            ).fetchone()
            if row is None:
                now = utc_now_iso()
                next_run = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
                conn.execute(
                    """
                    INSERT INTO scheduled_jobs (
                        id,job_type,enabled,interval_seconds,max_retries,retry_count,
                        next_run_at,last_run_at,last_status,last_error,payload_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "job_email_inbox",
                        "process_unread_emails",
                        1,
                        settings.default_email_job_interval_seconds,
                        3,
                        0,
                        next_run,
                        None,
                        "scheduled",
                        None,
                        json.dumps({"mailbox": "INBOX", "limit": 10}),
                    ),
                )

    def get_latest_email_record(self, customer_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT mailbox, uid, sender, subject, date_text, snippet, intent, raw_json
                FROM email_records
                WHERE customer_id=?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (customer_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "mailbox": row["mailbox"],
            "uid": row["uid"],
            "sender": row["sender"],
            "subject": row["subject"],
            "date_text": row["date_text"],
            "snippet": row["snippet"],
            "intent": row["intent"],
            "raw": json.loads(row["raw_json"] or "{}"),
        }

    def get_email_record(self, mailbox: str, uid: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT mailbox, uid, sender, subject, date_text, snippet, intent, raw_json, customer_id
                FROM email_records
                WHERE mailbox=? AND uid=?
                LIMIT 1
                """,
                (mailbox, uid),
            ).fetchone()
        if row is None:
            return None
        return {
            "mailbox": row["mailbox"],
            "uid": row["uid"],
            "sender": row["sender"],
            "subject": row["subject"],
            "date_text": row["date_text"],
            "snippet": row["snippet"],
            "intent": row["intent"],
            "customer_id": row["customer_id"],
            "raw": json.loads(row["raw_json"] or "{}"),
        }

    def upsert_production_schedule(
        self,
        order_id: str,
        customer_id: str,
        line_name: str,
        planned_start: str,
        planned_end: str,
        status: str,
        progress: int,
    ) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM production_schedule WHERE order_id=?",
                (order_id,),
            ).fetchone()
            if row is None:
                schedule_id = f"ps_{uuid.uuid4().hex[:10]}"
                conn.execute(
                    """
                    INSERT INTO production_schedule (
                        id, order_id, customer_id, line_name, planned_start, planned_end,
                        status, progress, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        schedule_id,
                        order_id,
                        customer_id,
                        line_name,
                        planned_start,
                        planned_end,
                        status,
                        max(0, min(100, progress)),
                        now,
                        now,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE production_schedule
                    SET customer_id=?, line_name=?, planned_start=?, planned_end=?,
                        status=?, progress=?, updated_at=?
                    WHERE order_id=?
                    """,
                    (
                        customer_id,
                        line_name,
                        planned_start,
                        planned_end,
                        status,
                        max(0, min(100, progress)),
                        now,
                        order_id,
                    ),
                )

    def list_production_schedule(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    ps.id,
                    ps.order_id,
                    ps.customer_id,
                    c.name AS customer_name,
                    o.product_name,
                    o.quantity,
                    o.status AS order_status,
                    ps.line_name,
                    ps.planned_start,
                    ps.planned_end,
                    ps.status,
                    ps.progress
                FROM production_schedule ps
                JOIN orders o ON o.id = ps.order_id
                JOIN customers c ON c.id = ps.customer_id
                ORDER BY ps.planned_start ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def detect_schedule_conflicts(
        self,
        schedule_id: str,
        line_name: str,
        planned_start: str,
        planned_end: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    ps.id,
                    ps.order_id,
                    c.name AS customer_name,
                    ps.planned_start,
                    ps.planned_end,
                    ps.line_name
                FROM production_schedule ps
                JOIN customers c ON c.id = ps.customer_id
                WHERE ps.line_name=?
                  AND ps.id != ?
                  AND ps.planned_start < ?
                  AND ps.planned_end > ?
                ORDER BY ps.planned_start ASC
                """,
                (line_name, schedule_id, planned_end, planned_start),
            ).fetchall()
        return [dict(r) for r in rows]

    def reschedule_production_item(
        self,
        schedule_id: str,
        line_name: str,
        planned_start: str,
        planned_end: str,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM production_schedule WHERE id=?", (schedule_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE production_schedule
                SET line_name=?, planned_start=?, planned_end=?, updated_at=?
                WHERE id=?
                """,
                (line_name, planned_start, planned_end, utc_now_iso(), schedule_id),
            )

        with self._connect() as conn:
            updated = conn.execute(
                """
                SELECT
                    ps.id,
                    ps.order_id,
                    ps.customer_id,
                    c.name AS customer_name,
                    o.product_name,
                    o.quantity,
                    o.status AS order_status,
                    ps.line_name,
                    ps.planned_start,
                    ps.planned_end,
                    ps.status,
                    ps.progress
                FROM production_schedule ps
                JOIN orders o ON o.id = ps.order_id
                JOIN customers c ON c.id = ps.customer_id
                WHERE ps.id=?
                """,
                (schedule_id,),
            ).fetchone()

        return dict(updated) if updated else None

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM scheduled_jobs ORDER BY id").fetchall()
        return [
            {
                "id": r["id"],
                "job_type": r["job_type"],
                "enabled": bool(r["enabled"]),
                "interval_seconds": r["interval_seconds"],
                "max_retries": r["max_retries"],
                "retry_count": r["retry_count"],
                "next_run_at": r["next_run_at"],
                "last_run_at": r["last_run_at"],
                "last_status": r["last_status"],
                "last_error": r["last_error"],
                "payload_json": r["payload_json"],
            }
            for r in rows
        ]

    def get_due_jobs(self) -> list[dict[str, Any]]:
        now = utc_now_iso()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scheduled_jobs WHERE enabled=1 AND next_run_at<=? ORDER BY next_run_at ASC",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_job_success(self, job_id: str, interval_seconds: int) -> None:
        now_dt = datetime.now(timezone.utc)
        next_dt = now_dt + timedelta(seconds=interval_seconds)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE scheduled_jobs
                SET retry_count=0,last_run_at=?,last_status='success',last_error=NULL,next_run_at=?
                WHERE id=?
                """,
                (now_dt.isoformat(), next_dt.isoformat(), job_id),
            )

    def mark_job_failure(self, job_id: str, interval_seconds: int, max_retries: int, retry_count: int, error: str) -> None:
        now_dt = datetime.now(timezone.utc)
        new_retry = retry_count + 1
        enabled = 0 if new_retry > max_retries else 1
        delay_seconds = min(interval_seconds * (2 ** min(new_retry, 4)), 3600)
        next_dt = now_dt + timedelta(seconds=delay_seconds)

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE scheduled_jobs
                SET retry_count=?,enabled=?,last_run_at=?,last_status='failed',last_error=?,next_run_at=?
                WHERE id=?
                """,
                (new_retry, enabled, now_dt.isoformat(), error[:500], next_dt.isoformat(), job_id),
            )

    def run_job_now(self, job_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE scheduled_jobs SET next_run_at=?, enabled=1 WHERE id=?",
                (utc_now_iso(), job_id),
            )

    def set_job_enabled(self, job_id: str, enabled: bool) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE scheduled_jobs SET enabled=? WHERE id=?", (1 if enabled else 0, job_id))


persistence_service = PersistenceService(settings.database_path)
