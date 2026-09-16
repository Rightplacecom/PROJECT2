$python = "C:\Users\adity\AppData\Local\Programs\Python\Python313\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
& $python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
