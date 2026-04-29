import json
import re
from typing import Any

import httpx

from app.core.config import llm_provider_config
from app.core.config import settings
from app.core.schemas import EmailProcessReport
from app.services.email_tool_adapter import EmailToolError, email_tool_adapter
from app.services.persistence_service import persistence_service


def _extract_quantity(text: str) -> int:
    match = re.search(r"\b(\d{1,6})\b", text)
    return int(match.group(1)) if match else 1000


def _extract_price(text: str) -> float | None:
    match = re.search(r"\$\s?(\d+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s?(usd|dollar)", text.lower())
    return float(match.group(1)) if match else None


class EmailOrchestrationService:
    classification_threshold = settings.email_classification_confidence_threshold
    extraction_threshold = settings.email_extraction_confidence_threshold

    async def _call_llm_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        ready = (
            llm_provider_config.enabled
            and llm_provider_config.base_url
            and llm_provider_config.api_key
            and llm_provider_config.model_name
        )
        if not ready:
            return None

        endpoint = f"{llm_provider_config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": llm_provider_config.model_name,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {llm_provider_config.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=llm_provider_config.timeout_seconds) as client:
                resp = await client.post(endpoint, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if not text:
                return None

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r"\{[\s\S]*\}", text)
                if match:
                    return json.loads(match.group(0))
                return None
        except Exception:
            return None

    async def classify_email(self, email_data: dict[str, Any]) -> dict[str, Any]:
        subject = str(email_data.get("subject", ""))
        snippet = str(email_data.get("snippet", ""))
        text = f"{subject}\n{snippet}".lower()

        llm_result = await self._call_llm_json(
            system_prompt=(
                "Classify trade emails. Output JSON only with keys: "
                "intent, confidence, reasons."
            ),
            user_prompt=(
                "Intents: new_inquiry, quotation_reply, order_confirmation, "
                "payment_notice, logistics_docs, old_customer_followup, non_business_spam.\n"
                f"Subject: {subject}\nSnippet: {snippet}"
            ),
        )
        if llm_result and isinstance(llm_result, dict) and llm_result.get("intent"):
            return {
                "intent": str(llm_result.get("intent")),
                "confidence": float(llm_result.get("confidence", 0.7)),
                "reasons": llm_result.get("reasons", []),
            }

        if any(k in text for k in ["purchase order", "po", "pi confirmed", "order confirm"]):
            return {"intent": "order_confirmation", "confidence": 0.88, "reasons": ["order keywords"]}
        if any(k in text for k in ["payment", "deposit", "swift", "wire transfer"]):
            return {"intent": "payment_notice", "confidence": 0.82, "reasons": ["payment keywords"]}
        if any(k in text for k in ["bl", "bill of lading", "tracking", "shipment"]):
            return {"intent": "logistics_docs", "confidence": 0.78, "reasons": ["logistics keywords"]}
        if any(k in text for k in ["quote", "quotation", "price", "counter offer"]):
            return {"intent": "quotation_reply", "confidence": 0.76, "reasons": ["quotation keywords"]}
        if any(k in text for k in ["inquiry", "rfq", "looking for", "need supplier"]):
            return {"intent": "new_inquiry", "confidence": 0.8, "reasons": ["inquiry keywords"]}
        if any(k in text for k in ["unsubscribe", "newsletter", "promotion"]):
            return {"intent": "non_business_spam", "confidence": 0.9, "reasons": ["spam keywords"]}
        return {"intent": "old_customer_followup", "confidence": 0.6, "reasons": ["default"]}

    async def extract_fields(self, email_data: dict[str, Any]) -> dict[str, Any]:
        subject = str(email_data.get("subject", ""))
        snippet = str(email_data.get("snippet", ""))
        text = f"{subject} {snippet}"

        llm_result = await self._call_llm_json(
            system_prompt=(
                "Extract fields from trade email. Output JSON only with keys: "
                "product_name, quantity, target_price, currency."
            ),
            user_prompt=f"Subject: {subject}\nSnippet: {snippet}",
        )
        if llm_result and isinstance(llm_result, dict):
            product_name = str(llm_result.get("product_name") or "General Product")
            quantity = int(llm_result.get("quantity") or 1000)
            target_price = llm_result.get("target_price")
            target_price = float(target_price) if target_price is not None else None
            currency = str(llm_result.get("currency") or "USD")
            return {
                "product_name": product_name,
                "quantity": quantity,
                "target_price": target_price,
                "currency": currency,
                "confidence": float(llm_result.get("confidence", 0.74)),
            }

        return {
            "product_name": "Rice Moisture Sensor",
            "quantity": _extract_quantity(text),
            "target_price": _extract_price(text),
            "currency": "USD",
            "confidence": 0.62,
        }

    def plan_actions(self, intent: str, fields: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = [{"type": "timeline_append", "reason": f"intent={intent}"}]
        if intent == "new_inquiry":
            actions.extend(
                [
                    {"type": "update_customer_stage", "stage": "inquiry"},
                    {"type": "draft_reply_email"},
                ]
            )
        elif intent == "quotation_reply":
            actions.append({"type": "update_customer_stage", "stage": "negotiation"})
        elif intent == "order_confirmation":
            actions.append(
                {
                    "type": "create_order",
                    "product_name": fields["product_name"],
                    "quantity": fields["quantity"],
                    "unit_price": fields["target_price"],
                    "currency": fields["currency"],
                    "status": "待确认",
                }
            )
        elif intent == "payment_notice":
            actions.append({"type": "update_latest_order_status", "status": "生产中"})
        elif intent == "logistics_docs":
            actions.append({"type": "update_latest_order_status", "status": "已发货"})
        return actions

    async def process_unread(self, mailbox: str = "INBOX", limit: int = 10) -> EmailProcessReport:
        report = EmailProcessReport(
            scanned=0,
            processed=0,
            skipped=0,
            review_queued=0,
            orders_created=0,
            timeline_added=0,
            details=[],
        )

        try:
            unread = await email_tool_adapter.check(
                limit=limit,
                mailbox=mailbox,
                unseen=True,
            )
        except EmailToolError as exc:
            raise EmailToolError(f"Unread email processing failed at fetch stage: {exc}") from exc

        if not isinstance(unread, list):
            return report

        report.scanned = len(unread)

        for item in unread:
            uid = str(item.get("uid", ""))
            if not uid:
                report.skipped += 1
                continue
            if persistence_service.is_email_processed(mailbox=mailbox, uid=uid):
                report.skipped += 1
                continue

            sender = str(item.get("from", "Unknown"))
            subject = str(item.get("subject", "(no subject)"))
            snippet = str(item.get("snippet", ""))
            date_text = item.get("date")
            customer = persistence_service.resolve_customer_from_sender(sender)

            classified = await self.classify_email(item)
            fields = await self.extract_fields(item)

            classification_conf = float(classified.get("confidence", 0.0))
            extraction_conf = float(fields.get("confidence", 0.0))
            if (
                classification_conf < self.classification_threshold
                or extraction_conf < self.extraction_threshold
            ):
                queue_item = persistence_service.upsert_review_queue_item(
                    mailbox=mailbox,
                    uid=uid,
                    customer_id=customer["id"],
                    intent=classified["intent"],
                    classification_confidence=classification_conf,
                    extraction_confidence=extraction_conf,
                    reasons=[
                        f"classification<{self.classification_threshold}" if classification_conf < self.classification_threshold else "classification_ok",
                        f"extraction<{self.extraction_threshold}" if extraction_conf < self.extraction_threshold else "extraction_ok",
                    ],
                    payload={
                        "email": item,
                        "classification": classified,
                        "fields": fields,
                    },
                )

                persistence_service.save_email_record(
                    mailbox=mailbox,
                    uid=uid,
                    sender=sender,
                    subject=subject,
                    date_text=str(date_text) if date_text else None,
                    snippet=snippet,
                    customer_id=customer["id"],
                    intent=classified["intent"],
                    processed=False,
                    raw_payload={
                        "email": item,
                        "classification": classified,
                        "fields": fields,
                        "review_queue": queue_item,
                    },
                )

                persistence_service.add_timeline_event(
                    customer_id=customer["id"],
                    source="agent",
                    title=f"Manual review required: {subject[:64]}",
                    summary=(
                        f"Low confidence detected. classification={classification_conf:.2f}, "
                        f"extraction={extraction_conf:.2f}."
                    ),
                    timestamp=str(date_text) if date_text else None,
                )
                report.timeline_added += 1
                report.review_queued += 1
                report.details.append(
                    {
                        "uid": uid,
                        "customer_id": customer["id"],
                        "intent": classified["intent"],
                        "status": "queued_for_review",
                    }
                )
                continue

            actions = self.plan_actions(classified["intent"], fields)

            for action in actions:
                if action["type"] == "timeline_append":
                    persistence_service.add_timeline_event(
                        customer_id=customer["id"],
                        source="email",
                        title=f"Email: {subject[:80]}",
                        summary=(
                            f"Intent={classified['intent']} | From={sender} | "
                            f"Snippet={snippet[:180]}"
                        ),
                        timestamp=str(date_text) if date_text else None,
                    )
                    report.timeline_added += 1
                elif action["type"] == "update_customer_stage":
                    persistence_service.upsert_customer_stage(
                        customer_id=customer["id"],
                        stage=str(action["stage"]),
                    )
                elif action["type"] == "create_order":
                    persistence_service.create_order(
                        customer_id=customer["id"],
                        product_name=str(action["product_name"]),
                        quantity=int(action["quantity"]),
                        unit_price=float(action["unit_price"]) if action["unit_price"] is not None else None,
                        currency=str(action["currency"]),
                        status=str(action["status"]),
                        payload={"intent": classified["intent"], "source_uid": uid},
                    )
                    report.orders_created += 1
                elif action["type"] == "update_latest_order_status":
                    persistence_service.update_latest_order_status(
                        customer_id=customer["id"],
                        status=str(action["status"]),
                    )

            persistence_service.save_email_record(
                mailbox=mailbox,
                uid=uid,
                sender=sender,
                subject=subject,
                date_text=str(date_text) if date_text else None,
                snippet=snippet,
                customer_id=customer["id"],
                intent=classified["intent"],
                processed=True,
                raw_payload={
                    "email": item,
                    "classification": classified,
                    "fields": fields,
                    "actions": actions,
                },
            )

            report.processed += 1
            report.details.append(
                {
                    "uid": uid,
                    "customer_id": customer["id"],
                    "intent": classified["intent"],
                    "actions": actions,
                }
            )

        return report


email_orchestration_service = EmailOrchestrationService()
