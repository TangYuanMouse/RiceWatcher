import { useEffect, useState } from "react";

import { fetchCustomers, fetchTimeline } from "../api/client";
import type { Customer, TimelineEvent } from "../types";

export default function CustomerTimeline() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState("");
  const [events, setEvents] = useState<TimelineEvent[]>([]);

  useEffect(() => {
    fetchCustomers().then(setCustomers).catch(console.error);
  }, []);

  useEffect(() => {
    fetchTimeline(selectedCustomer || undefined).then(setEvents).catch(console.error);
  }, [selectedCustomer]);

  return (
    <section className="panel">
      <h2>Customer Timeline</h2>

      <div className="toolbar">
        <label>
          Customer
          <select value={selectedCustomer} onChange={(e) => setSelectedCustomer(e.target.value)}>
            <option value="">All</option>
            {customers.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name} ({c.stage})
              </option>
            ))}
          </select>
        </label>
      </div>

      <ul className="timeline-list">
        {events.map((event) => (
          <li key={event.id} className="timeline-item">
            <div className="timeline-head">
              <strong>{event.title}</strong>
              <span>{new Date(event.timestamp).toLocaleString()}</span>
            </div>
            <div className="timeline-meta">{event.source} | customer: {event.customer_id}</div>
            <p>{event.summary}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
