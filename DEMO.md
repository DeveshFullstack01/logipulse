# Demo script — 3 minutes

Run `reset-demo.bat` first, then start the simulator and let it run for
90 seconds so vessels are mid-voyage rather than all sitting in port.

---

**0:00 — What it is**

> "LogiPulse is a control tower for a shipping fleet. Every vessel reports its
> position as an event; the screen you're looking at is that stream, live."

Point at the message counter climbing and vessels moving.

---

**0:25 — The architecture, on screen**

Switch to the Kafka console at localhost:8090 → Consumer Groups.

> "Two consumer groups read the same topic independently. One keeps current
> state in Redis, the other watches for delays. That's why Kafka rather than a
> queue — a queue would give each message to only one of them."

---

**0:50 — Make something go wrong**

Back to the dashboard. Click **Congest Singapore**.

> "That writes to a key the simulator reads on its next tick. Nothing here is
> mocked — the delay events go through Kafka, both workers pick them up, and
> the alerts come back over the WebSocket."

Wait for the alerts to arrive. Point out markers turning red.

---

**1:20 — Follow one vessel**

Click a red marker. The course plots as a dashed great circle.

> "Selecting a vessel draws its plotted course. Every position on that line
> came from an event."

Click through to the shipment detail page.

> "And this timeline is rebuilt from the event log, not from a status column.
> Because the log is append-only, the current state is derived — which means
> the history is always there."

---

**2:00 — Analysis**

Open the Analysis tab.

> "Delay causes and per-leg performance, aggregated from the same events."

---

**2:20 — What you'd ask next**

> "If a worker dies mid-batch, Kafka redelivers and the event_id unique index
> makes reprocessing a no-op. If Redis goes down, health reports degraded and
> the dashboard falls back to Postgres. The workers talk to the API over Redis
> pub/sub rather than directly, so multiple API replicas work unchanged."

Click **Restore calm** to close.
