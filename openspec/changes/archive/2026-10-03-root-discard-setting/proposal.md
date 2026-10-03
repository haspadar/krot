# Online discard on the root filesystem is an inventory setting

## Why

Cloud images mount the root filesystem with `discard`, so every delete sends an UNMAP to the
virtual disk in the write path. A machine whose `fstrim.timer` already trims weekly gains
nothing from it. Measured 2026-10-03 on a production machine (QEMU disk, sysstat at
10-minute intervals): disk waits of 5–40% at 3–40 writes a second several times a day, with
discard spikes in some of those intervals (1077, 11 246, 13 428 blocks a second against single
digits) and not in others. A checkpoint of 71 buffers took 35.7 s in one stall and 39 requests
timed out after it. The link to discard is partial and unproven; the change is an experiment
measured a week before and a week after.

krot did not touch mounts at all. A one-off edit on the machine would make it unlike the others
with nothing showing it; a setting shows in the inventory and rolls back by one line.

## What Changes

- `common_root_discard`, undefined by default: the role leaves `/etc/fstab` and the mount alone
- `false` removes `discard` from the root line's options and remounts `/` with `nodiscard`;
  refused unless `fstrim.timer` is enabled, so trimming never stops altogether
- `true` adds it back the same way, which is the rollback
- Only the options field of the root line is rewritten; the edited fstab is checked with
  `findmnt --verify`, and a copy of the previous one is kept

## Boundaries

No other mount, no other option, no change for machines that do not set it. The measurement
belongs to the machine's owner.
