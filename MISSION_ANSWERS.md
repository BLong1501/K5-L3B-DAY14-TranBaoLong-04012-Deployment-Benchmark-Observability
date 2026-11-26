# Day 14 Lab - Mission Answers

> **Họ và tên:** TranBaoLong
> **Lớp:** K5-L3B
> **MSSV:** 04012

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`
1. **Hardcode API key & DB URL trong code** (`OPENAI_API_KEY`, `DATABASE_URL` ở dòng 17–18): nếu push lên GitHub sẽ lộ secret ngay lập tức.
2. **Log ra secret** (`print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` ở dòng 34): bất kỳ ai đọc log đều thấy API key.
3. **Dùng `print()` thay vì structured logging** (dòng 33–38): khó tìm kiếm, lọc theo level/timestamp khi chạy production.
4. **Không có health check / readiness endpoint**: platform (Railway/Render/Kubernetes) không biết app sống hay chết để restart hoặc định tuyến traffic.
5. **Bind `host="localhost"`, `port=8000` cố định và bật `reload=True`** (dòng 49–53): container không nhận được kết nối từ bên ngoài nếu bind `localhost`, không nhận biến `PORT` do cloud platform cấp, và `reload=True` lãng phí tài nguyên ở production.
6. **Không xử lý graceful shutdown**: khi tắt app đột ngột sẽ cắt ngang các request đang xử lý.

### Exercise 1.2: Kết quả chạy bản develop
- Chạy `python app.py` trong `01-localhost-vs-production/develop/` và test `POST /ask?question=Hello` trả về JSON `{"answer": "..."}` (chỉ chạy được trên local).

### Exercise 1.3: So sánh `develop` vs `production`
| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| Config | Hardcode (`OPENAI_API_KEY`, `PORT=8000`) | Đọc từ biến môi trường (`config.settings`) | Tách secret khỏi code, cùng 1 codebase chạy được mọi môi trường |
| Health check | Không có | Có `/health` (liveness) & `/ready` (readiness) | Platform tự phát hiện lỗi để restart hoặc ngừng route traffic |
| Logging | `print()` chữ thường, in cả secret | `logging` xuất JSON có `time`, `level`, `msg` | Dễ đưa vào hệ thống gom log (Loki, Datadog) và không lộ secret |
| Host / Port | `localhost:8000`, `reload=True` | `0.0.0.0:$PORT`, không reload | Chạy được trong container và nhận đúng `PORT` từ cloud |
| Shutdown | Dừng đột ngột | `lifespan` + `SIGTERM` graceful shutdown | Không làm rớt request đang xử lý của người dùng |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)
1. **Base image:** `FROM python:3.11` (full Debian + Python ~1 GB, dẫn đến image cuối nặng 1.67 GB; trong production đổi sang `python:3.11-slim`).
2. **Working directory:** `WORKDIR /app` — đặt thư mục làm việc mặc định bên trong container để các lệnh `COPY`, `RUN`, `CMD` chạy gọn tại `/app`.
3. **Vì sao `COPY requirements.txt` đứng trước `COPY . .`:** Để tận dụng **Docker layer cache** — khi chỉ sửa code (`app.py`) mà không đổi thư viện, Docker dùng lại layer `pip install` đã cache, giúp build nhanh hơn nhiều.
4. **Lệnh khởi chạy:** `CMD ["python", "app.py"]` (exec form, giúp process chạy ở PID 1 để nhận tín hiệu `SIGTERM`).

### Exercise 2.2 & 2.3: Image size comparison (`docker images` / `check_production_ready.py`)
- Develop (`my-agent:latest`, `FROM python:3.11`): **`1.67 GB` (~1,670 MB)**
- Production (multi-stage `python:3.11-slim` ở `06-lab-complete/`): **`56 MB`** (base image `python:3.11-slim` là `188 MB`)
- Chênh lệch: giảm khoảng **`96.6%`** dung lượng image nhờ multi-stage build (tách stage `builder` và `runtime`, chỉ copy thư viện đã cài và code cần thiết, dùng `.dockerignore` loại bỏ `.venv`, cache, tài liệu).

### Exercise 2.4: Docker Compose stack & Nginx (`02-docker/production/docker-compose.yml`)
- **Sơ đồ service:** `Client → nginx (port 80) → agent (2 replicas, port 8000 nội bộ) → redis (session/rate limit) & qdrant (vector DB)` trên mạng nội bộ `internal` (chỉ `nginx` mở port ra ngoài).

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6
- Public URL: `https://glorious-presence-production-c41a016f.up.railway.app`
- Screenshots: `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

### So sánh `railway.toml` vs `render.yaml`
- **Cấu trúc & phạm vi:** `railway.toml` cấu hình cho từng service (chọn `builder = "DOCKERFILE"`, `healthcheckPath = "/health"`, `restartPolicyType`), còn `render.yaml` là Blueprint khai báo cả cụm nhiều service/database trong một file (`services` + `databases`).
- **Quản lý biến môi trường & secret:** Trên Railway, biến môi trường và secret (`AGENT_API_KEY`, `REDIS_URL`) được đặt trực tiếp qua Railway Dashboard/CLI hoặc tham chiếu service (`${{Redis.REDIS_URL}}`); trong `render.yaml`, có thể khai báo danh sách `envVars` ngay trong file với `sync: false` hoặc `generateValue: true` để không lộ secret.
- **Port & Healthcheck:** Cả hai đều tự động inject biến `PORT` vào container và kiểm tra `/health` trước khi chuyển traffic sang bản deploy mới.

### Exercise 3.3: Cloud Run pipeline (`03-cloud-deployment/production-cloud-run/`)
Pipeline CI/CD trong `cloudbuild.yaml` và `service.yaml` gồm 4 bước tuần tự khi push code lên nhánh `main`:
1. **Test (`test`):** Dùng image `python:3.11-slim` cài `requirements.txt` và `pytest`, chạy toàn bộ unit test (`pytest tests/`).
2. **Build (`build`):** Build Docker image bằng `gcr.io/cloud-builders/docker` (gắn tag `$COMMIT_SHA` và `latest`, tận dụng `--cache-from`).
3. **Push (`push`):** Đẩy image vừa build lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`deploy`):** Triển khai bản image mới lên Cloud Run (`gcloud run deploy`) tại region `asia-southeast1` với cấu hình tài nguyên, autoscaling và probe theo `service.yaml`.

---

## Part 4: API Security

### Exercise 4.1–4.3: Kết quả test (`401`, `200`, `429`)

**Trường hợp 401 (thiếu / sai token hoặc API key):**
```http
curl.exe -i -X POST http://127.0.0.1:8001/ask -H "Content-Type: application/json" -d '{\"question\": \"Test\"}'

HTTP/1.1 401 Unauthorized
date: Thu, 26 Nov 2026 08:47:36 GMT
server: uvicorn
www-authenticate: Bearer
content-length: 76
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

**Trường hợp 200 (JWT hợp lệ, `student`):**
```http
curl.exe -i -X POST http://127.0.0.1:8001/ask -H "Authorization: Bearer <TOKEN_HIDDEN>" -H "Content-Type: application/json" -d '{\"question\": \"Explain JWT\"}'

HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:41:23 GMT
server: uvicorn
content-length: 215
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}
```

**Trường hợp 429 (vượt quá 10 requests/phút trong vòng lặp 12 request):**
```http
--- Request 11 ---
HTTP/1.1 429 Too Many Requests
date: Thu, 26 Nov 2026 08:45:37 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795682798
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Trả lời câu hỏi Exercise 4.3 (`04-api-gateway/production/rate_limiter.py`)
- **Algorithm:** Sliding Window Counter (dùng `deque` lưu timestamp của từng `user_id`, loại bỏ các timestamp cũ hơn `now - window_seconds`).
- **Giới hạn:** `10 requests/phút` cho user thường (`rate_limiter_user`), `100 requests/phút` cho admin/teacher (`rate_limiter_admin`).
- **Tách limit cho admin:** Phân quyền theo `role` trong JWT payload để chọn instance `rate_limiter_admin` (hoặc bỏ qua bước kiểm tra rate limit nếu role là admin).

### Exercise 4.4: Giải thích Cost Guard (`04-api-gateway/production/cost_guard.py`)
- **Cơ chế:** Theo dõi `input_tokens` và `output_tokens` theo từng `user_id` mỗi ngày (`UsageRecord`), quy đổi ra chi phí USD theo đơn giá token (`PRICE_PER_1K_INPUT_TOKENS`, `PRICE_PER_1K_OUTPUT_TOKENS`).
- **Kiểm tra trước khi gọi LLM (`check_budget`):**
  - Nếu vượt ngân sách toàn hệ thống (`global_daily_budget_usd = $10/ngày`) → trả `503 Service Unavailable`.
  - Nếu user vượt ngân sách cá nhân (`daily_budget_usd = $1/ngày`) → trả `402 Payment Required`.
  - Khi đạt ≥ 80% ngân sách (`warn_at_pct = 0.8`) → ghi log cảnh báo.
- **Vì sao cần cả Rate Limit lẫn Cost Guard:** Rate limit bảo vệ **tốc độ/tần suất request** (chống spam/DoS), còn Cost Guard bảo vệ **chi phí thực tế theo lượng token** (vì một request prompt/response rất dài vẫn có thể tốn nhiều tiền dù chưa chạm ngưỡng số request/phút).

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.5: Kết quả test & giải thích
- **Kết quả chạy `python test_stateless.py` với 3 instance (`--scale agent=3`):**
  ```text
  Total requests: 5
  Instances used: {'instance-4a65e6', 'instance-f5ecea', 'instance-08908f'}
  ✅ All requests served despite different instances!
  ```
- **Giải thích:** Nginx load balancer phân phối 5 request sang 3 container agent khác nhau (`instance-4a65e6`, `instance-f5ecea`, `instance-08908f`), nhưng toàn bộ conversation history/state được lưu tập trung trong **Redis** (không lưu trong RAM của từng container), nên mọi instance đều đọc được đúng ngữ cảnh của cùng một `session_id`.
- **Phân biệt `/health` (Liveness) vs `/ready` (Readiness):**
  - `/health`: kiểm tra tiến trình app còn sống không (trả `200 OK` ngay cả khi Redis gặp sự cố để tránh platform restart nhầm).
  - `/ready`: kiểm tra app đã sẵn sàng nhận traffic chưa (ping Redis; nếu mất Redis phải trả `503 Service Unavailable` để Load Balancer tạm ngừng gửi request vào instance đó).
- **Graceful shutdown (`SIGTERM`):** Khi nhận tín hiệu dừng, server ngừng nhận kết nối mới, chờ các request đang xử lý chạy xong và đóng kết nối Redis sạch sẽ trước khi thoát.

---

## Part 6: Final Project (`06-lab-complete/`)

### Output `python check_production_ready.py` (Checklist Deliverable)
```text
[Chưa điền — dán kết quả PASS 12/12 vào đây]
```

---

## AI Log
- Sử dụng AI hỗ trợ debug môi trường Windows/PowerShell (`curl.exe`, `.venv`, `PATH`), Railway `Procfile`, và tổng hợp báo cáo `MISSION_ANSWERS.md`.
