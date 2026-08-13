# Day 7 — install

xcopy /E /I /Y "C:\projects\logipulse\day7\backend\*" "C:\projects\logipulse\backend\"
copy /Y "C:\projects\logipulse\day7\README.md"      "C:\projects\logipulse\"
copy /Y "C:\projects\logipulse\day7\DEMO.md"        "C:\projects\logipulse\"
copy /Y "C:\projects\logipulse\day7\start-all.bat"  "C:\projects\logipulse\"
copy /Y "C:\projects\logipulse\day7\reset-demo.bat" "C:\projects\logipulse\"

## Run the tests
cd C:\projects\logipulse\backend
.venv\Scripts\activate
pip install pytest pytest-asyncio httpx
pytest

Expect: 34 passed.
Docker must be running; the tests use your real Postgres and Redis.
They clean up after themselves but will wipe test rows - run reset-demo.bat
afterwards before recording.

## Scripts
start-all.bat   opens all five processes in separate windows
reset-demo.bat  wipes and reseeds a fresh fleet before recording
