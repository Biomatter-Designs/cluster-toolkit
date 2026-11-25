# Boot disk speed: PD vs Hyperdisk (measured 2026-11-25)

64 GiB boot disks, measured on the nodes with fio:
`bmd/tools/disk_bench.sh <dir>` (4 GiB test file, 30 s per test, direct
I/O). PD: pd-balanced (`gcp4c32rspot`); Hyperdisk: Hyperdisk Balanced on
`gcp8c64rspot` at three settings (IOPS / MiB/s provisioned). Random 4k:
queue depth 64 × 4 jobs; sequential 1M: the read test, 32 × 4; "queue
depth 1": one job, one request at a time; "at saturation": the average
latency of the random 4k read test, 256 requests in flight. That one
follows from the IOPS (256 / IOPS: 256 / 3578 = 71.5 ms), so it shows the
same limit as the IOPS row, seen from the waiting side.

| | PD | Hyperdisk, default (3000 / 140) | Hyperdisk, 6000 / 280 | Hyperdisk, 32000 / 1000 (current) |
|---|---|---|---|---|
| Random read 4k | 3,578 IOPS | 3,579 IOPS | 6,344 IOPS | 33,900 IOPS |
| Random write 4k | 3,416 IOPS | 3,413 IOPS | 6,055 IOPS | 32,300 IOPS |
| Sequential read 1M | 159 MiB/s | 237 MiB/s | 281 MiB/s | 1,002 MiB/s |
| Latency, queue depth 1 (avg) | 370 µs | 570 µs | 576 µs | 565 µs |
| Latency at saturation | 71.5 ms | 71.5 ms | 40.3 ms | 7.6 ms |

What it shows:
- The disks deliver what is provisioned: IOPS and throughput follow the
  setting almost exactly (the N4 machine did not cap 32000 / 1000).
- Default Hyperdisk is no faster than PD in IOPS, only in sequential
  throughput (237 vs 159 MiB/s).
- A single request is not faster on Hyperdisk (about 570 µs vs 370 µs on
  PD) and doesn't improve with provisioning. What improves is how many
  requests are served at once: with 256 in flight each waits 7.6 ms
  instead of 71.5 ms.
- So the provisioned limits pay off for parallel I/O (many processes,
  conda installs, scratch on `/`), not for single-threaded small reads.
