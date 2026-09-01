import jwt



dd = jwt.decode("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6ImZ1cWluZyIsInVzZXJpZCI6IjI4MDU2NiIsIm5iZiI6MTc4Njc3OTA0NCwiZXhwIjoxNzg3MzgzODQ0LCJpc3MiOiJEYXRhIiwiYXVkIjoiQWxsIn0.EAVguAR5IKSkrWImknx7dRF55SfCh1MKT-pb9TXq2k4","change-me-in-production-secure-key", algorithms=['HS256'])
print(dd)