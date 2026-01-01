# Load Test Specification

## Overview

This document explains the load testing strategy for the ticketing system, including why Go was chosen over k6 for spike testing.

## Load Test Types

| Type            | Purpose                                                   | Tool |
| --------------- | --------------------------------------------------------- | ---- |
| **Smoke Test**  | Validate end-to-end functionality under minimal load      | k6   |
| **Stress Test** | Evaluate behavior during sustained high load (rush hours) | k6   |
| **Spike Test**  | Simulate sudden surge at ticket sale opening              | Go   |

## Why Go for Spike Testing

### k6 Limitations

k6 is designed around **Virtual Users (VUs)**, where each VU represents an independent client. This architecture has inherent limitations for spike testing:

| Limitation               | Description                                                                    |
| ------------------------ | ------------------------------------------------------------------------------ |
| **Memory Overhead**      | Each VU requires 1-5 MB (isolated JavaScript VM)                               |
| **TCP Connection Limit** | Each VU maintains its own TCP connection; Linux ephemeral ports cap at ~64,500 |
| **Sequential Execution** | VU must wait for response before starting next iteration                       |
| **Max Concurrency**      | Hard limit of ~64,500 requests in-flight                                       |
| **No Shared State**      | VUs are isolated; correctness validation requires external store               |

### Go Advantages

Go's architecture is fundamentally different and better suited for high-throughput spike testing:

| Advantage                  | Description                                                 |
| -------------------------- | ----------------------------------------------------------- |
| **Lightweight Goroutines** | ~2 KB overhead vs k6's 1-5 MB per VU                        |
| **Connection Pooling**     | Multiple goroutines share TCP connections via `http.Client` |
| **Fire-and-Forget**        | Send all requests without waiting for responses             |
| **Native Shared State**    | Implement correctness validation directly in Go             |
| **No Hard Limits**         | Can easily send hundreds of thousands of requests           |

## Test Objectives

| Tool   | Best For                                                                                                |
| ------ | ------------------------------------------------------------------------------------------------------- |
| **k6** | Simulating realistic multi-user concurrent connections - How many concorrent requests can we handle?    |
| **Go** | Testing maximum system TPS (Transactions Per Second) - How many tickets can we actually sell per second |

### When to Use Each

**Use k6 for:**

- Load testing (sustained traffic patterns)
- Stress testing (gradual ramp-up)
- Testing connection handling capacity
- Realistic user behavior simulation

**Use Go for:**

- Spike testing (instant burst of requests)
- **Maximum TPS measurement** (actual completed transactions)
- Correctness validation (no double bookings)
- Testing system limits
