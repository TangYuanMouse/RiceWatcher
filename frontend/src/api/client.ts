import type {
  Customer,
  DelayRiskReport,
  FactoryRecord,
  FulfillmentMilestoneItem,
  FulfillmentStatus,
  FulfillmentTaskItem,
  OrderRecord,
  ProductionRescheduleResponse,
  ProductionScheduleItem,
  ReplyDraftRecord,
  ReplyDraftResponse,
  SampleDecision,
  SampleItemStatus,
  SampleOrderConversionResponse,
  SampleOrderSuggestionResponse,
  SampleRequestItem,
  SampleRequestRecord,
  SampleRequestStatus,
  ReviewQueueItem,
  RunAccepted,
  TimelineEvent,
} from "../types";

const API_BASE = "http://localhost:8000/api/v1";

export async function postMessage(params: {
  session_key: string;
  text: string;
  channel?: string;
  customer_id?: string;
}): Promise<RunAccepted> {
  const resp = await fetch(`${API_BASE}/gateway/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!resp.ok) {
    throw new Error(`Failed to submit message: ${resp.status}`);
  }

  return resp.json();
}

export function streamRunEvents(runId: string, startIndex = 0): EventSource {
  return new EventSource(
    `${API_BASE}/gateway/runs/${runId}/events/stream?start_index=${startIndex}`
  );
}

export async function fetchCustomers(): Promise<Customer[]> {
  const resp = await fetch(`${API_BASE}/customers`);
  if (!resp.ok) {
    throw new Error(`Failed to load customers: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchTimeline(
  customerId?: string
): Promise<TimelineEvent[]> {
  const query = customerId ? `?customer_id=${customerId}` : "";
  const resp = await fetch(`${API_BASE}/timeline/events${query}`);
  if (!resp.ok) {
    throw new Error(`Failed to load timeline: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchOrders(customerId?: string): Promise<OrderRecord[]> {
  const query = customerId ? `?customer_id=${customerId}` : "";
  const resp = await fetch(`${API_BASE}/orders${query}`);
  if (!resp.ok) {
    throw new Error(`Failed to load orders: ${resp.status}`);
  }
  return resp.json();
}

export async function generateReplyDraft(params: {
  customer_id: string;
  mailbox?: string;
  uid?: string;
  tone?: string;
  language?: string;
  additional_instruction?: string;
}): Promise<ReplyDraftResponse> {
  const resp = await fetch(`${API_BASE}/email/reply-draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!resp.ok) {
    throw new Error(`Failed to generate reply draft: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchReplyDrafts(params?: {
  customer_id?: string;
  status?: string;
}): Promise<ReplyDraftRecord[]> {
  const query = new URLSearchParams();
  if (params?.customer_id) query.set("customer_id", params.customer_id);
  if (params?.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const resp = await fetch(`${API_BASE}/email/drafts${suffix}`);
  if (!resp.ok) {
    throw new Error(`Failed to load reply drafts: ${resp.status}`);
  }
  return resp.json();
}

export async function updateReplyDraft(
  draftId: string,
  payload: { subject?: string; body?: string }
): Promise<ReplyDraftRecord> {
  const resp = await fetch(`${API_BASE}/email/drafts/${draftId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(`Failed to update draft: ${resp.status}`);
  }
  return resp.json();
}

export async function submitReplyDraft(draftId: string, actor = "operator"): Promise<ReplyDraftRecord> {
  const resp = await fetch(`${API_BASE}/email/drafts/${draftId}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor }),
  });
  if (!resp.ok) {
    throw new Error(`Failed to submit draft for approval: ${resp.status}`);
  }
  return resp.json();
}

export async function approveReplyDraft(draftId: string, actor = "approver"): Promise<ReplyDraftRecord> {
  const resp = await fetch(`${API_BASE}/email/drafts/${draftId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor }),
  });
  if (!resp.ok) {
    throw new Error(`Failed to approve draft: ${resp.status}`);
  }
  return resp.json();
}

export async function rejectReplyDraft(
  draftId: string,
  reason: string,
  actor = "approver"
): Promise<ReplyDraftRecord> {
  const resp = await fetch(`${API_BASE}/email/drafts/${draftId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor, reason }),
  });
  if (!resp.ok) {
    throw new Error(`Failed to reject draft: ${resp.status}`);
  }
  return resp.json();
}

export async function sendApprovedDraft(draftId: string): Promise<ReplyDraftRecord> {
  const resp = await fetch(`${API_BASE}/email/drafts/${draftId}/send`, {
    method: "POST",
  });
  if (!resp.ok) {
    throw new Error(`Failed to send approved draft: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchReviewQueue(status = "pending"): Promise<ReviewQueueItem[]> {
  const resp = await fetch(`${API_BASE}/email/review-queue?status=${encodeURIComponent(status)}`);
  if (!resp.ok) {
    throw new Error(`Failed to load review queue: ${resp.status}`);
  }
  return resp.json();
}

export async function resolveReviewQueueItem(
  itemId: string,
  action: "approved" | "rejected",
  note?: string
): Promise<ReviewQueueItem> {
  const resp = await fetch(`${API_BASE}/email/review-queue/${itemId}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, resolver: "operator", note }),
  });
  if (!resp.ok) {
    throw new Error(`Failed to resolve review queue item: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchProductionSchedule(): Promise<ProductionScheduleItem[]> {
  const resp = await fetch(`${API_BASE}/production/schedule`);
  if (!resp.ok) {
    throw new Error(`Failed to load production schedule: ${resp.status}`);
  }
  return resp.json();
}

export async function planProductionSchedule(): Promise<{ planned_count: number }> {
  const resp = await fetch(`${API_BASE}/production/plan`, {
    method: "POST",
  });
  if (!resp.ok) {
    throw new Error(`Failed to plan production schedule: ${resp.status}`);
  }
  return resp.json();
}

export async function rescheduleProductionItem(
  scheduleId: string,
  payload: { line_name: string; planned_start: string; planned_end: string }
): Promise<ProductionRescheduleResponse> {
  const resp = await fetch(`${API_BASE}/production/schedule/${scheduleId}/reschedule`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(`Failed to reschedule production item: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchFactories(): Promise<FactoryRecord[]> {
  const resp = await fetch(`${API_BASE}/production/factories`);
  if (!resp.ok) {
    throw new Error(`Failed to load factories: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchFulfillmentTasks(status?: string, search?: string): Promise<FulfillmentTaskItem[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (search) params.set("search", search);
  const query = params.toString() ? `?${params.toString()}` : "";
  const resp = await fetch(`${API_BASE}/production/tasks${query}`);
  if (!resp.ok) {
    throw new Error(`Failed to load fulfillment tasks: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchTaskMilestones(taskId: string): Promise<FulfillmentMilestoneItem[]> {
  const resp = await fetch(`${API_BASE}/production/tasks/${taskId}/milestones`);
  if (!resp.ok) {
    throw new Error(`Failed to load milestones: ${resp.status}`);
  }
  return resp.json();
}

export async function assignFactoryToTask(
  taskId: string,
  factoryId: string
): Promise<FulfillmentTaskItem> {
  const resp = await fetch(`${API_BASE}/production/tasks/${taskId}/assign-factory`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ factory_id: factoryId }),
  });
  if (!resp.ok) {
    throw new Error(`Failed to assign factory: ${resp.status}`);
  }
  return resp.json();
}

export async function updateMilestone(
  milestoneId: string,
  payload: {
    status?: FulfillmentStatus;
    planned_date?: string;
    actual_date?: string;
    responsible_party?: string;
    note?: string;
    proof_url?: string;
  }
): Promise<FulfillmentMilestoneItem> {
  const resp = await fetch(`${API_BASE}/production/milestones/${milestoneId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(`Failed to update milestone: ${resp.status}`);
  }
  return resp.json();
}

export async function scanDelayRisks(autoMark = true): Promise<DelayRiskReport> {
  const resp = await fetch(`${API_BASE}/production/delay-risks/scan?auto_mark=${String(autoMark)}`, {
    method: "POST",
  });
  if (!resp.ok) {
    throw new Error(`Failed to scan delay risks: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchSampleRequests(status?: string, search?: string): Promise<SampleRequestRecord[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (search) params.set("search", search);
  const query = params.toString() ? `?${params.toString()}` : "";
  const resp = await fetch(`${API_BASE}/production/samples${query}`);
  if (!resp.ok) {
    throw new Error(`Failed to load sample requests: ${resp.status}`);
  }
  return resp.json();
}

export async function createSampleRequest(payload: {
  customer_id: string;
  factory_id: string;
  categories: Array<{ category_name: string; quantity: number }>;
  note?: string;
}): Promise<SampleRequestRecord> {
  const resp = await fetch(`${API_BASE}/production/samples`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(`Failed to create sample request: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchSampleItems(sampleId: string): Promise<SampleRequestItem[]> {
  const resp = await fetch(`${API_BASE}/production/samples/${sampleId}/items`);
  if (!resp.ok) {
    throw new Error(`Failed to load sample items: ${resp.status}`);
  }
  return resp.json();
}

export async function updateSampleRequest(
  sampleId: string,
  payload: {
    status?: SampleRequestStatus;
    feedback?: string;
    decision?: SampleDecision;
    note?: string;
  }
): Promise<SampleRequestRecord> {
  const resp = await fetch(`${API_BASE}/production/samples/${sampleId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(`Failed to update sample request: ${resp.status}`);
  }
  return resp.json();
}

export async function updateSampleItem(
  itemId: string,
  payload: {
    status?: SampleItemStatus;
    tracking_no?: string;
    note?: string;
  }
): Promise<SampleRequestItem> {
  const resp = await fetch(`${API_BASE}/production/sample-items/${itemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(`Failed to update sample item: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchSampleOrderSuggestions(sampleId: string): Promise<SampleOrderSuggestionResponse> {
  const resp = await fetch(`${API_BASE}/production/samples/${sampleId}/order-suggestions`);
  if (!resp.ok) {
    throw new Error(`Failed to load sample order suggestions: ${resp.status}`);
  }
  return resp.json();
}

export async function convertSampleToOrders(sampleId: string): Promise<SampleOrderConversionResponse> {
  const resp = await fetch(`${API_BASE}/production/samples/${sampleId}/convert-to-orders`, {
    method: "POST",
  });
  if (!resp.ok) {
    throw new Error(`Failed to convert sample to draft orders: ${resp.status}`);
  }
  return resp.json();
}
