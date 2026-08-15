# Tasks: a failed assert skipped the job silently

## Measurement (busel, systemd 255, 2026-08-13)
Probe units, installed and removed by hand; `krot-traffic` and `krot-cf-ranges` untouched.

- [x] `AssertPathIsDirectory=/nonexistent` + `systemctl start`: **`Result=success`**,
      `ExecMainStatus=0`, `ActiveState=inactive`, `AssertResult=no`, `systemctl --failed` empty.
      The `start` command itself returned 1 and printed `Assertion failed on job for …` — that
      is, **the failure is visible only to whoever starts it by hand**, and a timer has no such
      channel
- [x] `WorkingDirectory=/nonexistent` without assert: `Result=exit-code`, `ExecMainStatus=200`
      (CHDIR), `ActiveState=failed`, one line in `systemctl --failed`
- [x] The same **under a timer**, not by hand: `OnCalendar=*-*-* *:*:00`, after the first firing the
      unit is in `--failed`. This is the acceptance criterion — a manual start proves nothing, the
      job is started by a timer
- [x] **The assert checks the path as root, not as `User=`** (found during review, measured on the
      spot). Directory `0700 root:root`: with the assert and `User=km` the unit is `success`, and
      the command **ran** — confirmed afterwards on disk, not by `systemctl show` fields. With
      `WorkingDirectory=` and the same `User=km` — `failed`, 200/CHDIR; with `User=root` —
      `success`. So `chdir` happens after `setresuid`, and the removed assert was not only silent
      but also blind to permissions
- [x] Cleaned up afterwards: probe `.service`/`.timer` removed, `daemon-reload`, `reset-failed`;
      `/srv/krot-probe` removed; only `krot-cf-ranges.*` and `krot-traffic.*` remain on the machine,
      `--failed` empty

## The change
- [x] `AssertPathIsDirectory=` removed from `job.service.j2` along with the `[Unit]` condition
      section
- [x] Explanation and measurement moved to `WorkingDirectory=` — to the line that now provides the
      failure
- [x] `defaults/main.yml`: the description of `working_directory` says that a symlink pointing
      nowhere fails the job rather than running it from `/`
- [x] README: the same in the section on periodic jobs
- [x] CHANGELOG: 5.1.1, noting that units on deployed machines will be rewritten

## Verification
- [x] The template renders both ways: with `working_directory` and without it — in the second case
      `WorkingDirectory=` does not appear at all, and the unit is still valid
- [x] **Acceptance on the unit rendered by the role.** That very file, produced by the fixed
      template, was placed on busel with a `working_directory` pointing nowhere and wired to a
      timer. After the firing: `status=200/CHDIR`, `ActiveState=failed`, a line in
      `systemctl --failed`. What was checked was not "the assert is gone" but the visibility of the
      failure
- [x] Probe removed, `krot-traffic` and `krot-cf-ranges` in place, `--failed` empty
- [x] `yamllint`, `ansible-lint` (profile production) clean
- [ ] Do not apply on busel: the role is installed and working there, the sites are up. A run is a
      separate decision after the merge
