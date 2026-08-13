export type Status =
  | 'CREATED' | 'PICKED_UP' | 'IN_TRANSIT' | 'DELAYED' | 'DELIVERED';

export type Severity = 'HIGH' | 'MEDIUM' | 'LOW';

/** Live position pushed over the WebSocket / read from Redis. */
export interface LiveShipment {
  shipment_number: string;
  status: Status;
  latitude: number | null;
  longitude: number | null;
  progress: number | null;
  speed_kmh?: number | null;
  delay_hours?: number | null;
  delay_reason?: string | null;
  estimated_delivery?: string | null;
  updated_at?: string;
}

/** Durable record from Postgres, including the plotted course. */
export interface Shipment {
  shipment_number: string;
  status: Status;
  mode: string;
  origin: string;
  destination: string;
  route: string;
  origin_lat: number; origin_lon: number;
  dest_lat: number;   dest_lon: number;
  current_lat: number | null;
  current_lon: number | null;
  progress: number;
  distance_km: number;
  expected_delivery: string;
  estimated_delivery: string | null;
  delay_reason: string | null;
  live?: LiveShipment | null;
}

export interface Alert {
  id: number;
  shipment_number: string;
  alert_type: 'DELAY' | 'STALE';
  severity: Severity;
  message: string;
  status: 'OPEN' | 'RESOLVED';
  created_at: string;
  resolved_at: string | null;
}

export interface Summary {
  active: number;
  delayed: number;
  at_risk: number;
  delivered: number;
  open_alerts: number;
  on_time_rate: number;
  live_positions: number | null;
  degraded?: boolean;
}

export interface TimelineEvent {
  event_id: string;
  event_type: string;
  status: string | null;
  latitude: number | null;
  longitude: number | null;
  occurred_at: string;
  delay_hours?: number | null;
  delay_reason?: string | null;
}
