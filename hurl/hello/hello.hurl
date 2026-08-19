# GET /api/hello - health check / greeting
# NOTE: message is hour-dependent (morning/noon/afternoon/evening), so the
# assertion matches the greeting family instead of a fixed string.
GET {{host}}/api/hello
HTTP 200
[Asserts]
jsonpath "$.message" matches /Good (morning|noon|afternoon|evening)!/