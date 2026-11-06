@echo off
REM Keep this window open while using the app.
if not exist "C:\Users\Abhishek\mongodata" mkdir "C:\Users\Abhishek\mongodata"
"D:\MongoDB\Server\9.0\bin\mongod.exe" --dbpath "C:\Users\Abhishek\mongodata" --bind_ip 127.0.0.1 --port 27017
pause
