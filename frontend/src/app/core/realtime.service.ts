import { Injectable, signal } from '@angular/core';
import { Alert, LiveShipment } from './models';

const WS_URL = 'ws://localhost:8000/ws/shipments';
const FLUSH_MS = 400;
const RECONNECT_MS = 2000;
const MAX_ALERTS = 60;

/**
 * Holds the live view of the fleet.
 *
 * The backend pushes roughly one message per shipment every two seconds —
 * around 50/second with a full fleet moving. Writing to a signal on every
 * message would ask Angular to run change detection 50 times a second for
 * updates the eye cannot resolve. Instead messages land in a plain Map and
 * a timer publishes the whole Map a few times a second. The data stays
 * current; the rendering stays calm.
 */
@Injectable({ providedIn: 'root' })
export class RealtimeService {
  readonly connected = signal(false);
  readonly shipments = signal<Map<string, LiveShipment>>(new Map());
  readonly alerts = signal<Alert[]>([]);
  readonly messageCount = signal(0);

  private buffer = new Map<string, LiveShipment>();
  private dirty = false;
  private socket?: WebSocket;
  private flushTimer?: number;
  private retryTimer?: number;

  start(): void {
    if (this.socket) return;
    this.open();
    this.flushTimer = window.setInterval(() => this.flush(), FLUSH_MS);
  }

  stop(): void {
    clearInterval(this.flushTimer);
    clearTimeout(this.retryTimer);
    this.socket?.close();
    this.socket = undefined;
  }

  private open(): void {
    const ws = new WebSocket(WS_URL);
    this.socket = ws;

    ws.onopen = () => this.connected.set(true);

    ws.onmessage = (e) => {
      this.messageCount.update((n) => n + 1);
      let msg: any;
      try { msg = JSON.parse(e.data); } catch { return; }
      this.handle(msg);
    };

    ws.onclose = () => {
      this.connected.set(false);
      this.socket = undefined;
      // The server restarting mid-session is normal in development, and a
      // dashboard that silently stops updating is worse than one that says
      // it is offline. Retry until it comes back.
      this.retryTimer = window.setTimeout(() => this.open(), RECONNECT_MS);
    };

    ws.onerror = () => ws.close();
  }

  private handle(msg: any): void {
    switch (msg.type) {
      case 'SNAPSHOT':
        // Sent on connect so a tab joining mid-stream isn't staring at an
        // empty chart until the next event happens to arrive.
        for (const s of msg.shipments ?? []) {
          if (s?.shipment_number) this.buffer.set(s.shipment_number, s);
        }
        this.dirty = true;
        break;

      case 'SHIPMENT_UPDATED': {
        const prev = this.buffer.get(msg.shipment_number);
        this.buffer.set(msg.shipment_number, { ...prev, ...msg } as LiveShipment);
        this.dirty = true;
        break;
      }

      case 'ALERT_CREATED':
        this.alerts.update((list) =>
          [msg as Alert, ...list.filter((a) => a.id !== msg.id)].slice(0, MAX_ALERTS)
        );
        break;

      case 'ALERT_RESOLVED':
        this.alerts.update((list) =>
          msg.id
            ? list.filter((a) => a.id !== msg.id)
            : list.filter(
                (a) =>
                  !(a.shipment_number === msg.shipment_number &&
                    a.alert_type === msg.alert_type)
              )
        );
        break;
    }
  }

  private flush(): void {
    if (!this.dirty) return;
    this.dirty = false;
    this.shipments.set(new Map(this.buffer));
  }

  /** Seed the alert list from REST so the panel isn't empty on first load. */
  seedAlerts(alerts: Alert[]): void {
    this.alerts.set(alerts.slice(0, MAX_ALERTS));
  }
}
