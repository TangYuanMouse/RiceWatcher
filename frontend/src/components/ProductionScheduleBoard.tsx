import { type MouseEvent as ReactMouseEvent, useEffect, useMemo, useState } from "react";

import {
  fetchProductionSchedule,
  planProductionSchedule,
  rescheduleProductionItem,
} from "../api/client";
import type { ProductionScheduleItem } from "../types";

function toDate(value: string): Date {
  return new Date(value);
}

export default function ProductionScheduleBoard() {
  const [items, setItems] = useState<ProductionScheduleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [rescheduleBusyId, setRescheduleBusyId] = useState<string | null>(null);
  const [conflictText, setConflictText] = useState("");

  async function reload() {
    const rows = await fetchProductionSchedule();
    setItems(rows);
  }

  useEffect(() => {
    reload().catch(console.error);
  }, []);

  const minStart = useMemo(() => {
    if (items.length === 0) return null;
    return items
      .map((x) => toDate(x.planned_start).getTime())
      .reduce((a, b) => Math.min(a, b), Number.MAX_SAFE_INTEGER);
  }, [items]);

  const maxEnd = useMemo(() => {
    if (items.length === 0) return null;
    return items
      .map((x) => toDate(x.planned_end).getTime())
      .reduce((a, b) => Math.max(a, b), 0);
  }, [items]);

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

  function barStyle(item: ProductionScheduleItem): { left: string; width: string } {
    if (!minStart || !maxEnd || maxEnd <= minStart) return { left: "0%", width: "100%" };
    const start = toDate(item.planned_start).getTime();
    const end = toDate(item.planned_end).getTime();
    const total = maxEnd - minStart;
    const left = ((start - minStart) / total) * 100;
    const width = Math.max(8, ((end - start) / total) * 100);
    return { left: `${left}%`, width: `${width}%` };
  }

  function shiftDays(isoText: string, deltaDays: number): string {
    const next = new Date(isoText);
    next.setDate(next.getDate() + deltaDays);
    return next.toISOString();
  }

  function onBarMouseDown(event: ReactMouseEvent<HTMLDivElement>, item: ProductionScheduleItem) {
    event.preventDefault();
    const startX = event.clientX;
    setDraggingId(item.id);

    const handleMouseUp = async (upEvent: MouseEvent) => {
      window.removeEventListener("mouseup", handleMouseUp);
      const deltaX = upEvent.clientX - startX;
      const dayDelta = Math.round(deltaX / 36);
      setDraggingId(null);

      if (dayDelta === 0) {
        return;
      }

      setRescheduleBusyId(item.id);
      try {
        const payload = {
          line_name: item.line_name,
          planned_start: shiftDays(item.planned_start, dayDelta),
          planned_end: shiftDays(item.planned_end, dayDelta),
        };
        const result = await rescheduleProductionItem(item.id, payload);

        setItems((prev) => prev.map((x) => (x.id === item.id ? result.updated : x)));
        if (result.conflicts.length > 0) {
          const names = result.conflicts.map((x) => x.customer_name).join(", ");
          setConflictText(`Conflict on ${item.line_name}: overlaps with ${names}`);
        } else {
          setConflictText("No line conflicts after reschedule.");
        }
        await reload();
      } catch (err) {
        console.error(err);
      } finally {
        setRescheduleBusyId(null);
      }
    };

    window.addEventListener("mouseup", handleMouseUp);
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Production Scheduling</h2>
        <button className="btn-primary" onClick={onPlan} disabled={loading}>
          {loading ? "Planning..." : "Auto Plan"}
        </button>
      </div>
      <div className="hint">Drag a schedule bar horizontally to move it by days (about 36px per day).</div>
      {conflictText && <div className="hint schedule-conflict">{conflictText}</div>}

      <div className="schedule-list">
        {items.map((item) => (
          <div key={item.id} className="schedule-item">
            <div className="schedule-meta">
              <strong>{item.customer_name}</strong>
              <span>
                {item.product_name} x {item.quantity} ({item.line_name})
              </span>
              <span>
                {new Date(item.planned_start).toLocaleDateString()} - {new Date(item.planned_end).toLocaleDateString()}
              </span>
            </div>

            <div className="schedule-track">
              <div
                className={`schedule-bar ${draggingId === item.id ? "dragging" : ""}`}
                style={barStyle(item)}
                onMouseDown={(event) => onBarMouseDown(event, item)}
              >
                <span>{item.order_status}</span>
              </div>
            </div>

            {rescheduleBusyId === item.id && <div className="hint">Rescheduling...</div>}

            <div className="progress-wrap">
              <div className="progress-fill" style={{ width: `${item.progress}%` }} />
              <span>{item.progress}%</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
