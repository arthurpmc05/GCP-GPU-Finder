# gcp_gpu_finder

Find NVIDIA GPU capacity on Google Cloud and keep trying until it is held.

One Python file, standard library only, nothing to install. It signs you in through the Google Cloud CLI (or the metadata server on a Compute Engine VM), checks your project, works out how many GPUs your NVIDIA model or product actually needs, tells you whether quota or availability is what stands in your way, files the exact quota increase if you ask it to, then sweeps regions, zones, machine types and acquisition methods, for days or weeks if needed, taking GPUs as they appear until every one you asked for is yours. Everything it does is printed as it happens and written to an append-only audit log.

## Why It Exists

Getting GPUs on a cloud is two problems wearing one error message. Quota is a limit Google sets on your project; availability is whether Google has free hardware in a zone right now. Most people discover which one is blocking them by reading `ZONE_RESOURCE_POOL_EXHAUSTED` and `QUOTA_EXCEEDED` for an afternoon. This tool separates the two, reads your real limits from the Cloud Quotas API, prints a one-sentence verdict, fixes what can be fixed from your side, and then does the patient part: trying the best option first, then every alternative you allowed, over and over, until the request is fully met.

## What It Does

### Checks Your Quota And Says Exactly What Blocks You

- Reads quota limits and current usage per region and per GPU family from the Cloud Quotas API (falling back to Compute's own quota view and saying so), for the exact machine types and acquisition method you chose, because reservations, on-demand VMs, Spot, flex-start and calendar mode are counted against different quotas.
- Shows headroom per region in VMs and in GPUs, names the binding quota and its usage over limit, and shows the hourly price from the public Cloud Billing catalog beside it.
- Ends the analysis with a verdict line: quota allows the full goal and the loop now hunts capacity; quota stops the plan before capacity matters; or quota caps the plan at a smaller number, so the loop hunts capacity for those and the rest need more quota.
- `plan` does all of this and creates nothing.

### Requests Quota Increases Correctly, Once

- Opt-in (`--quota-request offer` or `file`). Nothing is filed until quota is confirmed to be the limit for your plan and you typed `yes` on a screen that shows each request in full.
- Requests only what the plan still needs: current usage plus the shortfall, in one region (or split across regions with `--quota-split`), never a round number plucked from the air.
- Files each quota once, never re-files or escalates, checks eligibility first (billing, usage history, whether Google takes requests for that quota), lists requests already on file from any tool, and then polls the status of what it filed during the run and in `status`.
- Carries your contact email, use case and justification exactly as you typed them.

### Sizes GPUs For NVIDIA Models In Vertex AI Model Garden

- Lists NVIDIA's models in Vertex AI Model Garden live from the Agent Platform API, every version, with every machine type, GPU type, GPU count and serving setting Google tested for it. Only GPUs Google tested for that model are offered.
- Asks two questions about your traffic: the longest request (prompt plus answer, in tokens) and the peak requests in flight at once, across all copies.
- Reads the model's published architecture and weight size from the repository Model Garden deploys, and estimates how many requests one copy of the model holds at once on each tested machine type: GPU memory left after the weights, over the cache a request needs, capped by Google's own concurrency setting.
- Recommends the total: model copies needed, VM instances needed, GPUs in total, fewest GPUs first, and makes that recommendation the default for every later question. GPU types and machine types that cannot fit the model are hidden and the reason is printed.

### Sizes GPUs For NVIDIA Products On Google Cloud Marketplace

- Knows the NVIDIA products Google documents for Google Cloud: Omniverse Development and Enterprise Workstations, Isaac Sim Development Workstation, Kit App Streaming, BioNeMo and NIM, each with the GPU rule from Google's own page and links to it.
- Reads NVIDIA's Marketplace VM images live from NVIDIA's image project, newest current image per product, with its operating system, CPU architecture, minimum disk and whether Google charges a license fee, and boots your VMs from the one you pick.
- Asks how many workstations, streaming nodes or jobs run at the same time, then recommends machine type, VM count and GPUs in total the same way it does for models.

### Recommends From What Is Available And What You Need

- The GPU model, machine types and GPU total default to the sizing recommendation; the machine types are listed in order of how easy they are to obtain, and the regions that actually offer them are grouped by geography.
- Preferred regions are tried in your order. Fallback regions are ranked by Google's capacity advisor score, then by price, so the loop goes where hardware is most likely to be free and cheapest first.
- Prices are shown per method (on-demand, Spot, flex-start, calendar) for every region and machine type, and an optional hourly spending cap for everything held keeps the loop from buying past your budget.
- The `doctor` command checks sign-in, project, billing, enabled APIs, the IAM permissions each method needs, organization policies, networks and usable regions, and suggests the smallest predefined role that fixes anything missing. Menus grey out what your account cannot do rather than failing later.

### Searches As Narrowly Or As Broadly As You Want

- Narrow: one region, one machine type, one method, one zone at a time; or a cluster layout that only accepts whole groups of VMs in a single zone.
- Broad: regions by name, by group (`asia-pacific`, `europe`) or by prefix (`asia`), a fallback list, an exclusion list, several machine types in preference order, and `all` at any question to open it up to every region or every machine type that offers your GPU.
- Six ways to hold capacity, chosen per run: on-demand reservation, on-demand VMs, Spot VMs, flex-start VMs and flex-start groups (Dynamic Workload Scheduler), and calendar-mode future reservations for the A3 and A4 families.
- Every question accepts a flag, so the same search can be scripted; `--dry-run` runs one full pass of the search without a single write.

### Runs Until The Entire Request Is Met

- Loops for days or weeks, one attempt at a time so a large ladder of regions, zones and sizes is swept every few minutes without hammering your project's rate limits (it reads your real per-region limits and uses a fraction of them).
- Takes capacity as it appears: each attempt asks for exactly what is still missing, sized to the remaining GPUs, the quota headroom in that region and the spending cap, never more than the goal unless you allow overshoot. Held GPUs accumulate across zones, machine types and attempts until held equals goal.
- Options that are quota-bound are parked and re-verified on a schedule instead of being retried uselessly; filed quota requests are polled, and when one is granted the parked options come back into the sweep.
- The live dashboard shows which machine type, zone and method is being tried, the Google call and operation in flight, what comes next and how far the sweep has got; `--plain` gives the same as a line log for `nohup`, `screen` or `tmux`.
- Stop with Ctrl-C at any time: new attempts stop, queued flex-start requests are cancelled so nothing appears later unseen, a summary prints, and you choose to keep or release what was obtained. `resume RUN_ID` picks a stopped run back up; `--maintain` keeps running after the goal and replaces anything Google reclaims.

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

A sized, scripted example: size for an NVIDIA model in Model Garden at a given context length and peak concurrency, search a preferred region with the rest of a continent as fallback, hold the capacity as Spot VMs, and let the tool offer a quota request if quota turns out to be the limit.

```
python3 gcp_gpu_finder.py --workload model --model super-120b-a12b-fp8 --context 8192 --peak 32 \
    --region asia-southeast1 --fallback asia-pacific --method spot --quota-request offer --session logged
```

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

The self-test runs offline and covers the parser, the request planner, the quota verdict, the Model Garden sizing, the audit trail and its file permissions, the token error path, archive extraction safety and the setup helpers. `ruff check gcp_gpu_finder.py` passes with no findings.

## Reporting A Problem

Open an issue with the command you ran, the verdict line and the relevant lines of the audit log (`log --last N`), after reading them for anything you would not share. Tokens never appear in a log; account names, project ids and your answers do.

## License

Apache License, Version 2.0; the full text is in `LICENSE`. Use, change and redistribute it freely, keep the `LICENSE` and `NOTICE` files and the copyright line in the script header with any copy, and mark the files you change. `NOTICE` carries the attribution that section 4(d) of the license requires derivative works to keep.
