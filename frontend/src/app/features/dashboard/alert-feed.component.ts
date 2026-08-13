import { Component, inject, input, output } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { Alert } from '../../core/models';

@Component({
  selector: 'lp-alert-feed',
  standalone: true,
  template: `
    <header class="head">
      <span class="label">Signals</span>
      <span class="count figure">{{ alerts().length }}</span>
    </header>

    @if (alerts().length === 0) {
      <p class="empty">No open signals. The fleet is proceeding as planned.</p>
    }

    <ul class="list">
      @for (a of alerts(); track a.id) {
        <li class="item" [class.high]="a.severity === 'HIGH'">
          <span class="flag" [class]="a.severity.toLowerCase()"></span>
          <div class="body">
            <button class="ship figure" (click)="pick.emit(a.shipment_number)">
              {{ a.shipment_number }}
            </button>
            <p class="msg">{{ a.message }}</p>
            <span class="meta">{{ a.alert_type }} · {{ time(a.created_at) }}</span>
          </div>
          <button class="clear" (click)="resolve(a)" title="Mark handled">Clear</button>
        </li>
      }
    </ul>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; height: 100%;
            background: var(--panel); border-left: 1px solid var(--rule); }
    .head { display: flex; justify-content: space-between; align-items: baseline;
            padding: 13px 15px; border-bottom: 1px solid var(--rule);
            box-shadow: 0 2px 0 -1px var(--rule-soft); }
    .count { font-size: 13px; color: var(--ink-soft); }
    .empty { margin: 22px 16px; font-size: 12.5px; color: var(--ink-faint);
             line-height: 1.55; }
    .list { list-style: none; margin: 0; padding: 0; overflow-y: auto; flex: 1; }
    .item { display: grid; grid-template-columns: 3px 1fr auto; gap: 11px;
            padding: 11px 15px 11px 12px; border-bottom: 1px solid var(--rule-soft);
            align-items: start; }
    .flag { width: 3px; align-self: stretch; }
    .flag.high   { background: var(--signal-red); }
    .flag.medium { background: var(--signal-amber); }
    .flag.low    { background: var(--ink-faint); }
    .ship { background: none; border: 0; padding: 0; cursor: pointer;
            font-size: 12px; font-weight: 500; color: var(--navy);
            letter-spacing: .01em; }
    .ship:hover { text-decoration: underline; }
    .msg { margin: 3px 0 4px; font-size: 12.5px; line-height: 1.4; }
    .meta { font-family: var(--cond); font-size: 10px; letter-spacing: .1em;
            text-transform: uppercase; color: var(--ink-faint); }
    .clear { align-self: center; background: none; border: 1px solid var(--rule);
             color: var(--ink-soft); font-family: var(--cond); font-size: 10px;
             letter-spacing: .12em; text-transform: uppercase; padding: 4px 8px;
             cursor: pointer; }
    .clear:hover { background: var(--chart); color: var(--ink); }
  `],
})
export class AlertFeedComponent {
  alerts = input.required<Alert[]>();
  pick = output<string>();
  private api = inject(ApiService);

  time(iso: string): string {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  resolve(a: Alert): void {
    // The worker broadcasts ALERT_RESOLVED, so the list updates itself
    // here and on every other open dashboard.
    this.api.resolveAlert(a.id).subscribe();
  }
}
