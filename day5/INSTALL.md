# Day 5 — install

From C:\projects\logipulse\frontend

1. npm i leaflet @types/leaflet
2. Copy src/ over your generated src/ (merge, replace when asked)
3. Add the fonts to src/index.html inside <head>:

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500&display=swap" rel="stylesheet">

4. Make the ROOT component template just:   <router-outlet />
   - Angular 20+: src/app/app.html
   - Angular 17-19: src/app/app.component.html
   and make sure RouterOutlet is imported in that component.

5. If angular.json lists "src/styles.scss", either rename my styles.css to
   styles.scss or change angular.json to point at styles.css.

6. ng serve  ->  http://localhost:4200

If provideZonelessChangeDetection errors (Angular < 18), delete that line
from app.config.ts and leave the rest.
