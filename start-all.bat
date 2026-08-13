@echo off
REM Opens every LogiPulse process in its own window. Docker must be running.
cd /d "%~dp0"

echo Starting infrastructure...
docker compose up -d
timeout /t 6 /nobreak >nul

start "LogiPulse API"      cmd /k "cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"
timeout /t 3 /nobreak >nul
start "State Worker"       cmd /k "cd backend && .venv\Scripts\activate && python -m workers.state_worker"
start "Alert Worker"       cmd /k "cd backend && .venv\Scripts\activate && python -m workers.alert_worker"
timeout /t 2 /nobreak >nul
start "Simulator"          cmd /k "cd backend && .venv\Scripts\activate && python -m simulator.shipment_simulator"
start "Frontend"           cmd /k "cd frontend && ng serve"

echo.
echo   Dashboard      http://localhost:4200
echo   API docs       http://localhost:8000/docs
echo   Kafka console  http://localhost:8090
echo.
pause
