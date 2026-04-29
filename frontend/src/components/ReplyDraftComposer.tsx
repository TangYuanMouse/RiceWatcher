import { useEffect, useMemo, useState } from "react";

import {
  approveReplyDraft,
  fetchCustomers,
  fetchOrders,
  fetchReplyDrafts,
  fetchReviewQueue,
  generateReplyDraft,
  rejectReplyDraft,
  resolveReviewQueueItem,
  sendApprovedDraft,
  submitReplyDraft,
  updateReplyDraft,
} from "../api/client";
import type {
  Customer,
  OrderRecord,
  ReplyDraftRecord,
  ReplyDraftResponse,
  ReviewQueueItem,
} from "../types";

export default function ReplyDraftComposer() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [orders, setOrders] = useState<OrderRecord[]>([]);
  const [drafts, setDrafts] = useState<ReplyDraftRecord[]>([]);
  const [reviewQueue, setReviewQueue] = useState<ReviewQueueItem[]>([]);
  const [customerId, setCustomerId] = useState("");
  const [tone, setTone] = useState("professional");
  const [language, setLanguage] = useState("en");
  const [instruction, setInstruction] = useState("");
  const [draft, setDraft] = useState<ReplyDraftResponse | null>(null);
  const [currentDraft, setCurrentDraft] = useState<ReplyDraftRecord | null>(null);
  const [editableSubject, setEditableSubject] = useState("");
  const [editableBody, setEditableBody] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [busyAction, setBusyAction] = useState("");

  async function reloadDrafts(targetCustomerId?: string) {
    const rows = await fetchReplyDrafts({ customer_id: targetCustomerId || customerId });
    setDrafts(rows);
  }

  async function reloadReviewQueue() {
    const rows = await fetchReviewQueue("pending");
    setReviewQueue(rows);
  }

  useEffect(() => {
    fetchCustomers()
      .then((rows) => {
        setCustomers(rows);
        if (rows.length > 0) {
          setCustomerId(rows[0].id);
        }
      })
      .catch(console.error);

    reloadReviewQueue().catch(console.error);
  }, []);

  useEffect(() => {
    if (!customerId) {
      setOrders([]);
      setDrafts([]);
      return;
    }
    fetchOrders(customerId).then(setOrders).catch(console.error);
    reloadDrafts(customerId).catch(console.error);
  }, [customerId]);

  useEffect(() => {
    if (!currentDraft) {
      return;
    }
    setEditableSubject(currentDraft.subject);
    setEditableBody(currentDraft.body);
  }, [currentDraft]);

  const canGenerate = useMemo(() => customerId.trim().length > 0 && !loading, [customerId, loading]);

  async function onGenerate() {
    if (!canGenerate) return;
    setLoading(true);
    try {
      const next = await generateReplyDraft({
        customer_id: customerId,
        tone,
        language,
        additional_instruction: instruction || undefined,
      });
      setDraft(next);
      await reloadDrafts(customerId);
      if (next.draft_id) {
        const latest = await fetchReplyDrafts({ customer_id: customerId });
        const found = latest.find((x) => x.id === next.draft_id) || null;
        setCurrentDraft(found);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function runAction(action: string, fn: () => Promise<void>) {
    setBusyAction(action);
    try {
      await fn();
      await reloadDrafts(customerId);
    } catch (err) {
      console.error(err);
    } finally {
      setBusyAction("");
    }
  }

  const selectedDraft = useMemo(() => {
    if (!currentDraft) {
      return null;
    }
    return drafts.find((x) => x.id === currentDraft.id) || currentDraft;
  }, [currentDraft, drafts]);

  useEffect(() => {
    if (!selectedDraft) {
      return;
    }
    setEditableSubject(selectedDraft.subject);
    setEditableBody(selectedDraft.body);
  }, [selectedDraft?.id]);

  return (
    <section className="panel">
      <h2>Reply Draft Assistant</h2>

      <div className="form-grid">
        <label>
          Customer
          <select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.stage})
              </option>
            ))}
          </select>
        </label>

        <div className="split-grid">
          <label>
            Tone
            <select value={tone} onChange={(e) => setTone(e.target.value)}>
              <option value="professional">professional</option>
              <option value="friendly">friendly</option>
              <option value="firm">firm</option>
            </select>
          </label>

          <label>
            Language
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="en">English</option>
              <option value="zh">Chinese</option>
            </select>
          </label>
        </div>

        <label>
          Additional instruction
          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            rows={2}
            placeholder="e.g. emphasize MOQ and lead time options"
          />
        </label>

        <button className="btn-primary" onClick={onGenerate} disabled={!canGenerate}>
          {loading ? "Generating..." : "Generate Reply Draft"}
        </button>
      </div>

      <div className="hint">Linked orders for selected customer: {orders.length}</div>

      {draft && (
        <div className="draft-card">
          <h3>Generated Draft</h3>
          <p>{draft.subject}</p>
          <pre className="draft-pre">{draft.body}</pre>

          <h3>Context used</h3>
          <ul>
            {draft.context_used.map((line, idx) => (
              <li key={`${idx}-${line}`}>{line}</li>
            ))}
          </ul>

          <h3>Suggestions</h3>
          <ul>
            {draft.suggestions.map((line, idx) => (
              <li key={`${idx}-${line}`}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="draft-list-wrap">
        <h3>Draft Approval Queue</h3>
        <div className="draft-list">
          {drafts.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`draft-pill ${selectedDraft?.id === item.id ? "active" : ""}`}
              onClick={() => setCurrentDraft(item)}
            >
              <span>{item.subject}</span>
              <em>{item.status}</em>
            </button>
          ))}
          {drafts.length === 0 && <div className="hint">No drafts yet.</div>}
        </div>
      </div>

      {selectedDraft && (
        <div className="draft-card">
          <h3>Edit & Approval</h3>
          <div className="form-grid">
            <label>
              Subject
              <input
                value={editableSubject}
                onChange={(e) => setEditableSubject(e.target.value)}
              />
            </label>
            <label>
              Body
              <textarea value={editableBody} rows={8} onChange={(e) => setEditableBody(e.target.value)} />
            </label>
            <div className="draft-actions">
              <button
                className="btn-primary"
                disabled={busyAction.length > 0}
                onClick={() =>
                  runAction("save", async () => {
                    const updated = await updateReplyDraft(selectedDraft.id, {
                      subject: editableSubject,
                      body: editableBody,
                    });
                    setCurrentDraft(updated);
                  })
                }
              >
                {busyAction === "save" ? "Saving..." : "Save Draft"}
              </button>
              <button
                className="btn-primary"
                disabled={busyAction.length > 0}
                onClick={() =>
                  runAction("submit", async () => {
                    const updated = await submitReplyDraft(selectedDraft.id);
                    setCurrentDraft(updated);
                  })
                }
              >
                {busyAction === "submit" ? "Submitting..." : "Submit Approval"}
              </button>
              <button
                className="btn-primary"
                disabled={busyAction.length > 0}
                onClick={() =>
                  runAction("approve", async () => {
                    const updated = await approveReplyDraft(selectedDraft.id);
                    setCurrentDraft(updated);
                  })
                }
              >
                {busyAction === "approve" ? "Approving..." : "Approve"}
              </button>
              <button
                className="btn-primary"
                disabled={busyAction.length > 0 || rejectReason.trim().length === 0}
                onClick={() =>
                  runAction("reject", async () => {
                    const updated = await rejectReplyDraft(selectedDraft.id, rejectReason);
                    setCurrentDraft(updated);
                    setRejectReason("");
                  })
                }
              >
                {busyAction === "reject" ? "Rejecting..." : "Reject"}
              </button>
              <button
                className="btn-primary"
                disabled={busyAction.length > 0 || selectedDraft.status !== "approved"}
                onClick={() =>
                  runAction("send", async () => {
                    const updated = await sendApprovedDraft(selectedDraft.id);
                    setCurrentDraft(updated);
                  })
                }
              >
                {busyAction === "send" ? "Sending..." : "Send Approved"}
              </button>
            </div>

            <label>
              Rejection reason
              <input
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Required when rejecting"
              />
            </label>

            <div className="hint">
              Status: {selectedDraft.status} | Recipient: {selectedDraft.recipient || "missing"}
            </div>
          </div>
        </div>
      )}

      <div className="draft-card">
        <h3>Manual Review Queue</h3>
        <div className="review-list">
          {reviewQueue.map((item) => (
            <div key={item.id} className="review-item">
              <strong>
                {item.intent} | {item.customer_id} | UID {item.uid}
              </strong>
              <div className="hint">
                classification={item.classification_confidence.toFixed(2)} extraction={item.extraction_confidence.toFixed(2)}
              </div>
              <div className="draft-actions">
                <button
                  className="btn-primary"
                  onClick={() =>
                    runAction("review-approve", async () => {
                      await resolveReviewQueueItem(item.id, "approved", "Manually approved");
                      await reloadReviewQueue();
                    })
                  }
                >
                  Approve Item
                </button>
                <button
                  className="btn-primary"
                  onClick={() =>
                    runAction("review-reject", async () => {
                      await resolveReviewQueueItem(item.id, "rejected", "Manually rejected");
                      await reloadReviewQueue();
                    })
                  }
                >
                  Reject Item
                </button>
              </div>
            </div>
          ))}
          {reviewQueue.length === 0 && <div className="hint">No pending review items.</div>}
        </div>
      </div>
    </section>
  );
}
