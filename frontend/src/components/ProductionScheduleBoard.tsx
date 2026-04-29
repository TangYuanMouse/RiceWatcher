import { useEffect, useState } from "react";

import {
  assignFactoryToTask,
  createSampleRequest,
  convertSampleToOrders,
  fetchCustomers,
  fetchFactories,
  fetchFulfillmentTasks,
  fetchSampleOrderSuggestions,
  fetchSampleItems,
  fetchSampleRequests,
  fetchTaskMilestones,
  planProductionSchedule,
  scanDelayRisks,
  updateMilestone,
  updateSampleItem,
  updateSampleRequest,
} from "../api/client";
import type {
  Customer,
  DelayRiskReport,
  FactoryRecord,
  FulfillmentMilestoneItem,
  FulfillmentStatus,
  FulfillmentTaskItem,
  SampleItemStatus,
  SampleOrderSuggestionResponse,
  SampleRequestItem,
  SampleRequestRecord,
  SampleRequestStatus,
} from "../types";

type MilestoneDraft = {
  status: FulfillmentStatus;
  planned_date: string;
  actual_date: string;
  responsible_party: string;
  note: string;
  proof_url: string;
};

type SampleDraft = {
  status: SampleRequestStatus;
  decision: "pending" | "order" | "no_order";
  feedback: string;
  note: string;
};

type SampleItemDraft = {
  status: SampleItemStatus;
  tracking_no: string;
  note: string;
};

function toDateInput(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  return value.slice(0, 10);
}

function toIsoFromDateInput(value: string): string | undefined {
  if (!value) {
    return undefined;
  }
  return new Date(`${value}T00:00:00Z`).toISOString();
}

function parseCategoryInput(raw: string): Array<{ category_name: string; quantity: number }> {
  return raw
    .split(",")
    .map((x) => x.trim())
    .filter((x) => x.length > 0)
    .map((item) => {
      const [namePart, qtyPart] = item.split(":").map((x) => x.trim());
      const qty = Number.parseInt(qtyPart || "1", 10);
      return {
        category_name: namePart,
        quantity: Number.isNaN(qty) || qty <= 0 ? 1 : qty,
      };
    });
}

export default function ProductionScheduleBoard() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [factories, setFactories] = useState<FactoryRecord[]>([]);
  const [tasks, setTasks] = useState<FulfillmentTaskItem[]>([]);
  const [milestonesByTask, setMilestonesByTask] = useState<Record<string, FulfillmentMilestoneItem[]>>({});
  const [sampleRequests, setSampleRequests] = useState<SampleRequestRecord[]>([]);
  const [sampleItemsByRequest, setSampleItemsByRequest] = useState<Record<string, SampleRequestItem[]>>({});
  const [sampleOrderSuggestions, setSampleOrderSuggestions] = useState<Record<string, SampleOrderSuggestionResponse>>({});
  const [sampleOrderConversionMsg, setSampleOrderConversionMsg] = useState<Record<string, string>>({});
  const [milestoneDrafts, setMilestoneDrafts] = useState<Record<string, MilestoneDraft>>({});
  const [sampleDrafts, setSampleDrafts] = useState<Record<string, SampleDraft>>({});
  const [sampleItemDrafts, setSampleItemDrafts] = useState<Record<string, SampleItemDraft>>({});
  const [riskReport, setRiskReport] = useState<DelayRiskReport | null>(null);
  const [searchText, setSearchText] = useState("");

  const [newSampleCustomerId, setNewSampleCustomerId] = useState("");
  const [newSampleFactoryId, setNewSampleFactoryId] = useState("");
  const [newSampleCategories, setNewSampleCategories] = useState("Rice moisture sensor:2, Temperature probe:1");
  const [newSampleNote, setNewSampleNote] = useState("");

  const [loading, setLoading] = useState(false);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [busyMilestoneId, setBusyMilestoneId] = useState<string | null>(null);
  const [busySampleId, setBusySampleId] = useState<string | null>(null);
  const [busySampleItemId, setBusySampleItemId] = useState<string | null>(null);
  const [busySuggestionSampleId, setBusySuggestionSampleId] = useState<string | null>(null);
  const [busyConvertSampleId, setBusyConvertSampleId] = useState<string | null>(null);

  async function reload() {
    const [customerRows, factoryRows, taskRows, sampleRows] = await Promise.all([
      fetchCustomers(),
      fetchFactories(),
      fetchFulfillmentTasks(undefined, searchText || undefined),
      fetchSampleRequests(undefined, searchText || undefined),
    ]);
    setCustomers(customerRows);
    setFactories(factoryRows);
    setTasks(taskRows);
    setSampleRequests(sampleRows);

    if (!newSampleCustomerId && customerRows.length > 0) {
      setNewSampleCustomerId(customerRows[0].id);
    }
    if (!newSampleFactoryId && factoryRows.length > 0) {
      setNewSampleFactoryId(factoryRows[0].id);
    }

    const milestoneMap: Record<string, FulfillmentMilestoneItem[]> = {};
    const nextMilestoneDrafts: Record<string, MilestoneDraft> = {};
    const milestonePairs = await Promise.all(
      taskRows.map(async (task) => {
        const milestones = await fetchTaskMilestones(task.id);
        return [task.id, milestones] as const;
      })
    );
    for (const [taskId, rows] of milestonePairs) {
      milestoneMap[taskId] = rows;
      for (const ms of rows) {
        nextMilestoneDrafts[ms.id] = {
          status: ms.status,
          planned_date: toDateInput(ms.planned_date),
          actual_date: toDateInput(ms.actual_date),
          responsible_party: ms.responsible_party || "",
          note: ms.note || "",
          proof_url: ms.proof_url || "",
        };
      }
    }
    setMilestonesByTask(milestoneMap);
    setMilestoneDrafts(nextMilestoneDrafts);

    const itemMap: Record<string, SampleRequestItem[]> = {};
    const nextSampleDrafts: Record<string, SampleDraft> = {};
    const nextSampleItemDrafts: Record<string, SampleItemDraft> = {};
    const samplePairs = await Promise.all(
      sampleRows.map(async (sample) => {
        const items = await fetchSampleItems(sample.id);
        return [sample.id, items] as const;
      })
    );
    for (const [sampleId, items] of samplePairs) {
      itemMap[sampleId] = items;
      const sample = sampleRows.find((x) => x.id === sampleId);
      if (sample) {
        nextSampleDrafts[sample.id] = {
          status: sample.status,
          decision: sample.decision,
          feedback: sample.feedback || "",
          note: sample.note || "",
        };
      }
      for (const item of items) {
        nextSampleItemDrafts[item.id] = {
          status: item.status,
          tracking_no: item.tracking_no || "",
          note: item.note || "",
        };
      }
    }
    setSampleItemsByRequest(itemMap);
    setSampleDrafts(nextSampleDrafts);
    setSampleItemDrafts(nextSampleItemDrafts);
  }

  useEffect(() => {
    reload().catch(console.error);
  }, []);

  async function onPlan() {
    setLoading(true);
    try {
      await planProductionSchedule();
      await reload();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function onScanRisks() {
    try {
      const report = await scanDelayRisks(true);
      setRiskReport(report);
      await reload();
    } catch (err) {
      console.error(err);
    }
  }

  async function onAssignFactory(taskId: string, factoryId: string) {
    setBusyTaskId(taskId);
    try {
      await assignFactoryToTask(taskId, factoryId);
      await reload();
    } catch (err) {
      console.error(err);
    } finally {
      setBusyTaskId(null);
    }
  }

  async function onSaveMilestone(ms: FulfillmentMilestoneItem) {
    const draft = milestoneDrafts[ms.id];
    if (!draft) {
      return;
    }
    setBusyMilestoneId(ms.id);
    try {
      await updateMilestone(ms.id, {
        status: draft.status,
        planned_date: toIsoFromDateInput(draft.planned_date),
        actual_date: toIsoFromDateInput(draft.actual_date),
        responsible_party: draft.responsible_party,
        note: draft.note,
        proof_url: draft.proof_url,
      });
      await reload();
    } catch (err) {
      console.error(err);
    } finally {
      setBusyMilestoneId(null);
    }
  }

  async function onCreateSampleRequest() {
    const categories = parseCategoryInput(newSampleCategories);
    if (!newSampleCustomerId || !newSampleFactoryId || categories.length === 0) {
      return;
    }
    setBusySampleId("creating");
    try {
      await createSampleRequest({
        customer_id: newSampleCustomerId,
        factory_id: newSampleFactoryId,
        categories,
        note: newSampleNote || undefined,
      });
      setNewSampleNote("");
      await reload();
    } catch (err) {
      console.error(err);
    } finally {
      setBusySampleId(null);
    }
  }

  async function onSaveSample(sampleId: string) {
    const draft = sampleDrafts[sampleId];
    if (!draft) {
      return;
    }
    setBusySampleId(sampleId);
    try {
      await updateSampleRequest(sampleId, {
        status: draft.status,
        decision: draft.decision,
        feedback: draft.feedback,
        note: draft.note,
      });
      await reload();
    } catch (err) {
      console.error(err);
    } finally {
      setBusySampleId(null);
    }
  }

  async function onSaveSampleItem(itemId: string) {
    const draft = sampleItemDrafts[itemId];
    if (!draft) {
      return;
    }
    setBusySampleItemId(itemId);
    try {
      await updateSampleItem(itemId, {
        status: draft.status,
        tracking_no: draft.tracking_no,
        note: draft.note,
      });
      await reload();
    } catch (err) {
      console.error(err);
    } finally {
      setBusySampleItemId(null);
    }
  }

  async function onGenerateOrderSuggestions(sampleId: string) {
    setBusySuggestionSampleId(sampleId);
    try {
      const data = await fetchSampleOrderSuggestions(sampleId);
      setSampleOrderSuggestions((prev) => ({ ...prev, [sampleId]: data }));
    } catch (err) {
      console.error(err);
    } finally {
      setBusySuggestionSampleId(null);
    }
  }

  async function onConvertSampleToOrders(sampleId: string) {
    setBusyConvertSampleId(sampleId);
    try {
      const result = await convertSampleToOrders(sampleId);
      setSampleOrderConversionMsg((prev) => ({
        ...prev,
        [sampleId]: `created=${result.created_order_ids.join(",") || "none"} | existing=${result.existing_order_ids.join(",") || "none"}`,
      }));
      await reload();
    } catch (err) {
      console.error(err);
    } finally {
      setBusyConvertSampleId(null);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Factory Fulfillment Board</h2>
        <div className="draft-actions">
          <button className="btn-primary" onClick={onPlan} disabled={loading}>
            {loading ? "Planning..." : "Auto Plan Milestones"}
          </button>
          <button className="btn-primary" onClick={onScanRisks}>
            Scan Delay Risks
          </button>
        </div>
      </div>
      <div className="hint">Trade operators manually update factory progress milestones and sample flow records.</div>

      <div className="search-row">
        <input
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          placeholder="Search by order/customer/product/factory"
        />
        <button className="btn-primary" onClick={() => reload().catch(console.error)}>
          Search
        </button>
      </div>

      {riskReport && (
        <div className="draft-card">
          <h3>Delay Risk Agent</h3>
          <p>
            scanned={riskReport.scanned} | at_risk={riskReport.at_risk} | auto_marked={riskReport.auto_marked}
          </p>
          <ul>
            {riskReport.items.slice(0, 5).map((item) => (
              <li key={item.milestone_id}>
                [{item.risk_level}] {item.customer_name} - {item.milestone_name} ({item.factory_name})
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="schedule-list">
        <h3>Factory Fulfillment Tasks</h3>
        {tasks.length === 0 && <div className="hint">No fulfillment tasks yet. Click Auto Plan Milestones.</div>}
        {tasks.map((task) => (
          <div key={task.id} className="schedule-item">
            <div className="schedule-meta">
              <strong>
                {task.customer_name} | Order {task.order_id}
              </strong>
              <span>
                {task.product_name} x {task.quantity} | Task status {task.status}
              </span>
              <span>
                Planned {new Date(task.planned_start).toLocaleDateString()} - {new Date(task.planned_end).toLocaleDateString()}
              </span>
            </div>

            <label>
              Assigned Factory
              <select
                value={task.factory_id}
                onChange={(e) => onAssignFactory(task.id, e.target.value)}
                disabled={busyTaskId === task.id}
              >
                {factories.map((factory) => (
                  <option key={factory.id} value={factory.id}>
                    {factory.name} ({factory.country})
                  </option>
                ))}
              </select>
            </label>

            <div className="milestone-list">
              {(milestonesByTask[task.id] || []).map((ms) => {
                const draft = milestoneDrafts[ms.id];
                if (!draft) {
                  return null;
                }
                return (
                  <div key={ms.id} className="milestone-item">
                    <strong>
                      {ms.sequence}. {ms.milestone_name}
                    </strong>
                    <div className="split-grid">
                      <label>
                        Status
                        <select
                          value={draft.status}
                          onChange={(e) =>
                            setMilestoneDrafts((prev) => ({
                              ...prev,
                              [ms.id]: { ...prev[ms.id], status: e.target.value as FulfillmentStatus },
                            }))
                          }
                        >
                          <option value="planned">planned</option>
                          <option value="in_progress">in_progress</option>
                          <option value="done">done</option>
                          <option value="delayed">delayed</option>
                          <option value="blocked">blocked</option>
                        </select>
                      </label>
                      <label>
                        Owner
                        <input
                          value={draft.responsible_party}
                          onChange={(e) =>
                            setMilestoneDrafts((prev) => ({
                              ...prev,
                              [ms.id]: { ...prev[ms.id], responsible_party: e.target.value },
                            }))
                          }
                        />
                      </label>
                    </div>
                    <div className="split-grid">
                      <label>
                        Planned date
                        <input
                          type="date"
                          value={draft.planned_date}
                          onChange={(e) =>
                            setMilestoneDrafts((prev) => ({
                              ...prev,
                              [ms.id]: { ...prev[ms.id], planned_date: e.target.value },
                            }))
                          }
                        />
                      </label>
                      <label>
                        Actual date
                        <input
                          type="date"
                          value={draft.actual_date}
                          onChange={(e) =>
                            setMilestoneDrafts((prev) => ({
                              ...prev,
                              [ms.id]: { ...prev[ms.id], actual_date: e.target.value },
                            }))
                          }
                        />
                      </label>
                    </div>
                    <label>
                      Proof URL
                      <input
                        value={draft.proof_url}
                        onChange={(e) =>
                          setMilestoneDrafts((prev) => ({
                            ...prev,
                            [ms.id]: { ...prev[ms.id], proof_url: e.target.value },
                          }))
                        }
                      />
                    </label>
                    <label>
                      Note
                      <textarea
                        rows={2}
                        value={draft.note}
                        onChange={(e) =>
                          setMilestoneDrafts((prev) => ({
                            ...prev,
                            [ms.id]: { ...prev[ms.id], note: e.target.value },
                          }))
                        }
                      />
                    </label>
                    <button
                      className="btn-primary"
                      onClick={() => onSaveMilestone(ms)}
                      disabled={busyMilestoneId === ms.id}
                    >
                      {busyMilestoneId === ms.id ? "Saving..." : "Save Milestone"}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="draft-card">
        <h3>Sample Shipment Workflow</h3>
        <div className="form-grid">
          <label>
            Customer
            <select value={newSampleCustomerId} onChange={(e) => setNewSampleCustomerId(e.target.value)}>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Factory
            <select value={newSampleFactoryId} onChange={(e) => setNewSampleFactoryId(e.target.value)}>
              {factories.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Categories (name:qty, comma separated)
            <input value={newSampleCategories} onChange={(e) => setNewSampleCategories(e.target.value)} />
          </label>
          <label>
            Note
            <textarea rows={2} value={newSampleNote} onChange={(e) => setNewSampleNote(e.target.value)} />
          </label>
          <button className="btn-primary" onClick={onCreateSampleRequest} disabled={busySampleId === "creating"}>
            {busySampleId === "creating" ? "Creating..." : "Create Sample Request"}
          </button>
        </div>

        <div className="review-list">
          {sampleRequests.map((sr) => {
            const sampleDraft = sampleDrafts[sr.id];
            if (!sampleDraft) {
              return null;
            }
            return (
              <div key={sr.id} className="review-item">
                <strong>
                  {sr.id} | {sr.customer_name} -> {sr.factory_name}
                </strong>
                <div className="split-grid">
                  <label>
                    Request status
                    <select
                      value={sampleDraft.status}
                      onChange={(e) =>
                        setSampleDrafts((prev) => ({
                          ...prev,
                          [sr.id]: { ...prev[sr.id], status: e.target.value as SampleRequestStatus },
                        }))
                      }
                    >
                      <option value="requested">requested</option>
                      <option value="making">making</option>
                      <option value="shipped">shipped</option>
                      <option value="received">received</option>
                      <option value="feedback_received">feedback_received</option>
                      <option value="converted_to_order">converted_to_order</option>
                      <option value="closed_no_order">closed_no_order</option>
                    </select>
                  </label>
                  <label>
                    Customer decision
                    <select
                      value={sampleDraft.decision}
                      onChange={(e) =>
                        setSampleDrafts((prev) => ({
                          ...prev,
                          [sr.id]: { ...prev[sr.id], decision: e.target.value as "pending" | "order" | "no_order" },
                        }))
                      }
                    >
                      <option value="pending">pending</option>
                      <option value="order">order</option>
                      <option value="no_order">no_order</option>
                    </select>
                  </label>
                </div>
                <label>
                  Feedback
                  <textarea
                    rows={2}
                    value={sampleDraft.feedback}
                    onChange={(e) =>
                      setSampleDrafts((prev) => ({
                        ...prev,
                        [sr.id]: { ...prev[sr.id], feedback: e.target.value },
                      }))
                    }
                  />
                </label>
                <button className="btn-primary" onClick={() => onSaveSample(sr.id)} disabled={busySampleId === sr.id}>
                  {busySampleId === sr.id ? "Saving..." : "Save Sample Request"}
                </button>

                <div className="draft-actions">
                  <button
                    className="btn-primary"
                    onClick={() => onGenerateOrderSuggestions(sr.id)}
                    disabled={busySuggestionSampleId === sr.id}
                  >
                    {busySuggestionSampleId === sr.id ? "Generating..." : "Generate Order Suggestions"}
                  </button>
                  <button
                    className="btn-primary"
                    onClick={() => onConvertSampleToOrders(sr.id)}
                    disabled={busyConvertSampleId === sr.id}
                  >
                    {busyConvertSampleId === sr.id ? "Converting..." : "Create Draft Orders"}
                  </button>
                </div>

                {sampleOrderConversionMsg[sr.id] && <div className="hint">{sampleOrderConversionMsg[sr.id]}</div>}

                {sampleOrderSuggestions[sr.id] && (
                  <div className="milestone-item">
                    <strong>Order Draft Suggestions</strong>
                    <ul>
                      {sampleOrderSuggestions[sr.id].suggestions.map((s) => (
                        <li key={s.sample_item_id}>
                          {s.suggested_product_name} x {s.suggested_quantity} ({s.reason})
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="milestone-list">
                  {(sampleItemsByRequest[sr.id] || []).map((item) => {
                    const itemDraft = sampleItemDrafts[item.id];
                    if (!itemDraft) {
                      return null;
                    }
                    return (
                      <div key={item.id} className="milestone-item">
                        <strong>
                          {item.category_name} x {item.quantity}
                        </strong>
                        <div className="split-grid">
                          <label>
                            Item status
                            <select
                              value={itemDraft.status}
                              onChange={(e) =>
                                setSampleItemDrafts((prev) => ({
                                  ...prev,
                                  [item.id]: { ...prev[item.id], status: e.target.value as SampleItemStatus },
                                }))
                              }
                            >
                              <option value="requested">requested</option>
                              <option value="making">making</option>
                              <option value="shipped">shipped</option>
                              <option value="received">received</option>
                            </select>
                          </label>
                          <label>
                            Tracking no
                            <input
                              value={itemDraft.tracking_no}
                              onChange={(e) =>
                                setSampleItemDrafts((prev) => ({
                                  ...prev,
                                  [item.id]: { ...prev[item.id], tracking_no: e.target.value },
                                }))
                              }
                            />
                          </label>
                        </div>
                        <label>
                          Note
                          <input
                            value={itemDraft.note}
                            onChange={(e) =>
                              setSampleItemDrafts((prev) => ({
                                ...prev,
                                [item.id]: { ...prev[item.id], note: e.target.value },
                              }))
                            }
                          />
                        </label>
                        <button
                          className="btn-primary"
                          onClick={() => onSaveSampleItem(item.id)}
                          disabled={busySampleItemId === item.id}
                        >
                          {busySampleItemId === item.id ? "Saving..." : "Save Sample Item"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
          {sampleRequests.length === 0 && <div className="hint">No sample requests yet.</div>}
        </div>
      </div>
    </section>
  );
}
