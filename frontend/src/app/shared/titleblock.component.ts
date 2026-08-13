import { Component, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

/** The title block, after the cartouche printed in a chart's corner. */
@Component({
  selector: 'lp-titleblock',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  template: `
    <header class="titleblock rule-double">
      <div class="mark">
        <h1>LogiPulse</h1>
        <span class="sub">Logistics Control Tower</span>
      </div>

      <nav>
        <a routerLink="/dashboard" routerLinkActive="on">Chart</a>
        <a routerLink="/shipments" routerLinkActive="on">Manifest</a>
        <a routerLink="/analytics" routerLinkActive="on">Analysis</a>
      </nav>

      <div class="status">
        <ng-content />
      </div>
    </header>
  `,
  styles: [`
    .titleblock { display: flex; justify-content: space-between; align-items: flex-end;
                  gap: 30px; padding: 14px 20px 12px; background: var(--panel); }
    .mark h1 { margin: 0; font-family: var(--cond); font-size: 21px; font-weight: 600;
               letter-spacing: .1em; text-transform: uppercase; }
    .sub { font-family: var(--cond); font-size: 10.5px; letter-spacing: .22em;
           text-transform: uppercase; color: var(--ink-faint); }
    nav { display: flex; gap: 22px; flex: 1; padding-bottom: 3px; }
    nav a { font-family: var(--cond); font-size: 11px; letter-spacing: .16em;
            text-transform: uppercase; color: var(--ink-faint); text-decoration: none;
            padding-bottom: 3px; border-bottom: 1px solid transparent; }
    nav a:hover { color: var(--ink-soft); }
    nav a.on { color: var(--ink); border-bottom-color: var(--navy); }
    .status { display: flex; gap: 20px; align-items: center; font-size: 11px;
              color: var(--ink-soft); }
  `],
})
export class TitleBlockComponent {}
