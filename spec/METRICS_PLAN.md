# CloudWatch Metrics Implementation Plan

**Status**: Not Implemented (Planned for Future)
**Priority**: Medium
**Effort**: 2-3 hours

---

## 📊 Current State

**What's Already Working**:

- ✅ **ECS Container Insights** - CPU, Memory, Network metrics (automatic)
- ✅ **MSK Enhanced Monitoring** - Kafka broker/topic metrics (automatic)
- ✅ **Aurora Enhanced Monitoring** - Database performance metrics (automatic)
- ✅ **CloudWatch Logs** - Application logs from ECS containers

**What's Missing**:

- ❌ **Application-level Metrics** - Business logic metrics (booking success rate, latency, etc.)
- ❌ **Custom Dashboards** - Visualization of business KPIs

---

## 🎯 Goals

Implement **application-level metrics** to track:

1. **Booking Metrics**
   - `booking.attempts` (Count) - Total booking requests
   - `booking.success` (Count) - Successful bookings
   - `booking.failure` (Count) - Failed bookings
   - `booking.duration` (Milliseconds) - Booking processing time
   - `booking.success_rate` (Percent) - Calculated metric

2. **Payment Metrics**
   - `payment.attempts` (Count) - Payment requests
   - `payment.success` (Count) - Successful payments
   - `payment.failure` (Count) - Failed payments
   - `payment.duration` (Milliseconds) - Payment processing time

3. **Seat Reservation Metrics**
   - `reservation.lock_acquired` (Count) - Successful seat locks
   - `reservation.lock_failed` (Count) - Failed seat locks (contention)
   - `reservation.lock_duration` (Milliseconds) - Lock acquisition time

4. **Kafka Consumer Metrics**
   - `consumer.messages_processed` (Count) - Messages consumed
   - `consumer.errors` (Count) - Processing errors
   - `consumer.lag` (Count) - Consumer lag (if needed)

---

## 🏗️ Architecture

### Layer Separation (Hexagonal Architecture)

```plain
┌─────────────────────────────────────────────────────┐
│  Domain Layer (Business Logic)                      │
│  ┌─────────────────────────────────────────┐        │
│  │  MetricsService (Protocol/Interface)    │        │
│  │  - increment(metric_name, value)        │        │
│  │  - record_timing(metric_name, value_ms) │        │
│  │  - set_property(key, value)             │        │
│  └─────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────┘
                      ▲
                      │ Dependency Inversion
                      │
┌─────────────────────┴───────────────────────────────┐
│  Infrastructure Layer (AWS Implementation)          │
│  ┌─────────────────────────────────────────┐        │
│  │  CloudWatchMetricsAdapter               │        │
│  │  - Uses AWS Embedded Metrics (EMF)      │        │
│  │  - No boto3 required (via logs)         │        │
│  │  - Automatic batching                   │        │
│  └─────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────┘
```

**Why This Design?**

- **Domain layer doesn't depend on AWS** - Easy to test, easy to switch providers
- **Protocol-based** - Use Python's `Protocol` for compile-time type checking
- **Async-first** - Works seamlessly with FastAPI/anyio

---

## 📦 Implementation Steps

### Step 1: Add Dependency (1 min)

```bash
uv add aws-embedded-metrics
```

**Why AWS Embedded Metrics?**

- ✅ No boto3/AWS SDK needed (sends metrics via CloudWatch Logs)
- ✅ Automatic batching and buffering (high performance)
- ✅ Works in ECS, Lambda, EC2, and local development
- ✅ Zero infrastructure changes (uses existing log streams)

---

### Step 2: Create Domain Protocol (10 min)

**File**: `src/service/ticketing/domain/service/metrics_service.py`

```python
"""Metrics Service - Domain abstraction for application metrics."""

from typing import Protocol

class MetricsService(Protocol):
    """Protocol for emitting application metrics."""

    async def increment(
        self,
        metric_name: str,
        *,
        value: float = 1.0,
        dimensions: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter metric."""
        ...

    async def record_timing(
        self,
        metric_name: str,
        *,
        value_ms: float,
        dimensions: dict[str, str] | None = None,
    ) -> None:
        """Record a timing/latency metric in milliseconds."""
        ...
```

**Key Design Decisions**:

- `Protocol` instead of `ABC` - More Pythonic, better IDE support
- `async` methods - Non-blocking, works with FastAPI
- `dimensions` - CloudWatch metric dimensions for filtering

---

### Step 3: Implement CloudWatch Adapter (30 min)

**File**: `src/service/ticketing/driven_adapter/metrics/cloudwatch_metrics_adapter.py`

```python
"""CloudWatch Metrics Adapter using AWS Embedded Metrics."""

import asyncio
from aws_embedded_metrics import metric_scope
from aws_embedded_metrics.logger.metrics_logger import MetricsLogger

class CloudWatchMetricsAdapter:
    """CloudWatch metrics implementation using EMF."""

    def __init__(
        self,
        *,
        namespace: str,
        service_name: str,
        environment: str = 'production',
    ) -> None:
        self._namespace = namespace
        self._service_name = service_name
        self._default_dimensions = {
            'Service': service_name,
            'Environment': environment,
        }

    async def increment(
        self,
        metric_name: str,
        *,
        value: float = 1.0,
        dimensions: dict[str, str] | None = None,
    ) -> None:
        """Emit counter metric."""
        await self._emit_metric(
            metric_name=metric_name,
            value=value,
            unit='Count',
            dimensions=dimensions,
        )

    async def _emit_metric(
        self,
        *,
        metric_name: str,
        value: float,
        unit: str,
        dimensions: dict[str, str] | None = None,
    ) -> None:
        """Emit metric using EMF (runs in thread pool)."""

        def _sync_emit() -> None:
            @metric_scope
            def emit_with_scope(metrics: MetricsLogger) -> None:
                metrics.set_namespace(self._namespace)

                all_dimensions = {**self._default_dimensions}
                if dimensions:
                    all_dimensions.update(dimensions)
                metrics.set_dimensions(all_dimensions)

                metrics.put_metric(metric_name, value, unit)

            emit_with_scope()

        # Run in thread pool (EMF is sync)
        await asyncio.to_thread(_sync_emit)
```

**Why `asyncio.to_thread()`?**

- AWS Embedded Metrics is **synchronous**
- Our domain is **async** (FastAPI)
- `to_thread()` bridges sync ↔ async without blocking event loop

---

### Step 4: Wire Dependency Injection (10 min)

**File**: `src/platform/config/di.py`

```python
from service.ticketing.driven_adapter.metrics import CloudWatchMetricsAdapter

# In setup() function
container = Container()
container.register(
    MetricsService,
    CloudWatchMetricsAdapter(
        namespace='TicketingSystem/Booking',
        service_name='ticketing-service',
        environment=os.getenv('ENVIRONMENT', 'production'),
    ),
    scope=Scope.singleton,
)
```

---

### Step 5: Add Metrics to Use Cases (20 min per use case)

**Example**: `src/service/ticketing/app/command/reserve_ticket.py`

```python
from service.ticketing.domain.service.metrics_service import MetricsService

class ReserveTicketUseCase:
    def __init__(
        self,
        *,
        booking_repo: BookingRepository,
        event_bus: EventBus,
        metrics: MetricsService,  # 👈 Inject
    ) -> None:
        self._booking_repo = booking_repo
        self._event_bus = event_bus
        self._metrics = metrics

    async def execute(self, command: ReserveTicketCommand) -> Result:
        import time
        start = time.perf_counter()

        # Track attempt
        await self._metrics.increment('booking.attempts')

        try:
            # Business logic
            result = await self._reserve_ticket(command)

            # Track success
            await self._metrics.increment('booking.success')
            duration_ms = (time.perf_counter() - start) * 1000
            await self._metrics.record_timing(
                'booking.duration',
                value_ms=duration_ms,
                dimensions={'status': 'success'}
            )

            return result
        except Exception as e:
            # Track failure
            await self._metrics.increment(
                'booking.failure',
                dimensions={'error_type': type(e).__name__}
            )
            duration_ms = (time.perf_counter() - start) * 1000
            await self._metrics.record_timing(
                'booking.duration',
                value_ms=duration_ms,
                dimensions={'status': 'failure'}
            )
            raise
```

**Key Points**:

- Metrics at **use case layer** (business logic), not controllers
- Track: **attempts**, **success**, **failure**, **duration**
- Use **dimensions** for filtering (e.g., error_type)

---

### Step 6: Test Locally (10 min)

```bash
# Run app locally (EMF will output to stdout in local mode)
make dra

# Make a booking request
curl -X POST http://localhost:8000/api/booking/reserve \
  -H "Content-Type: application/json" \
  -d '{...}'

# Check logs - you should see EMF JSON
docker-compose logs ticketing-service | grep -A 5 "LogGroup"
```

**Expected Output**:

```json
{
  "_aws": {
    "Timestamp": 1234567890,
    "CloudWatchMetrics": [
      {
        "Namespace": "TicketingSystem/Booking",
        "Dimensions": [["Service", "Environment"]],
        "Metrics": [
          {"Name": "booking.attempts", "Unit": "Count"}
        ]
      }
    ]
  },
  "Service": "ticketing-service",
  "Environment": "production",
  "booking.attempts": 1
}
```

---

### Step 7: Verify in CloudWatch (AWS) (5 min)

After deploying to ECS:

1. **Go to CloudWatch Console** → Metrics
2. **Select** "TicketingSystem/Booking" namespace
3. **See metrics**: `booking.attempts`, `booking.success`, `booking.failure`, `booking.duration`
4. **Create dashboard** with success rate graph

---

## 📈 Example CloudWatch Dashboard

After implementation, create a dashboard with:

1. **Booking Success Rate** (%)
   - Formula: `(booking.success / booking.attempts) * 100`

2. **Booking Latency** (p50, p95, p99)
   - Metric: `booking.duration`
   - Statistics: Percentiles

3. **Error Rate by Type**
   - Metric: `booking.failure`
   - Dimension: `error_type`

4. **Consumer Lag**
   - Metric: `consumer.messages_processed`
   - Compare with Kafka topic offset

---

## 🧪 Testing Strategy

1. **Unit Tests** - Mock `MetricsService`

   ```python
   async def test_reserve_ticket_tracks_success():
       mock_metrics = Mock(spec=MetricsService)
       use_case = ReserveTicketUseCase(metrics=mock_metrics)

       await use_case.execute(command)

       mock_metrics.increment.assert_any_call('booking.attempts')
       mock_metrics.increment.assert_any_call('booking.success')
   ```

2. **Integration Tests** - Use real CloudWatch in staging
3. **Load Tests** - Verify metrics during k6 stress tests

---

## 💰 Cost Estimate

**CloudWatch Metrics Pricing** (us-west-2):

- First 10,000 metrics: **FREE**
- Additional metrics: **$0.30 per metric/month**
- API requests: **$0.01 per 1,000 requests**

**Expected Monthly Cost** (10,000 TPS):

- Metrics: ~20 custom metrics × $0.30 = **$6/month**
- API requests: Negligible (batched via EMF)
- **Total**: ~$6-10/month

---

## 🎓 Learning Resources

1. **AWS Embedded Metrics**
   - [GitHub](https://github.com/awslabs/aws-embedded-metrics-python)
   - [Docs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html)

2. **CloudWatch Metrics**
   - [Concepts](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html)
   - [Pricing](https://aws.amazon.com/cloudwatch/pricing/)

3. **Observability Best Practices**
   - [Logging vs Metrics vs Tracing](https://www.honeycomb.io/blog/observability-101-terminology-and-concepts)

---

## 🚀 When to Implement

**Recommended Timeline**:

1. **After ECS deployment is stable** - Infrastructure first
2. **Before production launch** - Need observability for debugging
3. **During load testing** - Validate metrics under load

**Effort**: 2-3 hours total (including testing)

---

## ✅ Acceptance Criteria

- [ ] `MetricsService` protocol defined in domain layer
- [ ] `CloudWatchMetricsAdapter` implemented in infrastructure layer
- [ ] Metrics injected into at least 3 use cases
- [ ] Local testing shows EMF output in logs
- [ ] CloudWatch dashboard shows metrics in AWS
- [ ] Unit tests mock `MetricsService` correctly
- [ ] Load test confirms metrics are accurate

---

**Questions?** See the implementation code examples above or ask!
