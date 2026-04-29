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

                CREATE TABLE IF NOT EXISTS factories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    country TEXT NOT NULL,
                    contact_person TEXT,
                    contact_email TEXT,
                    tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fulfillment_tasks (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL UNIQUE,
                    customer_id TEXT NOT NULL,
                    factory_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    planned_start TEXT NOT NULL,
                    planned_end TEXT NOT NULL,
                    actual_end TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fulfillment_milestones (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    milestone_name TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    planned_date TEXT NOT NULL,
                    actual_date TEXT,
                    responsible_party TEXT,
                    note TEXT,
                    proof_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(task_id, sequence)
                );

                CREATE TABLE IF NOT EXISTS sample_requests (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    factory_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    feedback TEXT,
                    decision TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sample_request_items (
                    id TEXT PRIMARY KEY,
                    sample_request_id TEXT NOT NULL,
                    category_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    tracking_no TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sample_order_links (
                    id TEXT PRIMARY KEY,
                    sample_request_id TEXT NOT NULL,
                    sample_item_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(sample_request_id, sample_item_id)
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

            fcnt = conn.execute("SELECT COUNT(1) FROM factories").fetchone()[0]
            if fcnt == 0:
                now = utc_now_iso()
                factories = [
                    (
                        "f001",
                        "Jiangsu Precision Works",
                        "China",
                        "Li Wei",
                        "ops@jiangsu-precision.example",
                        json.dumps(["sensor", "electronics"]),
                        now,
                        now,
                    ),
                    (
                        "f002",
                        "Shenzhen Export Assembly",
                        "China",
                        "Annie Chen",
                        "delivery@sz-assembly.example",
                        json.dumps(["assembly", "inspection"]),
                        now,
                        now,
                    ),
                    (
                        "f003",
                        "Ningbo Fulfillment Plant",
                        "China",
                        "Tom Hu",
                        "schedule@ningbo-plant.example",
                        json.dumps(["shipping", "loading"]),
                        now,
                        now,
                    ),
                ]
                conn.executemany(
                    """
                    INSERT INTO factories
                    (id,name,country,contact_person,contact_email,tags_json,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    factories,
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

            risk_row = conn.execute(
                "SELECT id FROM scheduled_jobs WHERE job_type=?",
                ("scan_delay_risks",),
            ).fetchone()
            if risk_row is None:
                next_run = (datetime.now(timezone.utc) + timedelta(seconds=45)).isoformat()
                conn.execute(
                    """
                    INSERT INTO scheduled_jobs (
                        id,job_type,enabled,interval_seconds,max_retries,retry_count,
                        next_run_at,last_run_at,last_status,last_error,payload_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "job_delay_risks",
                        "scan_delay_risks",
                        1,
                        900,
                        3,
                        0,
                        next_run,
                        None,
                        "scheduled",
                        None,
                        json.dumps({"auto_mark": True}),
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

    def list_factories(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id,name,country,contact_person,contact_email,tags_json
                FROM factories
                ORDER BY name ASC
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "country": row["country"],
                "contact_person": row["contact_person"],
                "contact_email": row["contact_email"],
                "tags": json.loads(row["tags_json"] or "[]"),
            }
            for row in rows
        ]

    def upsert_fulfillment_task(
        self,
        order_id: str,
        customer_id: str,
        factory_id: str,
        status: str,
        planned_start: str,
        planned_end: str,
    ) -> str:
        now = utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM fulfillment_tasks WHERE order_id=?",
                (order_id,),
            ).fetchone()
            if row is None:
                task_id = f"ft_{uuid.uuid4().hex[:10]}"
                conn.execute(
                    """
                    INSERT INTO fulfillment_tasks (
                        id, order_id, customer_id, factory_id, status,
                        planned_start, planned_end, actual_end, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        task_id,
                        order_id,
                        customer_id,
                        factory_id,
                        status,
                        planned_start,
                        planned_end,
                        None,
                        now,
                        now,
                    ),
                )
                return task_id

            task_id = str(row["id"])
            conn.execute(
                """
                UPDATE fulfillment_tasks
                SET customer_id=?, factory_id=?, status=?, planned_start=?, planned_end=?, updated_at=?
                WHERE id=?
                """,
                (customer_id, factory_id, status, planned_start, planned_end, now, task_id),
            )
        return task_id

    def assign_factory_to_fulfillment_task(self, task_id: str, factory_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM fulfillment_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE fulfillment_tasks SET factory_id=?, updated_at=? WHERE id=?",
                (factory_id, utc_now_iso(), task_id),
            )

        with self._connect() as conn:
            task = conn.execute(
                """
                SELECT
                    ft.id,
                    ft.order_id,
                    ft.customer_id,
                    c.name AS customer_name,
                    o.product_name,
                    o.quantity,
                    o.status AS order_status,
                    ft.factory_id,
                    f.name AS factory_name,
                    ft.status,
                    ft.planned_start,
                    ft.planned_end,
                    ft.actual_end
                FROM fulfillment_tasks ft
                JOIN orders o ON o.id = ft.order_id
                JOIN customers c ON c.id = ft.customer_id
                JOIN factories f ON f.id = ft.factory_id
                WHERE ft.id=?
                """,
                (task_id,),
            ).fetchone()
        return dict(task) if task else None

    def list_fulfillment_tasks(
        self,
        status: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                ft.id,
                ft.order_id,
                ft.customer_id,
                c.name AS customer_name,
                o.product_name,
                o.quantity,
                o.status AS order_status,
                ft.factory_id,
                f.name AS factory_name,
                ft.status,
                ft.planned_start,
                ft.planned_end,
                ft.actual_end
            FROM fulfillment_tasks ft
            JOIN orders o ON o.id = ft.order_id
            JOIN customers c ON c.id = ft.customer_id
            JOIN factories f ON f.id = ft.factory_id
        """
        args: list[Any] = []
        clauses: list[str] = []
        if status:
            clauses.append("ft.status=?")
            args.append(status)
        if search:
            kw = f"%{search.strip()}%"
            clauses.append(
                "(ft.order_id LIKE ? OR c.name LIKE ? OR o.product_name LIKE ? OR f.name LIKE ?)"
            )
            args.extend([kw, kw, kw, kw])
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY ft.planned_start ASC"

        with self._connect() as conn:
            rows = conn.execute(query, tuple(args)).fetchall()
        return [dict(row) for row in rows]

    def upsert_fulfillment_milestones(self, task_id: str, milestones: list[dict[str, Any]]) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            for item in milestones:
                row = conn.execute(
                    "SELECT id FROM fulfillment_milestones WHERE task_id=? AND sequence=?",
                    (task_id, int(item["sequence"])),
                ).fetchone()
                if row is None:
                    milestone_id = f"fm_{uuid.uuid4().hex[:10]}"
                    conn.execute(
                        """
                        INSERT INTO fulfillment_milestones (
                            id, task_id, milestone_name, sequence, status,
                            planned_date, actual_date, responsible_party, note,
                            proof_url, created_at, updated_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            milestone_id,
                            task_id,
                            str(item["milestone_name"]),
                            int(item["sequence"]),
                            str(item.get("status") or "planned"),
                            str(item["planned_date"]),
                            item.get("actual_date"),
                            item.get("responsible_party"),
                            item.get("note"),
                            item.get("proof_url"),
                            now,
                            now,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE fulfillment_milestones
                        SET milestone_name=?, status=?, planned_date=?, updated_at=?
                        WHERE task_id=? AND sequence=?
                        """,
                        (
                            str(item["milestone_name"]),
                            str(item.get("status") or "planned"),
                            str(item["planned_date"]),
                            now,
                            task_id,
                            int(item["sequence"]),
                        ),
                    )

    def list_fulfillment_milestones(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    task_id,
                    milestone_name,
                    sequence,
                    status,
                    planned_date,
                    actual_date,
                    responsible_party,
                    note,
                    proof_url
                FROM fulfillment_milestones
                WHERE task_id=?
                ORDER BY sequence ASC
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_fulfillment_milestones_with_context(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    fm.id AS milestone_id,
                    fm.task_id,
                    fm.milestone_name,
                    fm.sequence,
                    fm.status,
                    fm.planned_date,
                    fm.actual_date,
                    ft.order_id,
                    ft.customer_id,
                    c.name AS customer_name,
                    f.name AS factory_name
                FROM fulfillment_milestones fm
                JOIN fulfillment_tasks ft ON ft.id = fm.task_id
                JOIN customers c ON c.id = ft.customer_id
                JOIN factories f ON f.id = ft.factory_id
                ORDER BY fm.planned_date ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def update_fulfillment_milestone(
        self,
        milestone_id: str,
        status: str | None = None,
        planned_date: str | None = None,
        actual_date: str | None = None,
        responsible_party: str | None = None,
        note: str | None = None,
        proof_url: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            current = conn.execute(
                "SELECT * FROM fulfillment_milestones WHERE id=?",
                (milestone_id,),
            ).fetchone()
            if current is None:
                return None

            next_status = status if status is not None else current["status"]
            next_planned_date = planned_date if planned_date is not None else current["planned_date"]
            next_actual_date = actual_date if actual_date is not None else current["actual_date"]
            next_responsible_party = (
                responsible_party if responsible_party is not None else current["responsible_party"]
            )
            next_note = note if note is not None else current["note"]
            next_proof_url = proof_url if proof_url is not None else current["proof_url"]

            conn.execute(
                """
                UPDATE fulfillment_milestones
                SET status=?, planned_date=?, actual_date=?, responsible_party=?,
                    note=?, proof_url=?, updated_at=?
                WHERE id=?
                """,
                (
                    next_status,
                    next_planned_date,
                    next_actual_date,
                    next_responsible_party,
                    next_note,
                    next_proof_url,
                    utc_now_iso(),
                    milestone_id,
                ),
            )

            updated = conn.execute(
                """
                SELECT
                    id,
                    task_id,
                    milestone_name,
                    sequence,
                    status,
                    planned_date,
                    actual_date,
                    responsible_party,
                    note,
                    proof_url
                FROM fulfillment_milestones
                WHERE id=?
                """,
                (milestone_id,),
            ).fetchone()

        return dict(updated) if updated else None

    def create_sample_request(
        self,
        customer_id: str,
        factory_id: str,
        categories: list[dict[str, Any]],
        note: str | None = None,
    ) -> dict[str, Any]:
        sample_id = f"sr_{uuid.uuid4().hex[:10]}"
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sample_requests (
                    id, customer_id, factory_id, status, feedback, decision, note, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    sample_id,
                    customer_id,
                    factory_id,
                    "requested",
                    None,
                    "pending",
                    note,
                    now,
                    now,
                ),
            )

            for item in categories:
                item_id = f"sri_{uuid.uuid4().hex[:10]}"
                conn.execute(
                    """
                    INSERT INTO sample_request_items (
                        id, sample_request_id, category_name, quantity, status,
                        tracking_no, note, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        item_id,
                        sample_id,
                        str(item["category_name"]),
                        int(item.get("quantity") or 1),
                        "requested",
                        None,
                        None,
                        now,
                        now,
                    ),
                )

        row = self.get_sample_request(sample_id)
        return row or {}

    def get_sample_request(self, sample_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    sr.id,
                    sr.customer_id,
                    c.name AS customer_name,
                    sr.factory_id,
                    f.name AS factory_name,
                    sr.status,
                    sr.feedback,
                    sr.decision,
                    sr.note,
                    sr.created_at,
                    sr.updated_at,
                    COUNT(sri.id) AS item_count
                FROM sample_requests sr
                JOIN customers c ON c.id = sr.customer_id
                JOIN factories f ON f.id = sr.factory_id
                LEFT JOIN sample_request_items sri ON sri.sample_request_id = sr.id
                WHERE sr.id=?
                GROUP BY sr.id
                """,
                (sample_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_sample_requests(
        self,
        status: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                sr.id,
                sr.customer_id,
                c.name AS customer_name,
                sr.factory_id,
                f.name AS factory_name,
                sr.status,
                sr.feedback,
                sr.decision,
                sr.note,
                sr.created_at,
                sr.updated_at,
                COUNT(sri.id) AS item_count
            FROM sample_requests sr
            JOIN customers c ON c.id = sr.customer_id
            JOIN factories f ON f.id = sr.factory_id
            LEFT JOIN sample_request_items sri ON sri.sample_request_id = sr.id
        """
        clauses: list[str] = []
        args: list[Any] = []
        if status:
            clauses.append("sr.status=?")
            args.append(status)
        if search:
            kw = f"%{search.strip()}%"
            clauses.append("(sr.id LIKE ? OR c.name LIKE ? OR f.name LIKE ? OR sr.note LIKE ?)")
            args.extend([kw, kw, kw, kw])
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " GROUP BY sr.id ORDER BY sr.updated_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, tuple(args)).fetchall()
        return [dict(row) for row in rows]

    def list_sample_request_items(self, sample_request_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    sample_request_id,
                    category_name,
                    quantity,
                    status,
                    tracking_no,
                    note
                FROM sample_request_items
                WHERE sample_request_id=?
                ORDER BY created_at ASC
                """,
                (sample_request_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_sample_request(
        self,
        sample_id: str,
        status: str | None = None,
        feedback: str | None = None,
        decision: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        current = self.get_sample_request(sample_id)
        if current is None:
            return None

        next_status = status if status is not None else current["status"]
        next_feedback = feedback if feedback is not None else current["feedback"]
        next_decision = decision if decision is not None else current["decision"]
        next_note = note if note is not None else current["note"]

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sample_requests
                SET status=?, feedback=?, decision=?, note=?, updated_at=?
                WHERE id=?
                """,
                (next_status, next_feedback, next_decision, next_note, utc_now_iso(), sample_id),
            )
        return self.get_sample_request(sample_id)

    def update_sample_request_item(
        self,
        item_id: str,
        status: str | None = None,
        tracking_no: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            current = conn.execute(
                "SELECT * FROM sample_request_items WHERE id=?",
                (item_id,),
            ).fetchone()
            if current is None:
                return None

            next_status = status if status is not None else current["status"]
            next_tracking = tracking_no if tracking_no is not None else current["tracking_no"]
            next_note = note if note is not None else current["note"]

            conn.execute(
                """
                UPDATE sample_request_items
                SET status=?, tracking_no=?, note=?, updated_at=?
                WHERE id=?
                """,
                (next_status, next_tracking, next_note, utc_now_iso(), item_id),
            )

            updated = conn.execute(
                """
                SELECT
                    id,
                    sample_request_id,
                    category_name,
                    quantity,
                    status,
                    tracking_no,
                    note
                FROM sample_request_items
                WHERE id=?
                """,
                (item_id,),
            ).fetchone()

        return dict(updated) if updated else None

    def generate_sample_order_suggestions(self, sample_id: str) -> dict[str, Any] | None:
        sample = self.get_sample_request(sample_id)
        if sample is None:
            return None
        items = self.list_sample_request_items(sample_id)

        suggestions: list[dict[str, Any]] = []
        for item in items:
            suggested_qty = max(500, int(item["quantity"]) * 1000)
            suggestions.append(
                {
                    "sample_item_id": item["id"],
                    "category_name": item["category_name"],
                    "suggested_product_name": str(item["category_name"]),
                    "suggested_quantity": suggested_qty,
                    "suggested_status": "待确认",
                    "reason": (
                        "Sample flow reached customer feedback stage; "
                        "this draft quantity is a conservative commercial starting point."
                    ),
                }
            )

        return {
            "sample_request_id": sample_id,
            "decision": sample["decision"],
            "suggestions": suggestions,
        }

    def convert_sample_to_order_drafts(self, sample_id: str) -> dict[str, Any] | None:
        sample = self.get_sample_request(sample_id)
        if sample is None:
            return None

        suggestions_payload = self.generate_sample_order_suggestions(sample_id)
        if suggestions_payload is None:
            return None

        created_order_ids: list[str] = []
        existing_order_ids: list[str] = []

        for suggestion in suggestions_payload["suggestions"]:
            sample_item_id = str(suggestion["sample_item_id"])
            with self._connect() as conn:
                existing = conn.execute(
                    """
                    SELECT order_id FROM sample_order_links
                    WHERE sample_request_id=? AND sample_item_id=?
                    """,
                    (sample_id, sample_item_id),
                ).fetchone()

            if existing is not None:
                existing_order_ids.append(str(existing["order_id"]))
                continue

            order = self.create_order(
                customer_id=str(sample["customer_id"]),
                product_name=str(suggestion["suggested_product_name"]),
                quantity=int(suggestion["suggested_quantity"]),
                unit_price=None,
                currency="USD",
                status="待确认",
                payload={
                    "source": "sample_request",
                    "sample_request_id": sample_id,
                    "sample_item_id": sample_item_id,
                    "factory_id": sample["factory_id"],
                },
            )
            created_order_ids.append(str(order["id"]))

            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sample_order_links (
                        id, sample_request_id, sample_item_id, order_id, created_at
                    ) VALUES (?,?,?,?,?)
                    """,
                    (
                        f"sol_{uuid.uuid4().hex[:10]}",
                        sample_id,
                        sample_item_id,
                        str(order["id"]),
                        utc_now_iso(),
                    ),
                )

        status = "converted_to_order" if created_order_ids or existing_order_ids else sample["status"]
        decision = "order" if created_order_ids or existing_order_ids else sample["decision"]
        self.update_sample_request(
            sample_id=sample_id,
            status=status,
            decision=decision,
        )

        return {
            "sample_request_id": sample_id,
            "created_order_ids": created_order_ids,
            "existing_order_ids": existing_order_ids,
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
