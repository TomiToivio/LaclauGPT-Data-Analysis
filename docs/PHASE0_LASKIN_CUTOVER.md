# Phase 0 Laskin cutover

Issue #175 intentionally does not assume that a coding agent has shell access to Laskin.

## Operator checklist: turn Phase 1 OFF

Run these checks on Laskin before enabling Phase 0. Record the output somewhere private if it contains machine-specific paths or credentials.

```bash
# cron
crontab -l
systemctl --user list-timers --all
systemctl --user list-units --type=service --all

# long-running jobs
ps aux | grep -Ei 'laclaugpt|data-collection|data-analysis|data-visualization'
tmux ls || true
screen -ls || true
```

Identify Phase 1 jobs belonging to the Data Collection, Data Analysis and Data Visualization repositories. Disable only their runtime launch points. Do not delete code or configuration.

For cron, comment the relevant Phase 1 entries and save the previous crontab. For systemd user timers/services, use `systemctl --user disable --now <unit>`. For tmux/screen/manual processes, stop the verified Phase 1 process cleanly.

Re-run the inspection commands and verify that no Phase 1 job is still mutating the shared dataset.

## Phase 0 remains default-off until that verification

After Phase 1 shutdown is verified:

```bash
cd /path/to/LaclauGPT-Data-Analysis
git switch phase-0
export MONGO_URI='...'
export MONGO_DB_NAME='...'
export LACLAUGPT_PROJECT_ID='ai26'
export OLLAMA_MODEL='gemma4:12b'

python laclaugpt/laclaugpt_process.py --limit 1 --dry-run
python laclaugpt/laclaugpt_process.py --limit 1
```

A deliberately boring cron entry can then run the processor, for example:

```cron
*/10 * * * * cd /path/to/LaclauGPT-Data-Analysis && /path/to/python laclaugpt/laclaugpt_process.py --limit 100 >> data/logs/phase0-cron.log 2>&1
```

## Re-enable Phase 1

Reverse only the runtime changes recorded during shutdown: restore the saved cron entries, re-enable the exact systemd units, or restart the exact verified manual launch command.

Phase 0 does not delete Phase 1 code.

## Deliberately not implemented in Phase 0

No frame analysis, OCR, Whisper, OpenCV, Redis, CSC Allas, SQLite core state, event bus, worker queue, distributed lock, DNA, SNA, graph/RDF, or multimodal processing is required by the minimal RSS/text path.
