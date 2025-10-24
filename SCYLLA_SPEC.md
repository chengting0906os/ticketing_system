# Scylla Note

## Consistency Level

The default CL value when using the CQL Shell is ONE.

The Consistency Level is tunable per operation in CQL. This is known as tunable consistency. Sometimes response latency is more important, making it necessary to adjust settings on a per-query or operation level to override keyspace or even data center-wide consistency settings. In other words, the Consistency Level setting allows you to choose a point in the consistency vs. latency tradeoff.

Some of the most common Consistency Levels used are:

- **ANY** – (Write Only) – If all replica nodes are down, write succeeds after a hinted-handoff. Provides low latency, guarantees writes never fail.
- **QUORUM** – When a majority of the replicas respond, the request is honored. If RF=3, then 2 replicas respond. QUORUM can be calculated using the formula (n/2 +1) where n is the Replication Factor.
- **ONE** – If one replica responds; the request is honored.
- **LOCAL_ONE** – At least one replica in the local data center responds.
- **LOCAL_QUORUM** – A quorum of replicas in the local datacenter responds.
- **EACH_QUORUM** – (unsupported for reads) – A quorum of replicas in ALL datacenters must be written to.
- **ALL** – A write must be written to all replicas in the cluster, a read waits for a response from all replicas. Provides the lowest availability with the highest consistency.

**Our Configuration**: We use `LOCAL_QUORUM` for strong consistency within a datacenter while maintaining acceptable latency.

## Connection Pooling and Shard-Aware Architecture

### Shard-Per-Core Architecture

ScyllaDB uses a **shard-per-core architecture** where each CPU core has its own shard with dedicated memory and I/O resources. This eliminates lock contention and enables linear scalability.

### Python Driver Configuration

Our configuration in [scylla_setting.py](src/platform/database/scylla_setting.py) optimizes for ScyllaDB's architecture:

#### Load Balancing Policy

```python
TokenAwarePolicy(WhiteListRoundRobinPolicy(contact_points))
```

- **TokenAwarePolicy**: Routes requests directly to the shard owning the data
  - Eliminates inter-shard data transfer
  - Significantly reduces latency
  - Automatically enabled by wrapping the base policy
- **WhiteListRoundRobinPolicy**: Restricts connections to specified contact points
  - Prevents Docker internal IP auto-discovery (172.x.x.x addresses)
  - Essential for test environments using localhost

#### Connection Pool Behavior

**Default (Shard-Aware Enabled)**:

- Driver opens **one connection per shard** automatically
- For a 4-core node: 4 connections established
- With protocol v4: Each connection handles up to 32,768 concurrent requests using stream IDs

**Disabling Shard Awareness** (not recommended for production):

```python
Cluster(shard_aware_options=dict(disable=True))
```

Use only when you have many client processes connecting from one host.

#### Protocol Version

- **Protocol v4** (configured): Supports up to 32,768 concurrent requests per connection
- Makes "one connection per shard" highly efficient
- No need to manually configure connection pool sizes

#### Executor Threads

```python
executor_threads=8
```

- Thread pool for async operations (connection establishment, metadata refresh)
- Not directly related to shard connections
- 8 threads provides good balance for handling concurrent operations

### Monitoring Shard Connections

Check shard-aware connection status in Python:

```python
cluster = Cluster(...)
stats = cluster.shard_aware_stats()
is_aware = cluster.is_shard_aware()
```

### Performance Implications

**With TokenAwarePolicy (Shard-Aware)**:

- ✅ Requests routed directly to data-owning shard
- ✅ No inter-shard communication overhead
- ✅ Lower latency (significant reduction)
- ✅ Better CPU utilization

**Without TokenAwarePolicy**:

- ❌ Requests may land on wrong shard
- ❌ Data must be transferred between shards
- ❌ Higher latency
- ❌ Wasted CPU cycles

### References

- [ScyllaDB Java Driver: Connection Pooling](https://java-driver.docs.scylladb.com/scylla-3.11.5.x/manual/pooling/)
- [ScyllaDB Python Driver: Scylla-Specific Features](https://python-driver.docs.scylladb.com/stable/scylla-specific.html)
- [Making a Shard-Aware Python Driver for ScyllaDB](https://www.scylladb.com/2020/10/15/making-a-shard-aware-python-driver-for-scylla-part-2/)

## Run in Docker

<https://docs.scylladb.com/manual/stable/operating-scylla/procedures/tips/best-practices-scylla-on-docker.html#getting-performance-out-of-your-docker-container>
