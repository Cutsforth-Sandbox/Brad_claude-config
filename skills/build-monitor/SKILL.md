---
name: build-monitor
description: Monitor a long-running background build or command — periodic progress,
  stage, new warnings/errors, and a completion summary — without babysitting the
  terminal. Use when the user asks to monitor a build/job/long command running in the
  background, whether Claude started it or the user already has it running elsewhere.
---

# Build Monitor

Tie the watch to a running process, not a clock: a tracked background task plus one
`Monitor` polling its log.

## Why not ScheduleWakeup or /loop

- `ScheduleWakeup` outside an active `/loop` isn't guaranteed to fire.
- `/loop`'s fixed-interval mode routes to `CronCreate`; those jobs have not fired
  reliably.
- Both depend on the harness waking the session at a future timestamp with no live
  process behind it, and give no signal that anything is actually armed.

## 1. Get the command running and tracked

- **Claude starts it**: launch with `Bash` (`run_in_background: true`), wrapping the
  command so it self-reports its own PID without a second layer of backgrounding:
  `sh -c 'echo "MONITOR_PID:$$"; exec <command>' > <logfile> 2>&1`. `exec` replaces the
  shell in place, so the printed PID stays valid for the command's entire life. Never
  wrap it in `nohup cmd &` instead — that backgrounds it a second time, the wrapper
  exits immediately, and the harness reports the task "completed" while the real
  process keeps running untracked. Read `PID` back with
  `grep -m1 '^MONITOR_PID:' <logfile> | cut -d: -f2`.
- **It's already running**: skip launching. Get the log file path from the user (or
  locate it). For the PID, don't reach for `pgrep` — it isn't installed in Git Bash on
  Windows. Use `ps -ef | grep -F "<distinctive part of the command>" | grep -v grep`
  instead (universally available) and read the PID column. If more than one process
  matches, ask the user which one rather than guessing — a wrong PID makes the liveness
  check in step 3 fire on an unrelated process's exit.

Done when the log path is known and confirmed live — task output shows it running, or a
fresh `tail` on the log is still growing.

## 2. Derive the signals from the real log

Read the log's actual output — don't guess these blind, and ask the user only if
inspection leaves one genuinely unclear:

- **Progress pattern** — whatever this log actually reports: percent, step count, or
  line count.
- **Percent-complete** (feeds the ETA in step 3), when derivable:
  - Already a percentage (`42%`) → the integer.
  - A step count (`N/M`) → `N*100/M`, unless `M` is `0` or not a positive integer — then
    treat it the same as "not derivable" below, never divide by it.
  - An unbounded line count with no known total → not derivable; report `unknown` for
    both ETA fields rather than fabricate one.
  - Whatever integer comes out, the template forces base-10 (`$((10#$percent))`) before
    using it — a bare `08` or `09` is octal to both `$(())` arithmetic and `printf`,
    which would otherwise crash or silently misprint. Keep that conversion; don't
    "simplify" it away.
- **Progress detail** — descriptive text riding alongside the percent/step token (e.g.
  the filename being compiled), with that token stripped out. Empty if the log carries
  none.
- **Completion pattern** — a regex alternation covering every terminal state, not just
  success: the success marker AND every visible failure signature (`Error`, `Traceback`,
  `FAILED`, `panic`, etc.). The template checks it only against each cycle's newly
  written lines, not the whole log — so a stray match in an early banner or an
  intermediate report can't trigger a false finish. `PID` (when set) backs this up: the
  loop also ends if that process has exited even with no matching log line, catching a
  silent crash the regex didn't anticipate.

Done when every pattern above has been tried by hand against the log's current content
and actually matches.

## 3. Arm one Monitor

Fill the template below with the results of steps 1–2 and a poll cadence of roughly 1/10
of the expected run time, kept between 30 seconds and 5 minutes (30s for a 5-minute job,
5 minutes for anything over 50 minutes), so each monitor window reports at least six
times. Too fast risks the harness auto-stopping a noisy monitor; too slow means nothing
arrives before it's already done.

`Monitor`'s `timeout_ms` defaults to 300000 (5 minutes) and is capped at 1800000
(30 minutes; 10 in single-prompt `-p` runs); there is no persistent mode. Set it to the
expected duration plus a buffer, up to that cap. A run that can outlast the cap is
re-armed on each expiry notice with the same template, filling `START_EPOCH` and
`LASTCHECKPOINT` from the last `checkpoint = … || start_epoch = …` line the expired
monitor emitted. That line can arrive as its own notification, separate from the progress
lines above it. The new monitor resumes at the first line the old one had not finished
examining. A monitor killed mid-cycle re-reads that cycle's lines, so a warning near the
expiry can be counted twice; no line is skipped.
Give `description` something specific; it's what shows up in every notification.

```bash
LOG=<log path from step 1>
PID=<pid from step 1, if one was captured>
START_EPOCH=<first arm: $(date +%s); re-arm: start_epoch from the last checkpoint line>
LASTCHECKPOINT=<first arm: $(wc -l < "$LOG"); re-arm: checkpoint from the last checkpoint line>
fmt_dur() { printf '%02d:%02d:%02d' "$(($1/3600))" "$((($1%3600)/60))" "$(($1%60))"; }
while true; do
  now_epoch=$(date +%s); elapsed=$(( now_epoch - START_EPOCH ))
  total=$(wc -l < "$LOG")
  new_lines=""
  [ "$total" -gt "$LASTCHECKPOINT" ] && new_lines=$(sed -n "$((LASTCHECKPOINT + 1)),${total}p" "$LOG")
  LASTCHECKPOINT=$total
  progress_line=$(grep -oE "<progress pattern from step 2>" "$LOG" | tail -1)
  raw_percent=$(<percent-complete extraction from step 2, integer 0-100 or empty>)
  percent=""; [ -n "$raw_percent" ] && percent=$((10#$raw_percent))
  progress_detail=$(<progress_line with the percent/step token stripped, or empty>)
  new_warn=$(grep -icE "WARNING|^ERROR" <<< "$new_lines")
  if [ -n "$percent" ]; then percent_display=$(printf '%02d' "$percent"); else percent_display="??"; fi
  if [ -n "$percent" ] && [ "$percent" -gt 0 ] 2>/dev/null && [ "$elapsed" -gt 0 ]; then
    remaining=$(( elapsed * (100 - percent) / percent ))
    completion_epoch=$(( now_epoch + remaining ))
    eta_remaining=$(fmt_dur $remaining)
    if [ "$(date -d "@$completion_epoch" '+%Y-%m-%d')" = "$(date '+%Y-%m-%d')" ]; then
      est_completion=$(date -d "@$completion_epoch" '+%H:%M:%S')
    else
      est_completion=$(date -d "@$completion_epoch" '+%Y-%m-%d %H:%M:%S')
    fi
  else
    eta_remaining="unknown"; est_completion="unknown"
  fi
  printf '[%s] elapsed = %s  ||  percent = [%s%%]\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$(fmt_dur $elapsed)" "$percent_display"
  printf 'eta_remaining = %s  ||  est_completion = %s\n' "$eta_remaining" "$est_completion"
  printf 'progress_detail = %s\n' "$progress_detail"
  printf 'new_warnings = %s\n' "$new_warn"
  log_done=false; grep -qE "<completion pattern from step 2>" <<< "$new_lines" && log_done=true
  proc_dead=false; [ -n "$PID" ] && ! kill -0 "$PID" 2>/dev/null && proc_dead=true
  if [ "$log_done" = true ] || [ "$proc_dead" = true ]; then
    echo "FINISHED -- final lines:"; tail -30 "$LOG"; break
  fi
  printf 'checkpoint = %s  ||  start_epoch = %s\n' "$LASTCHECKPOINT" "$START_EPOCH"
  sleep <cadence>
done
```

`new_lines` is exactly the newline-terminated lines between the checkpoint and the
`wc -l` count taken at the top of the cycle, and the checkpoint advances to that count. A
line still being written stays for the next cycle, so a completion line is never consumed
half-written. The first arm starts the checkpoint at the log's current length, so text
already in the log (a startup banner, an earlier error) never ends the watch.

ETA fields extrapolate linearly from percent-complete and are estimates, not guarantees
— real builds usually aren't constant-rate (a slow link/package step at the end throws
off a rate learned from fast parallel compiles). `est_completion` includes the calendar
date only when the estimate lands on a different date than the current check, not just
when more than 24 hours away — a build checked at 23:40 with an ETA of 01:33 the next
morning gets the date-qualified form. `date -d "@<epoch>"` is GNU-date syntax
(Git Bash/Linux); macOS/BSD `date` needs `-r <epoch>` instead.

This loop has no independent stall detector: if the completion pattern never matches
and `PID` (if set) never exits, it polls until `Monitor`'s timeout, and each re-arm
repeats that. Getting the completion pattern right in
step 2 is what bounds this, not the timeout.

After arming, tell the user the `Monitor` description in one line so they know what's
watching and can `TaskStop` it to cancel early.
