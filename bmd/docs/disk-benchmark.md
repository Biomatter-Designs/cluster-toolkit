# Boot disk speed: PD vs Hyperdisk

Measured 2026-11-25 on 64 GiB boot disks with `bmd/tools/disk_bench.sh`
(fio). PD is pd-balanced; Hyperdisk is Hyperdisk Balanced at three settings
(provisioned IOPS / MiB/s).

| | PD | Hyperdisk 3000 / 140 (default) | Hyperdisk 6000 / 280 | Hyperdisk 32000 / 1000 (now) |
|---|---|---|---|---|
| Random read, IOPS | 3,578 | 3,579 | 6,344 | 33,900 |
| Random write, IOPS | 3,416 | 3,413 | 6,055 | 32,300 |
| Sequential read, MiB/s | 159 | 237 | 281 | 1,002 |
| Single request latency | 370 µs | 570 µs | 576 µs | 565 µs |
| Latency under full load | 71.5 ms | 71.5 ms | 40.3 ms | 7.6 ms |

In short:
- **Hyperdisk delivers what you provision.** Default Hyperdisk is no faster
  than PD, except for sequential reads.
- **A single request isn't faster** on Hyperdisk (slightly slower than PD).
- **Higher limits help parallel I/O** (many processes, conda installs,
  scratch on `/`): under load, requests wait 7.6 ms instead of 71.5 ms.
