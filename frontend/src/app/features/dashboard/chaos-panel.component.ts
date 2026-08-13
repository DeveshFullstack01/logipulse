import { HttpClient } from '@angular/common/http';
import { Component, inject, input, signal } from '@angular/core';

const BASE = 'http://localhost:8000';

/**
 * Demo controls. Each button writes to a Redis key the simulator reads on
 * its next tick, so the consequences arrive through the real pipeline —
 * Kafka, both workers, Redis, WebSocket — a few seconds later. Nothing is
 * faked in the UI, which is rather the point.
 */
@Component({
  selector: 'lp-chaos',
  standalone: true,
  template: `
    <div class="panel">
      <span class="label">Inject conditions</span>
      <div class="buttons">
        <button (click)="port('Singapore')">Congest Singapore</button>
        <button (click)="port('Dubai')">Congest Dubai</button>
        <button (click)="storm()">Storm across fleet</button>
        @if (selected(); as s) {
          <button (click)="freeze(s)">Silence {{ s }}</button>
        }
        <button class="calm" (click)="clear()">Restore calm</button>
      </div>
      @if (note(); as n) { <span class="note">{{ n }}</span> }
    </div>
  `,
  styles: [`
    .panel { display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
             padding: 9px 20px; background: var(--panel);
             border-bottom: 1px solid var(--rule); }
    .buttons { display: flex; gap: 7px; flex-wrap: wrap; }
    button { font-family: var(--cond); font-size: 10px; letter-spacing: .12em;
             text-transform: uppercase; padding: 5px 10px; cursor: pointer;
             background: var(--chart); border: 1px solid var(--rule);
             color: var(--ink-soft); }
    button:hover { border-color: var(--signal-amber); color: var(--ink); }
    button.calm:hover { border-color: var(--signal-green); }
    .note { font-size: 11px; color: var(--ink-faint); font-style: italic; }
  `],
})
export class ChaosPanelComponent {
  selected = input<string | null>(null);
  private http = inject(HttpClient);
  note = signal<string | null>(null);

  private say(msg: string) {
    this.note.set(msg);
    setTimeout(() => this.note.set(null), 6000);
  }

  port(name: string) {
    this.http.post(`${BASE}/api/chaos/port/${name}`, {}).subscribe(() =>
      this.say(`${name} congested — watch for delays on those legs.`)
    );
  }

  storm() {
    this.http.post(`${BASE}/api/chaos/storm`, {}).subscribe(() =>
      this.say('Weather closing in across every route.')
    );
  }

  freeze(number: string) {
    this.http.post(`${BASE}/api/chaos/freeze/${number}`, {}).subscribe(() =>
      this.say(`${number} has stopped reporting. A stale signal follows shortly.`)
    );
  }

  clear() {
    this.http.delete(`${BASE}/api/chaos`).subscribe(() =>
      this.say('Conditions cleared. Vessels recover on their own.')
    );
  }
}
