# RiceWatcher

OpenClaw-style foreign-trade AI assistant skeleton.

## What is included

- Gateway-first backend with per-session serialized execution lanes.
- Multi-agent supervisor routing (gateway supervisor + domain agents).
- Streaming run events via Server-Sent Events.
- Customer list and timeline APIs.
- React dashboard with run console + timeline view.
- Third-party LLM provider config file (api_key, base_url, model_name).
- IMAP/SMTP plugin adapter integration (`imap-smtp-email`).
- SQLite persistence for customers, timeline, orders, and email processing records.
- Email orchestration pipeline (classify -> extract -> action plan -> write timeline/order).
- Built-in scheduler with retry/backoff for unread email processing.
- Built-in scheduler for unread email processing and fulfillment delay-risk scanning.
- Context-aware reply draft generation using customer + order + email context.
- Reply draft approval flow (edit -> submit -> approve/reject -> send).
- Confidence-threshold-based manual review queue for low-confidence emails.
- Production scheduling planner and visualization-ready API.
- Drag-reschedule API with production line conflict detection.
- Factory fulfillment tracking for trader-to-factory order execution milestones.
- Manual factory milestone editing with searchable fulfillment board.
- Sample shipment workflow from inquiry to feedback to order/no-order decision.
- Auto-generated order draft suggestions from sample feedback, with one-click conversion.

## Project structure

- docs/
- backend/
- frontend/

## Configure third-party LLM

Edit local file:

- backend/config/llm_provider.local.json

Fields:

- provider
- base_url
- api_key
- model_name
- timeout_seconds
- enabled

If local file does not exist, backend falls back to:

- backend/config/llm_provider.json

Environment variable overrides are also supported:

- LLM_PROVIDER
- LLM_BASE_URL
- LLM_API_KEY
- LLM_MODEL_NAME
- LLM_TIMEOUT_SECONDS
- LLM_ENABLED
- LLM_PROVIDER_CONFIG
- EMAIL_CLASSIFICATION_CONFIDENCE_THRESHOLD
- EMAIL_EXTRACTION_CONFIDENCE_THRESHOLD

## Configure email plugin integration

This project integrates the workspace plugin at:

- imap-smtp-email/

Backend adapter defaults:

- `EMAIL_SKILL_DIR=../imap-smtp-email` (workspace absolute path resolved automatically)
- `EMAIL_SKILL_NODE=node`
- `EMAIL_TOOL_TIMEOUT_SECONDS=45`

Prepare plugin dependencies and credentials:

1. cd imap-smtp-email
2. npm install
3. Ensure plugin `.env` is configured (IMAP/SMTP credentials)

Then you can call backend email endpoints below.

## Run backend

1. cd backend
2. pip install -r requirements.txt
3. uvicorn app.main:app --reload --port 8000

## Run frontend

1. cd frontend
2. npm install
3. npm run dev

Open:

- Frontend: http://localhost:5173
- Backend: http://localhost:8000

## Main API endpoints

- GET /api/v1/health
- POST /api/v1/gateway/messages
- GET /api/v1/gateway/runs/{run_id}
- GET /api/v1/gateway/runs/{run_id}/events/stream
- GET /api/v1/gateway/config/llm
- GET /api/v1/gateway/agents
- GET /api/v1/email/status
- GET /api/v1/email/agents
- POST /api/v1/email/check
- POST /api/v1/email/fetch
- POST /api/v1/email/search
- POST /api/v1/email/send
- POST /api/v1/email/verify-smtp
- POST /api/v1/email/process-unread
- POST /api/v1/email/reply-draft
- GET /api/v1/email/drafts
- PATCH /api/v1/email/drafts/{draft_id}
- POST /api/v1/email/drafts/{draft_id}/submit
- POST /api/v1/email/drafts/{draft_id}/approve
- POST /api/v1/email/drafts/{draft_id}/reject
- POST /api/v1/email/drafts/{draft_id}/send
- GET /api/v1/email/review-queue
- POST /api/v1/email/review-queue/{item_id}/resolve
- GET /api/v1/customers
- GET /api/v1/timeline/events
- GET /api/v1/orders
- GET /api/v1/production/schedule
- POST /api/v1/production/plan
- PATCH /api/v1/production/schedule/{schedule_id}/reschedule
- GET /api/v1/production/factories
- GET /api/v1/production/tasks
- GET /api/v1/production/tasks/{task_id}/milestones
- PATCH /api/v1/production/tasks/{task_id}/assign-factory
- PATCH /api/v1/production/milestones/{milestone_id}
- POST /api/v1/production/delay-risks/scan
- GET /api/v1/production/samples
- POST /api/v1/production/samples
- GET /api/v1/production/samples/{sample_id}/items
- PATCH /api/v1/production/samples/{sample_id}
- PATCH /api/v1/production/sample-items/{item_id}
- GET /api/v1/production/samples/{sample_id}/order-suggestions
- POST /api/v1/production/samples/{sample_id}/convert-to-orders
- GET /api/v1/automation/jobs
- POST /api/v1/automation/jobs/{job_id}/run-now
- POST /api/v1/automation/jobs/{job_id}/enable
- POST /api/v1/automation/jobs/{job_id}/disable
