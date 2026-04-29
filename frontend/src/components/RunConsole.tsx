import { useMemo, useState } from "react";

import { postMessage, streamRunEvents } from "../api/client";
import type { RunEvent } from "../types";

function colorByStream(stream: string): string {
  if (stream === "lifecycle") return "tag tag-life";
  if (stream === "tool") return "tag tag-tool";
  return "tag tag-assistant";
}

export default function RunConsole() {
  const [sessionKey, setSessionKey] = useState("customer:c001");
  const [text, setText] = useState("请给这个客户一份跟进建议");
  const [runId, setRunId] = useState("");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [loading, setLoading] = useState(false);

  const canSubmit = useMemo(
    () => sessionKey.trim().length > 0 && text.trim().length > 0 && !loading,
    [loading, sessionKey, text]
  );

  async function onSubmit() {
    if (!canSubmit) return;
    setLoading(true);
    setEvents([]);

    try {
      const accepted = await postMessage({
        session_key: sessionKey.trim(),
        text: text.trim(),
      });
      setRunId(accepted.run_id);

      const source = streamRunEvents(accepted.run_id, 0);
      source.onmessage = (evt) => {
        const parsed = JSON.parse(evt.data) as RunEvent;
        setEvents((prev) => [...prev, parsed]);

        if (parsed.stream === "lifecycle" && (parsed.phase === "end" || parsed.phase === "error")) {
          source.close();
          setLoading(false);
        }
      };

      source.onerror = () => {
        source.close();
        setLoading(false);
      };
    } catch (err) {
      console.error(err);
      setLoading(false);
    }
  }

  return (
    <section className="panel">
      <h2>Gateway Run Console</h2>

      <div className="form-grid">
        <label>
          Session Key
          <input
            value={sessionKey}
            onChange={(e) => setSessionKey(e.target.value)}
            placeholder="customer:c001"
          />
        </label>

        <label>
          Instruction
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            placeholder="Type your instruction"
          />
        </label>

        <button className="btn-primary" disabled={!canSubmit} onClick={onSubmit}>
          {loading ? "Running..." : "Run Agent"}
        </button>
      </div>

      <div className="run-meta">Run ID: {runId || "-"}</div>

      <ul className="event-list">
        {events.map((event, idx) => (
          <li key={`${event.created_at}-${idx}`} className="event-item">
            <span className={colorByStream(event.stream)}>{event.stream}</span>
            <span className="event-time">{new Date(event.created_at).toLocaleTimeString()}</span>
            <span className="event-content">
              {event.tool_name ? `[${event.tool_name}] ` : ""}
              {event.content || ""}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
