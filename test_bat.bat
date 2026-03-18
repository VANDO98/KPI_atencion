@echo off
echo PREPARING LOOP
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8080 ^| findstr LISTENING') do (
    echo FOUND: %%a
)
echo DONE
pause
