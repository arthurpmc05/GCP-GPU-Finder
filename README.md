# gcp_gpu_finder

Find NVIDIA GPU capacity on Google Cloud and keep trying until it is held.

One Python file, standard library only, nothing to install. It signs you in through the Google Cloud CLI (or the metadata server on a Compute Engine VM), checks your project, asks what the GPUs will run, shows quota and availability as two separate things, then sweeps regions, zones, machine types and acquisition methods, for days if needed, until the GPUs you asked for are yours. Everything it does is printed as it happens and written to an append-only audit log.

## Requirements

- Python 3.9 or newer. No third-party packages.
- A Google Cloud account with a project, or a project to create one in. If `gcloud` is missing, `setup` offers to install Google's official archive for your OS and CPU, without administrator rights.
- Permissions are listed in the file header under PERMISSIONS and checked for you by `doctor`; `roles/compute.viewer` is enough to plan.

## Quick Start

```
python3 gcp_gpu_finder.py setup      # install gcloud if needed, sign in, pick the project, enable APIs
python3 gcp_gpu_finder.py plan       # quota, availability and options for what you want; creates nothing
python3 gcp_gpu_finder.py            # the wizard asks everything, then holds the capacity
```

Every question has a default, a skip (`>`), a skip-all (`>>`), a back (`<`) and a flag, so the same run can be scripted. Ctrl-C stops new attempts, prints a summary and asks whether to keep or release what was obtained.

## Commands

- `plan` analysis only: quota, availability, prices and the options that fit.
- `setup` install gcloud, sign in, choose the project, enable the APIs, create a network if the project has none; each step asks first.
- `doctor` environment and permission report, with the exact command or link that fixes each finding.
- `run --config F` replay a saved run's answers; add `--yes --session logged` for an unattended run.
- `status RUN_ID`, `resume RUN_ID`, `release RUN_ID` what a run holds, continue a stopped run, delete only what that run created.
- `log [RUN_ID|PATH]` read an audit log back; `knobs` every tunable setting and its default; `self-test` offline checks of this file.

`--help` on any command lists its flags. The file header is the full manual.

## How It Holds Capacity

You choose one method per run. All of them create real, billed resources in your project.

- `reservation` on-demand reservation, capacity held in your name with no VMs running yet.
- `vms` standard on-demand VMs created in bulk.
- `spot` Spot VMs, much cheaper, reclaimable by Google at any time.
- `flex` and `flex-group` flex-start (Dynamic Workload Scheduler) VMs, queued per request, discounted, deleted after their run time.
- `calendar` calendar-mode future reservation for the A3 and A4 families, no quota needed, billed for the whole period.

## What It Never Does

- Install software, sign in, enable an API or create a network without asking first (`--install-missing` is the only way to pre-approve those).
- Link billing, change IAM, edit organization policies, or touch a resource it did not create. Everything a run creates carries the label `gpu-finder-run=<run id>` or a name starting with `gpuf-<run>`, and `release` deletes only those.
- File a quota increase unless you opted in, quota is confirmed to be the limit, and you typed `yes` on a screen showing the exact request. It files each quota once and never re-files or escalates.
- Store, print or log an access token, a key or a password.

## Credentials

The tool never handles long-lived credentials itself. It holds short-lived access tokens in memory and nothing else.

- Tokens come from `gcloud auth print-access-token` (optionally with `--impersonate-service-account`), from the Compute Engine metadata server, or from `GPUF_ACCESS_TOKEN` when you supply one. They are refreshed on a schedule and never written to disk, the audit log or the screen. If the token command fails, only its error text is reported, never its output.
- A key file (`--key-file`) is handed to `gcloud auth login --cred-file` and read by the tool only for its type, account and project. When another account is already active, the sign-in goes into a separate gcloud configuration (`GPUF_SETUP_GCLOUD_CONFIG`, default `gpu-finder`) so your own setup is untouched.
- gcloud's own token cache lives where gcloud keeps it; in an ephemeral session it lives in a tmpfs copy that is deleted when the session ends.
- Network calls go to `*.googleapis.com`, `huggingface.co` (a chosen model's public architecture file, no token), the metadata server on GCE, and `dl.google.com` only when setup installs gcloud. `HTTPS_PROXY`, `NO_PROXY`, `--ca-bundle` and `GPUF_CA_BUNDLE` are honored. The gcloud download is verified over TLS; set `GPUF_GCLOUD_SHA256` to the checksum Google publishes to pin it.

## Sessions And Files

Before anything is read or written the tool asks whether the session is `logged` or `ephemeral` (`--session`, or `GPUF_SESSION`).

- `logged` writes under `GPUF_HOME` (default `~/.gcp_gpu_finder`): `setup.json`, `logs/<command>-<time>-<pid>.jsonl`, `runs/<run id>/{state.json,config.json,events.jsonl,summary.txt}` and `cache/`. Runs can be resumed, released and read back by id.
- `ephemeral` writes nothing to this computer. Run state, answers and caches stay in memory; gcloud runs on a private copy of its configuration in a tmpfs folder (`/dev/shm`, `$XDG_RUNTIME_DIR` or `GPUF_EPHEMERAL_DIR`) that is deleted at exit, including after Ctrl-C or SIGTERM. Capacity obtained is still real and is found later by its label. Swap without encryption can still leave traces of RAM on disk; that is outside the tool's control.

Audit logs, run state and `setup.json` are created readable by your user only, in folders created the same way. The log records the signed-in account and project, your user name, working folder and command line, every answer, and at trace level the full body of each write request (for a quota request that includes the contact email and justification you gave). Treat a log as yours before sharing it.

## Configuration

Every limit, interval, path, color and threshold is an environment variable with a documented default; `python3 gcp_gpu_finder.py knobs` prints all of them with their meaning. Nothing needs editing in the source. Flags override saved answers, which override knob defaults.

## Unattended Runs

```
python3 gcp_gpu_finder.py run --config ~/.gcp_gpu_finder/runs/<run id>/config.json --yes --session logged
```

Add `--install-missing` and `--key-file` to let a scripted run install gcloud and sign in. For runs of days, sign in with a service account (`--impersonate-service-account`), run under `nohup`, `screen` or `tmux`, and use `--plain` for a line log. Exit codes: 0 goal reached or plan finished, 1 error before the run, 2 stopped before the goal, 3 blocked for a named reason, 130 cancelled at a question.

## Verifying The File

```
python3 -m py_compile gcp_gpu_finder.py
python3 gcp_gpu_finder.py self-test
```

The self-test runs offline and covers the parser, the request planner, the audit trail and its file permissions, the token error path, archive extraction safety and the setup helpers. `ruff check gcp_gpu_finder.py` passes with no findings.

## Reporting A Problem

Open an issue with the command you ran, the verdict line and the relevant lines of the audit log (`log --last N`), after reading them for anything you would not share. Tokens never appear in a log; account names, project ids and your answers do.

## License

Apache License, Version 2.0; the full text is in `LICENSE`. Use, change and redistribute it freely, keep the `LICENSE` and `NOTICE` files and the copyright line in the script header with any copy, and mark the files you change. `NOTICE` carries the attribution that section 4(d) of the license requires derivative works to keep.
