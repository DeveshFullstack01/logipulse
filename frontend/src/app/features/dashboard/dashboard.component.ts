import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { RealtimeService } from '../../core/realtime.service';
import { LiveShipment, Shipment, Summary } from '../../core/models';
import { AlertFeedComponent } from './alert-feed.component';
import { LiveMapComponent } from './live-map.component';

@Component({
  selector: 'lp-dashboard',
  standalone: true,
  imports: [LiveMapComponent, AlertFeedComponent],
  template: `
    <!-- Title block, after the cartouche printed in a chart's corner -->
    <header class="titleblock rule-double">
      <div class="mark">
        <h1>LogiPulse</h1>
        <span class="sub">Logistics Control Tower</span>
      </div>

      <div class="status">
        <span class="link" [class.on]="rt.connected()">
          <i></i>{{ rt.connected() ? 'Live feed' : 'Reconnecting' }}
        </span>
        <span class="rate figure">{{ rt.messageCount() }} msgs</span>
        <span class="clock figure">{{ clock() }}</span>
      </div>
    </header>

    <!-- Readings, set like a chart's depth legend: figure over label -->
    <section class="readings">
      @for (r of readings(); track r.label) {
        <div class="reading" [class.alarm]="r.alarm">
          <span class="value figure">{{ r.value }}</span>
          <span class="label">{{ r.label }}</span>
        </div>
      }
    </section>

    <main class="deck">
      <div class="chart">
        <lp-live-map [live]="rt.shipments()" (selected)="onSelect($event)" />
      </div>

      <aside class="side">
        @if (detail(); as d) {
          <div class="detail">
            <div class="detail-head">
              <span class="figure num">{{ d.shipment_number }}</span>
              <button class="close" (click)="detail.set(null)">Close</button>
            </div>
            <p class="leg">{{ d.origin }} <span class="arrow">→</span> {{ d.destination }}</p>

            <!-- Scale bar: distance run against distance to go -->
            <div class="scale">
              <div class="bar">
                <div class="run" [style.width.%]="pct(d)"></div>
              </div>
              <div class="scale-labels">
                <span class="figure">{{ km(d) }} km run</span>
                <span class="figure">{{ remaining(d) }} km to go</span>
              </div>
            </div>

            <dl class="facts">
              <dt class="label">State</dt><dd>{{ d.status }}</dd>
              <dt class="label">Mode</dt><dd>{{ d.mode }}</dd>
              <dt class="label">Due</dt><dd class="figure">{{ date(d.expected_delivery) }}</dd>
              @if (d.estimated_delivery) {
                <dt class="label">Now expected</dt>
                <dd class="figure">{{ date(d.estimated_delivery) }}</dd>
              }
              @if (d.delay_reason) {
                <dt class="label">Cause</dt><dd>{{ pretty(d.delay_reason) }}</dd>
              }
            </dl>
          </div>
        }
        <lp-alert-feed [alerts]="rt.alerts()" (pick)="onSelect($event)" />
      </aside>
    </main>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; height: 100vh; }

    .titleblock { display: flex; justify-content: space-between; align-items: flex-end;
                  padding: 14px 20px 12px; background: var(--panel); }
    .mark h1 { margin: 0; font-family: var(--cond); font-size: 21px; font-weight: 600;
               letter-spacing: .1em; text-transform: uppercase; }
    .sub { font-family: var(--cond); font-size: 10.5px; letter-spacing: .22em;
           text-transform: uppercase; color: var(--ink-faint); }
    .status { display: flex; gap: 20px; align-items: center; font-size: 11px;
              color: var(--ink-soft); }
    .link { display: flex; align-items: center; gap: 6px; font-family: var(--cond);
            letter-spacing: .12em; text-transform: uppercase; font-size: 10px; }
    .link i { width: 7px; height: 7px; border-radius: 50%; background: var(--signal-red); }
    .link.on i { background: var(--signal-green); }
    .rate, .clock { font-size: 11px; color: var(--ink-faint); }

    .readings { display: grid; grid-template-columns: repeat(6, 1fr);
                background: var(--panel); border-bottom: 1px solid var(--rule); }
    .reading { padding: 15px 20px; border-right: 1px solid var(--rule-soft);
               display: flex; flex-direction: column; gap: 3px; }
    .reading:last-child { border-right: 0; }
    .value { font-size: 25px; font-weight: 500; line-height: 1; }
    .reading.alarm .value { color: var(--signal-red); }

    .deck { flex: 1; display: grid; grid-template-columns: 1fr 340px; min-height: 0; }
    .chart { min-height: 0; }
    .side { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }

    .detail { background: var(--panel); border-left: 1px solid var(--rule);
              border-bottom: 1px solid var(--rule); padding: 14px 15px; }
    .detail-head { display: flex; justify-content: space-between; align-items: baseline; }
    .num { font-size: 14px; font-weight: 500; }
    .close { background: none; border: 0; cursor: pointer; font-family: var(--cond);
             font-size: 10px; letter-spacing: .12em; text-transform: uppercase;
             color: var(--ink-faint); }
    .leg { margin: 5px 0 12px; font-size: 13px; }
    .arrow { color: var(--ink-faint); }

    .scale .bar { height: 4px; background: var(--rule-soft); position: relative; }
    .scale .run { height: 100%; background: var(--navy); }
    .scale-labels { display: flex; justify-content: space-between; margin-top: 5px;
                    font-size: 10px; color: var(--ink-faint); }

    .facts { display: grid; grid-template-columns: auto 1fr; gap: 6px 14px;
             margin: 14px 0 0; align-items: baseline; }
    .facts dd { margin: 0; font-size: 12.5px; }

    @media (max-width: 900px) {
      .readings { grid-template-columns: repeat(3, 1fr); }
      .deck { grid-template-columns: 1fr; grid-template-rows: 55% 45%; }
    }
  `],
})
export class DashboardComponent implements OnInit, OnDestroy {
  rt = inject(RealtimeService);
  private api = inject(ApiService);

  summary = signal<Summary | null>(null);
  detail = signal<Shipment | null>(null);
  clock = signal(this.now());

  private timers: number[] = [];

  readings = computed(() => {
    const s = this.summary();
    const live = this.rt.shipments();
    const moving = [...live.values()].filter(
      (v: LiveShipment) => v.status === 'IN_TRANSIT'
    ).length;
    return [
      { label: 'In transit',   value: moving || s?.active || 0, alarm: false },
      { label: 'Delayed',      value: s?.delayed ?? 0,      alarm: (s?.delayed ?? 0) > 0 },
      { label: 'At risk',      value: s?.at_risk ?? 0,      alarm: false },
      { label: 'Delivered',    value: s?.delivered ?? 0,    alarm: false },
      { label: 'Open signals', value: this.rt.alerts().length, alarm: this.rt.alerts().length > 0 },
      { label: 'On time',      value: (s?.on_time_rate ?? 0) + '%', alarm: false },
    ];
  });

  ngOnInit(): void {
    this.rt.start();
    this.refresh();
    this.api.alerts().subscribe((r) => this.rt.seedAlerts(r.alerts));

    // Live positions arrive by socket; these aggregates are cheap SQL and
    // don't need to be pushed, so a slow poll keeps the API quiet.
    this.timers.push(window.setInterval(() => this.refresh(), 10_000));
    this.timers.push(window.setInterval(() => this.clock.set(this.now()), 1000));
  }

  ngOnDestroy(): void {
    this.timers.forEach(clearInterval);
    this.rt.stop();
  }

  private refresh(): void {
    this.api.summary().subscribe((s) => this.summary.set(s));
  }

  onSelect(number: string): void {
    this.api.shipment(number).subscribe((s) => this.detail.set(s));
  }

  pct(d: Shipment): number { return Math.round((d.progress ?? 0) * 100); }
  km(d: Shipment): number { return Math.round(d.distance_km * (d.progress ?? 0)); }
  remaining(d: Shipment): number { return Math.round(d.distance_km * (1 - (d.progress ?? 0))); }

  date(iso: string): string {
    return new Date(iso).toLocaleString([], {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  }

  pretty(s: string): string {
    return s.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase());
  }

  private now(): string {
    return new Date().toLocaleTimeString([], {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    }) + ' UTC' + (new Date().getTimezoneOffset() > 0 ? '' : '');
  }
}
