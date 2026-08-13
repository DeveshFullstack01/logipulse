import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { Shipment } from '../../core/models';
import { TitleBlockComponent } from '../../shared/titleblock.component';

@Component({
  selector: 'lp-manifest',
  standalone: true,
  imports: [TitleBlockComponent, RouterLink],
  template: `
    <lp-titleblock />

    <div class="controls">
      <input
        class="search"
        placeholder="Search by number, origin or destination"
        (input)="onSearch($event)"
      />
      <div class="filters">
        @for (f of filters; track f) {
          <button [class.on]="status() === f" (click)="setStatus(f)">
            {{ f === '' ? 'All' : pretty(f) }}
          </button>
        }
      </div>
      <span class="total figure">{{ total() }} vessels</span>
    </div>

    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th>Number</th><th>Leg</th><th>Mode</th><th>State</th>
            <th class="r">Progress</th><th>Due</th><th>Cause</th>
          </tr>
        </thead>
        <tbody>
          @for (s of rows(); track s.shipment_number) {
            <tr [routerLink]="['/shipments', s.shipment_number]">
              <td class="figure num">{{ s.shipment_number }}</td>
              <td>{{ s.origin }} <span class="arrow">→</span> {{ s.destination }}</td>
              <td class="mode">{{ s.mode }}</td>
              <td><span class="state" [class]="s.status.toLowerCase()">{{ pretty(s.status) }}</span></td>
              <td class="r">
                <div class="prog"><div [style.width.%]="s.progress * 100"></div></div>
              </td>
              <td class="figure dim">{{ date(s.expected_delivery) }}</td>
              <td class="dim">{{ s.delay_reason ? pretty(s.delay_reason) : '—' }}</td>
            </tr>
          }
        </tbody>
      </table>
      @if (rows().length === 0) {
        <p class="empty">No vessels match that search. Try a port name or a shipment number.</p>
      }
    </div>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; height: 100vh; }
    .controls { display: flex; align-items: center; gap: 16px; padding: 11px 20px;
                background: var(--panel); border-bottom: 1px solid var(--rule); }
    .search { flex: 1; max-width: 340px; padding: 6px 9px; font-family: var(--sans);
              font-size: 12.5px; background: var(--chart); border: 1px solid var(--rule);
              color: var(--ink); }
    .filters { display: flex; gap: 6px; }
    .filters button { font-family: var(--cond); font-size: 10px; letter-spacing: .12em;
                      text-transform: uppercase; padding: 5px 9px; cursor: pointer;
                      background: none; border: 1px solid transparent; color: var(--ink-faint); }
    .filters button.on { border-color: var(--rule); background: var(--chart); color: var(--ink); }
    .total { margin-left: auto; font-size: 11px; color: var(--ink-faint); }

    .scroll { flex: 1; overflow-y: auto; }
    table { width: 100%; border-collapse: collapse; }
    th { text-align: left; font-family: var(--cond); font-size: 10px; letter-spacing: .16em;
         text-transform: uppercase; color: var(--ink-faint); font-weight: 500;
         padding: 9px 20px; border-bottom: 1px solid var(--rule);
         position: sticky; top: 0; background: var(--chart); }
    td { padding: 9px 20px; font-size: 12.5px; border-bottom: 1px solid var(--rule-soft); }
    tbody tr { cursor: pointer; }
    tbody tr:hover { background: var(--panel); }
    .num { color: var(--navy); }
    .arrow, .dim { color: var(--ink-faint); }
    .mode { font-family: var(--cond); font-size: 11px; letter-spacing: .1em; color: var(--ink-soft); }
    .r { text-align: right; }
    .state { font-family: var(--cond); font-size: 10.5px; letter-spacing: .1em;
             text-transform: uppercase; }
    .state.in_transit { color: var(--signal-green); }
    .state.delayed    { color: var(--signal-red); }
    .state.delivered, .state.created, .state.picked_up { color: var(--ink-faint); }
    .prog { width: 70px; height: 3px; background: var(--rule-soft); margin-left: auto; }
    .prog div { height: 100%; background: var(--navy); }
    .empty { padding: 40px 20px; color: var(--ink-faint); font-size: 13px; }
  `],
})
export class ManifestComponent {
  private api = inject(ApiService);
  filters = ['', 'IN_TRANSIT', 'DELAYED', 'DELIVERED'];

  rows = signal<Shipment[]>([]);
  total = signal(0);
  status = signal('');
  private term = '';
  private debounce?: number;

  constructor() { this.load(); }

  private load(): void {
    this.api
      .shipments({ status: this.status() || undefined, search: this.term || undefined })
      .subscribe((r) => { this.rows.set(r.shipments); this.total.set(r.total); });
  }

  setStatus(s: string): void { this.status.set(s); this.load(); }

  onSearch(e: Event): void {
    this.term = (e.target as HTMLInputElement).value;
    clearTimeout(this.debounce);
    // Firing a query on every keystroke would hammer the API for results
    // nobody reads; wait for a pause in typing.
    this.debounce = window.setTimeout(() => this.load(), 300);
  }

  pretty(s: string): string {
    return s.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase());
  }

  date(iso: string): string {
    return new Date(iso).toLocaleDateString([], { day: '2-digit', month: 'short' });
  }
}
