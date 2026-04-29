import { useEffect, useState } from "react";

import RunConsole from "./components/RunConsole";
import CustomerTimeline from "./components/CustomerTimeline";
import ReplyDraftComposer from "./components/ReplyDraftComposer";
import ProductionScheduleBoard from "./components/ProductionScheduleBoard";

interface LLMStatus {
  provider: string;
  base_url: string;
  model_name: string;
  enabled: boolean;
  configured: boolean;
}

export default function App() {
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/v1/gateway/config/llm")
      .then((r) => r.json())
      .then(setLlmStatus)
      .catch(() => setLlmStatus(null));
  }, []);

  return (
    <main className="app-shell">
      <header className="hero">
        <h1>RiceWatcher Agent Console</h1>
        <p>OpenClaw-style gateway architecture for foreign-trade workflows.</p>
      </header>

      <section className="status-grid">
        <article className="status-card">
          <h3>LLM Provider</h3>
          <p>provider: {llmStatus?.provider || "N/A"}</p>
          <p>base_url: {llmStatus?.base_url || "N/A"}</p>
          <p>model: {llmStatus?.model_name || "N/A"}</p>
          <p>enabled: {String(llmStatus?.enabled ?? false)}</p>
          <p>configured: {String(llmStatus?.configured ?? false)}</p>
        </article>

        <article className="status-card">
          <h3>MVP Scope</h3>
          <ul>
            <li>Single gateway source of truth</li>
            <li>Session lane serialization</li>
            <li>SSE event streaming</li>
            <li>Customer timeline</li>
          </ul>
        </article>
      </section>

      <section className="layout-grid">
        <RunConsole />
        <CustomerTimeline />
        <ReplyDraftComposer />
        <ProductionScheduleBoard />
      </section>
    </main>
  );
}
