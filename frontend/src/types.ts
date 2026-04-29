export type StreamType = "lifecycle" | "assistant" | "tool";

export interface RunAccepted {
  run_id: string;
  status: "accepted" | "running" | "done" | "error";
  accepted_at: string;
}

export interface RunEvent {
  run_id: string;
  stream: StreamType;
  phase?: string;
  content?: string;
  tool_name?: string;
  created_at: string;
}

export interface Customer {
  id: string;
  name: string;
  country: string;
  stage: string;
  tags: string[];
}

export interface TimelineEvent {
  id: string;
  customer_id: string;
  timestamp: string;
  source: "email" | "manual" | "agent" | "order";
  title: string;
  summary: string;
}

export interface OrderRecord {
  id: string;
  customer_id: string;
  product_name: string;
  quantity: number;
  unit_price: number | null;
  currency: string;
  total_amount: number | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ReplyDraftResponse {
  draft_id?: string | null;
  subject: string;
  body: string;
  context_used: string[];
  suggestions: string[];
}

export interface ReplyDraftRecord {
  id: string;
  customer_id: string;
  mailbox: string;
  recipient: string | null;
  subject: string;
  body: string;
  status: "draft" | "pending_approval" | "approved" | "rejected" | "sent";
  created_at: string;
  updated_at: string;
  approved_by: string | null;
  approved_at: string | null;
  sent_at: string | null;
  rejection_reason: string | null;
}

export interface ReviewQueueItem {
  id: string;
  mailbox: string;
  uid: string;
  customer_id: string;
  intent: string;
  classification_confidence: number;
  extraction_confidence: number;
  reasons: string[];
  status: "pending" | "approved" | "rejected";
  created_at: string;
  resolved_at: string | null;
  resolver: string | null;
  note: string | null;
}

export interface ProductionRescheduleResponse {
  updated: ProductionScheduleItem;
  conflicts: Array<{
    id: string;
    order_id: string;
    customer_name: string;
    planned_start: string;
    planned_end: string;
    line_name: string;
  }>;
}

export interface ProductionScheduleItem {
  id: string;
  order_id: string;
  customer_id: string;
  customer_name: string;
  product_name: string;
  quantity: number;
  order_status: string;
  line_name: string;
  planned_start: string;
  planned_end: string;
  status: string;
  progress: number;
}

export interface FactoryRecord {
  id: string;
  name: string;
  country: string;
  contact_person: string | null;
  contact_email: string | null;
  tags: string[];
}

export type FulfillmentStatus = "planned" | "in_progress" | "done" | "delayed" | "blocked";

export interface FulfillmentTaskItem {
  id: string;
  order_id: string;
  customer_id: string;
  customer_name: string;
  product_name: string;
  quantity: number;
  order_status: string;
  factory_id: string;
  factory_name: string;
  status: FulfillmentStatus;
  planned_start: string;
  planned_end: string;
  actual_end: string | null;
}

export interface FulfillmentMilestoneItem {
  id: string;
  task_id: string;
  milestone_name: string;
  sequence: number;
  status: FulfillmentStatus;
  planned_date: string;
  actual_date: string | null;
  responsible_party: string | null;
  note: string | null;
  proof_url: string | null;
}

export interface DelayRiskItem {
  milestone_id: string;
  task_id: string;
  order_id: string;
  customer_name: string;
  factory_name: string;
  milestone_name: string;
  planned_date: string;
  status: FulfillmentStatus;
  overdue_days: number;
  risk_level: "low" | "medium" | "high";
  reminder: string;
}

export interface DelayRiskReport {
  scanned: number;
  at_risk: number;
  auto_marked: number;
  items: DelayRiskItem[];
}

export type SampleRequestStatus =
  | "requested"
  | "making"
  | "shipped"
  | "received"
  | "feedback_received"
  | "converted_to_order"
  | "closed_no_order";
export type SampleItemStatus = "requested" | "making" | "shipped" | "received";
export type SampleDecision = "pending" | "order" | "no_order";

export interface SampleRequestRecord {
  id: string;
  customer_id: string;
  customer_name: string;
  factory_id: string;
  factory_name: string;
  status: SampleRequestStatus;
  feedback: string | null;
  decision: SampleDecision;
  note: string | null;
  created_at: string;
  updated_at: string;
  item_count: number;
}

export interface SampleRequestItem {
  id: string;
  sample_request_id: string;
  category_name: string;
  quantity: number;
  status: SampleItemStatus;
  tracking_no: string | null;
  note: string | null;
}

export interface SampleOrderSuggestionItem {
  sample_item_id: string;
  category_name: string;
  suggested_product_name: string;
  suggested_quantity: number;
  suggested_status: "待确认";
  reason: string;
}

export interface SampleOrderSuggestionResponse {
  sample_request_id: string;
  decision: SampleDecision;
  suggestions: SampleOrderSuggestionItem[];
}

export interface SampleOrderConversionResponse {
  sample_request_id: string;
  created_order_ids: string[];
  existing_order_ids: string[];
}
