import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./features/dashboard/dashboard.component').then((m) => m.DashboardComponent),
  },
  {
    path: 'shipments',
    loadComponent: () =>
      import('./features/shipments/manifest.component').then((m) => m.ManifestComponent),
  },
  {
    // `id` is bound straight into the component's input() by
    // withComponentInputBinding() — no ActivatedRoute plumbing needed.
    path: 'shipments/:id',
    loadComponent: () =>
      import('./features/shipments/shipment-detail.component')
        .then((m) => m.ShipmentDetailComponent),
  },
  {
    path: 'analytics',
    loadComponent: () =>
      import('./features/analytics/analytics.component').then((m) => m.AnalyticsComponent),
  },
  { path: '**', redirectTo: 'dashboard' },
];
