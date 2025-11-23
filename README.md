
# Performance Tuning: Consumer Configuration

## Problem: High Latency from Producer to Consumer

During local development, I used **Jaeger** to observe system performance with a **spike test of 1000 concurrent requests**.

### Before: 10 Consumers × 0.5 CPU (Total: 5 CPU reserved)

```yaml
resources:
  limits:
    cpus: '1'
    memory: 1024M
  reservations:
    cpus: '0.5'
    memory: 512M
```

**Result (longest trace):** Producer → Consumer latency: **~11 seconds** (1.54s ~ 12.55s)

![Before optimization - Jaeger trace](.github/image/v0.0.1-interval-jaejar-low.png)
![Before optimization - Go client](.github/image/v0.0.1-interval-go-low.png)

---

### After: 50 Consumers × 0.1 CPU (Total: 5 CPU reserved)

```yaml
resources:
  limits:
    cpus: '0.25'
    memory: 512M
  reservations:
    cpus: '0.1'
    memory: 128M
```

**Result (longest trace):** Producer → Consumer latency: **~1 second** (4.35s ~ 5.53s)

![After optimization - Jaeger trace](.github/image/v0.0.1-interval-jaejar-high.png)
![After optimization - Go client](.github/image/v0.0.1-interval-go-high.png)

---

## Key Insight

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Consumer count | 10 | 50 | 5× more |
| CPU per consumer | 0.5 | 0.1 | 5× less |
| Total CPU reserved | 5 | 5 | Same |
| Producer → Consumer latency | 11.01s | 1.18s | **89.3% faster** |
| Total sellout duration | 14.25s | 7.91s | **44.5% faster** |
| P50 latency | 2.98s | 3.80s | 27.5% slower |
| P95 latency | 5.87s | 6.87s | 17.0% slower |
| P99 latency | 6.73s | 7.82s | 16.2% slower |
| Throughput | 138.33/s | 119.66/s | 13.5% lower |

**Conclusion:** For I/O-bound Kafka consumers, **more lightweight consumers** outperform fewer heavyweight ones. The bottleneck was not CPU per consumer, but **parallelism** — having more consumers to process partitions concurrently dramatically reduced queue wait time.

### Why P95 is slower but total duration is faster?

| Factor | 10 Consumers × 0.5 CPU | 50 Consumers × 0.1 CPU |
|--------|------------------------|------------------------|
| Queue wait time | Long (messages pile up) | Short (more consumers polling) |
| Processing per request | Fast (more CPU) | Slightly slower (less CPU) |
| Parallelism | Low | High |

**Observation:** All latency percentiles (P50, P95, P99) are ~17-27% slower, and throughput dropped by 13.5%. Yet the total sellout duration improved by 44.5%.

**Possible causes:**

1. **Resource contention** - 50 containers competing for CPU/memory causes more context switching
2. **Docker scheduling overhead** - Managing 50 containers is more complex than 10
3. **Connection pool pressure** - More consumers = more concurrent connections to Kafka/Kvrocks/PostgreSQL

**Trade-off:** We sacrifice per-request latency to gain faster overall completion. For spike tests with 1000 concurrent requests, reducing the **backend processing time** (first ticket → last ticket) matters more than individual request speed.
