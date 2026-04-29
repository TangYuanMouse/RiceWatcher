import json
import re
from typing import Any

import httpx

from app.core.config import llm_provider_config
from app.core.schemas import ReplyDraftResponse
from app.services.persistence_service import persistence_service


class ReplyGenerationError(RuntimeError):
    pass


class ReplyGenerationService:
    @staticmethod
    def _extract_recipient(sender_text: str | None) -> str | None:
        if not sender_text:
            return None
        match = re.search(r"[\w.+-]+@[\w.-]+", sender_text)
        return match.group(0) if match else None

    async def _call_llm_json(self, prompt: str) -> dict[str, Any] | None:
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
            "temperature": 0.35,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a B2B foreign-trade email assistant. "
                        "Output JSON with keys: subject, body, suggestions. "
                        "Do not fabricate unavailable order or lead-time commitments."
                    ),
                },
                {"role": "user", "content": prompt},
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
                text = (
                    resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
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

    async def generate_reply(
        self,
        customer_id: str,
        mailbox: str = "INBOX",
        uid: str | None = None,
        tone: str = "professional",
        language: str = "en",
        additional_instruction: str | None = None,
    ) -> ReplyDraftResponse:
        customer = persistence_service.get_customer(customer_id)
        if customer is None:
            raise ReplyGenerationError("Customer not found")

        orders = persistence_service.list_orders(customer_id=customer_id)
        email = (
            persistence_service.get_email_record(mailbox=mailbox, uid=uid)
            if uid
            else persistence_service.get_latest_email_record(customer_id=customer_id)
        )

        context_used = [
            f"Customer: {customer['name']} ({customer['country']})",
            f"Stage: {customer['stage']}",
            f"Orders linked: {len(orders)}",
        ]
        if email:
            context_used.append(
                f"Latest email: subject={email.get('subject')} | sender={email.get('sender')}"
            )

        latest_order_line = "No active order context."
        if orders:
            latest = orders[0]
            latest_order_line = (
                f"Latest order: {latest['product_name']} x {latest['quantity']}, "
                f"status={latest['status']}, currency={latest['currency']}, "
                f"unit_price={latest['unit_price']}"
            )

        email_snippet = email.get("snippet", "") if email else ""
        email_subject = email.get("subject", "") if email else ""

        prompt = (
            f"Language: {language}\n"
            f"Tone: {tone}\n"
            f"Customer: {customer['name']}\n"
            f"Customer stage: {customer['stage']}\n"
            f"{latest_order_line}\n"
            f"Incoming email subject: {email_subject}\n"
            f"Incoming email snippet: {email_snippet}\n"
            f"Additional instruction: {additional_instruction or ''}\n"
            "Write a reply email draft with a clear subject and actionable body."
        )

        llm_result = await self._call_llm_json(prompt)
        if llm_result and llm_result.get("subject") and llm_result.get("body"):
            subject = str(llm_result["subject"])
            body = str(llm_result["body"])
            suggestions = [str(x) for x in llm_result.get("suggestions", [])]
            recipient = self._extract_recipient(email.get("sender") if email else None)
            draft = persistence_service.create_reply_draft(
                customer_id=customer_id,
                mailbox=mailbox,
                uid=uid,
                recipient=recipient,
                subject=subject,
                body=body,
                context_used=context_used,
                suggestions=suggestions,
            )
            return ReplyDraftResponse(
                draft_id=draft.get("id"),
                subject=subject,
                body=body,
                context_used=context_used,
                suggestions=suggestions,
            )

        fallback_subject = f"Re: {email_subject or 'Your inquiry'}"
        fallback_body = (
            f"Dear {customer['name']},\n\n"
            "Thank you for your message. We have reviewed your request and aligned it with your current order and account context. "
            "Please find our proposed next steps below:\n"
            "1) Confirm final quantity and target delivery window.\n"
            "2) Confirm payment terms and preferred shipping mode.\n"
            "3) We will send a formal PI/quotation update right after confirmation.\n\n"
            "Best regards,\n"
            "RiceWatcher Team"
        )

        recipient = self._extract_recipient(email.get("sender") if email else None)
        draft = persistence_service.create_reply_draft(
            customer_id=customer_id,
            mailbox=mailbox,
            uid=uid,
            recipient=recipient,
            subject=fallback_subject,
            body=fallback_body,
            context_used=context_used,
            suggestions=[
                "If customer asks for discount, offer tiered pricing by quantity.",
                "If lead-time is sensitive, provide two shipment options.",
            ],
        )

        return ReplyDraftResponse(
            draft_id=draft.get("id"),
            subject=fallback_subject,
            body=fallback_body,
            context_used=context_used,
            suggestions=[
                "If customer asks for discount, offer tiered pricing by quantity.",
                "If lead-time is sensitive, provide two shipment options.",
            ],
        )


reply_generation_service = ReplyGenerationService()
