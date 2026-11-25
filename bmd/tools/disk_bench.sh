#!/usr/bin/env bash
# Compare GCP disks (PD vs Hyperdisk) with fio.
# Usage: ./disk_bench.sh /mnt/pd /mnt/hyperdisk
# Each argument is a directory on a mounted filesystem backed by the disk to test.
# Optional env: SIZE=4G RUNTIME=30
# Results so far: bmd/README.md, "Boot disk speed".

set -euo pipefail
command -v fio >/dev/null || { sudo apt-get update -qq; sudo apt-get install -y -qq fio; }

SIZE=${SIZE:-4G}
RUNTIME=${RUNTIME:-30}

run() { # name file rw bs iodepth numjobs
  echo "--- $1 ---"
  fio --name="$1" --filename="$2" --size="$SIZE" --runtime="$RUNTIME" --time_based \
      --direct=1 --ioengine=libaio --group_reporting \
      --rw="$3" --bs="$4" --iodepth="$5" --numjobs="$6" \
    | grep -E "^\s*(read|write):|^\s+lat \(|99.00th" || true
}

for dir in "$@"; do
  f="$dir/fio.testfile"
  echo
  echo "=================== $dir ==================="
  df -h "$dir" | tail -1

  echo "Pre-writing $SIZE test file (one time, not measured)..."
  fio --name=prefill --filename="$f" --size="$SIZE" --rw=write --bs=1M \
      --iodepth=32 --direct=1 --ioengine=libaio >/dev/null

  run "rand-read-4k-IOPS"   "$f" randread  4k 64 4
  run "rand-write-4k-IOPS"  "$f" randwrite 4k 64 4
  run "seq-read-1M-MBps"    "$f" read      1M 32 4
  run "seq-write-1M-MBps"   "$f" write     1M 32 4
  run "latency-4k-qd1"      "$f" randread  4k 1  1
  rm -f "$f"
done
