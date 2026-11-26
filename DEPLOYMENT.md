# Deployment Information

## Public URL
https://glorious-presence-production-c41a016f.up.railway.app

## Platform
Railway (Agent Part 6 `06-lab-complete/` + Railway Redis)

## Environment Variables Configured on Platform
- `AGENT_API_KEY`: (set via Railway Dashboard Variables, not stored in repo)
- `REDIS_URL`: `${{Redis.REDIS_URL}}`
- `RATE_LIMIT_PER_MINUTE`: `10`
- `DAILY_BUDGET_USD`: `1.0`

## Test Commands

```powershell
$BASE = "https://glorious-presence-production-c41a016f.up.railway.app"
$KEY = "<your-agent-api-key>"

# 1. Health check (Expected: 200)
curl.exe -s -o NUL -w "%{http_code}`n" "$BASE/health"

# 2. Readiness check with Redis (Expected: 200)
curl.exe -s -o NUL -w "%{http_code}`n" "$BASE/ready"

# 3. Protected endpoint without API key (Expected: 401)
curl.exe -s -o NUL -w "%{http_code}`n" -X POST "$BASE/ask" -H "Content-Type: application/json" -d '{\"question\":\"Hello\"}'

# 4. Protected endpoint with valid API key (Expected: 200)
curl.exe -s -o NUL -w "%{http_code}`n" -X POST "$BASE/ask" -H "Content-Type: application/json" -H "X-API-Key: $KEY" -d '{\"question\":\"Hello\"}'
```

## Screenshots
- `screenshots/dashboard.png`
- `screenshots/running.png`
- `screenshots/test.png`
