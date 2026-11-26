# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** TranBaoLong (K5-L3B · MSSV: 04012)
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows 11, Python 3.13 (.venv), Docker Desktop

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Đảm bảo trải nghiệm người dùng mượt (< 0.5s) ở tải thông thường; phản ánh tail latency tốt hơn average |
| Error rate `/ask` | < 2.0 % | Chấp nhận lỗi ngẫu nhiên nhỏ của upstream LLM nhưng phát hiện sớm sự cố hệ thống |
| Accuracy trên golden dataset | ≥ 80 % | Đảm bảo chất lượng trả lời của agent v2 (RAG) và chặn regression trước khi merge/deploy |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.6 | 202.0 | 386.3 | 1723.9 | 0.33% | PASS |
| 10 | 40.05 | 201.8 | 233.7 | 1716.5 | 1.33% | PASS |
| 50 | 110.12 | 213.7 | 262.0 | 1707.2 | 1.00% | PASS |
| 100 | 50.46 | 383.3 | 3849.6 | 4070.5 | 0.67% | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không. RPS tăng mạnh từ concurrency 1 (3.6 req/s) → 10 (40.05 req/s) → 50 (110.12 req/s) nhờ xử lý bất đồng bộ, nhưng đến concurrency 100 thì RPS **giảm xuống 50.46 req/s** và p95 vọt lên **3849.6 ms** (vi phạm SLO ≤ 500 ms). Nguyên nhân là khi quá nhiều request đồng thời trên 1 process uvicorn, event loop / connection / CPU bị bão hòa và request phải xếp hàng chờ xử lý.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 199.3 | 231.1 | 235.1 |
| 0.03 (mặc định) | 206.5 | 232.1 | 235.9 |
| 0.1 | 352.8 | 1705.4 | 1725.6 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

`p95` và `p99` nhạy nhất với request chậm: khi `MOCK_SLOW_RATE` tăng lên `0.1` (10% request chậm), `avg` chỉ tăng từ 199.3 ms lên 352.8 ms (~1.77×), nhưng `p95` nhảy vọt từ 231.1 ms lên **1705.4 ms** (~7.4×). Vì giá trị trung bình (average) bị pha loãng bởi 90% request nhanh và che giấu trải nghiệm tệ của nhóm người dùng chậm nhất, nên SLO phải đặt theo **p95 / p99**.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.3 | 109.1 | 113.7 |
| Tổng cost (USD) | $0.000406 | $0.000762 | $0.000790 |
| Cost / câu đúng (USD) | $0.00040635 | $0.00003627 | $0.00003436 |
| Quality gate | FAIL | PASS (min 80%) | PASS (min 100%) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry về JWT (`["jwt"]`) vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry về Kubernetes HPA (`["hpa", "kubernetes", "autoscal"]`) vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

Agent v2 (có RAG retrieval) tăng `avg tokens/câu` từ 57.3 lên 113.7 (tổng cost gần gấp đôi: $0.000406 → $0.000790) và latency p50 tăng nhẹ (~154.7 ms → ~204.4 ms). Tuy nhiên, **accuracy tăng từ 4.35% lên 100%**, kéo **`cost / câu đúng` giảm hơn 11 lần** ($0.00040635 → $0.00003436). Trong production, chỉ số "cost / câu đúng" phản ánh hiệu quả thực tế tốt hơn nhiều so với "cost / câu".
*(CI quality gate: dùng `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85` trong GitHub Actions; khi accuracy < 85% hoặc có regression, script trả về exit code 1 để tự động chặn merge PR.)*

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals) — `screenshots/grafana-dashboard.png`
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian) — `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger (có event `exception`) — `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing** (đạt 3 alert cùng firing) — `screenshots/prometheus-alert-firing.png`

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | ~1 phút (`for: 1m`) | Error rate & Requests/s theo status code (503) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | ~2 phút (`for: 2m`) | Latency p95 & Latency /ask — p50 / p95 / p99 |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (nếu vượt $2/h) | ~2 phút (`for: 2m`) | LLM cost (1h) & Cost burn rate (USD/giờ) |
| D | `docker pause` 1 instance | `AgentInstanceDown` | ~30 giây (`for: 30s`) | Instances up (giảm từ 3 xuống 2) |
| E | `AGENT_VERSION=v1` | Không có alert nào | — | Không thấy trên infra dashboard (chỉ thấy khi chạy eval) |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Alert hạ tầng (Prometheus) chỉ đo được HTTP status, latency và cost, không biết câu trả lời đúng hay sai. Để phát hiện sự cố chất lượng như dùng nhầm `v1`:
1. Chạy **Eval / Quality Gate** tự động trong CI/CD trước khi deploy (chặn merge nếu accuracy giảm).
2. Chạy **Online Eval / Canary Evaluation** lấy mẫu traffic thật hoặc thu thập **user feedback** (thumbs up/down) và gắn metric chất lượng lên dashboard để alert khi accuracy tụt.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được (từ ảnh `screenshots/jaeger-slow-trace.png`):

- `trace_id`: `de0be07...` *(chạy `docker compose -p k5-day14-observability logs agent | Select-String "de0be07"` để lấy đầy đủ 32 ký tự và dòng log JSON trước khi `down`)*
- Tổng thời gian: `1700 ms` (`1.7s`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (~`1680 ms`, ~`98.8%`; còn `agent.retrieve_context` chỉ mất `18.3 ms`)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "...", "event": "http_request", "route": "/ask", "status": 200, "ms": 1700, "trace_id": "de0be07..."}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 66.02 | 190 | 250 | 1700 | 68 (0.86%) |
| 3 | 65.88 | 190 | 230 | 1700 | 70 (0.89%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Scale từ 1 lên 3 instance giúp **p95 giảm từ 250 ms xuống 230 ms** (riêng `POST /ask` giảm từ 260 ms xuống 230 ms) do tải được chia đều qua Nginx. Tuy nhiên tổng RPS giữ quanh ~66 req/s và `p99` vẫn ở 1700 ms vì: (1) Locust chạy 100 user có `wait_time` giữa các request nên lưu lượng phát sinh tối đa chỉ ~66 req/s (chưa làm bão hòa 1 instance), và (2) `p99 = 1700 ms` đến từ `MOCK_SLOW_RATE=0.03` (mô phỏng độ trễ của upstream LLM — nút thắt nằm ở LLM/downstream nên thêm replica không làm LLM trả lời nhanh hơn).

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
