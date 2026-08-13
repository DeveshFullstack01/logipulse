@echo off
REM Wipes shipments, events and alerts, then reseeds a fresh fleet.
REM Stop the simulator first, run this, then start it again.
cd /d "%~dp0"

docker exec -it logipulse-postgres psql -U logipulse -d logipulse -c "TRUNCATE shipment_events, alerts, shipments RESTART IDENTITY CASCADE;"
docker exec -it logipulse-redis redis-cli FLUSHALL
docker exec -it logipulse-redis redis-cli DEL sim:chaos

cd backend
call .venv\Scripts\activate
python seed.py

echo.
echo Fresh fleet seeded. Start the simulator when you are ready to record.
pause
