# Expose raw machine update facts

## Why

The consumer selects availability-impacting maintenance in its own interface. External
keyword monitors duplicate that responsibility. Restarts and reboots remain manual.

## What changes

- Remove UptimeRobot registration and its inventory variables from updates_monitor
- Keep the secret path and legacy text response semantics
- Negotiate JSON using Accept: application/json on the same path, including collection
  time/failure/freshness, reboot marker/packages, running kernel, all needrestart services
  and the same overdue update count used in text alerts
- Failed or unavailable collection returns null facts rather than healthy empty values;
  stale successful facts retain their collection timestamp and carry stale=true
- Document that package/service/kernel names become visible to holders of the secret URL
- Release a major version because external monitor registration is removed
