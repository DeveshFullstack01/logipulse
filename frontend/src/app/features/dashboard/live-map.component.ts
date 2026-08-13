import {
  AfterViewInit, Component, ElementRef, OnDestroy, effect,
  inject, input, output, viewChild,
} from '@angular/core';
import * as L from 'leaflet';
import { ApiService } from '../../core/api.service';
import { LiveShipment, Shipment } from '../../core/models';

const COLOUR: Record<string, string> = {
  IN_TRANSIT: '#1f6f5c',
  PICKED_UP:  '#2b5a78',
  CREATED:    '#8b989c',
  DELAYED:    '#ac3527',
  DELIVERED:  '#8b989c',
};

/** Great-circle interpolation, mirroring the backend so the plotted course
 *  on screen matches the path the simulator actually walks. */
function greatCircle(
  a: [number, number], b: [number, number], steps = 64
): [number, number][] {
  const rad = Math.PI / 180, deg = 180 / Math.PI;
  const [p1, l1] = [a[0] * rad, a[1] * rad];
  const [p2, l2] = [b[0] * rad, b[1] * rad];
  const d = 2 * Math.asin(Math.sqrt(
    Math.sin((p2 - p1) / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin((l2 - l1) / 2) ** 2
  ));
  if (d < 1e-9) return [a, b];

  const out: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const f = i / steps;
    const A = Math.sin((1 - f) * d) / Math.sin(d);
    const B = Math.sin(f * d) / Math.sin(d);
    const x = A * Math.cos(p1) * Math.cos(l1) + B * Math.cos(p2) * Math.cos(l2);
    const y = A * Math.cos(p1) * Math.sin(l1) + B * Math.cos(p2) * Math.sin(l2);
    const z = A * Math.sin(p1) + B * Math.sin(p2);
    out.push([Math.atan2(z, Math.hypot(x, y)) * deg, Math.atan2(y, x) * deg]);
  }
  return out;
}

@Component({
  selector: 'lp-live-map',
  standalone: true,
  template: `
    <div class="wrap">
      <div class="legend">
        <span class="label">Chart key</span>
        @for (k of keys; track k.status) {
          <span class="key"><i [style.background]="k.colour"></i>{{ k.text }}</span>
        }
      </div>
      <div #host class="map"></div>
    </div>
  `,
  styles: [`
    .wrap { position: relative; height: 100%; }
    .map  { height: 100%; width: 100%; }
    .legend {
      position: absolute; z-index: 500; left: 12px; bottom: 12px;
      background: rgba(244,246,242,.92); border: 1px solid var(--rule);
      padding: 8px 11px; display: flex; flex-direction: column; gap: 5px;
    }
    .legend .label { margin-bottom: 2px; }
    .key { display: flex; align-items: center; gap: 7px; font-size: 11px;
           font-family: var(--cond); letter-spacing: .04em; color: var(--ink-soft); }
    .key i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  `],
})
export class LiveMapComponent implements AfterViewInit, OnDestroy {
  live = input.required<Map<string, LiveShipment>>();
  selected = output<string>();

  private host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private api = inject(ApiService);

  private map?: L.Map;
  private markers = new Map<string, L.CircleMarker>();
  private course?: L.Polyline;
  private endpoints: L.CircleMarker[] = [];
  private selectedId?: string;

  keys = [
    { status: 'IN_TRANSIT', colour: COLOUR['IN_TRANSIT'], text: 'On course' },
    { status: 'DELAYED',    colour: COLOUR['DELAYED'],    text: 'Delayed' },
    { status: 'CREATED',    colour: COLOUR['CREATED'],    text: 'Awaiting departure' },
  ];

  constructor() {
    effect(() => {
      const data = this.live();
      if (this.map) this.render(data);
    });
  }

  ngAfterViewInit(): void {
    this.map = L.map(this.host().nativeElement, {
      center: [18, 66],
      zoom: 3,
      worldCopyJump: true,
      zoomControl: true,
      attributionControl: true,
    });

    // A pale, low-ink basemap: the vessels should be the only strong marks
    // on the chart, the way ports and depths sit quietly under plotted work.
    L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
      { maxZoom: 18, attribution: '&copy; OpenStreetMap &copy; CARTO' }
    ).addTo(this.map);

    this.render(this.live());
  }

  ngOnDestroy(): void { this.map?.remove(); }

  private render(data: Map<string, LiveShipment>): void {
    const map = this.map!;
    const seen = new Set<string>();

    for (const [id, s] of data) {
      if (s.latitude == null || s.longitude == null) continue;
      seen.add(id);
      const colour = COLOUR[s.status] ?? COLOUR['CREATED'];
      const existing = this.markers.get(id);

      if (existing) {
        existing.setLatLng([s.latitude, s.longitude]);
        existing.setStyle({ fillColor: colour, color: colour });
      } else {
        const m = L.circleMarker([s.latitude, s.longitude], {
          radius: 4.5, weight: 1.5, color: colour, fillColor: colour,
          fillOpacity: 0.85,
        })
          .addTo(map)
          .on('click', () => this.select(id));
        m.bindTooltip(id, { direction: 'top', offset: [0, -6], className: 'lp-tip' });
        this.markers.set(id, m);
      }
    }

    // Drop markers for shipments that have been delivered and left the set
    for (const [id, m] of this.markers) {
      if (!seen.has(id)) { m.remove(); this.markers.delete(id); }
    }
  }

  private select(id: string): void {
    this.selectedId = id;
    this.selected.emit(id);
    this.plotCourse(id);
  }

  /** The signature: draw the navigator's plotted course for one vessel.
   *  Drawing all 100+ courses at once would be an unreadable web of lines —
   *  a navigator plots the leg they are working, not the whole fleet. */
  private plotCourse(id: string): void {
    this.api.shipment(id).subscribe((s: Shipment) => {
      this.clearCourse();
      const path = greatCircle(
        [s.origin_lat, s.origin_lon], [s.dest_lat, s.dest_lon]
      );
      this.course = L.polyline(path, {
        color: '#2b5a78', weight: 1.2, opacity: 0.75, dashArray: '5 5',
      }).addTo(this.map!);

      for (const [pt, label] of [
        [[s.origin_lat, s.origin_lon], s.origin],
        [[s.dest_lat, s.dest_lon], s.destination],
      ] as [[number, number], string][]) {
        this.endpoints.push(
          L.circleMarker(pt, {
            radius: 3, weight: 1, color: '#2b5a78',
            fillColor: '#e9ede7', fillOpacity: 1,
          })
            .addTo(this.map!)
            .bindTooltip(label, { permanent: true, direction: 'right',
                                  className: 'lp-port' })
        );
      }
    });
  }

  private clearCourse(): void {
    this.course?.remove();
    this.course = undefined;
    this.endpoints.forEach((e) => e.remove());
    this.endpoints = [];
  }
}
