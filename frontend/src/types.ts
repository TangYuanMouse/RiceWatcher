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
