import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { Alert, Shipment, Summary, TimelineEvent } from './models';

const BASE = 'http://localhost:8000';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  summary(): Observable<Summary> {
    return this.http.get<Summary>(`${BASE}/api/dashboard/summary`);
  }

  shipments(params: { status?: string; search?: string; limit?: number } = {}) {
    const q = new URLSearchParams();
    if (params.status) q.set('status', params.status);
    if (params.search) q.set('search', params.search);
    q.set('limit', String(params.limit ?? 200));
    return this.http.get<{ total: number; shipments: Shipment[] }>(
      `${BASE}/api/shipments?${q}`
    );
  }

  shipment(number: string): Observable<Shipment> {
    return this.http.get<Shipment>(`${BASE}/api/shipments/${number}`);
  }

  timeline(number: string) {
    return this.http.get<{ events: TimelineEvent[] }>(
      `${BASE}/api/shipments/${number}/timeline`
    );
  }

  alerts(status = 'OPEN') {
    return this.http.get<{ alerts: Alert[]; open_by_severity: Record<string, number> }>(
      `${BASE}/api/alerts?status=${status}`
    );
  }

  resolveAlert(id: number): Observable<Alert> {
    return this.http.patch<Alert>(`${BASE}/api/alerts/${id}/resolve`, {});
  }

  analytics() {
    return this.http.get<any>(`${BASE}/api/analytics`);
  }
}
