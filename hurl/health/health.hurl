# 1. Liveness -- the process answers, independent of dependencies
GET {{host}}/health

HTTP 200
[Asserts]
jsonpath "$.status" == "alive"

# 2. Readiness -- PostgreSQL and Redis are reachable
GET {{host}}/health/ready

HTTP 200
[Asserts]
jsonpath "$.status" == "ready"
jsonpath "$.checks.database.healthy" == true
jsonpath "$.checks.redis.healthy" == true

# 3. Startup -- the app reports started
GET {{host}}/health/started

HTTP 200
[Asserts]
jsonpath "$.status" == "started"