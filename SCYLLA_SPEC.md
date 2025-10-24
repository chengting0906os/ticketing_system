# Scylla Note

## Consitency level

The default CL value when using the CQL Shell is ONE.

The Consistency Level is tunable per operation in CQL. This is known as tunable consistency. Sometimes response latency is more important, making it necessary to adjust settings on a per-query or operation level to override keyspace or even data center-wide consistency settings. In other words, the Consistency Level setting allows you to choose a point in the consistency vs. latency tradeoff.

Some of the most common Consistency Levels used are:

ANY – (Write Only) – If all replica nodes are down, write succeeds after a hinted-handoff. Provides low latency, guarantees writes never fail.
QUORUM – When a majority of the replicas respond, the request is honored. If RF=3, then 2 replicas respond. QUORUM can be calculated using the formula (n/2 +1) where n is the Replication Factor.
ONE – If one replica responds; the request is honored.
LOCAL_ONE – At least one replica in the local data center responds.
LOCAL_QUORUM – A quorum of replicas in the local datacenter responds.
EACH_QUORUM – (unsupported for reads) – A quorum of replicas in ALL datacenters must be written to.
ALL – A write must be written to all replicas in the cluster, a read waits for a response from all replicas. Provides the lowest availability with the highest consistency.

## Run in Docker

<https://docs.scylladb.com/manual/stable/operating-scylla/procedures/tips/best-practices-scylla-on-docker.html#getting-performance-out-of-your-docker-container>
