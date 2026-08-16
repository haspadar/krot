# Proposal: a failed assert skipped the job silently

## Why

The `cron` role exists for one class of failure: a job stops running while the machine reports
health. That very failure was still present inside the role itself — in four lines that promised
the opposite.

```jinja
# Fail loudly if the directory is gone rather than running from / and blaming
# the command: a release symlink pointing nowhere is a real state after a
# botched deploy.
AssertPathIsDirectory={{ item.working_directory }}
```

The comment promises a loud failure. `Assert*=` does not deliver one: **a failed assert does not
fail the unit**. The job is skipped, the state stays successful, `systemctl --failed` is empty.

Measured on busel (systemd 255, 2026-08-13) with two probe units, not inferred from the
documentation:

| | `AssertPathIsDirectory=/nonexistent` | `WorkingDirectory=/nonexistent`, no assert |
|---|---|---|
| `Result` | **success** | `exit-code` |
| `ExecMainStatus` | **0** | 200 (CHDIR) |
| `ActiveState` | inactive | **failed** |
| lines in `systemctl --failed` | **0** | **1** |

The second column was also verified **under a timer**, not only by hand: a unit with
`OnCalendar=*-*-* *:*:00` landed in `--failed` after its very first firing.

When it fires: `working_directory` is the `current` release symlink, and after a failed deploy it
points nowhere. Exactly the case named in the comment. The job then stops running, while
`list-timers` shows a plausible next start and `--failed` stays quiet. `Persistent=` does not
catch up: the timer did fire, there is nothing to catch up on.

This is a founding defect of the role, reproduced inside the role itself.

### The other half: the assert checked as the wrong user

Found during review and measured on the spot. `Assert*=` is evaluated by PID 1, that is **root**,
while the one working in the directory will be `User=`. On a `0700 root:root` directory the two
diverge:

| unit | result | command |
|---|---|---|
| `AssertPathIsDirectory` + `User=km` | `success`, `--failed` empty | **ran** — from someone else's directory |
| `WorkingDirectory` + `User=km` | `failed`, 200/CHDIR | did not run |
| `WorkingDirectory` + `User=root` | `success` | ran normally |

The first row was verified afterwards on disk (`touch` in `ExecStart`), not by the fields of
`systemctl show`. A job that had lost its directory ran and returned 0 — that is, the assert was
not merely silent, it **let through a whole class of failure**: in systemd `chdir` happens after
`setresuid`, so permissions are checked as the one who will do the work, not as the one who
schedules the job.

## What Changes

`AssertPathIsDirectory=` is removed. A missing directory fails the unit on its own — through
`WorkingDirectory=`, which is already in the unit and stays there.

No code is added: the change is the deletion of four lines. The explanation moves to
`WorkingDirectory=`, because that line is what now provides the behaviour, and the measurement
moves with it. The wrong comment about failure visibility is how mistakes like this multiply, and
it would be believed a second time just as it was believed the first.

## Impact

- **The failure becomes visible.** A job with a broken `working_directory` shows up in
  `systemctl --failed`, and `systemctl status` shows `status=200/CHDIR`.
- **Units on deployed machines are rewritten** — a line leaves the `.service`. A run will report
  `changed`; this does not require restarting the job.
- **No check is lost at run time.** `Assert*` checked the state at start time, not at the time of
  the Ansible run: it caught nothing in advance, and there is nothing to replace it with, nor any
  reason to.
- **A check is gained.** The case "the directory exists, but the user cannot enter it" was skipped
  by the assert entirely, and `WorkingDirectory=` catches it.
- **On a machine with an already broken symlink, `--failed` will become non-empty** after the
  first timer firing. That is exactly the work of this change: the machine was broken before too,
  it just kept quiet.
- The behaviour of jobs with a working `working_directory` does not change.

## Out of scope

The review found seven more remarks about the role (escaping `\` in the unit, `JOB_REPLACE` on
time overrun, log directory permissions with a custom `user`, an orphaned `.service` on retire, no
validation of `schedule`, removal of the manual crontab line from the documentation, README and
defaults disagreeing about `fixed_random_delay`). They are handled separately: those are
improvements, whereas the single item fixed here is the one reproducing the founding defect.
