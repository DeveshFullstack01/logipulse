import { Component, inject, input, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { Shipment, TimelineEvent } from '../../core/models';
import { TitleBlockComponent } from '../../shared/titleblock.component';

@Component({
  selector: 'lp-shipment-detail',
  standalone: true,
  imports: [TitleBlockComponent],
  template: `
    <lp-titleblock />

    @if (ship(); as s) {
      <div class="page">
        <section class="head">
          <div>
            <span class="figure num">{{ s.shipment_number }}</span>
            <h2>{{ s.origin }} <span class="arrow">→</span> {{ s.destination }}</h2>
          </div>
          <span class="state" [class]="s.status.toLowerCase()">{{ pretty(s.status) }}</span>
        </section>

        <!-- Scale bar, after the distance scale printed along a chart's edge -->
        <section class="scale">
          <div class="bar"><div class="run" [style.width.%]="s.progress * 100"></div></div>
          <div class="ticks">
            <span class="figure">{{ s.origin }} · 0 km</span>
            <span class="figure mid">{{ round(s.distance_km * s.progress) }} km run</span>
            <span class="figure">{{ round(s.distance_km) }} km · {{ s.destination }}</span>
          </div>
        </section>

        <section class="facts">
          @for (f of facts(); track f.k) {
            <div class="fact">
              <span class="label">{{ f.k }}</span>
              <span class="v" [class.late]="f.late">{{ f.v }}</span>
            </div>
          }
        </section>

        <section class="timeline">
          <h3 class="label">Log</h3>
          <p class="note">
            Every entry below was reconstructed from the event log, not from the
            vessel's current record. This is what storing events rather than
            only state makes possible.
          </p>
          <ol>
            @for (e of events(); track e.event_id) {
              <li>
                <span class="time figure">{{ time(e.occurred_at) }}</span>
                <span class="dot" [class]="dotClass(e.event_type)"></span>
                <span class="what">
                  {{ label(e.event_type) }}
                  @if (e.latitude != null) {
                    <span class="pos figure">
                      {{ e.latitude.toFixed(3) }}, {{ e.longitude!.toFixed(3) }}
                    </span>
                  }
                  @if (e.delay_reason) {
                    <span class="cause">{{ pretty(e.delay_reason) }}</span>
                  }
                </span>
              </li>
            }
          </ol>
          @if (events().length === 0) {
            <p class="note">No entries yet. Start the simulator to log this voyage.</p>
          }
        </section>
      </div>
    } @else {
      <p class="loading">Fetching vessel record…</p>
    }
  `,
  styles: [`
    :host { display: flex; flex-direction: column; height: 100vh; }
    .page { flex: 1; overflow-y: auto; padding: 22px 26px 50px; max-width: 880px; }
    .loading { padding: 30px 26px; color: var(--ink-faint); }

    .head { display: flex; justify-content: space-between; align-items: flex-start; }
    .num { font-size: 12px; color: var(--ink-faint); letter-spacing: .04em; }
    h2 { margin: 4px 0 0; font-family: var(--cond); font-size: 26px; font-weight: 500; }
    .arrow { color: var(--ink-faint); }
    .state { font-family: var(--cond); font-size: 11px; letter-spacing: .16em;
             text-transform: uppercase; padding: 4px 10px; border: 1px solid currentColor; }
    .state.in_transit { color: var(--signal-green); }
    .state.delayed { color: var(--signal-red); }
    .state.delivered, .state.created, .state.picked_up { color: var(--ink-faint); }

    .scale { margin: 26px 0 22px; }
    .scale .bar { height: 5px; background: var(--rule-soft); }
    .scale .run { height: 100%; background: var(--navy); }
    .ticks { display: flex; justify-content: space-between; margin-top: 6px;
             font-size: 10.5px; color: var(--ink-faint); }
    .ticks .mid { color: var(--ink-soft); }

    .facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
             gap: 1px; background: var(--rule-soft); border: 1px solid var(--rule-soft); }
    .fact { background: var(--panel); padding: 11px 13px; display: flex;
            flex-direction: column; gap: 3px; }
    .fact .v { font-size: 13px; }
    .fact .v.late { color: var(--signal-red); }

    .timeline { margin-top: 32px; }
    .timeline h3 { margin: 0 0 6px; }
    .note { margin: 0 0 16px; font-size: 12px; color: var(--ink-faint);
            line-height: 1.55; max-width: 60ch; }
    ol { list-style: none; margin: 0; padding: 0; }
    li { display: grid; grid-template-columns: 62px 12px 1fr; gap: 10px;
         align-items: baseline; padding: 7px 0; border-bottom: 1px solid var(--rule-soft); }
    .time { font-size: 11px; color: var(--ink-faint); }
    .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ink-faint);
           transform: translateY(-1px); }
    .dot.go { background: var(--signal-green); }
    .dot.bad { background: var(--signal-red); }
    .dot.done { background: var(--navy); }
    .what { font-size: 12.5px; }
    .pos { color: var(--ink-faint); font-size: 11px; margin-left: 8px; }
    .cause { color: var(--signal-red); font-size: 11px; margin-left: 8px; }
  `],
})
export class ShipmentDetailComponent {
  /** Bound from the route via withComponentInputBinding(). */
  id = input.required<string>();

  private api = inject(ApiService);
  ship = signal<Shipment | null>(null);
  events = signal<TimelineEvent[]>([]);

  constructor() {
    queueMicrotask(() => {
      this.api.shipment(this.id()).subscribe((s) => this.ship.set(s));
      this.api.timeline(this.id()).subscribe((r) => this.events.set(r.events));
    });
  }

  facts() {
    const s = this.ship();
    if (!s) return [];
    const late =
      !!s.estimated_delivery &&
      new Date(s.estimated_delivery) > new Date(s.expected_delivery);
    return [
      { k: 'Mode', v: s.mode, late: false },
      { k: 'Distance', v: `${this.round(s.distance_km)} km`, late: false },
      { k: 'Promised', v: this.date(s.expected_delivery), late: false },
      { k: 'Now expected', v: s.estimated_delivery ? this.date(s.estimated_delivery) : '—', late },
      { k: 'Cause', v: s.delay_reason ? this.pretty(s.delay_reason) : '—', late: !!s.delay_reason },
    ];
  }

  label(t: string): string {
    const map: Record<string, string> = {
      SHIPMENT_CREATED: 'Booked',
      SHIPMENT_PICKED_UP: 'Collected',
      SHIPMENT_DEPARTED: 'Departed',
      SHIPMENT_LOCATION_UPDATED: 'Position reported',
      SHIPMENT_DELAYED: 'Running late',
      SHIPMENT_DELIVERED: 'Delivered',
    };
    return map[t] ?? this.pretty(t);
  }

  dotClass(t: string): string {
    if (t === 'SHIPMENT_DELAYED') return 'bad';
    if (t === 'SHIPMENT_DELIVERED') return 'done';
    if (t === 'SHIPMENT_DEPARTED' || t === 'SHIPMENT_PICKED_UP') return 'go';
    return '';
  }

  round(n: number): number { return Math.round(n); }

  pretty(s: string): string {
    return s.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase());
  }

  time(iso: string): string {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  date(iso: string): string {
    return new Date(iso).toLocaleString([], {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  }
}
