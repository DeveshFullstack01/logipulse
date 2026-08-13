import { Component, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { TitleBlockComponent } from '../../shared/titleblock.component';

interface Reason { reason: string; count: number; pct: number; }
interface RouteRow {
  route: string; shipments: number; delayed: number; on_time_pct: number;
}

@Component({
  selector: 'lp-analytics',
  standalone: true,
  imports: [TitleBlockComponent],
  template: `
    <lp-titleblock />

    <div class="page">
      <section class="block">
        <h3 class="label">Why vessels run late</h3>
        @if (reasons().length === 0) {
          <p class="empty">No delays recorded yet. Run the simulator, or inject
             conditions from the chart view.</p>
        }
        <ul class="bars">
          @for (r of reasons(); track r.reason) {
            <li>
              <span class="name">{{ r.reason }}</span>
              <span class="track">
                <span class="fill" [style.width.%]="scale(r.count)"></span>
              </span>
              <span class="figure val">{{ r.count }}</span>
              <span class="figure pct">{{ r.pct }}%</span>
            </li>
          }
        </ul>
      </section>

      <section class="block">
        <h3 class="label">Performance by leg</h3>
        <table>
          <thead>
            <tr><th>Leg</th><th class="r">Vessels</th><th class="r">Late</th>
                <th class="r">On time</th><th class="w">&nbsp;</th></tr>
          </thead>
          <tbody>
            @for (r of routes(); track r.route) {
              <tr>
                <td>{{ r.route }}</td>
                <td class="r figure">{{ r.shipments }}</td>
                <td class="r figure" [class.bad]="r.delayed > 0">{{ r.delayed }}</td>
                <td class="r figure">{{ r.on_time_pct }}%</td>
                <td class="w">
                  <span class="track thin">
                    <span class="fill"
                          [style.width.%]="r.on_time_pct"
                          [class.warn]="r.on_time_pct < 85"></span>
                  </span>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </section>

      <section class="block">
        <h3 class="label">Signals raised, last 7 days</h3>
        @if (days().length < 2) {
          <p class="empty">Not enough history yet — this fills in as the system runs.</p>
        } @else {
          <svg class="spark" [attr.viewBox]="'0 0 ' + w + ' ' + h" preserveAspectRatio="none">
            <polyline [attr.points]="linePoints()" fill="none"
                      stroke="var(--navy)" stroke-width="1.5" />
            <polygon [attr.points]="areaPoints()" fill="var(--navy)" opacity="0.08" />
          </svg>
          <div class="axis">
            @for (d of days(); track d.day) {
              <span class="figure">{{ shortDay(d.day) }}</span>
            }
          </div>
        }
      </section>
    </div>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; height: 100vh; }
    .page { flex: 1; overflow-y: auto; padding: 24px 26px 60px;
            display: grid; gap: 34px; max-width: 900px; }
    .block h3 { margin: 0 0 14px; }
    .empty { font-size: 12.5px; color: var(--ink-faint); line-height: 1.55; max-width: 58ch; }

    .bars { list-style: none; margin: 0; padding: 0; display: grid; gap: 9px; }
    .bars li { display: grid; grid-template-columns: 130px 1fr 42px 46px;
               gap: 12px; align-items: center; }
    .name { font-size: 12.5px; }
    .track { height: 9px; background: var(--rule-soft); display: block; }
    .track.thin { height: 4px; width: 90px; }
    .fill { display: block; height: 100%; background: var(--navy); }
    .fill.warn { background: var(--signal-amber); }
    .val { font-size: 12px; text-align: right; }
    .pct { font-size: 11px; color: var(--ink-faint); text-align: right; }

    table { width: 100%; border-collapse: collapse; }
    th { text-align: left; font-family: var(--cond); font-size: 10px; letter-spacing: .16em;
         text-transform: uppercase; color: var(--ink-faint); font-weight: 500;
         padding: 0 12px 7px 0; border-bottom: 1px solid var(--rule); }
    td { padding: 8px 12px 8px 0; font-size: 12.5px;
         border-bottom: 1px solid var(--rule-soft); }
    .r { text-align: right; }
    .w { width: 100px; }
    td.bad { color: var(--signal-red); }

    .spark { width: 100%; height: 90px; display: block;
             border-bottom: 1px solid var(--rule); }
    .axis { display: flex; justify-content: space-between; margin-top: 6px;
            font-size: 10px; color: var(--ink-faint); }
  `],
})
export class AnalyticsComponent {
  private api = inject(ApiService);

  reasons = signal<Reason[]>([]);
  routes = signal<RouteRow[]>([]);
  days = signal<{ day: string; alerts: number }[]>([]);

  readonly w = 600;
  readonly h = 90;

  constructor() {
    this.api.analytics().subscribe((a) => {
      this.reasons.set(a.delay_reasons ?? []);
      this.routes.set(a.routes ?? []);
      this.days.set(a.alerts_by_day ?? []);
    });
  }

  /** Bars are scaled against the largest value, not against 100, so the
   *  shape of the distribution stays readable when counts are small. */
  scale(count: number): number {
    const max = Math.max(...this.reasons().map((r) => r.count), 1);
    return (count / max) * 100;
  }

  private points(): [number, number][] {
    const d = this.days();
    const max = Math.max(...d.map((x) => x.alerts), 1);
    const step = d.length > 1 ? this.w / (d.length - 1) : this.w;
    return d.map((x, i) => [i * step, this.h - (x.alerts / max) * (this.h - 10)]);
  }

  linePoints(): string {
    return this.points().map(([x, y]) => `${x},${y}`).join(' ');
  }

  areaPoints(): string {
    const p = this.points();
    if (!p.length) return '';
    return `0,${this.h} ${this.linePoints()} ${p[p.length - 1][0]},${this.h}`;
  }

  shortDay(iso: string): string {
    return new Date(iso).toLocaleDateString([], { day: '2-digit', month: 'short' });
  }
}
