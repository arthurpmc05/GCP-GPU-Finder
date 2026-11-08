#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Arthur Perotti
"""
gcp_gpu_finder.py: find NVIDIA GPU capacity on Google Cloud and keep trying until it is held.

A single, self-contained file. Python 3.9 or newer, standard library only, no pip installs.
It signs in through the Google Cloud CLI (gcloud), or through the metadata server when it runs
on a Compute Engine VM. If gcloud is missing, it offers to install Google's official archive
for your computer, then to sign you in. Read this header before you run it.

WHAT IT DOES
  0. Sets up what is missing, asking before each step: finds gcloud even when it is not on
     PATH or installs it (no administrator rights), signs it in (browser or key file), lets you
     pick the project, enables the APIs it uses, and creates a VPC network if the project has
     none. Billing is shown and re-checked, never linked for you: it decides who pays.
  1. Checks your environment: gcloud sign-in, project, billing, enabled APIs, the IAM
     permissions each acquisition method needs, organization policies, networks, and the
     regions your project can use. Every problem comes with the exact command or link to fix it.
  2. Asks what the GPUs will run: an NVIDIA model in Vertex AI Model Garden (read live from the
     Agent Platform API, with the machine types Google tested), an NVIDIA product on Google Cloud
     (Omniverse and Isaac Sim workstations, Kit App Streaming, BioNeMo, NIM, and NVIDIA's
     Marketplace VM images read live), or nothing in particular. For a model it asks your longest
     request and peak requests at once, then lists only the machine types that fit and recommends
     the GPU total: model copies needed, VM instances needed, GPUs in total.
  3. Asks the rest: GPU model and total (the recommendation is the default), machine types,
     independent VMs or same-zone clusters, regions, how to hold the capacity, and for VMs the
     operating system from Google's current public images for that CPU, boot disk and network.
  4. Shows quota and availability as two separate things. Quota is a limit Google sets on your
     project; availability is whether Google has free hardware right now. The verdict line says
     which of the two stands between you and the GPUs.
  5. Loops, for days or weeks if needed, trying the best options first (preferred region and
     machine type), then the alternatives you allowed, until the requested GPUs are held. The
     live view shows, as it happens, which machine type, zone and method is being tried, the
     Google call and operation in flight, what comes next, and how far the sweep has got.

TERMS (as Google Cloud uses them)
  VM instance   one Compute Engine VM of one machine type, e.g. g4-standard-96 (2 x RTX PRO 6000)
  machine type  fixes the vCPUs, memory and the number of attached GPUs of a VM
  model copy    one running server of a model on the GPUs it needs inside one VM; Agent Platform
                (Vertex AI) calls each VM serving a deployed model a replica
  GPUs in total VM instances x GPUs per VM; quota and the goal are counted in GPUs

LOOK
  A dark grey background with NVIDIA green accents; blue for notices and what is happening now,
  yellow for warnings and alerts, red for errors. --theme terminal (or GPUF_THEME=terminal) keeps
  your terminal's own colors; NO_COLOR turns color off. Every color is a GPUF_THEME_* knob.

HOW IT HOLDS CAPACITY (you choose each run)
  reservation   On-demand reservation: capacity held in your name with no VMs running yet.
                Billed like running VMs while it exists. Needs standard GPU quota.
  vms           Standard on-demand VMs, created in bulk. Billed while they exist.
  spot          Spot VMs: much cheaper, but Google can reclaim them at any time.
  flex          Flex-start VMs (Dynamic Workload Scheduler): queued up to 2 hours per request,
                run up to 7 days, discounted. A2, G2, G4 and N1 only.
  flex-group    Flex-start group: a managed instance group resize request that creates all
                VMs of a group at once, when all are available.
  calendar      Calendar-mode future reservation for A4, A3 Ultra, A3 Mega, A3 High 8-GPU and
                A3 Edge: reserve 1 to 90 days ahead, no quota needed, billed for the whole period.

WHAT IT NEVER DOES
  - It never installs software, signs in, enables an API or creates a network without asking
    first (unattended runs only with --install-missing). It never links billing, changes IAM,
    edits organization policies, or touches resources it did not create. Everything a run creates
    carries the label gpu-finder-run=<run id> (VMs) or a name starting with gpuf-<run>
    (reservations, groups, templates), and `release` deletes only those.
  - It never files a quota increase unless you opted in, quota is confirmed to be the limit for
    your plan, and you typed "yes" on a screen that shows each request. It requests only current
    usage plus what the plan still needs, files each quota once, and never escalates or re-files.
  - It never stores or prints your access token, a key or a password (see TRANSPARENCY).

KEPT OR EPHEMERAL (asked before anything runs; --session logged|ephemeral, or GPUF_SESSION)
  logged      The audit log, caches of what Google returned, and each run's state are kept in
              GPUF_HOME, so a run can be resumed, released or checked by its id, and read back.
  ephemeral   Nothing is saved and nothing is logged on this computer; the screen is the only record.
              What the tool would write (caches, run state, answers, reports) is kept in memory.
              gcloud runs on a private copy of its configuration in a memory folder (/dev/shm, then
              $XDG_RUNTIME_DIR, or GPUF_EPHEMERAL_DIR; only a tmpfs mount is accepted) and is told
              to write no logs, update checks, survey prompts or usage reports; its token cache, a
              sign-in made in the session, and a gcloud installed for the session live there, and the
              folder is deleted when the session ends, also after Ctrl-C or a terminate signal. Its
              own configuration folder is not changed. A tmpfs lives in RAM, so nothing lands on a
              disk unless the operating system swaps memory out; a computer with swap enabled and
              without encrypted swap can still leave traces that way. Where no memory folder exists,
              gcloud is not run at all and sign-in uses GPUF_ACCESS_TOKEN or a VM's metadata server.
              Caches from earlier sessions are read, never written. Capacity obtained is real and
              billed: it carries the label
              gpu-finder-run=<run id>, and `release RUN_ID --project P` and `status` find it by that
              label. A stopped ephemeral run cannot be resumed; `resume` is always logged, because a
              saved run's state must record what is obtained.
  An unattended run must name one; `ask` (the default) asks before anything is read or written.

TRANSPARENCY AND AUDIT
  Every step says what it does and why, which Google API, file or command it uses, what it found
  and how long it took; every check names the API that answered it. Nothing runs unseen.
  Screen (--verbosity, or GPUF_VERBOSITY; default normal):
    quiet     the audit log's path, questions, results, warnings and errors (-q)
    normal    every step and check, and where each read comes from: a cache file with its age,
              or the Google API and method
    detailed  also each Google call (method, path, status, time, bytes, and a request body short
              enough to fit, GPUF_DETAIL_BODY_CHARS), each file read or written, each command run (-v)
    trace     also the whole body of every longer request sent (-vv)
  Audit log (--log-level normal|detailed|trace, or GPUF_LOG_LEVEL; default trace): one JSON line
    per record, for every session in logs/<command>-<time>-<pid>.jsonl and, once a run exists, in
    runs/<run id>/events.jsonl as well. The live dashboard shows what is happening now instead of
    step lines; the log records every step regardless. Every question's answer is recorded, marked
    when it was replayed after going back or skipped by >>, and so is each shortcut used. Read a
    log back with `log`.
  Never recorded: an access token (gcloud's token output is withheld by name, and a failed token
    call reports only gcloud's error text), a key, a password. A credential file is read for its
    type, account and project only. Other command output is recorded in part (the end of it; an
    installer's whole output goes to its own log file, named in the record). A failure to write the
    audit log is printed, once per file.
  Recorded, so treat the log as yours: the signed-in account and project, your user name, working
    folder and command line (the session record), every answer you typed, and at trace level the
    whole body of each write request, which for a quota request includes the contact email and
    justification you gave. Log files, run state and setup.json are created readable by your user
    only, inside folders created the same way; reports, caches and summaries meant to be shared
    are world-readable. Share a log knowingly.

SKIPPING, GOING BACK AND OTHER SHORTCUTS
  While questions are asked, a bar stays on the last two rows of the terminal; the text scrolls
  above it. Type a shortcut at any question, then Enter:
    >         skip this question: take its no-preference answer, so anything available counts (any
              operating system and its newest version, the smallest disk the image allows, any subnet,
              every region offering the machine types, no exclusions, no cap), or its default when it
              has none. A gray line under each question says what skip, all and none answer there.
    >>        skip this and every later question the same way and go to the search (to the plan in
              `plan`). Each skipped answer is shown. A question that cannot be skipped (one without a
              default) is asked, and skipping goes on after it. "Start the run now?" is always asked.
    all       every option, where the question offers it: all machine types, all regions
    none      no option, where the question offers it: no fallback, no exclusions, no spending cap,
              no workload sizing. Where all or none makes no sense (one GPU type, one image, one way
              of holding capacity per run), the question says why and is asked again.
    <         back one question. The screen is cleared, your earlier answers are replayed with what
              they showed, and that question is asked again with your answer as its default. Back
              from after a >> returns to the question where >> was typed.
    <<        start the questions over, each with its usual default
    ?         list the shortcuts, what skip, all and none mean at this question, and your answers
    Ctrl-C    quit; nothing is created in Google Cloud before you confirm it
  A confirmation that must be typed (start the run, file a quota request, commit to a calendar
  reservation) is never skipped.
  Going back works from the first planning question to "Start the run now?", including the quota
  request screen, until a quota request is filed: after that, going back or starting over would
  file it again, so both are refused. Sign-in and the environment checks are not repeated.
  The bar needs a terminal of GPUF_FOOTER_MIN_ROWS rows (default 12); GPUF_FOOTER=off hides it,
  and the shortcuts still work. It follows a resize, gives its rows back to the live dashboard,
  and is cleared on exit, Ctrl-C, a terminate signal or a closed terminal.

COMMANDS
  python3 gcp_gpu_finder.py                     interactive run (the wizard asks everything)
  python3 gcp_gpu_finder.py plan                analysis only: quota, availability, options
  python3 gcp_gpu_finder.py setup               install gcloud, sign in, pick the project, enable APIs
  python3 gcp_gpu_finder.py doctor              environment and permission report only
  python3 gcp_gpu_finder.py run --config F      replay a saved run unattended (add --yes --session logged)
  python3 gcp_gpu_finder.py status RUN_ID       what a run holds and requested
  python3 gcp_gpu_finder.py resume RUN_ID       continue a stopped run
  python3 gcp_gpu_finder.py release RUN_ID      delete what that run created (asks first)
  python3 gcp_gpu_finder.py self-test           offline checks of this file's logic
  python3 gcp_gpu_finder.py knobs               every tunable setting and its default
  python3 gcp_gpu_finder.py log [RUN_ID|PATH]   read an audit log back (--kinds, --last, --list)
  Add --help to any command for its flags. Every prompt has a flag, so runs can be scripted.

STOPPING
  Ctrl-C or q: stops new attempts, cancels queued flex requests, prints a summary, then asks
  whether to keep or release what was obtained (default keep). A second Ctrl-C exits at once;
  a request Google was still answering is found by name on `resume` and never made twice.
  Closing the terminal or SIGTERM: same as Ctrl-C without the question; obtained capacity is kept.
  Queued requests are cancelled so nothing appears later unseen.
  The run also stops by itself, with the fix, when every option is blocked by something waiting
  cannot change (a missing permission, a disabled API, a region the project cannot use).

EXIT CODES
  0 goal reached or plan finished   1 error before the run   2 stopped before the goal
  3 blocked (every option refused for a reason named on screen)   130 cancelled at a question

LONG RUNS
  Sign in with a service account (--impersonate-service-account) for runs of days: some
  organizations make people sign in again every few hours. Run it under nohup, screen or tmux,
  or on a small VM, with --plain for a line log. Attempts are made one at a time, so a large
  ladder (many regions, zones and sizes) is swept every few minutes, gently.

SERVICE ACCOUNT ON VMs
  VMs are created with no service account attached, which avoids the actAs permission and the
  "default service account disabled" failure. --vm-service-account EMAIL attaches one; the
  preflight checks iam.serviceAccounts.actAs on it first.

PERMISSIONS (checked for you by `doctor`; menus grey out what you cannot do)
  read and plan   compute.{regions,zones,machineTypes,acceleratorTypes,instances,reservations}.list,
                  compute.disks.list, resourcemanager.projects.get (roles/compute.viewer covers it)
  quota read      cloudquotas.quotas.get (roles/cloudquotas.viewer)
  quota request   cloudquotas.quotas.update (roles/cloudquotas.admin)
  reservation     compute.reservations.{create,delete,get,list}
  vms, spot, flex compute.instances.{create,delete,get,list,setLabels}, compute.disks.create,
                  compute.subnetworks.use
  flex-group      the above plus compute.instanceTemplates.* and compute.instanceGroupManagers.*
  calendar        compute.advice.calendarMode, compute.futureReservations.*
  setup fixes     serviceusage.services.enable (enable APIs), compute.networks.create (network)
  Google's live role list is read to suggest the smallest predefined role for anything missing.

SETUP (runs by itself when something is missing; `setup` runs it on purpose)
  gcloud     Found on PATH, in the folder setup remembered, or in a standard install folder. If
             none exists: Google's archive for this OS and CPU from dl.google.com, unpacked into
             GPUF_GCLOUD_DIR (default ~/google-cloud-sdk) after a free-space and path check, then
             Google's install script, which adds gcloud to your shell profile only if you agree.
             The download is trusted on TLS to dl.google.com (your CA bundle with --ca-bundle);
             its sha256 is shown and recorded in setup.json, and GPUF_GCLOUD_SHA256 set to the
             checksum Google publishes makes a mismatch refuse the archive. GPUF_GCLOUD_ARCHIVE_BASE
             changes where the archive comes from: point it only at a mirror you control.
  sign-in    gcloud auth login in a browser (a link to open elsewhere on a machine without one),
             or a service-account key / workload identity file (--key-file). When another account
             is already active, the key file signs in through a separate gcloud configuration
             (GPUF_SETUP_GCLOUD_CONFIG, default gpu-finder) so your own setup stays as it was.
  project    Chosen from the projects your account can see, then remembered.
  APIs       compute (required), cloudquotas, cloudbilling, cloudresourcemanager, iam,
             serviceusage and aiplatform (Model Garden), enabled in one batch (needs
             roles/serviceusage.serviceUsageAdmin).
  network    An auto-mode VPC network (GPUF_SETUP_NETWORK, default "default") with no firewall
             rules, offered only when the project has no subnet at all.
  billing    Shown with the accounts you can link and re-checked; linking stays your decision.
  Unattended: add --install-missing (and --key-file) to let a scripted run do the same.

FILES IT WRITES (default ~/.gcp_gpu_finder, change with GPUF_HOME)
  setup.json                  where gcloud is, the gcloud configuration and project setup chose
  logs/<cmd>-<time>-<pid>.jsonl  the audit log of each session, rotated and gzipped by size
  logs/doctor-<time>.json     the report of each `doctor`
  runs/<run id>/state.json    what was requested, held, pending and filed (atomic writes)
  runs/<run id>/config.json   your answers, replayable with `run --config`
  runs/<run id>/events.jsonl  the run's audit log: every step, check, call, file, command and
                              decision from the moment the run exists, rotated and gzipped
  runs/<run id>/summary.txt   the final summary
  cache/                      catalog, Model Garden, Marketplace and OS image lists, prices and
                              role lists, refreshed on a schedule

WHERE NVIDIA INFORMATION COMES FROM
  Models        Vertex AI Model Garden, publisher GPUF_MODEL_GARDEN_PUBLISHER (default nvidia), through
                the Agent Platform API: versions, and every machine type, GPU type, GPU count and
                serving setting Google tested. Only those GPUs are offered for a model.
  Requests per  estimated from the model's own published architecture and weight size (the
  copy          repository Model Garden deploys, its MODEL_ID), at the cache format and memory share
                Google's tested configuration sets, capped by its --max-num-seqs.
  Products      NVIDIA's Marketplace VM images from image project GPUF_MARKETPLACE_IMAGE_PROJECT, read
                live; Omniverse, Isaac Sim, Kit App Streaming, BioNeMo and NIM from Google's pages
                about them (no Google API lists Marketplace products), each with its GPU rule.
  Links         only Google pages about NVIDIA on Google Cloud: docs.cloud.google.com, Google Cloud
                solutions, GKE AI Labs, Google codelabs and the Google Cloud blog.

NETWORK CALLS
  compute, cloudquotas, cloudbilling, cloudresourcemanager, serviceusage, iam and aiplatform
  .googleapis.com; huggingface.co (a chosen model's published architecture only, no token); the
  metadata server on GCE; dl.google.com (only when setup installs gcloud).
  HTTPS_PROXY and NO_PROXY are honored; a custom CA bundle goes in --ca-bundle or GPUF_CA_BUNDLE.
  With a person's sign-in, calls carry X-Goog-User-Project so APIs that need a quota project work;
  --no-user-project turns that off, --user-project forces it on.

WHAT THE NUMBERS MEAN
  Quota limits come from the Cloud Quotas API (Compute's own quota view if that is unavailable,
  in which case GPU-family and Hyperdisk limits show as unknown). Usage counts what the project
  holds now. Prices come from the public Cloud Billing catalog, per method (on-demand, Spot,
  flex-start, calendar mode); n/a means the catalog lists no price for that combination. The
  capacity advisor score is Google's hint about Spot capacity only; attempts are the ground truth.

RATE LIMITS
  Compute rate quotas apply per project, per region, per minute, and refill at the start of each
  minute. This tool reads your project's real limits and uses at most GPUF_RATE_FRACTION of each
  (default 20%), leaving the rest for your other work. If Google still answers rateLimitExceeded,
  that bucket pauses to the next minute and halves its budget for a cool-down.

Version history and validation evidence ship separately; this file is the whole program.
Licensed under the Apache License, Version 2.0; the LICENSE and NOTICE files beside it carry the
terms and the attribution that travel with any copy.
"""
from __future__ import annotations

import argparse
import atexit
import contextlib
import copy
import datetime as dt
import gzip
import hashlib
import http.client
import io
import json
import math
import os
import platform
import queue
import random
import re
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

if sys.version_info < (3, 9):
    sys.exit(f"Python {sys.version.split()[0]} is too old: this script needs Python 3.9 or newer "
             "(python.org/downloads, or your package manager's python3 package)")

VERSION = "1.6.1"
UA = f"gcp-gpu-finder/{VERSION} (python {sys.version_info.major}.{sys.version_info.minor})"
COMPUTE = "https://compute.googleapis.com/compute/v1"
COMPUTE_BETA = "https://compute.googleapis.com/compute/beta"
QUOTAS = "https://cloudquotas.googleapis.com/v1"
BILLING = "https://cloudbilling.googleapis.com/v1"
CRM1 = "https://cloudresourcemanager.googleapis.com/v1"
SERVICEUSAGE = "https://serviceusage.googleapis.com/v1"
IAM = "https://iam.googleapis.com/v1"
HF = "https://huggingface.co"
METADATA = "http://169.254.169.254/computeMetadata/v1"
CONSOLE = "https://console.cloud.google.com"


# ------------------------------------------------------------------ settings
KNOBS = {}


def knob(name, default, doc):
    """Read GPUF_<name> from the environment; the type follows the documented default."""
    raw = os.environ.get("GPUF_" + name)
    val = default
    if raw not in (None, ""):
        try:
            if isinstance(default, bool):
                val = raw.strip().lower() in ("1", "true", "yes", "on")
            else:
                val = type(default)(raw)
        except ValueError:
            raise SystemExit(f"GPUF_{name}={raw!r} is not a valid {type(default).__name__} (default {default!r})")
    KNOBS[name] = (val, default, doc)
    return val


HOME = os.path.expanduser(knob("HOME", "~/.gcp_gpu_finder", "where runs, logs and caches are written"))
RATE_FRACTION = knob("RATE_FRACTION", 0.20, "share of each per-minute Compute API rate quota this tool may use")
FALLBACK_READS_PER_MIN = knob("FALLBACK_READS_PER_MIN", 1000, "per-region read limit assumed when the real one cannot be read")
FALLBACK_WRITES_PER_MIN = knob("FALLBACK_WRITES_PER_MIN", 1000, "per-region write limit assumed when the real one cannot be read")
FALLBACK_FILTERED_PER_MIN = knob("FALLBACK_FILTERED_PER_MIN", 75, "filtered-list limit assumed when the real one cannot be read")
OTHER_API_PER_MIN = knob("OTHER_API_PER_MIN", 60, "calls per minute to each non-Compute Google API")
RATE_COOL_S = knob("RATE_COOL_S", 600, "seconds a bucket stays at reduced budget after a rateLimitExceeded")
TARGET_INTERVAL_S = knob("TARGET_INTERVAL_S", 120, "minimum seconds between two attempts on the same zone, size and method")
BACKOFF_MAX_S = knob("BACKOFF_MAX_S", 1800, "longest wait between attempts on a target that keeps reporting no capacity")
SWEEP_S = knob("SWEEP_S", 3600, "seconds between fresh sweeps that reset every target's backoff")
JITTER_FRAC = knob("JITTER_FRAC", 0.2, "random spread applied to every wait so requests never align")
QUOTA_REFRESH_S = knob("QUOTA_REFRESH_S", 1800, "seconds between quota and usage refreshes during a run")
QUOTA_MIN_REFRESH_S = knob("QUOTA_MIN_REFRESH_S", 60, "shortest gap between two quota refreshes triggered by an attempt's result")
HOLD_CHECK_S = knob("HOLD_CHECK_S", 300, "seconds between checks that held capacity still exists")
PENDING_POLL_S = knob("PENDING_POLL_S", 60, "seconds between checks of queued flex-start requests")
QUOTA_POLL_S = knob("QUOTA_POLL_S", 900, "seconds between status checks of filed quota requests")
QUOTA_DECISION_WAIT_S = knob("QUOTA_DECISION_WAIT_S", 120, "seconds to wait for Google's immediate decision on the all-regions GPU request")
PARK_RECHECK_S = knob("PARK_RECHECK_S", 3600, "seconds before a target parked on a permanent error is re-checked")
QUOTA_VERIFY_S = knob("QUOTA_VERIFY_S", 21600, "seconds between single verification attempts on a quota-bound target")
CATALOG_TTL_S = knob("CATALOG_TTL_S", 21600, "seconds the machine and accelerator catalog is cached")
PRICE_TTL_S = knob("PRICE_TTL_S", 21600, "seconds the price list is cached")
ROLES_TTL_S = knob("ROLES_TTL_S", 86400, "seconds the predefined IAM role list is cached")
ADVISOR_TTL_S = knob("ADVISOR_TTL_S", 1800, "seconds a capacity advisor score is reused")
TOKEN_REFRESH_S = knob("TOKEN_REFRESH_S", 2700, "seconds before an access token is refreshed")
AUTH_RETRY_S = knob("AUTH_RETRY_S", 300, "seconds between sign-in retries while a token cannot be refreshed")
HTTP_TIMEOUT_S = knob("HTTP_TIMEOUT_S", 90, "socket deadline for one HTTP request; long operations are followed with the wait call instead")
HTTP_RETRIES = knob("HTTP_RETRIES", 5, "retries for a transient HTTP failure")
HTTP_BACKOFF_S = knob("HTTP_BACKOFF_S", 2.0, "first backoff between HTTP retries; doubles each retry")
OFFLINE_FAST_S = knob("OFFLINE_FAST_S", 120, "after a call fails to reach Google, later calls in this window try once instead of retrying")
OP_STALL_S = knob("OP_STALL_S", 900, "an operation whose status and progress do not change for this long is reported as stalled")
GCLOUD_TIMEOUT_S = knob("GCLOUD_TIMEOUT_S", 120, "deadline for one gcloud subprocess call")
GCLOUD_DIR = knob("GCLOUD_DIR", "~/google-cloud-sdk", "where setup installs the Google Cloud CLI when none is found")
GCLOUD_ARCHIVE_BASE = knob("GCLOUD_ARCHIVE_BASE", "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads",
                           "Google's download folder for the Google Cloud CLI archive")
GCLOUD_SHA256 = knob("GCLOUD_SHA256", "", "expected sha256 of the Google Cloud CLI archive setup downloads (the checksum Google lists beside it "
                                          "on its install page); when set, an archive with another digest is deleted and refused")
DOWNLOAD_STALL_S = knob("DOWNLOAD_STALL_S", 120, "a download that receives no bytes for this long is abandoned")
INSTALL_STALL_S = knob("INSTALL_STALL_S", 600, "an installer step that prints nothing for this long is reported as stalled")
SETUP_GCLOUD_CONFIG = knob("SETUP_GCLOUD_CONFIG", "gpu-finder", "gcloud configuration used when a key file is signed in beside another active account")
SETUP_NETWORK = knob("SETUP_NETWORK", "default", "name of the VPC network setup creates when the project has none")
SERVICE_POLL_S = knob("SERVICE_POLL_S", 5.0, "seconds between checks while Google enables APIs")
EVENTS_ROTATE_MB = knob("EVENTS_ROTATE_MB", 50, "events log size that triggers gzip rotation")
BOOT_DISK_GB = knob("BOOT_DISK_GB", 50, "boot disk size for VMs this tool creates")
IMAGE = knob("IMAGE", "projects/ubuntu-os-cloud/global/images/family/ubuntu-2404-lts-amd64",
             "default boot image when set here; otherwise the operating system question defaults to an image with the NVIDIA driver installed")
N1_VCPUS_PER_GPU = knob("N1_VCPUS_PER_GPU", 8, "vCPUs per attached GPU for N1 machines (T4, V100, P4, P100)")
NAME_PREFIX = knob("NAME_PREFIX", "gpuf", "prefix of every resource name this tool creates")
FLEX_WAIT_S = knob("FLEX_WAIT_S", 7200, "how long one flex-start request waits in its zone for capacity (GPUF_FLEX_WAIT_MIN_S to GPUF_FLEX_WAIT_MAX_S)")
FLEX_WAIT_MIN_S = knob("FLEX_WAIT_MIN_S", 90, "shortest wait Google accepts for one flex-start request (its documented limit)")
FLEX_WAIT_MAX_S = knob("FLEX_WAIT_MAX_S", 7200, "longest wait Google accepts for one flex-start request (its documented limit)")
FLEX_RUN_S = knob("FLEX_RUN_S", 604800, "how long flex-start VMs run before Google deletes them (GPUF_FLEX_RUN_MIN_S to GPUF_FLEX_RUN_MAX_S)")
FLEX_RUN_MIN_S = knob("FLEX_RUN_MIN_S", 600, "shortest flex-start run time Google accepts (its documented limit)")
FLEX_RUN_MAX_S = knob("FLEX_RUN_MAX_S", 604800, "longest flex-start run time Google accepts (its documented limit)")
FLEX_REQUEST_MAX_VMS = knob("FLEX_REQUEST_MAX_VMS", 8, "most VMs asked for in one flex-start request")
FLEX_GROUP_PARALLEL = knob("FLEX_GROUP_PARALLEL", 1, "flex-start group requests pending at once; more than 1 can overshoot")
RESERVATION_CHUNK_MAX = knob("RESERVATION_CHUNK_MAX", 16, "largest number of nodes asked for in one reservation when spreading")
CALENDAR_SEARCH_S = knob("CALENDAR_SEARCH_S", 900, "seconds between calendar-mode availability searches")
CALENDAR_REQUEST_MAX_VMS = knob("CALENDAR_REQUEST_MAX_VMS", 80, "most VMs asked for in one calendar-mode future reservation")
CALENDAR_START_MAX_DAYS = knob("CALENDAR_START_MAX_DAYS", 365, "latest start a calendar-mode reservation may be asked to have, in days from now")
CALENDAR_DAYS_MIN = knob("CALENDAR_DAYS_MIN", 1, "shortest calendar-mode reservation Google accepts, in days (its documented limit)")
CALENDAR_DAYS_MAX = knob("CALENDAR_DAYS_MAX", 90, "longest calendar-mode reservation Google accepts, in days (its documented limit)")
BOOT_DISK_MIN_GB = knob("BOOT_DISK_MIN_GB", 10, "smallest boot disk offered when the chosen image states no minimum")
CHECK_NAME_W = knob("CHECK_NAME_W", 40, "width of the check-name column in the environment report")
PLAIN_STATUS_S = knob("PLAIN_STATUS_S", 60, "seconds between status lines in plain (non-TTY) mode")
UI_REFRESH_S = knob("UI_REFRESH_S", 1.0, "seconds between dashboard redraws")
FIT_USABLE_FRAC = knob("FIT_USABLE_FRAC", 0.90, "share of GPU memory a serving engine may use when Google's tested config does not set it")
FIT_RUNTIME_GB = knob("FIT_RUNTIME_GB", 4.0, "per-GPU memory for CUDA context and activations")
FIT_KV_BYTES = knob("FIT_KV_BYTES", 2, "bytes per KV-cache element (2 for BF16); an FP8 cache in Google's tested config counts 1")
FIT_SSM_BYTES = knob("FIT_SSM_BYTES", 4, "bytes per Mamba state element (4 keeps the state in FP32)")
FIT_CONTEXT = knob("FIT_CONTEXT", 32768, "default longest prompt plus answer per request, in tokens, when sizing a model")
FIT_CONCURRENCY = knob("FIT_CONCURRENCY", 8, "default peak requests in flight across all copies when sizing a model")
HF_TIMEOUT_S = knob("HF_TIMEOUT_S", 30, "socket deadline for reading a Model Garden model's published architecture")
MODEL_GARDEN_LOCATION = knob("MODEL_GARDEN_LOCATION", "us-central1", "Agent Platform (Vertex AI) location whose endpoint lists Model Garden")
MODEL_GARDEN_PUBLISHER = knob("MODEL_GARDEN_PUBLISHER", "nvidia", "Model Garden publisher whose models are offered")
MARKETPLACE_IMAGE_PROJECT = knob("MARKETPLACE_IMAGE_PROJECT", "nvidia-ngc-public", "image project of NVIDIA's Google Cloud Marketplace VM products")
IMAGE_PROJECTS = knob("IMAGE_PROJECTS", "deeplearning-platform-release,ubuntu-os-accelerator-images,rocky-linux-accelerator-cloud,cos-cloud,"
                      "ubuntu-os-cloud,debian-cloud,rocky-linux-cloud,rhel-cloud,windows-cloud",
                      "public image projects offered as VM operating systems, in this order")
IMAGE_LOOKBACK_DAYS = knob("IMAGE_LOOKBACK_DAYS", 120, "images published within this many days are listed (older families are retired)")
IMAGE_FAMILY_EXCLUDE = knob("IMAGE_FAMILY_EXCLUDE", "tpu|baremetal", "image families matching this pattern are not offered for GPU VMs")
VERBOSITY = knob("VERBOSITY", "normal", "screen detail: quiet (questions, results, problems), normal (every step: what, where from, what it "
                 "found), detailed (also each Google call, file and command), trace (also what each write call sends)")
LOG_LEVEL = knob("LOG_LEVEL", "trace", "audit log detail: normal (steps, checks, notes), detailed (also each Google call, file and command), "
                 "trace (also what each write call sends)")
DETAIL_BODY_CHARS = knob("DETAIL_BODY_CHARS", 160, "a request body up to this many characters is shown on its call's line at detailed verbosity")
TRACE_BODY_CHARS = knob("TRACE_BODY_CHARS", 1500, "longest request body shown on screen at trace verbosity; the audit log keeps it whole")
THEME = knob("THEME", "nvidia", "terminal look: nvidia (dark grey background, NVIDIA green accents) or terminal (your terminal's own colors)")
THEME_BG = knob("THEME_BG", "#1a1a1a", "background color of the nvidia theme")
THEME_FG = knob("THEME_FG", "#e8e8e8", "text color of the nvidia theme")
THEME_GREEN = knob("THEME_GREEN", "#76b900", "accent, headings and success (NVIDIA green)")
THEME_BLUE = knob("THEME_BLUE", "#4fa8ff", "notifications, prompts, links and activity")
THEME_YELLOW = knob("THEME_YELLOW", "#f2c94c", "warnings and alerts")
THEME_RED = knob("THEME_RED", "#ff5c5c", "errors and blocking problems")
THEME_DIM = knob("THEME_DIM", "#8c8c8c", "secondary text")
FOOTER = knob("FOOTER", "on", "on: a shortcut bar stays on the last rows of the terminal while questions are asked; off: no bar (the shortcuts still work)")
FOOTER_MIN_ROWS = knob("FOOTER_MIN_ROWS", 12, "the shortcut bar is shown only in terminals with at least this many rows")
SECTION_RULE_MAX = knob("SECTION_RULE_MAX", 160, "longest rule drawn under a section heading, in characters")
SESSION_MODE = knob("SESSION", "ask", "ask: before anything runs, ask whether this session may leave files; logged: keep the audit log, caches and "
                                      "run state; ephemeral: save nothing and log nothing (also --session)")
GCLOUD_UNPACKED_MB = knob("GCLOUD_UNPACKED_MB", 600, "about how much room the unpacked Google Cloud CLI takes, in MB, as told before an install")
EPHEMERAL_DIR = knob("EPHEMERAL_DIR", "", "a memory-backed folder for an ephemeral session's private files (gcloud's configuration copy, a gcloud "
                                          "installed for the session); empty finds one: /dev/shm, then $XDG_RUNTIME_DIR, when held in memory")


# ------------------------------------------------------------------ small helpers
def now():
    return time.time()


def iso(ts=None):
    return dt.datetime.fromtimestamp(now() if ts is None else ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    if not s:
        return None
    s = re.sub(r"\.\d+", "", s.strip()).replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def human_dur(sec):
    if sec is None:
        return "-"
    sec = int(max(0, sec))
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}d{h:02d}h"
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def ago(ts):
    return "-" if not ts else human_dur(now() - ts) + " ago"


def plural_of(word):
    last = word.split()[-1]
    if last.endswith("y") and last[-2:-1] not in ("a", "e", "i", "o", "u"):
        return word[:-1] + "ies"
    return word + ("es" if last.endswith(("s", "x", "ch", "sh")) else "s")


def plural(n, word):
    """'1 copy', '3 copies', '2 VM instances'."""
    num = int(n) if float(n).is_integer() else n
    return f"{num} {word if num == 1 else plural_of(word)}"


def jitter(base, frac=None):
    f = JITTER_FRAC if frac is None else frac
    return max(0.0, base * (1 + random.uniform(-f, f)))


def region_of(zone):
    return zone.rsplit("-", 1)[0] if zone and zone.count("-") >= 2 else zone


def tail(url):
    return (url or "").rstrip("/").rsplit("/", 1)[-1]


def money(x):
    return "n/a" if x is None else f"${x:,.2f}"


def gb(x):
    return "n/a" if x is None else (f"{x:,.0f} GB" if x >= 10 else f"{x:.1f} GB")


def fnum(x):
    if x is None:
        return "n/a"
    return str(int(x)) if abs(x - round(x)) < 1e-9 else f"{x:.3f}".rstrip("0").rstrip(".")


def safe_name(*parts, limit=63):
    """A Compute resource name: lowercase letters, digits and hyphens, starting with a letter."""
    s = "-".join(str(p) for p in parts if p not in (None, ""))
    s = re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if not s or not s[0].isalpha():
        s = "x" + s
    return s[:limit].rstrip("-")


# what this session may leave on this computer. An ephemeral session writes no file: what it would write is kept in mem
# (path -> (text, time)), and the few files a program it runs must have (gcloud's configuration) live in ram, a private
# folder in a memory-backed file system that is deleted when the session ends.
SESSION = {"mode": None, "ephemeral": False, "ram": None, "ram_how": None, "gcloud_config": None, "gcloud_ok": True, "why_no_gcloud": None, "mem": {}}


def in_ram(path):
    r = SESSION["ram"]
    return bool(r) and os.path.abspath(path).startswith(r + os.sep)


def saved_where(path):
    """How a step says where its file went: written to disk, or kept in memory because this session saves nothing."""
    return f"saved to {short_path(path)}" if not SESSION["ephemeral"] or in_ram(path) else "kept in memory for this session only (nothing is written)"


def private_dir(path):
    """Create path and its missing parents readable by this user only; a folder that already exists keeps the permissions it has."""
    if path and not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent and parent != path:
            private_dir(parent)
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            pass
    return path


def atomic_write(path, text, mode=0o600):
    if SESSION["ephemeral"] and not in_ram(path):
        SESSION["mem"][os.path.abspath(path)] = (text, now())
        audit("file", op="kept", path=path, bytes=len(text.encode("utf-8")), note="in memory only: this session saves nothing")
        return
    private_dir(os.path.dirname(path))
    tmp = f"{path}.tmp.{os.getpid()}"
    # the file is born with its final permissions, so no reader sees it more open than that even for an instant
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode), "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    try:
        os.chmod(tmp, mode)
    except OSError:
        pass
    os.replace(tmp, path)
    audit("file", op="write", path=path, bytes=len(text.encode("utf-8")), mode=oct(mode))


def atomic_json(path, obj, mode=0o600):
    atomic_write(path, json.dumps(obj, indent=1, sort_keys=True, default=str), mode)


def load_json(path, default=None):
    hit = SESSION["mem"].get(os.path.abspath(path))
    if hit:
        audit("file", op="read", path=path, bytes=len(hit[0].encode("utf-8")), age_s=round(now() - hit[1]), note="from this session's memory")
        try:
            return json.loads(hit[0])
        except ValueError:
            return default
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        age = now() - os.path.getmtime(path)
    except FileNotFoundError:
        return default
    except OSError as e:
        audit("file", op="read", path=path, bytes=0, note=f"cannot be read ({type(e).__name__}: {e.strerror or e}); treated as absent")
        return default
    try:
        data = json.loads(text)
    except ValueError:
        audit("file", op="read", path=path, bytes=len(text), age_s=round(age), note="not valid JSON; ignored")
        return default
    audit("file", op="read", path=path, bytes=len(text), age_s=round(age))
    return data


def new_run_id():
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:4]


def run_short(run_id):
    """Eight characters that make every resource name of a run unique: date-time digits plus the random suffix."""
    m = re.match(r"(\d{8})T(\d{4})\d{2}Z-([0-9a-f]{4})", run_id or "")
    if not m:
        return safe_name(run_id)[:8]
    return (m.group(1)[4:] + m.group(2) + m.group(3))[-8:]


# ------------------------------------------------------------------ terminal
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


RESET = "\x1b[0m"
# what text returns to after a colored span: a plain reset, or the theme's background and text color
_BASE = [RESET]


def visible_len(s):
    return len(ANSI_RE.sub("", s))


def visible_text(s):
    return ANSI_RE.sub("", str(s))


def hex_rgb(color):
    h = (color or "").lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise SystemExit(f"theme color {color!r} is not #RRGGBB")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def xterm256(rgb):
    """The nearest of the 256 standard terminal colors, for terminals without 24-bit color."""
    steps = (0, 95, 135, 175, 215, 255)
    idx = [min(range(6), key=lambda i: abs(steps[i] - v)) for v in rgb]
    cube = [steps[i] for i in idx]
    gi = min(23, max(0, round((sum(rgb) / 3 - 8) / 10)))
    gray = 8 + 10 * gi
    if sum((v - gray) ** 2 for v in rgb) < sum((v - c) ** 2 for v, c in zip(rgb, cube)):
        return 232 + gi
    return 16 + 36 * idx[0] + 6 * idx[1] + idx[2]


class Term:
    """Colors, widths, the live dashboard and safe writes that survive a closed terminal."""

    CODES = {"b": "1", "d": "2", "u": "4", "r": "31", "g": "32", "y": "33", "bl": "34", "m": "34", "c": "34", "gr": "90", "rev": "7", "h": "1;32"}

    def __init__(self, plain=False, theme=None):
        self.out = sys.stdout
        try:
            self.tty = self.out.isatty() and sys.stdin.isatty()
        except (AttributeError, ValueError):
            self.tty = False
        self.plain = plain or not self.tty
        self.color = (not self.plain or self._out_tty()) and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
        enc = (getattr(self.out, "encoding", "") or "").lower().replace("-", "")
        self.utf = enc in ("utf8", "utf8mb4")
        self.in_dash = False
        self.dead = False
        self.lock = threading.RLock()
        # the shortcut bar: a function giving its lines for a width, and (screen rows, bar rows) while it is fenced off
        self.footer_fn = None
        self.footer_rows = None
        self._signals_set = False
        if os.name == "nt" and self.color:
            self.color = self._enable_vt()
        self.theme = (theme or THEME).lower()
        self.depth = self._depth()
        self.codes = dict(self.CODES)
        self.base = RESET
        self.painted = False
        if self.color and self.theme == "nvidia" and self.depth:
            fg = {k: self._sgr(38, c) for k, c in (("r", THEME_RED), ("g", THEME_GREEN), ("y", THEME_YELLOW), ("c", THEME_BLUE), ("gr", THEME_DIM))}
            self.codes.update(fg, bl=fg["c"], m=fg["c"], h="1;" + fg["g"])
            self.base = f"{RESET}\x1b[{self._sgr(48, THEME_BG)};{self._sgr(38, THEME_FG)}m"
            self.painted = True
        _BASE[0] = self.base

    def _depth(self):
        """24 for terminals that announce 24-bit color, 8 for 256-color terminals, 0 when the theme cannot be drawn."""
        if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit") or os.environ.get("WT_SESSION"):
            return 24
        return 8 if "256" in os.environ.get("TERM", "") else 0

    def _sgr(self, kind, color):
        rgb = hex_rgb(color)
        return f"{kind};2;{rgb[0]};{rgb[1]};{rgb[2]}" if self.depth == 24 else f"{kind};5;{xterm256(rgb)}"

    def paint_screen(self):
        """Fill the visible screen with the theme background before the first question."""
        if self.painted and self.tty and not self.plain:
            self.write(f"{self.base}\x1b[2J\x1b[H")

    def restore(self):
        self.footer_off()
        if self.painted:
            self.write(RESET)

    def _size(self):
        """Rows and columns of the terminal as it is now, read from the terminal itself so a resize is seen."""
        try:
            sz = os.get_terminal_size(self.out.fileno())
            return sz.lines, sz.columns
        except (OSError, ValueError, AttributeError):
            return self.height(), self.width()

    def footer_ensure(self):
        """Keep the shortcut bar on the last rows: text scrolls in the rows above it, the bar stays where it is."""
        if self.footer_fn is None or self.plain or not self.tty or self.in_dash or self.dead or str(FOOTER).lower() != "on":
            return
        rows, cols = self._size()
        n = len(self.footer_fn(cols))
        if rows < max(FOOTER_MIN_ROWS, n + 4):
            return
        with self.lock:
            if self.footer_rows is None:
                # free the bar's rows by pushing the text up, then fence them off from scrolling
                self.write("\n" * n + f"\x1b[{n}A")
                self._watch_signals()
            if self.footer_rows != (rows, n):
                self.write(f"\x1b7\x1b[1;{rows - n}r\x1b8")
                self.footer_rows = (rows, n)
            self.footer_draw()

    def footer_draw(self):
        if self.footer_rows is None or self.in_dash or self.footer_fn is None:
            return
        rows, n = self.footer_rows
        cols = self._size()[1]
        lines = self.footer_fn(cols)[:n]
        # save the cursor and colors, draw the bar, restore them, so the text being written above is not disturbed
        self.write("\x1b7" + "".join(f"\x1b[{rows - n + 1 + i};1H{self.base}{clip(ln, cols - 1)}\x1b[K" for i, ln in enumerate(lines)) + "\x1b8")

    def footer_off(self):
        """Give the bar's rows back to the terminal and clear them."""
        with self.lock:
            if self.footer_rows is None:
                return
            rows, n = self.footer_rows
            self.footer_rows = None
            self.write(f"\x1b7\x1b[r\x1b[{rows - n + 1};1H{self.base}\x1b[J\x1b8")

    def clear(self):
        """An empty screen for a rewind; the bar is drawn again at the bottom."""
        if self.tty and not self.plain and not self.in_dash:
            self.write(f"{self.base}\x1b[2J\x1b[H")
            self.footer_draw()

    def _watch_signals(self):
        # a resize redraws the bar; a terminate or hang-up before the hunt gives the rows back and exits instead of leaving them fenced
        if self._signals_set or threading.current_thread() is not threading.main_thread():
            return
        self._signals_set = True
        if hasattr(signal, "SIGWINCH"):
            old = signal.getsignal(signal.SIGWINCH)

            def on_resize(signum, frame):
                if self.footer_rows is not None and not self.in_dash:
                    rows, _ = self._size()
                    n = self.footer_rows[1]
                    self.write(f"\x1b7\x1b[1;{rows - n}r\x1b8")
                    self.footer_rows = (rows, n)
                    self.footer_draw()
                if callable(old):
                    old(signum, frame)
            signal.signal(signal.SIGWINCH, on_resize)
        for name in ("SIGTERM", "SIGHUP"):
            sig = getattr(signal, name, None)
            if sig is not None and signal.getsignal(sig) == signal.SIG_DFL:
                def on_stop(signum, frame, name=name):
                    self.restore()
                    raise SystemExit(f"stopped by {name} at a question; nothing was created after the last confirmed step")
                signal.signal(sig, on_stop)

    def _out_tty(self):
        try:
            return self.out.isatty()
        except (AttributeError, ValueError):
            return False

    def _enable_vt(self):
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if not k.GetConsoleMode(h, ctypes.byref(mode)):
                return False
            return bool(k.SetConsoleMode(h, mode.value | 0x0004))
        except Exception:
            return False

    def s(self, text, *styles):
        text = str(text)
        if not self.color or not styles:
            return text
        codes = ";".join(self.codes[x] for x in styles if x in self.codes)
        return f"\x1b[{codes}m{text}{self.base}"

    def write(self, text):
        if self.dead:
            return
        with self.lock:
            try:
                self.out.write(text)
                self.out.flush()
            except (OSError, ValueError):
                # the terminal went away (closed window, broken pipe); keep running, keep logging
                self.dead = True

    def line(self, text=""):
        # with the theme, each line is painted to the right edge so the background is one even block
        self.write(f"{self.base}{text}\x1b[K\n" if self.painted else text + "\n")

    def width(self):
        if not self._out_tty():
            # a file or pipe has no width; keep tables whole for logs
            return int(os.environ.get("COLUMNS") or 200)
        try:
            return max(60, shutil.get_terminal_size((120, 40)).columns)
        except OSError:
            return 120

    def height(self):
        try:
            return max(20, shutil.get_terminal_size((120, 40)).lines)
        except OSError:
            return 40

    def dash_start(self):
        if self.plain or self.in_dash:
            return
        self.footer_off()
        self.write("\x1b[?1049h\x1b[?25l" + (f"{self.base}\x1b[2J" if self.painted else ""))
        self.in_dash = True

    def dash_frame(self, lines):
        if not self.in_dash:
            return
        h = self.height()
        w = self.width()
        body = []
        for ln in lines[: h - 1]:
            body.append(self.base + clip(ln, w) + "\x1b[K")
        with self.lock:
            if self.in_dash:
                self.write("\x1b[H" + "\n".join(body) + self.base + "\x1b[J")

    def dash_stop(self):
        with self.lock:
            if self.in_dash:
                self.in_dash = False
                self.write(RESET + "\x1b[?25h\x1b[?1049l")

    def bar(self, frac, width):
        frac = 0.0 if frac is None else min(1.0, max(0.0, frac))
        full = int(round(frac * width))
        a, b = ("\u2588", "\u2591") if self.utf else ("#", ".")
        return self.s(a * full, "g") + self.s(b * (width - full), "gr")


def clip(text, width):
    """Cut a string with color codes to a visible width."""
    if visible_len(text) <= width:
        return text
    if not ANSI_RE.search(text):
        return text[: max(0, width - 1)] + "~"
    out, n, i = [], 0, 0
    while i < len(text) and n < width - 1:
        m = ANSI_RE.match(text, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        out.append(text[i])
        n += 1
        i += 1
    return "".join(out) + "~" + _BASE[0]


def table(headers, rows, width=None, right=()):
    """Plain column layout; the widest text columns shrink first when the terminal is narrow."""
    cols = len(headers)
    cells = [[str(h) for h in headers]] + [[("" if c is None else str(c)) for c in r] for r in rows]
    widths = [max(visible_len(r[i]) for r in cells) for i in range(cols)]
    if width:
        while sum(widths) + 2 * (cols - 1) > width and max(widths) > 6:
            j = widths.index(max(widths))
            widths[j] -= 1
    lines = []
    for k, r in enumerate(cells):
        parts = []
        for i, c in enumerate(r):
            c = clip(c, widths[i]) if visible_len(c) > widths[i] else c
            pad = widths[i] - visible_len(c)
            parts.append((" " * pad + c) if i in right else (c + " " * pad))
        lines.append("  ".join(parts).rstrip())
        if k == 0:
            lines.append("  ".join("-" * w for w in widths))
    return lines


# ------------------------------------------------------------------ what the screen shows of the audit trail
def format_record(t, rec, sym=(">", "+", "-"), body_chars=None):
    """One audit record as one readable line; the live screen and the `log` command both use it."""
    kind, d = rec.get("kind"), sym[2]
    if kind == "session":
        if rec.get("msg"):
            return t.s(rec["msg"], "gr")
        return t.s(f"session: {rec.get('cmd')} with GCP GPU Finder {rec.get('version')}, Python {rec.get('python')} on {rec.get('platform')}, "
                   f"user {rec.get('user')}, in {short_path(rec.get('cwd'))}; arguments: {' '.join(rec.get('argv') or []) or 'none'}; "
                   f"screen {rec.get('verbosity')}, log {rec.get('log_level')}", "c")
    if kind == "step":
        ph = rec.get("phase")
        if ph == "start":
            return t.s(f"{sym[0]} {rec.get('title')}", "c", "b") + (t.s(f"  {rec['why']}", "gr") if rec.get("why") else "")
        if ph == "done":
            mark, style = {"warning": ("!", "y"), "problem": ("x", "r")}.get(rec.get("outcome"), (sym[1], "g"))
            return t.s(f"{mark} ", style) + f"{rec.get('title')}: {rec.get('result')}" + t.s(f"  {rec.get('seconds')} s", "gr")
        return t.s(f"x {rec.get('title')} {ph}: {rec.get('error')}", "r")
    if kind == "check":
        st = rec.get("status")
        mark = t.s({"ok": "ok  ", "warn": "warn", "fail": "FAIL", "unknown": "??  "}.get(st, st), {"ok": "g", "warn": "y", "fail": "r"}.get(st, "y"))
        return f"{mark}  {rec.get('name'):<{CHECK_NAME_W}s} {rec.get('detail')}" + (t.s(f"   [{rec['source']}]", "gr") if rec.get("source") else "") + \
            (t.s(f"   {rec['more']}", "gr") if rec.get("more") else "") + (t.s(f"   fix: {rec['fix']}", "gr") if rec.get("fix") and st != "ok" else "")
    if kind == "say":
        return rec.get("msg", "")
    if kind == "answer":
        how = "  replayed after going back" if rec.get("replayed") else (f"  skipped by {rec['auto']}" if rec.get("auto") else "")
        return t.s("> " if rec.get("auto") else "? ", "c", "b") + f"{rec.get('q')}: " + t.s(rec.get("answer", ""), "c") + t.s(how, "gr")
    if kind == "nav":
        return t.s(f"{rec.get('action')}", "y") + f" at: {rec.get('q')}" + t.s(f"  {rec.get('outcome')}", "gr")
    if kind == "note":
        lvl = rec.get("level")
        return t.s(("note: " if lvl in (None, "info") else f"{lvl}: ") + rec.get("msg", ""), {"warn": "y", "error": "r", "good": "g"}.get(lvl, "c"))
    if kind in ("api", "http"):
        host = rec.get("host", "")
        name = host.replace(".googleapis.com", "") if host.endswith("googleapis.com") else host
        st = rec.get("status")
        stxt = t.s(str(st), "g" if st and 200 <= st < 300 else ("y" if st in (404, 409, 429) else "r"))
        extra = (f"  {rec['reason']}" if rec.get("reason") else "") + (f"  {rec['note'][:200]}" if rec.get("note") else "")
        return t.s(f"{d} ", "gr") + t.s(f"{rec.get('m', 'GET'):6s}", "c") + f"{name}  {api_path(host, rec.get('path'))}" + \
            (t.s(f"  sent {rec['sent']}", "gr") if rec.get("sent") else "") + "  " + stxt + \
            t.s(f"  {rec.get('ms', 0)} ms  {size_text(rec.get('bytes'))}{extra}", "gr")
    if kind == "file":
        op = {"read": "read  ", "write": "wrote "}.get(rec.get("op"), f"{rec.get('op', '')} ")
        age = f", written {human_dur(rec['age_s'])} ago" if rec.get("age_s") is not None else ""
        return t.s(f"{d} ", "gr") + t.s(op, "c") + short_path(rec.get("path")) + \
            t.s(f"  {size_text(rec.get('bytes'))}{age}" + (f"  {rec['note']}" if rec.get("note") else ""), "gr")
    if kind == "cmd":
        return t.s(f"{d} ", "gr") + t.s("ran   ", "c") + " ".join(rec.get("argv") or []) + \
            t.s(f"  exit {rec.get('rc')}  {rec.get('ms', 0)} ms" + (f"  {rec['withheld']}" if rec.get("withheld") else ""), "gr")
    if kind == "body":
        text = json.dumps(rec.get("body"), separators=(",", ":"), default=str)
        limit = TRACE_BODY_CHARS if body_chars is None else body_chars
        if limit and len(text) > limit:
            text = text[:limit] + f"... ({len(text)} characters; whole in the audit log)"
        return "    " + t.s(f"sent to {rec.get('m')} {api_path(rec.get('host'), rec.get('path'))}: {text}", "gr")
    if kind == "attempt":
        return t.s(f"{d} attempt ", "gr") + f"{rec.get('target')}: {rec.get('nodes')} VM(s), {rec.get('result')}"
    return json.dumps(rec, default=str)


def api_path(host, path):
    """A Google API path without the version and project prefix, so a reader sees the resource: zones/us-central1-a/reservations."""
    path = re.sub(r"^/(compute/)?(v1|v1beta1|beta|v2)/", "", path or "")
    return re.sub(r"^projects/[^/]+/", "", path)


class Report:
    """Shows the audit trail at the chosen verbosity: every step says what it does, which Google API, file or command it uses, and
    what it found; detailed adds each call, file and command; trace adds what was sent in each write."""

    def __init__(self, term, events, verbosity="normal"):
        self.t, self.ev = term, events
        self.level = LEVELS.get(verbosity, LEVELS["normal"])
        self.depth = 0
        self.hunting = False
        self.sym = ("\u25b8", "\u2713", "\u00b7") if term.utf else (">", "+", "-")
        events.printer = self.show
        events.report = self

    def pad(self):
        return "    " * self.depth + "  "

    def show(self, rec):
        t, kind = self.t, rec["kind"]
        # these are drawn by their own code (steps, checks, questions and answers), so the log record is not shown a second time
        if t.in_dash or t.dead or kind in ("step", "check", "say", "session", "attempt", "answer", "nav"):
            return
        if kind == "note":
            if self.hunting or (self.level < 1 and rec.get("level") not in ("warn", "error")):
                return
        elif self.level < KIND_LEVEL.get(kind, 1):
            return
        text = format_record(t, rec, self.sym)
        if text:
            t.line(self.pad() + text)

    def say(self, text, style=None, always=False):
        """One line of what is happening, at normal verbosity and above, and in the audit log."""
        self.ev.write("say", msg=visible_text(text))
        if (self.level >= 1 or always) and not self.t.in_dash:
            self.t.line(self.pad() + (self.t.s(text, style) if style else text))

    def step(self, title, why=None):
        return Step(self, title, why)


class Step:
    """One visible unit of work: its title and purpose before it starts, its details inside, its result and duration after."""

    def __init__(self, rep, title, why):
        self.rep, self.title, self.why, self.res, self.res_style = rep, title, why, None, "g"

    def __enter__(self):
        r, t = self.rep, self.rep.t
        r.ev.write("step", phase="start", title=self.title, why=self.why)
        if r.level >= 1 and not t.in_dash:
            if r.depth == 0:
                t.line("")
            t.line(r.pad() + t.s(f"{r.sym[0]} {self.title}", "c", "b") + (t.s(f"  {self.why}", "gr") if self.why else ""))
        r.depth += 1
        self.t0 = now()
        return self

    def say(self, text, style=None):
        self.rep.say(text, style)

    def result(self, text, style="g"):
        self.res, self.res_style = text, style

    def __exit__(self, et, e, tb):
        r, t = self.rep, self.rep.t
        dur = now() - self.t0
        if et is None:
            r.ev.write("step", phase="done", title=self.title, result=visible_text(self.res or "done"), seconds=round(dur, 2),
                       outcome={"y": "warning", "r": "problem"}.get(self.res_style, "ok"))
            if (r.level >= 1 or self.res_style in ("y", "r")) and not t.in_dash:
                mark = {"y": "!", "r": "x"}.get(self.res_style, r.sym[1])
                t.line(r.pad() + t.s(f"{mark} ", self.res_style) + (self.res or "done") + t.s(f"  {dur:.1f} s", "gr"))
        elif et in (GoBack, StartOver):
            r.ev.write("step", phase="left", title=self.title, why="a question inside it was answered with a shortcut", seconds=round(dur, 2))
        else:
            what = "cancelled" if et is KeyboardInterrupt else ("stopped" if et is SystemExit else "failed")
            r.ev.write("step", phase=what, title=self.title, error=f"{et.__name__}: {e}", seconds=round(dur, 2))
            if not t.in_dash:
                t.line(r.pad() + t.s(f"x {self.title} {what} after {dur:.1f} s" + (f": {e}" if e and str(e) else ""), "r"))
        r.depth -= 1
        return False


# ------------------------------------------------------------------ prompts
class GoBack(Exception):
    """Asked at a question: return to the question before it."""


class StartOver(Exception):
    """Asked at a question: answer every question again from the first."""


# what a person types at any question, then Enter; none of these is a valid answer to any question
SHORTCUT_BACK = ("<", "back")
SHORTCUT_RESTART = ("<<", "restart", "start over")
SHORTCUT_HELP = ("?", "help")
SHORTCUT_SKIP = (">", "skip")
SHORTCUT_SKIP_REST = (">>", "skip to search", "skip to plan", "skip the rest")
SHORTCUT_ALL = ("all",)
SHORTCUT_NONE = ("none",)
# the token recorded for each, so a replay after going back means the same thing again
SKIP_TOKENS = ("skip", ">>", "all", "none")
_NO = object()


class Nav:
    """The answers of one planning session in the order given, so going back can replay all of them but the last."""

    def __init__(self):
        self.answers = []
        self.replay = []
        self.prefer = None
        self.fed = None
        self.locked = None

    def rewind(self):
        """Drop the last answer; the ones before it are replayed and its question is asked again, with that answer as the default."""
        last = self.answers.pop()
        self.replay, self.answers, self.prefer, self.fed = list(self.answers), [], last, None
        return last[0]

    def restart(self):
        self.answers, self.replay, self.prefer, self.fed = [], [], None, None

    def lock(self, why):
        """Answers given so far led to something done in Google Cloud; going back past them would repeat it."""
        self.locked = (len(self.answers), why)


class Prompter:
    """Interactive questions with defaults; unattended runs take the default or fail naming the flag.
    At every planning question: `<` back one question, `<<` start over, `>` skip it, `>>` skip the rest and go to the search,
    `all` and `none` where the question offers them, `?` the shortcuts and the answers so far. Each question says what skip, all
    and none mean for it (alt): skip takes the question's no-preference answer, or its default when it has none."""

    def __init__(self, term, interactive, reader=None):
        self.t = term
        self.interactive = interactive
        self.reader = reader or input
        self.nav = None
        self.hinted = False
        self.skipping = False
        self.skipped = False
        self.dest = "search"
        self.cur = (None, None)
        term.footer_fn = self.footer_lines

    def begin(self):
        """Start recording answers so they can be gone back over; unattended runs record nothing."""
        self.nav = Nav() if self.interactive else None
        self.skipping = False
        return self.nav

    def end(self):
        self.nav = None
        self.skipping = False
        self.t.footer_draw()

    def lock(self, why):
        if self.nav:
            self.nav.lock(why)
            self.t.footer_draw()

    def _input(self, text):
        self.t.dash_stop()
        if self.t.painted:
            # paint the answer line first, so typed text sits on the theme background too
            self.t.write(self.t.base + "\x1b[K")
        try:
            return self.reader(text)
        except EOFError:
            raise SystemExit("input closed before the question was answered")

    def _need(self, q, flag):
        raise SystemExit(f"unattended run has no answer for: {q}" + (f" (pass {flag})" if flag else ""))

    def _gap(self):
        self.t.line("")

    def _default(self, q, default):
        """The question gone back to offers its earlier answer as the default (a skip, all or none is resolved afresh instead)."""
        nav = self.nav
        if nav and nav.prefer and not nav.replay:
            pq, pv = nav.prefer
            nav.prefer = None
            if pq == q and pv not in SKIP_TOKENS:
                return pv
        return default

    # ---- skip, skip to search, all, none
    def _word(self, s, alt):
        """The shortcut word typed, as its recorded token; these mean something only in the planning questions or where a question offers them."""
        if self.nav is None and alt is None:
            return None
        low = s.strip().lower()
        for words, token in ((SHORTCUT_SKIP_REST, ">>"), (SHORTCUT_SKIP, "skip"), (SHORTCUT_ALL, "all"), (SHORTCUT_NONE, "none")):
            if low in words:
                return token
        return None

    def _meaning(self, kind, alt, default):
        """(answer, note) that skip, all or none stands for at this question; answer None means it is not offered, and note says why."""
        alt = alt or {}
        if kind in alt:
            v = alt[kind]
            return v if isinstance(v, tuple) else (v, "")
        if kind == "skip":
            return (default, "the default") if default not in (None, "", []) else (None, "this question has no default; answer it")
        return None, f"'{kind}' is not an answer to this question"

    def _resolve(self, q, token, alt, default, show, valid=None):
        """The answer a shortcut word stands for here, or _NO after saying why it is not one."""
        t = self.t
        if token == ">>":
            if self.nav is None:
                t.line(t.s(f"  skipping to the {self.dest} works during the planning questions", "y"))
                return _NO
            if not self.skipping:
                self.skipping = True
                audit("nav", action=f"skip to {self.dest}", q=visible_text(q), outcome="every later question takes its skip answer; each is shown")
                t.footer_draw()
        kind = "skip" if token == ">>" else token
        val, note = self._meaning(kind, alt, default)
        why = None if val is not None else note
        if why is None and valid:
            why = valid(val)
        if why:
            t.line(t.s(f"  {kind}: {why}" + (f"; skip to {self.dest} goes on after this question is answered" if token == ">>" else ""), "y"))
            return _NO
        self.skipped = kind == "skip"
        t.line(t.s(f"  {'skipped' if kind == 'skip' else kind}: {show(val)}" + (f"  ({note})" if note else ""), "c"))
        return val

    def _auto(self, q, alt, default, show, valid=None):
        """While skipping to the search, answer with the skip answer and show it; a question without one is asked."""
        if not (self.nav and self.skipping):
            return _NO
        val, note = self._meaning("skip", alt, default)
        why = None if val is not None else note
        if why is None and valid:
            why = valid(val)
        if why:
            self._gap()
            self.t.line(self.t.s(f"  skip to {self.dest} stops at this question ({why}); after it, skipping goes on", "y"))
            return _NO
        self.skipped = True
        self.t.line(f"{self.t.s('>', 'c', 'b')} {q}: {self.t.s(show(val), 'c')}" + self.t.s(f"   skipped, {note or 'its skip answer'}", "gr"))
        audit("answer", q=visible_text(q), answer=visible_text(show(val)), replayed=False, auto=f"skip to {self.dest}")
        return val

    def _alt_hint(self, alt, default, show):
        """One line under the question: what skip, all and none would answer here."""
        if self.nav is None:
            return
        t, parts = self.t, []
        for kind, key in (("skip", "> skip"), ("all", "all"), ("none", "none")):
            val, note = self._meaning(kind, alt, default)
            if val is not None:
                shown = visible_text(show(val))
                # a short answer is shown with its meaning; a long one (a list of regions) by its meaning alone
                parts.append(f"{key}: " + (f"{shown} ({note})" if note and len(shown) <= 32 else (note or clip(shown, 60))))
        parts.append(f">> skip to {self.dest}")
        t.line(t.s("  " + "   ".join(parts), "gr"))

    def _read(self, prompt, q):
        """One answer: replayed after a rewind, or typed; back, start over and help are handled here and never reach a question."""
        nav, t = self.nav, self.t
        if nav and nav.fed is not None:
            # the question refused the replayed answer: what it offers changed since, so replay stops here
            t.line(t.s(f"  the earlier answer {nav.fed!r} no longer fits this question; answer it again", "y"))
            nav.replay, nav.fed = [], None
        if nav and nav.replay:
            pq, pv = nav.replay[0]
            if pq == q:
                nav.replay.pop(0)
                nav.fed = pv
                t.line(prompt + t.s(pv, "c") + t.s("   earlier answer, replayed", "gr"))
                return pv
            t.line(t.s(f"  this question was not asked before ({len(nav.replay)} earlier answer(s) left unused); answer from here", "y"))
            nav.replay = []
        t.footer_ensure()
        if not self.hinted and t.footer_rows is None:
            self.hinted = True
            t.line(t.s("  at any question: < back, << start over, > skip, >> skip to the " + self.dest + ", ? shortcuts and your answers", "gr"))
        while True:
            typed = self._input(prompt).strip()
            low = typed.lower()
            if low in SHORTCUT_HELP:
                audit("nav", action="shortcuts shown", q=visible_text(q), outcome=f"{len(nav.answers) if nav else 0} answer(s) listed")
                self.show_help()
                continue
            if low in SHORTCUT_BACK or low in SHORTCUT_RESTART:
                what = "back" if low in SHORTCUT_BACK else "restart"
                why = self._cannot(what)
                audit("nav", action="back one question" if what == "back" else "start over", q=visible_text(q), outcome=f"refused: {why}" if why else "done")
                if not why:
                    raise GoBack() if what == "back" else StartOver()
                t.line(t.s(f"  {why}", "y"))
                continue
            return typed

    def _cannot(self, what):
        nav = self.nav
        if nav is None:
            return "going back works during the planning questions; this question has nothing before it to return to"
        if nav.locked and (what == "restart" or len(nav.answers) <= nav.locked[0]):
            return f"not possible here: {nav.locked[1]}, so answering earlier questions again would repeat it; Ctrl-C ends this run"
        if what == "back" and not nav.answers:
            return "this is the first question; there is nothing before it (<< starts over, Ctrl-C quits)"
        return None

    def _accept(self, q, text, value=None):
        audit("answer", q=visible_text(q), answer=text, replayed=bool(self.nav and self.nav.fed is not None))
        if self.nav is not None:
            self.nav.answers.append((q, text))
            self.nav.fed = None
            self.t.footer_draw()
        return text if value is None else value

    def footer_lines(self, cols):
        """The bar on the last rows: the shortcuts, which of them work at this moment, and the question number."""
        t, nav = self.t, self.nav

        def key(k, what, on=True):
            return t.s(k, "g", "b") + (" " + what if what else "") if on else t.s(k + (" " + what if what else ""), "gr")
        alt, default = self.cur
        offered = {k: self._meaning(k, alt, default)[0] is not None for k in ("skip", "all", "none")} if nav else {}
        parts = [key("<", "back", self._cannot("back") is None), key("<<", "start over", self._cannot("restart") is None),
                 key(">", "skip", offered.get("skip", False)), key(">>", f"skip to {self.dest}", nav is not None),
                 key("all", "", offered.get("all", False)), key("none", "", offered.get("none", False)),
                 key("?", "help"), key("Ctrl-C", "quit")]
        left = "  " + "   ".join(parts)
        right = t.s((f"skipping to the {self.dest}  " if self.skipping else "") + f"question {len(nav.answers) + 1}  ", "gr") if nav else ""
        pad = max(2, cols - 1 - visible_len(left) - visible_len(right))
        return [t.s(("\u2500" if t.utf else "-") * max(0, cols - 1), "g"), left + " " * pad + right]

    def show_help(self):
        t, nav = self.t, self.nav
        t.line("")
        t.line(t.s("Shortcuts", "h") + t.s("  type one at any question, then Enter", "gr"))
        t.line(t.s(("\u2500" if t.utf else "-") * min(t.width() - 2, SECTION_RULE_MAX), "gr"))
        back, restart = self._cannot("back"), self._cannot("restart")
        alt, default = self.cur
        rows = [("<", "back one question" + (f": {nav.answers[-1][0]}" if not back else f" ({back})")),
                ("<<", "start the questions over" + (f" ({restart})" if restart else "")),
                (">", "skip this question: take its no-preference answer (anything available), or its default; the line under the question says which"),
                (">>", f"skip this and every later question the same way and go to the {self.dest}; each skipped answer is shown, and "
                       "the final go-ahead is still yours to type"),
                ("all", "every option, where the question offers it (machine types, regions)"),
                ("none", "no option, where the question offers it (no fallback regions, no exclusions, no spending cap)"),
                ("?", "this list and your answers so far"),
                ("Ctrl-C", "quit; nothing is created in Google Cloud before you confirm it")]
        for k, d in rows:
            t.line(f"  {t.s(k.ljust(8), 'g', 'b')}{d}")
        if nav is not None:
            here = []
            for kind in ("skip", "all", "none"):
                val, note = self._meaning(kind, alt, default)
                here.append(f"{kind}: " + ("not offered" if val is None else (note or "offered")))
            t.line(t.s("  at this question  " + ";  ".join(here), "gr"))
        if nav and nav.answers:
            t.line("")
            t.line(t.s("Your answers so far", "h"))
            w = max(20, min(t.width() - 40, 90))
            for i, (q, v) in enumerate(nav.answers, 1):
                t.line(f"  {i:3d}. {clip(q, w):<{w}s}  {t.s(v, 'c')}")
        t.line("")

    # ---- the questions
    def ask(self, q, default=None, check=None, flag=None, help_text=None, lead=None, alt=None):
        if not self.interactive:
            if default is None:
                self._need(q, flag)
            err = check(str(default)) if check else None
            if err:
                raise SystemExit(f"{q}: {err}")
            return str(default)
        self.skipped = False
        default = self._default(q, default)

        def show(v):
            return str(v)

        def valid(v):
            return check(str(v)) if check else None
        got = self._auto(q, alt, default, show, valid)
        if got is not _NO:
            return str(got)
        self.cur = (alt, default)
        self._gap()
        for ln in lead or []:
            self.t.line(ln)
        if help_text:
            self.t.line(self.t.s(help_text, "gr"))
        self._alt_hint(alt, default, show)
        while True:
            d = f" [{default}]" if default not in (None, "") else ""
            s = self._read(f"{self.t.s('?', 'c', 'b')} {q}{d}: ", q)
            token = self._word(s, alt)
            if token:
                v = self._resolve(q, token, alt, default, show, valid)
                if v is _NO:
                    continue
                return self._accept(q, token, str(v))
            if not s and default is not None:
                s = str(default)
            if not s:
                self.t.line(self.t.s("  an answer is required", "y"))
                continue
            err = check(s) if check else None
            if err:
                self.t.line(self.t.s(f"  {err}", "y"))
                continue
            return self._accept(q, s)

    def choose(self, q, options, default=None, flag=None, help_text=None, alt=None):
        """Pick one option; options are dicts with key, label, and optionally note and disabled (a reason)."""
        keys = [o["key"] for o in options]
        if not self.interactive:
            if default is None:
                self._need(q, flag)
            if default not in keys:
                raise SystemExit(f"{q}: {default!r} is not one of {', '.join(keys)}")
            o = options[keys.index(default)]
            if o.get("disabled"):
                raise SystemExit(f"{q}: {default} is not available: {o['disabled']}")
            return default
        self.skipped = False
        default = self._default(q, default)

        def show(k):
            return visible_text(options[keys.index(k)]["label"]).strip() if k in keys else str(k)

        def valid(k):
            if k not in keys:
                return f"{k} is not offered here"
            return f"it would choose {show(k)}, which is unavailable: {options[keys.index(k)]['disabled']}" if options[keys.index(k)].get("disabled") else None
        got = self._auto(q, alt, default, show, valid)
        if got is not _NO:
            return got
        self.cur = (alt, default)
        self._gap()
        self.t.line(self.t.s(q, "b"))
        if help_text:
            self.t.line(self.t.s(help_text, "gr"))
        for i, o in enumerate(options, 1):
            mark = self.t.s("*", "g") if o["key"] == default else " "
            label = o["label"] if not o.get("disabled") else self.t.s(o["label"], "gr")
            note = f"  {self.t.s(o['note'], 'gr')}" if o.get("note") else ""
            dis = f"  {self.t.s('unavailable: ' + o['disabled'], 'y')}" if o.get("disabled") else ""
            self.t.line(f" {mark}{i:3d}. {label}{note}{dis}")
        self._alt_hint(alt, default, show)
        while True:
            d = f" [{keys.index(default) + 1}]" if default in keys else ""
            s = self._read(f"{self.t.s('?', 'c', 'b')} choose 1-{len(options)}{d}: ", q)
            token = self._word(s, alt)
            if token:
                v = self._resolve(q, token, alt, default, show, valid)
                if v is _NO:
                    continue
                return self._accept(q, token, v)
            if not s and default in keys:
                s = str(keys.index(default) + 1)
            if not s:
                self.t.line(self.t.s(f"  this question has no default: enter a number from 1 to {len(options)}", "y"))
                continue
            pick = None
            if s.isdigit() and 1 <= int(s) <= len(options):
                pick = options[int(s) - 1]
            elif s in keys:
                pick = options[keys.index(s)]
            else:
                # a fragment of one option's name or key also picks it, when it matches only that option
                hits = [o for o in options if s.lower() in o["key"].lower() or s.lower() in visible_text(o["label"]).lower()]
                pick = hits[0] if len(hits) == 1 else None
                if len(hits) > 1:
                    self.t.line(self.t.s(f"  '{s}' matches {len(hits)} options; enter its number", "y"))
                    continue
            if not pick:
                self.t.line(self.t.s("  enter one of the numbers shown, or part of a name", "y"))
                continue
            if pick.get("disabled"):
                self.t.line(self.t.s(f"  {pick['key']} is unavailable: {pick['disabled']}", "y"))
                continue
            return self._accept(q, pick["key"])

    def multi(self, q, options, default=None, flag=None, help_text=None, alt=None):
        """Pick several options by number, range (2-5), key, or 'all'; order of entry is kept."""
        keys = [o["key"] for o in options]
        if not self.interactive:
            if default is None:
                self._need(q, flag)
            bad = [k for k in default if k not in keys]
            if bad:
                raise SystemExit(f"{q}: not available here: {', '.join(bad)}")
            return list(default)
        self.skipped = False
        pref = self._default(q, None)
        if pref is not None:
            default = csv_list(pref)
        enabled = [o["key"] for o in options if not o.get("disabled")]
        alt = dict({"all": (enabled, "every option listed")}, **(alt or {}))

        def show(ks):
            return ", ".join(ks)

        def valid(ks):
            bad = [k for k in ks if k not in enabled]
            return f"not available here: {', '.join(bad)}" if bad else (None if ks else "no option left")
        got = self._auto(q, alt, default, show, valid)
        if got is not _NO:
            return list(got)
        self.cur = (alt, default)
        self._gap()
        self.t.line(self.t.s(q, "b"))
        if help_text:
            self.t.line(self.t.s(help_text, "gr"))
        for i, o in enumerate(options, 1):
            mark = self.t.s("*", "g") if default and o["key"] in default else " "
            note = f"  {self.t.s(o['note'], 'gr')}" if o.get("note") else ""
            dis = f"  {self.t.s('unavailable: ' + o['disabled'], 'y')}" if o.get("disabled") else ""
            self.t.line(f" {mark}{i:3d}. {o['label']}{note}{dis}")
        self._alt_hint(alt, default, show)
        dtext = ",".join(str(keys.index(k) + 1) for k in (default or []) if k in keys)
        while True:
            s = self._read(f"{self.t.s('?', 'c', 'b')} numbers or ranges like 1,3-5" + (f" [{dtext}]" if dtext else "") + ": ", q)
            token = self._word(s, alt)
            if token:
                v = self._resolve(q, token, alt, default, show, valid)
                if v is _NO:
                    continue
                return self._accept(q, token, list(v))
            if not s and default:
                out = [k for k in default if k in keys]
                return self._accept(q, ",".join(out), out)
            out = []
            ok = True
            for part in re.split(r"[,\s]+", s):
                if not part:
                    continue
                if re.fullmatch(r"\d+-\d+", part):
                    a, b = (int(x) for x in part.split("-"))
                    if not (1 <= a <= b <= len(options)):
                        ok = False
                        break
                    out += [options[i - 1]["key"] for i in range(a, b + 1)]
                elif part.isdigit() and 1 <= int(part) <= len(options):
                    out.append(options[int(part) - 1]["key"])
                elif part in keys:
                    out.append(part)
                else:
                    ok = False
                    break
            out = [k for i, k in enumerate(out) if k not in out[:i]]
            dis = [k for k in out if options[keys.index(k)].get("disabled")]
            if not ok or not out:
                self.t.line(self.t.s("  enter numbers like 1,3-5, or all", "y"))
                continue
            if dis:
                self.t.line(self.t.s(f"  unavailable: {', '.join(dis)}", "y"))
                continue
            return self._accept(q, ",".join(out), out)

    def yes(self, q, default=False, flag=None, alt=None):
        if not self.interactive:
            return bool(default)
        self.skipped = False
        pref = self._default(q, None)
        if pref is not None:
            default = pref == "y"

        def show(v):
            return "yes" if v else "no"
        got = self._auto(q, alt, bool(default), show)
        if got is not _NO:
            return bool(got)
        self.cur = (alt, bool(default))
        d = "Y/n" if default else "y/N"
        self._gap()
        self._alt_hint(alt, bool(default), show)
        while True:
            s = self._read(f"{self.t.s('?', 'c', 'b')} {q} [{d}]: ", q).lower()
            token = self._word(s, alt)
            if token:
                v = self._resolve(q, token, alt, bool(default), show)
                if v is _NO:
                    continue
                return self._accept(q, token, bool(v))
            if not s:
                return self._accept(q, "y" if default else "n", bool(default))
            if s in ("y", "yes"):
                return self._accept(q, "y", True)
            if s in ("n", "no"):
                return self._accept(q, "n", False)
            self.t.line(self.t.s("  answer y or n", "y"))

    def typed(self, q, word="yes", preapproved=False):
        """A confirmation that needs the exact word; Enter alone never confirms, and no shortcut answers it."""
        if not self.interactive:
            return bool(preapproved)
        self.skipped = False
        self.cur = ({"skip": (None, "a confirmation is never skipped"), "all": (None, "a confirmation is never skipped")}, None)
        self._gap()
        while True:
            s = self._read(f"{self.t.s('!', 'y', 'b')} {q} Type {self.t.s(word, 'b')} to confirm, anything else cancels: ", q)
            if s.strip().lower() in SHORTCUT_SKIP + SHORTCUT_SKIP_REST + SHORTCUT_ALL:
                self.t.line(self.t.s(f"  this confirmation is never skipped: type {word} to go ahead, or anything else to cancel", "y"))
                continue
            return self._accept(q, s, s == word)


# ------------------------------------------------------------------ sign-in
class AuthError(Exception):
    def __init__(self, kind, message, fix):
        super().__init__(message)
        self.kind, self.message, self.fix = kind, message, fix


SETUP_FILE = os.path.join(HOME, "setup.json")
INSTALL_HINT = "run `python3 gcp_gpu_finder.py setup`, which installs the Google Cloud CLI and signs you in, or install it from https://cloud.google.com/sdk/docs/install"


_SETUP_SEEN = {"mtime": None, "data": {}}


def load_setup():
    """setup.json, read again only when it changes, so the audit trail lists each real read once; an ephemeral session's own copy is in memory."""
    hit = SESSION["mem"].get(os.path.abspath(SETUP_FILE))
    if hit:
        return dict(json.loads(hit[0]))
    try:
        m = os.path.getmtime(SETUP_FILE)
    except OSError:
        return {}
    if _SETUP_SEEN["mtime"] != m:
        _SETUP_SEEN.update(mtime=m, data=load_json(SETUP_FILE, {}) or {})
    return dict(_SETUP_SEEN["data"])


def save_setup(**kv):
    rec = load_setup()
    rec.update({k: v for k, v in kv.items()})
    rec["updated"] = iso()
    atomic_json(SETUP_FILE, rec, 0o600)
    return rec


def gcloud_names():
    return ["gcloud.cmd", "gcloud.exe", "gcloud"] if os.name == "nt" else ["gcloud"]


def gcloud_candidates():
    """Folders where installers put gcloud, for a CLI that is installed but not on PATH."""
    home = os.path.expanduser("~")
    dirs = [os.path.join(os.path.expanduser(GCLOUD_DIR), "bin"), os.path.join(home, "google-cloud-sdk", "bin"),
            "/usr/lib/google-cloud-sdk/bin", "/usr/share/google-cloud-sdk/bin", "/opt/google-cloud-sdk/bin", "/usr/local/google-cloud-sdk/bin",
            "/snap/bin", "/opt/homebrew/share/google-cloud-sdk/bin", "/usr/local/share/google-cloud-sdk/bin",
            "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]
    for env in ("LOCALAPPDATA", "ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env)
        if base:
            dirs.append(os.path.join(base, "Google", "Cloud SDK", "google-cloud-sdk", "bin"))
    return [d for i, d in enumerate(dirs) if d not in dirs[:i]]


def is_exe(path):
    return bool(path) and os.path.isfile(path) and (os.name == "nt" or os.access(path, os.X_OK))


def find_gcloud(with_origin=False):
    """gcloud from GPUF_GCLOUD, the path setup remembered, PATH, or a standard install folder."""
    hits = []
    if os.environ.get("GPUF_GCLOUD"):
        hits.append((os.environ["GPUF_GCLOUD"], "GPUF_GCLOUD"))
    if load_setup().get("gcloud"):
        hits.append((load_setup()["gcloud"], "remembered by setup"))
    for name in gcloud_names():
        p = shutil.which(name)
        if p:
            hits.append((p, "PATH"))
    for d in gcloud_candidates():
        for name in gcloud_names():
            hits.append((os.path.join(d, name), "installed, not on PATH"))
    for p, origin in hits:
        if is_exe(p):
            return (p, origin) if with_origin else p
    return (None, None) if with_origin else None


def gcloud_env(config=None):
    env = dict(os.environ)
    if config and not os.environ.get("CLOUDSDK_ACTIVE_CONFIG_NAME"):
        env["CLOUDSDK_ACTIVE_CONFIG_NAME"] = config
    py = load_setup().get("cloudsdk_python")
    if py and not os.environ.get("CLOUDSDK_PYTHON") and is_exe(py):
        env["CLOUDSDK_PYTHON"] = py
    if SESSION["ephemeral"]:
        if not SESSION["gcloud_ok"]:
            raise AuthError("ephemeral", f"gcloud is not run in this session: {SESSION['why_no_gcloud']}",
                            "sign in with GPUF_ACCESS_TOKEN or on a Compute Engine VM, or start a session that keeps files")
        # every file gcloud writes (token cache, its record of this machine) lands in the session's memory folder; no logs, update checks or reports
        env.update(CLOUDSDK_CONFIG=SESSION["gcloud_config"], CLOUDSDK_CORE_DISABLE_FILE_LOGGING="true",
                   CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK="true", CLOUDSDK_SURVEY_DISABLE_PROMPTS="true",
                   CLOUDSDK_CORE_DISABLE_USAGE_REPORTING="true", PYTHONDONTWRITEBYTECODE="1")
    return env


def gcloud_argv(gcloud, args, config=None):
    """The command as it is shown and logged: the program path, the configuration it runs in, and every argument."""
    return [short_path(gcloud)] + list(args) + ([f"(gcloud configuration {config})"] if config else [])


def run_gcloud(gcloud, args, config=None):
    """One gcloud call with no terminal input, so a sign-in prompt can never hang the run; recorded in the audit trail."""
    t0 = now()
    try:
        r = subprocess.run([gcloud] + args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=GCLOUD_TIMEOUT_S,
                           env=gcloud_env(config))
    except subprocess.TimeoutExpired:
        audit("cmd", argv=gcloud_argv(gcloud, args, config), rc=None, ms=int((now() - t0) * 1000), withheld="no answer; stopped at the deadline")
        raise AuthError("gcloud_timeout", f"gcloud {' '.join(args[:3])} gave no answer within {GCLOUD_TIMEOUT_S} s",
                        "check network access to Google and retry; raise GPUF_GCLOUD_TIMEOUT_S on a slow connection")
    except OSError as exc:
        audit("cmd", argv=gcloud_argv(gcloud, args, config), rc=None, ms=0, withheld=f"could not start: {exc}")
        raise AuthError("gcloud_missing", f"gcloud could not be started: {exc}", INSTALL_HINT)
    out, err = (r.stdout or "").strip(), (r.stderr or "").strip()
    secret = "print-access-token" in args
    audit("cmd", argv=gcloud_argv(gcloud, args, config), rc=r.returncode, ms=int((now() - t0) * 1000),
          withheld="output not recorded: it is an access token, kept in memory only" if secret and r.returncode == 0 else None,
          stdout=None if secret else out[-400:], stderr=err[-400:])
    return r.returncode, out, err


def gcloud_auth_error(stderr, impersonate):
    low = stderr.lower()
    m = re.search(r"active account \[([^\]]+)\] does not have any valid credentials", stderr or "")
    if m:
        return AuthError("not_logged_in", f"gcloud's active account {m.group(1)} has no credentials on this computer",
                         "run `python3 gcp_gpu_finder.py setup` to sign in, or `gcloud auth login`")
    if "do not currently have an active account" in low or "no credentialed accounts" in low:
        return AuthError("not_logged_in", "gcloud has no signed-in account",
                         "run `python3 gcp_gpu_finder.py setup` to sign in, or `gcloud auth login` (a person) or "
                         "`gcloud auth login --cred-file=KEY.json` (a service account)")
    if impersonate and ("impersonat" in low or "getaccesstoken" in low or "serviceaccounttokencreator" in low):
        return AuthError("impersonation", f"gcloud could not act as {impersonate}: {stderr.splitlines()[-1] if stderr else ''}",
                         f"grant your account roles/iam.serviceAccountTokenCreator on {impersonate}")
    if "reauth" in low or "invalid_grant" in low or "problem refreshing" in low or "credentials have expired" in low:
        return AuthError("reauth", "gcloud needs you to sign in again",
                         "run `gcloud auth login`; for runs of days or weeks prefer a service account (--impersonate-service-account) so session limits do not stop the run")
    first = next((ln.strip() for ln in (stderr or "").splitlines() if ln.strip().startswith("ERROR:")), None) or \
        next((ln.strip() for ln in (stderr or "").splitlines() if ln.strip()), "no message")
    return AuthError("gcloud_error", f"gcloud failed: {first}", "run `gcloud auth list` and `gcloud auth print-access-token` to see the problem")


class Tokens:
    """Access tokens from gcloud, the GCE metadata server, or GPUF_ACCESS_TOKEN; never written anywhere."""

    def __init__(self, source="auto", impersonate=None, gcloud=None, config=None):
        self.source_req = source
        self.impersonate = impersonate
        self.gcloud = gcloud or find_gcloud()
        self.config = config if config is not None else load_setup().get("gcloud_config")
        self.source = None
        self.account = None
        self.default_project = None
        self.gcloud_version = None
        self._tok = None
        self._at = 0.0

    def _metadata(self, path):
        req = urllib.request.Request(METADATA + path, headers={"Metadata-Flavor": "Google"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        t0 = now()
        try:
            with opener.open(req, timeout=3) as r:
                body = r.read().decode()
        except OSError as e:
            audit("http", m="GET", host="metadata server (169.254.169.254)", path=path, status=0, ms=int((now() - t0) * 1000), bytes=0,
                  note=f"{type(e).__name__}: not a Compute Engine VM, or no service account")
            raise
        audit("http", m="GET", host="metadata server (169.254.169.254)", path=path, status=200, ms=int((now() - t0) * 1000), bytes=len(body),
              note="access token kept in memory only" if path.endswith("/token") else None)
        return body

    def _gcloud_token(self):
        args = ["auth", "print-access-token", "--quiet"]
        if self.impersonate:
            args.append(f"--impersonate-service-account={self.impersonate}")
        rc, out, err = run_gcloud(self.gcloud, args, self.config)
        tok = out.splitlines()[-1].strip() if out else ""
        if rc != 0 or not tok or " " in tok:
            # only stderr reaches the error text: stdout of print-access-token may hold a token, and the error is printed and logged
            raise gcloud_auth_error(err, self.impersonate)
        return tok

    def _gcloud_value(self, key):
        rc, out, _ = run_gcloud(self.gcloud, ["config", "get-value", key, "--quiet"], self.config)
        v = out.splitlines()[-1].strip() if (rc == 0 and out) else ""
        return None if v in ("", "(unset)") else v

    def resolve(self):
        """Choose the token source and learn the signed-in account and the default project."""
        if self.source_req != "auto":
            order = [self.source_req]
        else:
            order = (["env"] if os.environ.get("GPUF_ACCESS_TOKEN") else []) + (["gcloud"] if self.gcloud else []) + ["metadata"]
        errors = {}
        for src in order:
            try:
                if src == "env":
                    tok = os.environ.get("GPUF_ACCESS_TOKEN", "").strip()
                    if not tok:
                        raise AuthError("env", "GPUF_ACCESS_TOKEN is empty", "set GPUF_ACCESS_TOKEN or use --token-source gcloud")
                    self._tok, self._at = tok, now()
                    self.account = os.environ.get("GPUF_ACCOUNT") or "access token from GPUF_ACCESS_TOKEN"
                elif src == "gcloud":
                    if not self.gcloud:
                        raise AuthError("gcloud_missing", "the Google Cloud CLI (gcloud) is not installed", INSTALL_HINT)
                    self._tok, self._at = self._gcloud_token(), now()
                    self.account = self.impersonate or self._gcloud_value("account")
                    self.default_project = self._gcloud_value("project")
                    rc, out, _ = run_gcloud(self.gcloud, ["version", "--format=value(\"Google Cloud SDK\")"], self.config)
                    self.gcloud_version = out.splitlines()[0] if rc == 0 and out else None
                elif src == "metadata":
                    try:
                        body = json.loads(self._metadata("/instance/service-accounts/default/token"))
                    except (OSError, ValueError) as exc:
                        raise AuthError("metadata", f"this is not a Compute Engine VM with a service account (no metadata server: {type(exc).__name__})",
                                        INSTALL_HINT)
                    self._tok, self._at = body["access_token"], now()
                    self.account = self._metadata("/instance/service-accounts/default/email").strip()
                    self.default_project = self._metadata("/project/project-id").strip()
                else:
                    raise AuthError("source", f"unknown token source {src}", "use auto, gcloud, metadata or env")
                self.source = src
                return self
            except AuthError as exc:
                errors[src] = exc
        # name the cause a person can act on: gcloud's own problem when it exists, else that it is missing
        if "gcloud" in errors:
            raise errors["gcloud"]
        if "metadata" in errors and not self.gcloud and self.source_req == "auto":
            raise AuthError("gcloud_missing", "the Google Cloud CLI (gcloud) was not found, and this is not a Compute Engine VM", INSTALL_HINT)
        raise next(iter(errors.values()), None) or AuthError("none", "no way to sign in was found", INSTALL_HINT)

    def token(self, force=False):
        if self._tok and not force and now() - self._at < TOKEN_REFRESH_S:
            return self._tok
        if self.source == "env":
            if force:
                raise AuthError("expired", "the token in GPUF_ACCESS_TOKEN was refused", "export a fresh token or use --token-source gcloud")
            return self._tok
        if self.source == "gcloud":
            self._tok = self._gcloud_token()
        elif self.source == "metadata":
            try:
                self._tok = json.loads(self._metadata("/instance/service-accounts/default/token"))["access_token"]
            except (OSError, ValueError, KeyError) as exc:
                raise AuthError("metadata", f"metadata token refresh failed: {exc}", "check the VM's service account and scopes")
        else:
            self.resolve()
        self._at = now()
        return self._tok

    def is_person(self):
        a = (self.account or "").lower()
        return bool(a) and "@" in a and not a.endswith("gserviceaccount.com")


# ------------------------------------------------------------------ events log
LEVELS = {"quiet": 0, "normal": 1, "detailed": 2, "trace": 3}
# the least detail level at which each kind of audit record is kept and shown
KIND_LEVEL = {"session": 1, "step": 1, "check": 1, "note": 1, "say": 1, "answer": 1, "nav": 1, "api": 2, "http": 2, "file": 2, "cmd": 2,
              "attempt": 2, "body": 3}
# the session's audit log, so helpers without a context (file access, gcloud, downloads) still record what they do
AUDIT = [None]


def short_path(p):
    home = os.path.expanduser("~")
    p = str(p or "")
    return "~" + p[len(home):] if home and p.startswith(home + os.sep) else p


def size_text(n):
    if n is None:
        return "-"
    return f"{n} B" if n < 1024 else (f"{n / 1024:.1f} KB" if n < 1 << 20 else f"{n / (1 << 20):.1f} MB")


def audit(kind, **fields):
    if AUDIT[0]:
        AUDIT[0].write(kind, **fields)


class Events:
    """The audit trail: append-only JSON lines of every step, check, Google call, file access and command, kept at the log level and
    shown at the screen level; rotated and gzipped by size."""

    def __init__(self, path=None, keep=200, log_level="trace"):
        self.paths = [path] if path else []
        self.ring = []
        self.keep = keep
        self.n = 0
        self.log_level = LEVELS.get(log_level, LEVELS["trace"])
        self.printer = None
        self.report = None
        self.broken = {}

    @property
    def path(self):
        return self.paths[-1] if self.paths else None

    @path.setter
    def path(self, p):
        # a run's own log is added beside the session log, so the session's record stays whole; an ephemeral session keeps none
        if p and p not in self.paths and not SESSION["ephemeral"]:
            self.paths.append(p)
            self.write("session", msg=f"this audit trail is also written to {short_path(p)}")

    def write(self, kind, **fields):
        rec = {"ts": iso(), "t": round(now(), 3), "kind": kind}
        rec.update(fields)
        if self.printer:
            self.printer(rec)
        if self.log_level < KIND_LEVEL.get(kind, 1):
            return
        line = json.dumps(rec, default=str, separators=(",", ":")) + "\n"
        for p in self.paths:
            try:
                private_dir(os.path.dirname(p))
                # the log names the account, project, working folder and every answer: created readable by this user only
                with open(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a", encoding="utf-8") as fh:
                    fh.write(line)
                self.n += 1
                if self.n % 500 == 0 and os.path.getsize(p) > EVENTS_ROTATE_MB * 1e6:
                    self.rotate(p)
            except OSError as e:
                if p not in self.broken:
                    self.broken[p] = f"{type(e).__name__}: {e}"
                    sys.stderr.write(f"audit log cannot be written: {short_path(p)}: {self.broken[p]}; the run continues without that file\n")

    def rotate(self, path):
        base = path[: -len(".jsonl")] if path.endswith(".jsonl") else path
        i = 1
        while os.path.exists(f"{base}.{i}.jsonl.gz"):
            i += 1
        gz = os.open(f"{base}.{i}.jsonl.gz", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with open(path, "rb") as src, open(gz, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb") as dst:
            shutil.copyfileobj(src, dst)
        os.truncate(path, 0)

    def note(self, msg, level="info", **fields):
        self.ring.append((now(), level, msg))
        if len(self.ring) > self.keep:
            del self.ring[: len(self.ring) - self.keep]
        self.write("note", level=level, msg=msg, **fields)


# ------------------------------------------------------------------ rate governor
class Interrupted(Exception):
    """The operator forced an exit (second Ctrl-C) while the program was waiting."""


class Bucket:
    """One per-minute rate budget, aligned to Google's synchronized one-minute windows."""

    def __init__(self, key, limit):
        self.key = key
        self.limit = limit
        self.scale = 1.0
        self.win = None
        self.count = 0
        self.blocked_until = 0.0
        self.cool_until = 0.0
        self.hits = 0
        self.total = 0
        self.peak = 0

    def budget(self):
        if not self.limit or self.limit < 0:
            return 10 ** 9
        return max(1, int(self.limit * RATE_FRACTION * self.scale))

    def take(self, t):
        """Zero when a call may go now (and counts it); otherwise the seconds to wait."""
        w = int(t // 60)
        if w != self.win:
            self.win = w
            self.count = 0
            if t >= self.cool_until and self.scale < 1.0:
                self.scale = min(1.0, self.scale * 1.5)
        if t < self.blocked_until:
            return self.blocked_until - t
        if self.count < self.budget():
            self.count += 1
            self.total += 1
            self.peak = max(self.peak, self.count)
            return 0.0
        return (w + 1) * 60 - t + random.uniform(0.5, 2.5)

    def penalize(self, t):
        self.hits += 1
        self.blocked_until = (int(t // 60) + 1) * 60 + random.uniform(1.0, 4.0)
        self.scale = max(0.05, self.scale / 2)
        self.cool_until = t + RATE_COOL_S


def route(url, method):
    """Which rate bucket a call spends from: (group, region)."""
    u = urllib.parse.urlparse(url)
    # operation links come back on www.googleapis.com/compute/...; they spend the same Compute budget
    if u.netloc == "compute.googleapis.com" or (u.netloc == "www.googleapis.com" and u.path.startswith("/compute/")):
        path = u.path
        is_read = method == "GET" or path.endswith("/wait")
        m = re.search(r"/(zones|regions)/([a-z0-9-]+)(/|$)", path)
        if m and "/aggregated/" not in path:
            region = m.group(2) if m.group(1) == "regions" else region_of(m.group(2))
            return ("reads" if is_read else "writes", region)
        return ("greads" if is_read else "gwrites", "")
    return ("api:" + u.netloc, "")


class Governor:
    """Rate buckets for every (group, region) this run touches, sized from the project's real limits."""

    QUOTA_IDS = {"reads": "ReadsPerMinutePerProjectPerRegion", "writes": "WritesPerMinutePerProjectPerRegion",
                 "greads": "GlobalReadsPerMinutePerProject", "gwrites": "GlobalWritesPerMinutePerProject",
                 "filtered": "ListRequestsFilterCostOverheadPerMinutePerProjectPerRegion"}

    def __init__(self):
        self.buckets = {}
        self.limits = {}
        self.source = "documented defaults"

    def set_limits(self, quota_infos):
        """Read the per-minute Compute limits from Cloud Quotas quota infos (as parsed by QuotaBook)."""
        found = 0
        for grp, qid in self.QUOTA_IDS.items():
            q = (quota_infos or {}).get(qid)
            if not q:
                continue
            for v in q["values"]:
                if v["value"] is None:
                    continue
                self.limits[(grp, v["dims"].get("region", ""))] = v["value"]
                found += 1
        if found:
            self.source = "this project's rate quotas"
            for b in self.buckets.values():
                b.limit = self.limit_for(*b.key)

    def limit_for(self, grp, region):
        if grp.startswith("api:"):
            return int(OTHER_API_PER_MIN / RATE_FRACTION) if RATE_FRACTION > 0 else OTHER_API_PER_MIN
        if (grp, region) in self.limits:
            return self.limits[(grp, region)]
        if (grp, "") in self.limits:
            return self.limits[(grp, "")]
        return {"reads": FALLBACK_READS_PER_MIN, "writes": FALLBACK_WRITES_PER_MIN, "greads": FALLBACK_READS_PER_MIN,
                "gwrites": FALLBACK_WRITES_PER_MIN, "filtered": FALLBACK_FILTERED_PER_MIN}.get(grp, FALLBACK_READS_PER_MIN)

    def bucket(self, grp, region):
        key = (grp, region)
        if key not in self.buckets:
            self.buckets[key] = Bucket(key, self.limit_for(grp, region))
        return self.buckets[key]

    def acquire(self, grp, region, sleeper):
        b = self.bucket(grp, region)
        waited = 0.0
        while True:
            w = b.take(now())
            if w <= 0:
                return waited
            sleeper(w)
            waited += w

    def penalize(self, grp, region):
        self.bucket(grp, region).penalize(now())

    def snapshot(self):
        """This minute's use per bucket, for the dashboard."""
        w = int(now() // 60)
        out = []
        for (grp, region), b in sorted(self.buckets.items()):
            out.append({"group": grp, "region": region, "used": b.count if b.win == w else 0, "budget": b.budget(),
                        "limit": b.limit, "hits": b.hits, "total": b.total, "peak": b.peak, "scale": round(b.scale, 3)})
        return out


# ------------------------------------------------------------------ HTTP client
class ApiError(Exception):
    def __init__(self, status, message, body=None, url=None, method=None, reason=None):
        super().__init__(f"HTTP {status}: {message}")
        self.status, self.message, self.url, self.method = status, message or "", url, method
        self.body = body if isinstance(body, dict) else {}
        err = self.body.get("error") if isinstance(self.body.get("error"), dict) else {}
        self.status_text = err.get("status") or ""
        self.reasons = [e.get("reason") for e in (err.get("errors") or []) if isinstance(e, dict) and e.get("reason")]
        self.details = err.get("details") or []
        self.error_info = next((d for d in self.details if isinstance(d, dict) and str(d.get("@type", "")).endswith("ErrorInfo")), None)
        self.reason = reason or (self.error_info or {}).get("reason") or (self.reasons[0] if self.reasons else "") or self.status_text

    def all_reasons(self):
        out = set(self.reasons)
        out.add(self.reason or "")
        out.add(self.status_text or "")
        if self.error_info:
            out.add(self.error_info.get("reason") or "")
        return {r for r in out if r}

    def short(self):
        return f"{self.reason or self.status}: {self.message.strip().splitlines()[0][:300] if self.message else ''}"


class OpStalled(Exception):
    def __init__(self, op):
        super().__init__(f"operation {op.get('name')} reported nothing new for {OP_STALL_S} s (status {op.get('status')})")
        self.op = op


def is_rate_limit(err):
    rs = {r.upper() for r in err.all_reasons()}
    if rs & {"RATELIMITEXCEEDED", "RATE_LIMIT_EXCEEDED", "USERRATELIMITEXCEEDED"}:
        return True
    return err.status == 429 and "googleapis.com/compute" in (err.url or "")


class Api:
    """Signed, rate-governed HTTPS calls to Google APIs, each one written to the events log."""

    def __init__(self, tokens, governor, events, project=None, ca_bundle=None, user_project=None, stopper=None):
        self.tokens = tokens
        self.gov = governor
        self.ev = events
        self.project = project
        self.stopper = stopper
        ctx = ssl.create_default_context(cafile=ca_bundle) if ca_bundle else ssl.create_default_context()
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
        # with a person's credentials some APIs need a quota project; a service account carries its own
        self.user_project = tokens.is_person() if user_project is None else bool(user_project)
        self.user_project_note = None
        self.calls = 0
        self.errors = 0
        self.offline_at = None
        # the call and the operation in flight, for the live view; replaced whole, so a reader thread never sees half an update
        self.current = None
        self.op = None

    def sleep(self, seconds):
        end = now() + max(0.0, seconds)
        while True:
            if self.stopper and self.stopper.forced:
                raise Interrupted()
            left = end - now()
            if left <= 0:
                return
            time.sleep(min(0.25, left))

    def _phase(self, text):
        cur = self.current
        if cur:
            self.current = dict(cur, phase=text, since=now())

    def _budget_sleep(self, seconds):
        self._phase(f"waiting {human_dur(seconds)} for this minute's API budget")
        self.sleep(seconds)

    def call(self, method, url, params=None, body=None, retries=None, quiet=False):
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
        self.current = {"m": method, "url": url, "t0": now(), "since": now(), "phase": "sending"}
        try:
            return self._call(method, url, body, retries)
        finally:
            self.current = None

    def _call(self, method, url, body, retries):
        data = json.dumps(body).encode() if body is not None else (b"" if method in ("POST", "PUT", "PATCH") else None)
        sent = None
        if body is not None:
            compact = json.dumps(body, separators=(",", ":"), default=str)
            if len(compact) <= DETAIL_BODY_CHARS:
                # short enough to ride on the call's own line, so detailed shows what was asked
                sent = compact
            else:
                u = urllib.parse.urlparse(url)
                self.ev.write("body", m=method, host=u.netloc, path=u.path, body=body)
        grp, region = route(url, method)
        retries = HTTP_RETRIES if retries is None else retries
        if self.offline_at and now() - self.offline_at < OFFLINE_FAST_S:
            # Google was unreachable moments ago: one try per call, so a dead network is reported in seconds, not minutes
            retries = 0
        tries, auth_retry, up_retry, rate_retry = 0, False, False, 0
        while True:
            tries += 1
            if self.gov:
                self.gov.acquire(grp, region, self._budget_sleep)
                if method == "GET" and "filter=" in url and grp in ("reads", "greads"):
                    self.gov.acquire("filtered", region, self._budget_sleep)
            self._phase("waiting for Google's answer" + (f", try {tries}" if tries > 1 else ""))
            hdr = {"Authorization": "Bearer " + self.tokens.token(), "User-Agent": UA, "Accept": "application/json"}
            if data is not None:
                hdr["Content-Type"] = "application/json"
            sent_up = bool(self.user_project and self.project and "googleapis.com" in url)
            if sent_up:
                hdr["X-Goog-User-Project"] = self.project
            req = urllib.request.Request(url, data=data, method=method, headers=hdr)
            t0 = now()
            self.calls += 1
            try:
                with self.opener.open(req, timeout=HTTP_TIMEOUT_S) as r:
                    raw = r.read()
                    status = r.status
                self._log(method, url, grp, region, status, "", t0, len(raw), sent=sent)
                self.offline_at = None
                return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                raw = e.read() or b""
                try:
                    eb = json.loads(raw)
                except ValueError:
                    eb = {"error": {"message": raw[:600].decode("utf-8", "replace")}}
                msg = (eb.get("error") or {}).get("message") if isinstance(eb.get("error"), dict) else str(eb.get("error"))
                err = ApiError(e.code, msg or e.reason, eb, url=url, method=method)
                self._log(method, url, grp, region, e.code, err.reason, t0, len(raw), note=(msg or e.reason or "")[:300], sent=sent)
                if e.code == 401 and not auth_retry:
                    auth_retry = True
                    self.tokens.token(force=True)
                    continue
                if is_rate_limit(err) and self.gov and rate_retry < retries + 3:
                    rate_retry += 1
                    self.gov.penalize(grp, region)
                    self.ev.note(f"Google answered rateLimitExceeded on {grp} {region or 'global'}; pausing that budget to the next minute", "warn")
                    continue
                if sent_up and not up_retry and self._user_project_problem(err):
                    up_retry = True
                    self.user_project = False
                    self.user_project_note = err.short()
                    self.ev.note("calls continue without the X-Goog-User-Project header: " + err.short(), "warn")
                    continue
                if e.code in (500, 502, 503, 504) and tries <= retries:
                    self._phase(f"Google answered HTTP {e.code}; retrying, {tries} of {retries}")
                    self.sleep(jitter(HTTP_BACKOFF_S * 2 ** (tries - 1)))
                    continue
                self.errors += 1
                raise err
            except ssl.SSLCertVerificationError as e:
                self._log(method, url, grp, region, 0, "TLS_VERIFY", t0, 0, sent=sent)
                raise ApiError(0, f"TLS certificate verification failed: {e}", {"error": {"status": "TLS"}}, url, method, reason="TLS_VERIFY")
            except (urllib.error.URLError, socket.timeout, ConnectionError, OSError, http.client.HTTPException) as e:
                inner = getattr(e, "reason", e)
                if isinstance(inner, ssl.SSLCertVerificationError):
                    self._log(method, url, grp, region, 0, "TLS_VERIFY", t0, 0, sent=sent)
                    raise ApiError(0, f"TLS certificate verification failed: {inner}", {"error": {"status": "TLS"}}, url, method, reason="TLS_VERIFY")
                self._log(method, url, grp, region, 0, "NETWORK", t0, 0, note=f"{type(inner).__name__}: {inner}", sent=sent)
                if tries <= retries:
                    self._phase(f"cannot reach Google ({type(inner).__name__}); retrying, {tries} of {retries}")
                    self.sleep(jitter(HTTP_BACKOFF_S * 2 ** (tries - 1)))
                    continue
                self.errors += 1
                self.offline_at = now()
                raise ApiError(0, f"cannot reach {urllib.parse.urlparse(url).netloc} after {tries} tries: {type(inner).__name__}: {inner}",
                               {"error": {"status": "NETWORK"}}, url, method, reason="NETWORK")

    @staticmethod
    def _user_project_problem(err):
        low = (err.message or "").lower()
        return "USER_PROJECT_DENIED" in err.all_reasons() or ("serviceusage.services.use" in low) or ("caller does not have required permission to use project" in low)

    def _log(self, method, url, grp, region, status, reason, t0, size, note=None, sent=None):
        u = urllib.parse.urlparse(url)
        rec = {"m": method, "host": u.netloc, "path": u.path, "grp": grp, "region": region, "status": status, "ms": int((now() - t0) * 1000), "bytes": size,
               "quota_project": bool(self.user_project and self.project)}
        if u.query:
            rec["query"] = urllib.parse.unquote(u.query)
        if reason:
            rec["reason"] = reason
        if note:
            rec["note"] = note
        if sent:
            rec["sent"] = sent
        self.ev.write("api", **rec)

    def get(self, url, **params):
        return self.call("GET", url, params=params)

    def pages(self, url, key, params=None):
        params = dict(params or {})
        tok = None
        while True:
            if tok:
                params["pageToken"] = tok
            body = self.call("GET", url, params=params)
            for item in body.get(key) or []:
                yield item
            tok = body.get("nextPageToken")
            if not tok:
                return

    def aggregated(self, kind, key=None, params=None):
        """A Compute aggregatedList as {zone or region: [items]}; unreachable scopes are reported, not hidden."""
        key = key or kind
        params = dict(params or {})
        params.setdefault("maxResults", 500)
        out, tok = {}, None
        while True:
            if tok:
                params["pageToken"] = tok
            body = self.call("GET", f"{COMPUTE}/projects/{self.project}/aggregated/{kind}", params=params)
            for scope, v in (body.get("items") or {}).items():
                items = v.get(key) or []
                if items:
                    out.setdefault(tail(scope), []).extend(items)
            for u in body.get("unreachables") or []:
                self.ev.note(f"Google reported {u} unreachable while listing {kind}", "warn")
            tok = body.get("nextPageToken")
            if not tok:
                return out

    def wait_op(self, op):
        """Follow a Compute operation with the wait call until it is done; stalls are reported, live work is never cut short."""
        url = op.get("selfLink")
        seen = (op.get("status"), op.get("progress"))
        last = t0 = now()
        try:
            while op.get("status") != "DONE":
                if self.stopper and self.stopper.forced:
                    raise Interrupted()
                self.op = {"name": op.get("name"), "type": op.get("operationType"), "target": tail(op.get("targetLink") or ""),
                           "status": op.get("status"), "progress": op.get("progress"), "since": t0}
                op = self.call("POST", url + "/wait")
                cur = (op.get("status"), op.get("progress"))
                if cur != seen:
                    seen, last = cur, now()
                elif now() - last >= OP_STALL_S:
                    raise OpStalled(op)
            return op
        finally:
            self.op = None


def op_error(op):
    """An ApiError for a finished Compute operation that failed, else None."""
    errs = ((op or {}).get("error") or {}).get("errors") or []
    if not errs:
        return None
    msgs = "; ".join(f"{e.get('code')}: {e.get('message')}" for e in errs)
    body = {"error": {"errors": [{"reason": e.get("code"), "message": e.get("message")} for e in errs],
                      "details": [d for e in errs for d in (e.get("errorDetails") or [])]}}
    err = ApiError(op.get("httpErrorStatusCode") or 0, msgs, body, url=op.get("targetLink"), method=op.get("operationType"))
    err.op = op
    return err


# ------------------------------------------------------------------ what went wrong, and how to fix it
TRANSIENT = {"stockout", "reservation_limit", "rate", "network", "server", "stalled", "unknown"}
# causes that apply to the whole project and method, not to one zone or size
PROJECT_WIDE = {"permission", "api_disabled", "billing", "user_project", "vpc_sc", "auth", "tls", "org_policy", "not_offered"}


class Cause:
    def __init__(self, kind, title, fix="", detail="", **extra):
        self.kind, self.title, self.fix, self.detail = kind, title, fix, detail
        self.transient = kind in TRANSIENT
        self.extra = extra

    def __repr__(self):
        return f"Cause({self.kind}: {self.title})"


PERM_RES = [re.compile(r"Required '([a-z0-9]+(?:\.[A-Za-z0-9]+)+)' permission"),
            re.compile(r"[Pp]ermission '([a-z0-9]+(?:\.[A-Za-z0-9]+)+)'"),
            re.compile(r"\b(compute\.[a-zA-Z]+\.[a-zA-Z]+)\b")]


def quota_names(err):
    names = re.findall(r"Quota '([A-Za-z0-9_-]+)' exceeded", err.message or "")
    for d in err.details:
        qi = d.get("quotaInfo") if isinstance(d, dict) else None
        if qi:
            names.append(qi.get("limitName") or qi.get("metricName"))
    return [n for i, n in enumerate(names) if n and n not in names[:i]]


def classify(err, project=None):
    """Name the cause of a failure and the exact fix; transient causes are retried, the rest park the target."""
    p = project or "PROJECT_ID"
    if isinstance(err, AuthError):
        return Cause("auth", err.message, err.fix)
    if isinstance(err, OpStalled):
        return Cause("stalled", str(err), "the request is tracked by name and reconciled on the next check")
    if not isinstance(err, ApiError):
        return Cause("unknown", f"{type(err).__name__}: {err}", "retried with backoff; see events.jsonl for the full record")
    msg = err.message or ""
    low = msg.lower()
    rs = {r.upper() for r in err.all_reasons()}
    if err.reason == "TLS_VERIFY":
        return Cause("tls", "TLS certificate verification failed (often a corporate proxy that inspects HTTPS)",
                     "pass --ca-bundle /path/to/corporate-ca.pem (or set GPUF_CA_BUNDLE)")
    if err.reason == "NETWORK":
        return Cause("network", msg[:200], "retried with backoff; check connectivity, HTTPS_PROXY and NO_PROXY")
    if err.reason == "NO_SUBNET":
        return Cause("no_subnet", msg, "create a subnet in that region, pass --subnet, or use the reservation method (it needs no network)")
    if rs & {"ZONE_RESOURCE_POOL_EXHAUSTED", "ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS", "RESOURCE_POOL_EXHAUSTED", "RESOURCE_AVAILABILITY"} or \
            "does not have enough resources available" in low or "resource_availability" in low or "currently unavailable" in low or \
            "not enough resources" in low or "insufficient capacity" in low or "no capacity" in low or "could not be provisioned" in low or \
            ("mincount" in low.replace(" ", "") and "could not" in low):
        return Cause("stockout", "no free capacity for this request right now", "the loop retries with backoff and tries the alternatives you allowed")
    if "RESERVATION_CAPACITY_LIMIT_EXCEEDED" in rs or "reservation capacity limit" in low:
        return Cause("reservation_limit", "the zone has no reservation capacity left for this machine family", "retried later; other zones and sizes are tried meanwhile")
    if is_rate_limit(err):
        return Cause("rate", "Google's per-minute API limit was reached", "that budget pauses to the next minute and halves for a cool-down")
    if rs & {"QUOTA_EXCEEDED", "QUOTAEXCEEDED"} or re.search(r"quota '[^']+' exceeded", low) or "quota exceeded" in low:
        names = quota_names(err)
        return Cause("quota", "quota limit reached" + (f": {', '.join(names)}" if names else ""),
                     f"see the quota panel; quota requests go through {CONSOLE}/iam-admin/quotas?project={p}", quotas=names)
    if rs & {"SERVICE_DISABLED", "ACCESSNOTCONFIGURED"} or "has not been used in project" in low or ("api" in low and "is disabled" in low):
        svc = ((err.error_info or {}).get("metadata") or {}).get("service")
        if not svc:
            m = re.search(r"([a-z0-9-]+\.googleapis\.com)", msg)
            svc = m.group(1) if m else (urllib.parse.urlparse(err.url or "").netloc or "the API")
        return Cause("api_disabled", f"{svc} is not enabled on {p}", f"gcloud services enable {svc} --project {p}", service=svc)
    if "BILLING_DISABLED" in rs or ("billing" in low and any(w in low for w in ("disabled", "not been enabled", "not enabled", "closed", "delinquent"))):
        return Cause("billing", f"billing is not enabled for {p}", f"link an open billing account: {CONSOLE}/billing/linkedaccount?project={p}")
    if "USER_PROJECT_DENIED" in rs or "quota project" in low:
        return Cause("user_project", "this API needs a quota project for your user credentials",
                     f"grant serviceusage.services.use on {p} (roles/serviceusage.serviceUsageConsumer), or sign in with a service account")
    if "SECURITY_POLICY_VIOLATED" in rs or "vpc service controls" in low or "vpcservicecontrols" in low.replace(" ", ""):
        m = re.search(r"vpcServiceControlsUniqueIdentifier[\"': ]+([A-Za-z0-9_-]+)", msg)
        return Cause("vpc_sc", "blocked by a VPC Service Controls perimeter",
                     "give your network administrator this request's identifier" + (f" {m.group(1)}" if m else "") + " and the API named in it")
    m = re.search(r"constraints/([A-Za-z0-9_.]+)", msg)
    if m or "CONSTRAINT_VIOLATED" in rs or "ORG_POLICY" in " ".join(rs):
        c = m.group(1) if m else "an organization policy"
        return Cause("org_policy", f"blocked by organization policy constraints/{c}",
                     f"ask your organization administrator to allow it, or choose options the policy allows ({CONSOLE}/iam-admin/orgpolicies?project={p})",
                     constraint=c)
    if "not available for this project" in low or "is not enabled for this project" in low or "not supported for this project" in low:
        return Cause("not_offered", f"Google does not offer this to the project: {msg.strip().rstrip('.')}",
                     "choose another holding method, or ask your Google account team to enable it for this project")
    m = re.search(r"permission denied on '?locations/([a-z0-9-]+)", low)
    if m:
        return Cause("region_access", f"{m.group(1)} is not open to this project", "the region is dropped from the plan; ask your Google account team for access if you need it",
                     region=m.group(1))
    if err.status == 403 or "IAM_PERMISSION_DENIED" in rs or "FORBIDDEN" in rs or "PERMISSION_DENIED" in rs:
        perms = []
        for rx in PERM_RES:
            perms += [x for x in rx.findall(msg) if x not in perms]
            if perms:
                break
        return Cause("permission", "permission denied" + (f": {', '.join(perms)}" if perms else ""),
                     "run `doctor` for the missing permissions and the smallest role that grants them", perms=perms)
    if err.status == 404:
        return Cause("not_found", msg[:200] or "not found", "check the project id, region, zone and machine type")
    if err.status == 409:
        return Cause("exists", msg[:200] or "already exists", "the existing resource is reconciled by name")
    if err.status == 429:
        return Cause("rate", "too many requests", "paused and retried after the next minute")
    if err.status == 400 or "INVALID" in " ".join(rs) or "BADREQUEST" in rs:
        return Cause("invalid", msg[:300] or "the request was refused as invalid", "this option is parked; the message names the field Google refused")
    if err.status >= 500:
        return Cause("server", msg[:200] or f"HTTP {err.status}", "retried with backoff")
    return Cause("unknown", err.short(), "retried with backoff; see events.jsonl")


# ------------------------------------------------------------------ stopping and run locks
class Stopper:
    """Turns Ctrl-C, SIGTERM and a closed terminal into a graceful stop; a second Ctrl-C forces exit."""

    def __init__(self, term=None):
        self.term = term
        self.stopping = False
        self.forced = False
        self.reason = None
        self.ask = True
        self._old = {}

    def install(self):
        self._old[signal.SIGINT] = signal.signal(signal.SIGINT, self._on_int)
        self._old[signal.SIGTERM] = signal.signal(signal.SIGTERM, self._on_term)
        if hasattr(signal, "SIGHUP"):
            self._old[signal.SIGHUP] = signal.signal(signal.SIGHUP, self._on_hup)
        if hasattr(signal, "SIGBREAK"):
            self._old[signal.SIGBREAK] = signal.signal(signal.SIGBREAK, self._on_term)

    def restore(self):
        for sig, old in self._old.items():
            try:
                signal.signal(sig, old)
            except (ValueError, TypeError, OSError):
                pass
        self._old = {}

    def request(self, reason, ask):
        if self.stopping:
            self.forced = True
            return
        self.stopping, self.reason, self.ask = True, reason, ask

    def _on_int(self, signum, frame):
        if self.stopping:
            self.forced = True
            raise KeyboardInterrupt()
        self.request("Ctrl-C", True)

    def _on_term(self, signum, frame):
        if self.stopping:
            self.forced = True
        self.request("SIGTERM", False)

    def _on_hup(self, signum, frame):
        if self.term:
            self.term.dead = True
        self.request("terminal closed (SIGHUP)", False)


class RunLock:
    """One process per run: a second copy of the same run refuses to start."""

    def __init__(self, path):
        self.path = path
        self.fh = None

    def acquire(self):
        if SESSION["ephemeral"]:
            return self
        private_dir(os.path.dirname(self.path))
        self.fh = open(os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600), "r+")
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.seek(0)
            pid = self.fh.read().strip()
            self.fh.close()
            self.fh = None
            raise SystemExit(f"this run is already active in another process (pid {pid or 'unknown'}); stop it first or use `status`")
        self.fh.seek(0)
        self.fh.truncate()
        self.fh.write(str(os.getpid()))
        self.fh.flush()
        return self

    def release(self):
        if self.fh:
            try:
                self.fh.close()
            except OSError:
                pass
            self.fh = None


# ------------------------------------------------------------------ hardware facts the API does not report
# GPU memory for accelerators whose catalog description omits it (NVIDIA product specifications); the API
# description gives it for the rest, for example "NVIDIA H100 80GB" or "NVIDIA B200 180GB".
GPU_MEMORY_GB = {"nvidia-rtx-pro-6000": 96, "nvidia-l4": 24, "nvidia-tesla-t4": 16, "nvidia-tesla-v100": 16,
                 "nvidia-tesla-p4": 8, "nvidia-tesla-p100": 16}
# NVIDIA architecture by accelerator name fragment, shown beside each GPU in the GPU list.
GPU_ARCH = [("rtx-pro-6000", "Blackwell"), ("gb300", "Blackwell"), ("gb200", "Blackwell"), ("b200", "Blackwell"), ("vr200", "Rubin"),
            ("h200", "Hopper"), ("h100", "Hopper"), ("l4", "Ada"), ("a100", "Ampere"), ("v100", "Volta"), ("t4", "Turing"),
            ("p100", "Pascal"), ("p4", "Pascal")]
# Boot disk type each machine family accepts (Compute Engine machine series docs); its regional storage quota.
BOOT_DISK = {"g4": "hyperdisk-balanced", "a3": "hyperdisk-balanced", "a4": "hyperdisk-balanced", "a4x": "hyperdisk-balanced",
             "a5x": "hyperdisk-balanced", "g2": "pd-balanced", "a2": "pd-balanced", "n1": "pd-balanced"}
DISK_QUOTA = {"hyperdisk-balanced": "HDB-TOTAL-GB-per-project-region", "pd-balanced": "SSD-TOTAL-GB-per-project-region"}
# Which holding methods Google offers for which machines (docs: GPU machine types, on-demand reservations,
# flex-start VMs, calendar-mode future reservations). Google's own answer at create time still decides.
METHODS = ["reservation", "vms", "spot", "flex", "flex-group", "calendar"]
METHOD_LABEL = {"reservation": "on-demand reservation", "vms": "on-demand VMs", "spot": "Spot VMs", "flex": "flex-start VMs",
                "flex-group": "flex-start group (all at once)", "calendar": "calendar-mode future reservation"}
CALENDAR_TYPES = ("a4-highgpu-8g", "a3-ultragpu-8g", "a3-megagpu-8g", "a3-highgpu-8g", "a3-edgegpu-8g")
FLEX_FAMILIES = ("a2", "g2", "g4", "n1")


def method_allows(method, shape):
    """Whether Google offers a holding method for a machine shape, with the reason when it does not."""
    name, fam = shape["name"], shape["family"]
    base = shape.get("base") or name
    if method == "calendar":
        return (base in CALENDAR_TYPES, "calendar mode covers A4, A3 Ultra, A3 Mega, A3 High 8-GPU and A3 Edge only")
    if method == "flex":
        return (fam in FLEX_FAMILIES, "standalone flex-start VMs cover A2, G2, G4 and N1; use flex-group for A3 and A4")
    if method in ("reservation", "vms"):
        if fam in ("a4", "a4x", "a5x") or base.startswith("a3-ultragpu"):
            return (False, "Google offers this machine through spot, flex-start, calendar mode or committed capacity only")
        if re.fullmatch(r"a3-highgpu-[124]g", base):
            return (False, "a3-highgpu-1g, -2g and -4g run only as Spot or flex-start VMs")
        if shape.get("fraction", 1.0) < 1.0 and method == "reservation":
            return (True, "")
        return (True, "")
    return (True, "")


def accel_arch(accel):
    for frag, arch in GPU_ARCH:
        if frag in (accel or ""):
            return arch
    return None


def accel_cores(accel):
    """Quota-name cores for an accelerator: nvidia-h100-80gb gives H100-80GB then H100."""
    core = re.sub(r"^nvidia-(tesla-)?", "", accel or "").upper()
    out = [core]
    short = re.sub(r"-\d+GB$", "", core)
    if short != core:
        out.append(short)
    return out


# ------------------------------------------------------------------ regions
GEO = [("asia-pacific", ("asia-", "australia-")), ("europe", ("europe-",)), ("north-america", ("us-", "northamerica-")),
       ("south-america", ("southamerica-",)), ("middle-east", ("me-",)), ("africa", ("africa-",))]


def geo_of(region):
    for name, prefixes in GEO:
        if region.startswith(prefixes):
            return name
    return "other"


def expand_regions(spec, known):
    """Turn names, geographic groups (asia-pacific), prefixes (asia, us, europe) or 'all' into known region names, in order."""
    out = []
    for raw in spec or []:
        item = raw.strip().lower()
        if not item:
            continue
        if item == "all":
            hits = sorted(known)
        elif item in dict(GEO):
            hits = sorted(r for r in known if geo_of(r) == item)
        elif item in known:
            hits = [item]
        else:
            hits = sorted(r for r in known if r.startswith(item + "-") or r.startswith(item))
        if not hits:
            raise SystemExit(f"region or group {raw!r} matches no region this project can see")
        out += [h for h in hits if h not in out]
    return out


# ------------------------------------------------------------------ run context
class Ctx:
    """Everything a run shares: terminal, prompts, sign-in, API client, caches and the latest discoveries."""

    def __init__(self, term, prompter, tokens, api, gov, events, project, stopper, opts):
        self.t, self.ask, self.tokens, self.api, self.gov, self.ev = term, prompter, tokens, api, gov, events
        self.project, self.stop, self.opts = project, stopper, opts
        self.rep = getattr(events, "report", None) or Report(term, events, "quiet")
        self.catalog = None
        self.book = None
        self.prices = None
        self.report = None
        self.caps = {}
        self.advice = {}
        self.prefs = None
        self.org = {}
        self.subnets = None
        self.blocked_regions = set()
        self.cmek_required = False
        self.project_info = {}

    def cache_path(self, name):
        return os.path.join(HOME, "cache", f"{safe_name(self.project or 'none')}-{name}.json")

    def say(self, msg, style=None):
        self.t.line(self.t.s(msg, style) if style else msg)


# ------------------------------------------------------------------ preflight
CAPS = {
    "read": ["compute.regions.list", "compute.zones.list", "compute.machineTypes.list", "compute.acceleratorTypes.list",
             "compute.instances.list", "compute.reservations.list", "compute.disks.list", "compute.regions.get", "compute.projects.get",
             "resourcemanager.projects.get"],
    "quota_read": ["cloudquotas.quotas.get"],
    "quota_request": ["cloudquotas.quotas.update"],
    "reservation": ["compute.reservations.create", "compute.reservations.delete", "compute.reservations.get"],
    "vms": ["compute.instances.create", "compute.instances.delete", "compute.instances.get", "compute.instances.setLabels",
            "compute.disks.create", "compute.subnetworks.use"],
    "flex-group": ["compute.instances.create", "compute.instances.delete", "compute.instances.setLabels", "compute.disks.create",
                   "compute.subnetworks.use", "compute.instanceTemplates.create", "compute.instanceTemplates.delete",
                   "compute.instanceTemplates.get", "compute.instanceTemplates.useReadOnly", "compute.instanceGroupManagers.create",
                   "compute.instanceGroupManagers.delete", "compute.instanceGroupManagers.get", "compute.instanceGroupManagers.update"],
    "calendar": ["compute.advice.calendarMode", "compute.futureReservations.create", "compute.futureReservations.get",
                 "compute.futureReservations.cancel", "compute.futureReservations.delete"],
    "advisor": ["compute.advice.capacity"],
    "services": ["serviceusage.services.get"],
    "user_project": ["serviceusage.services.use"],
    "org_policy": ["orgpolicy.policy.get"],
    "enable_apis": ["serviceusage.services.enable"],
    "network": ["compute.networks.create"],
}
CAPS["spot"] = CAPS["vms"]
CAPS["flex"] = CAPS["vms"]
CAP_USE = {"read": "list zones, machine types, GPUs, VMs, reservations and disks", "quota_read": "read quota limits",
           "quota_request": "file a quota increase request, only when you choose to", "reservation": "create and delete reservations",
           "vms": "create and delete VMs (on-demand, spot, flex-start)", "flex-group": "flex-start through a managed instance group",
           "calendar": "calendar-mode future reservations", "advisor": "ask the capacity advisor where GPUs are free",
           "user_project": "charge API calls to this project's quota", "org_policy": "read organization policies"}
METHOD_CAP = {"reservation": "reservation", "vms": "vms", "spot": "spot", "flex": "flex", "flex-group": "flex-group", "calendar": "calendar"}
APIS = [("compute.googleapis.com", True, "everything"), ("cloudquotas.googleapis.com", False, "quota limits and quota requests"),
        ("cloudbilling.googleapis.com", False, "billing status and prices"), ("cloudresourcemanager.googleapis.com", False, "permission and policy checks"),
        ("iam.googleapis.com", False, "role suggestions"), ("serviceusage.googleapis.com", False, "the API check itself"),
        ("aiplatform.googleapis.com", False, "NVIDIA models in Vertex AI Model Garden")]
ORG_CONSTRAINTS = ["gcp.resourceLocations", "compute.requireShieldedVm", "compute.trustedImageProjects", "compute.restrictNonCmekServices"]
LOCATION_GROUPS = {"us": "us", "eu": "europe", "europe": "europe", "asia": "asia", "northamerica": "northamerica", "southamerica": "southamerica",
                   "australia": "australia", "me": "me", "africa": "africa"}


class Check:
    def __init__(self, name, status, detail, fix="", more=""):
        self.name, self.status, self.detail, self.fix, self.more = name, status, detail, fix, more

    def as_dict(self):
        return {"name": self.name, "status": self.status, "detail": self.detail, "fix": self.fix, "more": self.more}


def test_permissions(api, project, perms):
    """testIamPermissions on the project; names Google cannot test on a project are dropped instead of failing the call."""
    perms = sorted(set(perms))
    dropped = []
    for _ in range(12):
        try:
            got = api.call("POST", f"{CRM1}/projects/{project}:testIamPermissions", body={"permissions": perms})
            return set(got.get("permissions") or []), dropped
        except ApiError as e:
            m = re.search(r"Permission ([a-zA-Z0-9_.]+) is not valid", e.message or "")
            if e.status == 400 and m and m.group(1) in perms:
                perms.remove(m.group(1))
                dropped.append(m.group(1))
                continue
            if e.status == 400:
                testable = set()
                body = {"fullResourceName": f"//cloudresourcemanager.googleapis.com/projects/{project}", "pageSize": 1000}
                while True:
                    q = api.call("POST", f"{IAM}/permissions:queryTestablePermissions", body=body)
                    testable |= {p["name"] for p in q.get("permissions") or []}
                    if not q.get("nextPageToken"):
                        break
                    body["pageToken"] = q["nextPageToken"]
                dropped += [p for p in perms if p not in testable]
                perms = [p for p in perms if p in testable]
                continue
            raise
    raise SystemExit("could not test permissions: Google kept refusing the permission list")


def role_index(ctx):
    """Predefined IAM roles with their permissions, cached, for 'smallest role that grants this' suggestions."""
    path = os.path.join(HOME, "cache", "roles-v2.json")
    cur = load_json(path, {})
    if cur.get("fetched") and now() - cur["fetched"] < ROLES_TTL_S:
        return cur["roles"]
    ctx.rep.say("reading Google's predefined IAM roles (IAM API, roles.list) to name the smallest role that grants what is missing")
    roles = []
    for r in ctx.api.pages(f"{IAM}/roles", "roles", {"view": "FULL", "pageSize": 1000}):
        if r.get("deleted") or r.get("stage") == "DEPRECATED":
            continue
        roles.append({"name": r["name"], "title": r.get("title", ""), "stage": r.get("stage") or "GA", "perms": sorted(r.get("includedPermissions") or [])})
    atomic_json(path, {"fetched": now(), "roles": roles}, 0o644)
    return roles


def suggest_role(ctx, missing):
    """The smallest grantable predefined role that holds every missing permission, preferring the permissions' own product."""
    try:
        roles = role_index(ctx)
    except (ApiError, AuthError) as e:
        return None, f"role list unavailable ({classify(e).title})"
    need = set(missing)
    # service-agent roles belong to Google's own robot accounts and must never be granted to people or workloads
    fits = [r for r in roles if need <= set(r["perms"]) and not r["name"].lower().endswith("serviceagent")
            and "service agent" not in r["title"].lower()]
    if not fits:
        return None, "no single predefined role grants all of them; grant them separately or through a custom role"
    products = {p.split(".")[0] for p in need}
    own = [r for r in fits if r["name"].split("/")[-1].split(".")[0] in products]
    best = min(own or fits, key=lambda r: (len(r["perms"]), r.get("stage", "GA") != "GA", len(r["name"])))
    return best, f"{best['name']} ({best['title']}, {len(best['perms'])} permissions)"


def member_of(account):
    if not account or "@" not in account:
        return "user:ACCOUNT"
    return ("serviceAccount:" if account.endswith("gserviceaccount.com") else "user:") + account


def location_allowed(region, policy):
    """True, False, or None (cannot tell) for a region under an effective gcp.resourceLocations policy."""
    lp = (policy or {}).get("listPolicy")
    if not lp:
        return True
    if lp.get("allValues") == "DENY":
        return False
    if lp.get("allValues") == "ALLOW":
        return True

    def match(v):
        v = v.replace("in:", "").replace("is:", "").lower()
        if v.endswith("-locations"):
            g = v[: -len("-locations")]
            if g == region:
                return True
            pref = LOCATION_GROUPS.get(g)
            if pref:
                return region.startswith(pref + "-")
            return None
        return v == region or v.startswith(region + "-")

    denied = [match(v) for v in lp.get("deniedValues") or []]
    if any(x is True for x in denied):
        return False
    allowed = [match(v) for v in lp.get("allowedValues") or []]
    if not allowed:
        return True
    if any(x is True for x in allowed):
        return True
    return None if any(x is None for x in allowed) else False


def check_act_as(ctx, sa):
    """Whether the caller may attach a service account to VMs (iam.serviceAccounts.actAs on that account)."""
    try:
        r = ctx.api.call("POST", f"{IAM}/projects/-/serviceAccounts/{sa}:testIamPermissions", body={"permissions": ["iam.serviceAccounts.actAs"]})
        ok = "iam.serviceAccounts.actAs" in (r.get("permissions") or [])
        return Check("VM service account", "ok" if ok else "fail", f"{sa}: " + ("can be attached" if ok else "iam.serviceAccounts.actAs is missing"),
                     "" if ok else f"grant roles/iam.serviceAccountUser on {sa} to {ctx.tokens.account}, or run without --vm-service-account")
    except ApiError as e:
        c = classify(e, ctx.project)
        return Check("VM service account", "fail", f"{sa}: {c.title}", c.fix)


# where each check's answer comes from, shown beside it
CHECK_SOURCE = [("python", "this computer"), ("sign-in", "the sign-in step above"), ("long runs", "the signed-in account's type"),
                ("proxy", "the HTTPS_PROXY variable"), ("network", "Resource Manager API, projects.get"),
                ("project", "Resource Manager API, projects.get"), ("api ", "Service Usage API, services.get"),
                ("billing", "Cloud Billing API, projects.getBillingInfo"), ("can ", "Resource Manager API, projects.testIamPermissions"),
                ("permissions", "Resource Manager API, projects.testIamPermissions"), ("quota project header", "answers to the calls above"),
                ("policy ", "Resource Manager API, projects.getEffectiveOrgPolicy"), ("organization policy", "Resource Manager API, projects.getEffectiveOrgPolicy"),
                ("networks", "Compute Engine API, subnetworks.aggregatedList"), ("shared VPC subnet", "Compute Engine API, subnetworks.testIamPermissions"),
                ("VM service account", "IAM API, serviceAccounts.testIamPermissions")]


def check_source(name):
    # an entry ending in a space matches every check that starts with it; the others match one check name exactly
    return next((src for key, src in CHECK_SOURCE if (key.endswith(" ") and name.startswith(key)) or name == key), "")


def show_check(ctx, c):
    """One check on screen as soon as it is made, with where its answer came from and, when it is not ok, the fix."""
    rep, t = ctx.rep, ctx.t
    src = check_source(c.name)
    ctx.ev.write("check", name=c.name, status=c.status, detail=c.detail, fix=c.fix, more=c.more, source=src)
    if t.in_dash or (rep.level < 1 and c.status in ("ok", "info")):
        return
    mark = {"ok": t.s("ok  ", "g"), "warn": t.s("warn", "y"), "fail": t.s("FAIL", "r", "b"), "unknown": t.s("??  ", "y"), "info": t.s("info", "c")}
    t.line(rep.pad() + f"{mark.get(c.status, c.status)}  {c.name:<{CHECK_NAME_W}s} {c.detail}" + (t.s(f"   [{src}]", "gr") if src else ""))
    if c.more and rep.level >= 2:
        t.line(rep.pad() + t.s(f"      {c.more}", "gr"))
    if c.fix and c.status != "ok":
        t.line(rep.pad() + t.s(f"      fix: {c.fix}", "gr"))


class CheckList(list):
    """Checks that show themselves as they are made."""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx

    def append(self, c):
        super().append(c)
        show_check(self.ctx, c)


def preflight(ctx, regions=None, subnet=None):
    """The environment checks as one visible step; every Google call in it only reads."""
    with ctx.rep.step("Checking this environment", "read-only: sign-in, project, the APIs this tool uses, billing, your permissions, "
                                                   "organization policies and networks") as s:
        checks, fatal = _preflight(ctx, regions, subnet)
        n = {k: sum(1 for c in checks if c.status == k) for k in ("ok", "warn", "fail", "unknown")}
        s.result(f"{len(checks)} checks: {n['ok']} ok, {n['warn']} warning(s), {n['unknown']} unreadable, {n['fail']} failed"
                 + ("; blocking problems above" if fatal else ""), "r" if fatal else ("y" if n["warn"] or n["unknown"] else "g"))
    return checks, fatal


def _preflight(ctx, regions=None, subnet=None):
    """Environment, project, APIs, billing, permissions, policies and networks, each with its fix."""
    api, p, checks = ctx.api, ctx.project, CheckList(ctx)
    tk = ctx.tokens
    checks.append(Check("python", "ok", f"Python {sys.version.split()[0]} on {sys.platform}"))
    checks.append(Check("sign-in", "ok", f"{tk.account or 'unknown account'} via {tk.source}" + (f" (gcloud {tk.gcloud_version})" if tk.gcloud_version else "")))
    if tk.source == "gcloud" and tk.is_person():
        checks.append(Check("long runs", "warn", "signed in as a person: some organizations require signing in again every few hours",
                            "for runs of days, use --impersonate-service-account SA (your account needs roles/iam.serviceAccountTokenCreator on SA)"))
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        checks.append(Check("proxy", "ok", "HTTPS_PROXY is set; requests go through it"))
    fatal = False
    info = {}
    try:
        pr = api.get(f"{CRM1}/projects/{p}")
        info = {"number": pr.get("projectNumber"), "state": pr.get("lifecycleState"), "parent": pr.get("parent")}
        st = "ok" if pr.get("lifecycleState") == "ACTIVE" else "fail"
        par = pr.get("parent") or {}
        checks.append(Check("project", st, f"{p} (number {pr.get('projectNumber')}, {pr.get('lifecycleState')}" +
                            (f", in {par.get('type')} {par.get('id')})" if par else ", no organization)"),
                            "" if st == "ok" else "the project is not active; choose another with --project"))
        fatal |= st == "fail"
    except ApiError as e:
        c = classify(e, p)
        if c.kind in ("network", "tls"):
            # nothing else can be checked without reaching Google; say so now instead of failing every check in turn
            checks.append(Check("network", "fail", c.title, c.fix))
            ctx.report = {"checks": [x.as_dict() for x in checks], "caps": {}, "fatal": True, "utc": iso()}
            return checks, True
        if e.status in (403, 404) and c.kind not in ("api_disabled", "user_project"):
            checks.append(Check("project", "fail", f"{p}: not found, or this account cannot see it ({e.short()})",
                                "check the id with `gcloud projects list`, or ask for roles/viewer on it"))
            fatal = True
        else:
            checks.append(Check("project", "unknown", c.title, c.fix))
    ctx.project_info = info
    for svc, required, use in APIS:
        try:
            s = api.get(f"{SERVICEUSAGE}/projects/{p}/services/{svc}", fields="state")
            on = s.get("state") == "ENABLED"
            checks.append(Check(f"api {svc}", "ok" if on else ("fail" if required else "warn"), ("enabled" if on else "not enabled") + f": {use}",
                                "" if on else f"gcloud services enable {svc} --project {p}"))
            fatal |= required and not on
        except ApiError as e:
            checks.append(Check(f"api {svc}", "unknown", f"cannot read service state ({classify(e, p).title})", "needs serviceusage.services.get"))
    try:
        b = api.get(f"{BILLING}/projects/{p}/billingInfo")
        on = bool(b.get("billingEnabled"))
        checks.append(Check("billing", "ok" if on else "fail", "billing enabled" if on else "billing is not enabled",
                            "" if on else f"link an open billing account: {CONSOLE}/billing/linkedaccount?project={p}"))
        fatal |= not on
    except ApiError as e:
        c = classify(e, p)
        checks.append(Check("billing", "unknown", f"cannot read billing status ({c.title})", c.fix))
    allp = sorted({x for v in CAPS.values() for x in v})
    try:
        have, dropped = test_permissions(api, p, allp)
        for cap, perms in CAPS.items():
            missing = [x for x in perms if x not in have and x not in dropped]
            ctx.caps[cap] = {"ok": not missing, "missing": missing}
        if dropped:
            ctx.ev.note(f"permissions Google cannot test on a project were skipped: {', '.join(dropped)}")
        for cap in ("read", "quota_read", "quota_request", "reservation", "vms", "flex-group", "calendar", "advisor", "user_project", "org_policy"):
            c = ctx.caps[cap]
            if c["ok"]:
                checks.append(Check(f"can {cap}", "ok", f"{CAP_USE[cap]}: all {len(CAPS[cap])} permission(s) granted",
                                    more="tested: " + ", ".join(CAPS[cap])))
            else:
                role, why = suggest_role(ctx, c["missing"]) if ctx.opts.get("suggest_roles", True) else (None, "")
                fix = f"missing {', '.join(c['missing'])}"
                if role:
                    fix += f"; smallest role granting them: {why}; an administrator runs: gcloud projects add-iam-policy-binding {p} " \
                           f"--member={member_of(tk.account)} --role={role['name']}"
                elif why:
                    fix += f"; {why}"
                checks.append(Check(f"can {cap}", "fail" if cap == "read" else "warn",
                                    f"{CAP_USE[cap]}: {len(c['missing'])} of {len(CAPS[cap])} permission(s) missing", fix,
                                    more="tested: " + ", ".join(CAPS[cap])))
                fatal |= cap == "read"
    except (ApiError, SystemExit) as e:
        for cap in CAPS:
            ctx.caps[cap] = {"ok": None, "missing": []}
        msg = classify(e, p).title if isinstance(e, ApiError) else str(e)
        checks.append(Check("permissions", "unknown", f"cannot test permissions ({msg}); options stay enabled and Google's answers decide",
                            "needs resourcemanager.projects.get on the project"))
    if api.user_project_note:
        checks.append(Check("quota project header", "warn", f"dropped: {api.user_project_note}",
                            f"grant serviceusage.services.use on {p} to use APIs that need a quota project"))
    ctx.org = {}
    if ctx.caps.get("org_policy", {}).get("ok") is not False:
        for con in ORG_CONSTRAINTS:
            try:
                pol = api.call("POST", f"{CRM1}/projects/{p}:getEffectiveOrgPolicy", body={"constraint": f"constraints/{con}"})
                ctx.org[con] = pol
            except ApiError as e:
                # 404: the constraint does not exist for this project, so it restricts nothing
                ctx.org[con] = {"absent": True} if e.status == 404 else {"error": classify(e, p).title}
        notes = org_policy_notes(ctx, regions)
        for n in notes:
            checks.append(n)
    else:
        checks.append(Check("organization policy", "unknown", "cannot read effective policies (orgpolicy.policy.get missing); refusals are explained when they happen"))
    try:
        subs = api.aggregated("subnetworks", params={"fields": "items/*/subnetworks(name,network,region,selfLink),nextPageToken"})
        ctx.subnets = {}
        for scope, items in subs.items():
            for s in items:
                ctx.subnets.setdefault(tail(s["region"]), []).append(s)
        n = sum(len(v) for v in ctx.subnets.values())
        checks.append(Check("networks", "ok" if n else "warn", f"{n} subnet(s) in {len(ctx.subnets)} region(s)" if n else "no subnets: VMs cannot be created",
                            "" if n else "create a VPC network with subnets, or pass --subnet; reservations need no network"))
    except ApiError as e:
        ctx.subnets = None
        checks.append(Check("networks", "unknown", f"cannot list subnets ({classify(e, p).title})", "VM methods will report the network Google refuses"))
    if subnet and subnet.startswith("projects/"):
        try:
            r = api.call("POST", f"{COMPUTE}/{subnet}/testIamPermissions", body={"permissions": ["compute.subnetworks.use"]})
            ok = "compute.subnetworks.use" in (r.get("permissions") or [])
            checks.append(Check("shared VPC subnet", "ok" if ok else "fail", subnet, "" if ok else f"ask the host project to grant roles/compute.networkUser on {subnet}"))
        except ApiError as e:
            checks.append(Check("shared VPC subnet", "fail", f"{subnet}: {classify(e, p).title}", classify(e, p).fix))
    if ctx.opts.get("vm_service_account"):
        checks.append(check_act_as(ctx, ctx.opts["vm_service_account"]))
    ctx.report = {"checks": [c.as_dict() for c in checks], "caps": ctx.caps, "fatal": fatal, "org": ctx.org, "project": info, "utc": iso()}
    return checks, fatal


def org_policy_notes(ctx, regions):
    out = []
    org = ctx.org
    loc = org.get("gcp.resourceLocations") or {}
    if "error" in loc:
        out.append(Check("policy resourceLocations", "unknown", loc["error"]))
    elif loc.get("listPolicy") and (loc["listPolicy"].get("allowedValues") or loc["listPolicy"].get("deniedValues")
                                    or loc["listPolicy"].get("allValues") == "DENY"):
        lp = loc["listPolicy"]
        vals = (lp.get("allowedValues") or []) + [f"not {v}" for v in lp.get("deniedValues") or []]
        out.append(Check("policy resourceLocations", "warn", "resources may only go to: " + (", ".join(vals[:8]) or "nowhere (all denied)"),
                         "regions outside the policy are dropped from plans"))
        ctx.blocked_regions = {r for r in (regions or []) if location_allowed(r, loc) is False}
    else:
        out.append(Check("policy resourceLocations", "ok", "no location restriction" + absent_note(loc)))
    cmek = org.get("compute.restrictNonCmekServices") or {}
    if "error" in cmek:
        out.append(Check("policy restrictNonCmekServices", "unknown", cmek["error"]))
    elif "compute.googleapis.com" in ((cmek.get("listPolicy") or {}).get("deniedValues") or []):
        out.append(Check("policy restrictNonCmekServices", "warn", "Compute disks must use customer-managed keys: VM methods are not offered",
                         "use the reservation or calendar method, or create VMs yourself with your key"))
        ctx.cmek_required = True
    else:
        out.append(Check("policy restrictNonCmekServices", "ok", "disks may use Google-managed keys" + absent_note(cmek)))
    imgs = org.get("compute.trustedImageProjects") or {}
    lp = imgs.get("listPolicy") or {}
    img_proj = (ctx.opts.get("image") or IMAGE).split("/global/")[0]
    if "error" in imgs:
        out.append(Check("policy trustedImageProjects", "unknown", imgs["error"]))
    elif lp.get("allowedValues"):
        allowed = [v.replace("is:", "") for v in lp["allowedValues"]]
        if img_proj not in allowed:
            out.append(Check("policy trustedImageProjects", "warn", f"images only from: {', '.join(allowed[:6])}",
                             f"pick an image from those projects with --image (current {img_proj})"))
        else:
            out.append(Check("policy trustedImageProjects", "ok", f"restricted, and the image project {img_proj} is allowed"))
    else:
        out.append(Check("policy trustedImageProjects", "ok", "VM images may come from any project" + absent_note(imgs)))
    shielded = org.get("compute.requireShieldedVm") or {}
    if "error" in shielded:
        out.append(Check("policy requireShieldedVm", "unknown", shielded["error"]))
    elif (shielded.get("booleanPolicy") or {}).get("enforced"):
        out.append(Check("policy requireShieldedVm", "ok", "enforced; VMs are created as Shielded VMs with a UEFI image"))
    else:
        out.append(Check("policy requireShieldedVm", "ok", "not enforced" + absent_note(shielded)))
    return out


def absent_note(pol):
    return " (this project has no such policy; Google answered 404)" if pol.get("absent") else ""


# ------------------------------------------------------------------ catalog
def fetch_catalog(ctx):
    """Every NVIDIA GPU machine shape and attachable accelerator, by zone, from the live Compute API."""
    api = ctx.api
    zones = {z["name"]: z for z in api.pages(f"{COMPUTE}/projects/{ctx.project}/zones", "items", {"fields": "items(name,status,region),nextPageToken"})}
    up = {n for n, z in zones.items() if z.get("status") == "UP"}
    regions = sorted({region_of(z) for z in up})
    mts = api.aggregated("machineTypes", params={"filter": 'name eq "(a[0-9]+[a-z]*|g[0-9]+)-.*"',
                                                 "fields": "items/*/machineTypes(name,description,guestCpus,memoryMb,accelerators,zone,architecture),nextPageToken"})
    accs = api.aggregated("acceleratorTypes", params={"fields": "items/*/acceleratorTypes(name,description,maximumCardsPerInstance,zone),nextPageToken"})
    n1 = api.aggregated("machineTypes", params={"filter": 'name eq "n1-standard-[0-9]+"',
                                                "fields": "items/*/machineTypes(name,guestCpus,memoryMb,zone,architecture),nextPageToken"})
    accel = {}
    # Google publishes a "-vws" accelerator type for each GPU that runs NVIDIA RTX Virtual Workstation (graphics) software
    vws = {a["name"][:-4] for items in accs.values() for a in items if a["name"].endswith("-vws")}
    for zone, items in accs.items():
        if zone not in up:
            continue
        for a in items:
            if not a["name"].startswith("nvidia-") or a["name"].endswith("-vws"):
                continue
            rec = accel.setdefault(a["name"], {"name": a["name"], "label": a.get("description") or a["name"], "max_per_vm": a.get("maximumCardsPerInstance") or 1,
                                               "zones": set()})
            rec["zones"].add(zone)
    for a in accel.values():
        m = re.search(r"(\d+)\s*GB", a["label"], re.I)
        a["mem_gb"] = float(m.group(1)) if m else GPU_MEMORY_GB.get(a["name"])
        a["arch"] = accel_arch(a["name"])
        a["label"] = a["label"].replace("_", " ").strip()
        a["vws"] = a["name"] in vws
    shapes = {}
    for zone, items in mts.items():
        if zone not in up:
            continue
        for x in items:
            acc = (x.get("accelerators") or [{}])[0]
            if not acc.get("guestAcceleratorType", "").startswith("nvidia-"):
                continue
            frac = 1.0
            m = re.search(r"(\d+)/(\d+)\s+NVIDIA", x.get("description") or "")
            if m:
                frac = int(m.group(1)) / int(m.group(2))
            s = shapes.setdefault(x["name"], {"name": x["name"], "base": x["name"], "family": x["name"].split("-")[0], "vcpus": x["guestCpus"],
                                               "mem_gib": round(x["memoryMb"] / 1024, 1), "accel": acc["guestAcceleratorType"],
                                               "gpus": acc.get("guestAcceleratorCount") or 1, "fraction": frac, "attached": False,
                                               "desc": x.get("description", ""), "cpu_arch": x.get("architecture"), "zones": set()})
            s["zones"].add(zone)
    bundled = {s["accel"] for s in shapes.values()}
    n1spec, n1zones = {}, {}
    for zone, items in n1.items():
        if zone not in up:
            continue
        for x in items:
            n1spec[x["name"]] = (x["guestCpus"], round(x["memoryMb"] / 1024, 1), x.get("architecture"))
            n1zones.setdefault(x["name"], set()).add(zone)
    for name, a in accel.items():
        if name in bundled:
            continue
        count = 1
        while count <= a["max_per_vm"]:
            base = f"n1-standard-{N1_VCPUS_PER_GPU * count}"
            zs = a["zones"] & n1zones.get(base, set())
            if base in n1spec and zs:
                sname = f"{base}+{name}x{count}"
                shapes[sname] = {"name": sname, "base": base, "family": "n1", "vcpus": n1spec[base][0], "mem_gib": n1spec[base][1], "accel": name,
                                 "gpus": count, "fraction": 1.0, "attached": True, "desc": f"N1 with {count} attached {a['label']}",
                                 "cpu_arch": n1spec[base][2], "zones": zs}
            count *= 2
    for s in shapes.values():
        a = accel.get(s["accel"]) or {}
        s["gpu_equiv"] = round(s["gpus"] * s["fraction"], 4)
        s["gpu_mem_gb"] = (a.get("mem_gb") or 0) * s["gpus"] * s["fraction"] if a.get("mem_gb") else None
        s["zones"] = sorted(s["zones"])
        s["regions"] = sorted({region_of(z) for z in s["zones"]})
        s["boot_disk"] = BOOT_DISK.get(s["family"], "pd-balanced")
    for a in accel.values():
        a["zones"] = sorted(a["zones"])
        a["regions"] = sorted({region_of(z) for z in a["zones"]})
        a["shapes"] = sorted((s["name"] for s in shapes.values() if s["accel"] == a["name"]),
                             key=lambda n: (shapes[n]["gpu_equiv"], shapes[n]["vcpus"]))
    return {"accels": accel, "shapes": shapes, "regions": regions, "zones": sorted(up), "fetched": now()}


def from_cache(s, path, cur, ttl, refresh):
    """Say whether a cached copy is used (which file, how old, when it is read again) or Google is asked; True when the cache is used."""
    if not refresh and cur.get("fetched") and now() - cur["fetched"] < ttl:
        s.say(f"from the cache file {short_path(path)}, read from Google {human_dur(now() - cur['fetched'])} ago "
              f"(read again after {human_dur(ttl)}, or now with --refresh)")
        return True
    s.say((f"the cached copy {short_path(path)} could not be read; asking Google" if os.path.exists(path) else "no cached copy")
          if not cur.get("fetched") else ("--refresh asks Google again" if refresh else
                                                           f"the cached copy is {human_dur(now() - cur['fetched'])} old, past {human_dur(ttl)}: asking Google again"))
    return False


def catalog(ctx, refresh=False):
    path = ctx.cache_path("catalog-v2")
    with ctx.rep.step("Reading the GPU catalog", "which NVIDIA GPUs and machine types exist, and in which zones this project can use them") as s:
        cur = load_json(path, {})
        if from_cache(s, path, cur, CATALOG_TTL_S, refresh):
            ctx.catalog = cur
        else:
            s.say("Compute Engine API: zones.list, machineTypes.aggregatedList for the A, G and N1 series, acceleratorTypes.aggregatedList")
            ctx.catalog = fetch_catalog(ctx)
            atomic_json(path, ctx.catalog, 0o644)
            s.say(saved_where(path))
        c = ctx.catalog
        s.result(f"{len(c['accels'])} NVIDIA GPU types, {len(c['shapes'])} machine types, {len(c['zones'])} zones in {len(c['regions'])} regions")
    return ctx.catalog


# ------------------------------------------------------------------ quota
class QuotaBook:
    """Quota limits (Cloud Quotas, with Compute's own quota view as fallback) and current usage."""

    def __init__(self):
        self.infos = {}
        self.source = None
        self.error = None
        self.legacy = {}
        self.caps = {}
        self.usage = {}
        self.fetched = 0
        self.families = set()

    @staticmethod
    def parse_infos(rows):
        out = {}
        for q in rows:
            vals = []
            for d in q.get("dimensionsInfos") or []:
                det = d.get("details")
                if det is None:
                    v = None
                else:
                    # Google omits zero values from JSON: details present without a value means 0
                    v = int(det["value"]) if "value" in det else 0
                vals.append({"dims": d.get("dimensions") or {}, "value": v})
            el = q.get("quotaIncreaseEligibility") or {}
            out[q["quotaId"]] = {"dims": q.get("dimensions") or [], "values": vals, "fixed": bool(q.get("isFixed")),
                                 "eligible": el.get("isEligible"), "inelig": el.get("ineligibilityReason"), "metric": q.get("metric"),
                                 "display": q.get("quotaDisplayName") or q.get("metricDisplayName") or q["quotaId"],
                                 "refresh": q.get("refreshInterval")}
        return out

    def load_limits(self, ctx):
        try:
            rows = list(ctx.api.pages(f"{QUOTAS}/projects/{ctx.project}/locations/global/services/compute.googleapis.com/quotaInfos", "quotaInfos",
                                      {"pageSize": 1000}))
            self.infos = self.parse_infos(rows)
            self.source = "Cloud Quotas API"
            self.error = None
            fam = self.infos.get("GPUS-PER-GPU-FAMILY-per-project-region")
            self.families = {v["dims"].get("gpu_family") for v in (fam or {}).get("values", []) if v["dims"].get("gpu_family")}
        except ApiError as e:
            self.infos = {}
            self.error = classify(e, ctx.project)
            self.source = "Compute quota view (Cloud Quotas unavailable: GPU-family and Hyperdisk limits unknown)"
        self.fetched = now()
        return self

    def load_usage(self, ctx, regions):
        """Limits and usage Compute reports itself, plus GPU-family and Hyperdisk usage counted from what the project holds."""
        api = ctx.api
        pj = api.get(f"{COMPUTE}/projects/{ctx.project}", fields="quotas")
        self.caps = {q["metric"]: (q.get("limit"), q.get("usage")) for q in pj.get("quotas") or []}
        self.legacy = {}
        for r in regions:
            try:
                rg = api.get(f"{COMPUTE}/projects/{ctx.project}/regions/{r}", fields="quotas,status")
                self.legacy[r] = {q["metric"]: (q.get("limit"), q.get("usage")) for q in rg.get("quotas") or []}
            except ApiError as e:
                c = classify(e, ctx.project)
                self.legacy[r] = {"_error": c.title}
        insts = api.aggregated("instances", params={"fields": "items/*/instances(name,machineType,status,scheduling/provisioningModel,guestAccelerators,labels),nextPageToken"})
        resv = api.aggregated("reservations", params={"fields": "items/*/reservations(name,status,specificReservation,zone),nextPageToken"})
        disks = api.aggregated("disks", params={"fields": "items/*/disks(type,sizeGb),nextPageToken"})
        use = {}

        def add(key, n):
            use[key] = use.get(key, 0) + n

        shapes = (ctx.catalog or {}).get("shapes") or {}
        by_base = {}
        for s in shapes.values():
            if not s["attached"]:
                by_base[s["name"]] = s
        for zone, items in insts.items():
            r = region_of(zone)
            for i in items:
                if i.get("status") == "TERMINATED":
                    continue
                mt = tail(i.get("machineType"))
                model = (i.get("scheduling") or {}).get("provisioningModel") or "STANDARD"
                pre = model in ("SPOT", "FLEX_START")
                cards = []
                if mt in by_base:
                    s = by_base[mt]
                    cards.append((s["accel"], s["gpus"]))
                for ga in i.get("guestAccelerators") or []:
                    cards.append((tail(ga.get("acceleratorType")), ga.get("acceleratorCount") or 0))
                for acc, n in cards:
                    add(("gpu", r, acc, "p" if pre else "s"), n)
        for zone, items in resv.items():
            r = region_of(zone)
            for x in items:
                sr = x.get("specificReservation") or {}
                free = int(sr.get("count") or 0) - int(sr.get("inUseCount") or 0)
                ip = sr.get("instanceProperties") or {}
                mt = ip.get("machineType")
                if free <= 0:
                    continue
                if mt in by_base:
                    add(("gpu", r, by_base[mt]["accel"], "s"), by_base[mt]["gpus"] * free)
                for ga in ip.get("guestAccelerators") or []:
                    add(("gpu", r, tail(ga.get("acceleratorType")), "s"), (ga.get("acceleratorCount") or 0) * free)
        for zone, items in disks.items():
            r = region_of(zone)
            for d in items:
                add(("disk", r, tail(d.get("type"))), int(d.get("sizeGb") or 0))
        self.usage = use
        self.fetched = now()
        return self

    def limit(self, qid, dims):
        """The enforced limit for a quota and dimensions: Cloud Quotas first, Compute's view second; -1 unlimited; None unknown."""
        q = self.infos.get(qid)
        if q:
            best, best_n = None, -1
            for v in q["values"]:
                vd = v["dims"]
                if all(dims.get(k) == val for k, val in vd.items()) and len(vd) > best_n:
                    best, best_n = v, len(vd)
            if best is not None and best["value"] is not None:
                return best["value"]
        metric = legacy_metric(qid)
        if metric:
            if "region" in dims:
                lim = (self.legacy.get(dims["region"]) or {}).get(metric)
            else:
                lim = self.caps.get(metric)
            if lim and lim[0] is not None:
                return int(lim[0])
        return None

    def used(self, layer):
        kind = layer["kind"]
        if kind == "gpu_all":
            v = self.caps.get("GPUS_ALL_REGIONS")
            return int(v[1]) if v else None
        if kind == "cpu_all":
            v = self.caps.get("CPUS_ALL_REGIONS")
            return int(v[1]) if v else None
        if kind in ("cpu", "pcpu", "a2cpu", "ssd"):
            metric = legacy_metric(layer["qid"])
            v = (self.legacy.get(layer["dims"]["region"]) or {}).get(metric)
            return int(v[1]) if v else None
        if kind == "gpu":
            metric = legacy_metric(layer["qid"])
            v = (self.legacy.get(layer["dims"]["region"]) or {}).get(metric) if metric else None
            if v and v[1] is not None:
                return int(v[1])
            return int(self.usage.get(("gpu", layer["dims"]["region"], layer["accel"], "p" if layer.get("pre") else "s"), 0))
        if kind == "disk":
            return int(self.usage.get(("disk", layer["dims"]["region"], layer["disk_type"]), 0))
        return None

    def info(self, qid):
        return self.infos.get(qid) or {}


def legacy_metric(qid):
    """Compute's metric name for a Cloud Quotas id, where one exists (NVIDIA-L4-GPUS-per-project-region gives NVIDIA_L4_GPUS)."""
    if qid.startswith(("GPUS-PER-GPU-FAMILY", "HDB-")):
        return None
    core = re.sub(r"-per-project(-region|-zone)?$", "", qid)
    return core.replace("-", "_")


def preemptible_active(book, qid, region):
    """Spot and flex-start draw on preemptible quota where Google has granted some; where it is 0 they draw on standard quota.
    Observed on a live project: a denied preemptible CPU request (granted 0) left a flex-start G4 VM free to start on standard CPU quota."""
    lim = book.limit(qid, {"region": region})
    return bool(lim and lim > 0)


def layers_for(ctx, shape, region, method):
    """Every quota a node of this shape draws on in this region with this method; empty for calendar mode."""
    if method == "calendar":
        return []
    book = ctx.book
    pre = method in ("spot", "flex", "flex-group")
    gpus = max(1, int(math.ceil(shape["gpus"] * shape["fraction"] - 1e-9))) if shape["fraction"] < 1 else shape["gpus"]
    out = [{"kind": "gpu_all", "qid": "GPUS-ALL-REGIONS-per-project", "dims": {}, "need": gpus, "scope": "all regions", "label": "GPUs (all regions)"}]
    accel = shape["accel"]
    cores = accel_cores(accel)
    gq = None
    if pre:
        for c in cores:
            qid = f"PREEMPTIBLE-NVIDIA-{c}-GPUS-per-project-region"
            if qid in book.infos or legacy_metric(qid) in (book.legacy.get(region) or {}):
                if preemptible_active(book, qid, region):
                    gq = {"kind": "gpu", "qid": qid, "dims": {"region": region}, "pre": True,
                          "label": f"preemptible {c} GPUs", "note": "spot and flex-start use preemptible quota here"}
                break
    if gq is None:
        fam = "NVIDIA_" + cores[-1].replace("-", "_")
        famq = "GPUS-PER-GPU-FAMILY-per-project-region"
        if fam in book.families:
            gq = {"kind": "gpu", "qid": famq, "dims": {"region": region, "gpu_family": fam}, "label": f"{fam} GPUs"}
        else:
            for c in cores:
                qid = f"NVIDIA-{c}-GPUS-per-project-region"
                if qid in book.infos or legacy_metric(qid) in (book.legacy.get(region) or {}):
                    gq = {"kind": "gpu", "qid": qid, "dims": {"region": region}, "label": f"{c} GPUs"}
                    break
        if gq and pre:
            gq["note"] = "spot and flex-start use standard quota here while no preemptible quota is granted"
    if gq is None:
        gq = {"kind": "gpu", "qid": None, "dims": {"region": region}, "label": f"{accel} GPUs",
              "note": "Google publishes no standard quota for this GPU; on-demand use goes through your account team" if not pre else "no quota found"}
    gq.update(need=gpus, scope=region, accel=accel)
    gq.setdefault("pre", False)
    out.append(gq)
    if pre and preemptible_active(book, "PREEMPTIBLE-CPUS-per-project-region", region):
        cq = {"kind": "pcpu", "qid": "PREEMPTIBLE-CPUS-per-project-region", "label": "preemptible vCPUs"}
    elif shape["family"] == "a2":
        cq = {"kind": "a2cpu", "qid": "A2-CPUS-per-project-region", "label": "A2 vCPUs"}
    else:
        cq = {"kind": "cpu", "qid": "CPUS-per-project-region", "label": "vCPUs"}
    cq.update(dims={"region": region}, need=shape["vcpus"], scope=region)
    out.append(cq)
    out.append({"kind": "cpu_all", "qid": "CPUS-ALL-REGIONS-per-project", "dims": {}, "need": shape["vcpus"], "scope": "all regions", "label": "vCPUs (all regions)"})
    if method in ("vms", "spot", "flex", "flex-group"):
        dt_ = shape["boot_disk"]
        qid = DISK_QUOTA.get(dt_)
        if qid:
            out.append({"kind": "disk" if dt_ == "hyperdisk-balanced" else "ssd", "qid": qid, "dims": {"region": region}, "need": ctx.opts.get("boot_disk_gb") or BOOT_DISK_GB,
                        "scope": region, "disk_type": dt_, "label": f"{dt_} GB"})
    return out


def headroom(ctx, shape, region, method):
    """How many more nodes the quotas allow, the binding layer, and every layer's numbers."""
    rows = []
    for L in layers_for(ctx, shape, region, method):
        lim = ctx.book.limit(L["qid"], L["dims"]) if L.get("qid") else None
        used = ctx.book.used(L) if L.get("qid") else None
        if lim is None:
            more = None
        elif lim < 0:
            more = 10 ** 6
        else:
            more = max(0, (lim - (used or 0)) // L["need"]) if L["need"] else 10 ** 6
        rows.append(dict(L, limit=lim, used=used, more=more))
    known = [r for r in rows if r["more"] is not None]
    if not rows:
        return {"more": None, "binding": None, "rows": []}
    if not known:
        return {"more": None, "binding": None, "rows": rows}
    tight = min(known, key=lambda r: r["more"])
    unknown = [r for r in rows if r["more"] is None]
    return {"more": tight["more"], "binding": tight, "rows": rows, "unknown": unknown}


def load_prefs(ctx):
    """Quota requests already on file for this project, from any tool or the console."""
    try:
        ctx.prefs = list(ctx.api.pages(f"{QUOTAS}/projects/{ctx.project}/locations/global/quotaPreferences", "quotaPreferences", {"pageSize": 200}))
    except ApiError as e:
        ctx.prefs = []
        ctx.ev.note(f"existing quota requests unreadable: {classify(e, ctx.project).title}", "warn")
    return ctx.prefs


def refresh_quota(ctx, regions):
    with ctx.rep.step("Reading quota and current usage", f"the limits Google sets on this project and what it holds now, in {len(regions)} region(s)") as s:
        if ctx.book is None:
            ctx.book = QuotaBook()
        s.say("limits: Cloud Quotas API, quotaInfos.list for compute.googleapis.com")
        ctx.book.load_limits(ctx)
        if ctx.prefs is None:
            s.say("quota increase requests already on file: Cloud Quotas API, quotaPreferences.list")
            load_prefs(ctx)
        s.say(f"usage: Compute Engine API, projects.get and regions.get for {', '.join(regions[:6])}{' and more' if len(regions) > 6 else ''}; "
              f"instances, reservations and disks with aggregatedList, counted per region")
        ctx.book.load_usage(ctx, regions)
        if ctx.book.infos:
            ctx.gov.set_limits(ctx.book.infos)
            s.say(f"API pacing: this tool now spends at most {RATE_FRACTION:.0%} of each per-minute Compute API limit read above")
        err = getattr(ctx.book, "error", None)
        s.result(f"{len(ctx.book.infos)} quotas from {ctx.book.source}; usage counted in {len(regions)} region(s); "
                 f"{len(ctx.prefs or [])} quota request(s) on file" + (f"; {err.title}" if err else ""), "y" if err else "g")
    return ctx.book


# ------------------------------------------------------------------ prices
# Billing catalog descriptions for GPU SKUs: (text that must appear, text that must not). Read from the live
# catalog (service 6F81-5844-456A, Compute Engine); a GPU missing here simply shows n/a.
GPU_SKU = {"nvidia-rtx-pro-6000": [("RTX 6000 96GB", None)], "nvidia-l4": [("Nvidia L4 GPU", None)], "nvidia-tesla-t4": [("Nvidia Tesla T4 GPU", None)],
           "nvidia-tesla-v100": [("Nvidia Tesla V100 GPU", None)], "nvidia-tesla-p4": [("Nvidia Tesla P4 GPU", None)],
           "nvidia-tesla-p100": [("Nvidia Tesla P100 GPU", None)], "nvidia-tesla-a100": [("Nvidia Tesla A100 GPU", "80GB")],
           "nvidia-a100-80gb": [("Nvidia Tesla A100 80GB GPU", None)], "nvidia-h100-80gb": [("Nvidia H100 80GB GPU", "Mega")],
           "nvidia-h100-mega-80gb": [("H100 80GB Mega", None), ("H100 Mega 80GB", None), ("H100 80GB Plus", None)],
           "nvidia-h200-141gb": [("H200 141GB GPU", None)], "nvidia-b200": [("Nvidia B200 (1 gpu slice)", None)]}
BUNDLED_PRICE = {"nvidia-b200"}


def fetch_prices(ctx):
    """On-demand, Spot and flex-start unit prices per region for GPU machine parts."""
    keep = re.compile(r"^(Spot Preemptible |DWS Defined Duration |DWS Calendar Mode |Reserved )?(([A-Z0-9]+ )?(Predefined )?Instance (Core|Ram)|"
                      r"(A[0-9]+[A-Za-z]* |G[0-9]+ |N1 Predefined )(Core|Ram))", re.I)
    out = {}
    for k in ctx.api.pages(f"{BILLING}/services/6F81-5844-456A/skus", "skus", {"pageSize": 5000, "currencyCode": "USD"}):
        desc = re.sub(r" running in .*$", "", k.get("description", ""))
        cat = k.get("category") or {}
        gpu = cat.get("resourceGroup") == "GPU" or " GPU" in desc or "gpu slice" in desc
        if not gpu and not keep.search(desc):
            continue
        try:
            pe = k["pricingInfo"][0]["pricingExpression"]
            u = pe["tieredRates"][-1]["unitPrice"]
            usd = float(u.get("units") or 0) + (u.get("nanos") or 0) / 1e9
        except (KeyError, IndexError):
            continue
        if cat.get("usageType") not in ("OnDemand", "Preemptible") or "Commit" in desc:
            continue
        # one price class per SKU: a calendar-mode or flex-start SKU must never stand in for on-demand
        if "Calendar Mode" in desc:
            model = "calendar"
        elif desc.startswith("Reserved "):
            # reserved-capacity SKUs outside calendar mode are not a price anyone pays on demand (some list $0)
            continue
        elif "DWS" in desc:
            model = "flex"
        elif cat.get("usageType") == "Preemptible" or "Spot" in desc or "Preemptible" in desc:
            model = "spot"
        else:
            model = "ondemand"
        for r in k.get("serviceRegions") or []:
            out.setdefault(r, []).append([desc, model, usd])
    return {"fetched": now(), "regions": out}


def prices(ctx, refresh=False):
    if ctx.prices and not refresh and not ctx.prices.get("error"):
        return ctx.prices
    path = ctx.cache_path("prices-v3")
    with ctx.rep.step("Reading GPU prices", "Google's public list prices, per region and holding method; read only, nothing is bought") as s:
        cur = load_json(path, {})
        if from_cache(s, path, cur, PRICE_TTL_S, refresh):
            ctx.prices = cur
        else:
            s.say("Cloud Billing Catalog API: services.skus.list for Compute Engine (service 6F81-5844-456A), in USD")
            try:
                ctx.prices = fetch_prices(ctx)
                atomic_json(path, ctx.prices, 0o644)
                s.say(saved_where(path))
            except ApiError as e:
                c = classify(e, ctx.project)
                ctx.prices = {"error": c.title, "regions": {}}
                s.result(f"Google refused the price list: {c.title}. Prices show as n/a; fix: {c.fix}", "y")
                return ctx.prices
        s.result(f"prices for {len(ctx.prices.get('regions') or {})} regions")
    return ctx.prices


def price_of(ctx, shape, region, method):
    """USD per hour for one node, or None when the catalog lacks a part."""
    rows = ((ctx.prices or {}).get("regions") or {}).get(region) or []
    model = {"spot": "spot", "flex": "flex", "flex-group": "flex", "calendar": "calendar"}.get(method, "ondemand")

    def find(pred, m):
        for desc, mm, usd in rows:
            if mm == m and pred(desc):
                return usd
        return None

    fam = shape["family"].upper()
    acc = shape["accel"]

    def gpu_price():
        for want, avoid in GPU_SKU.get(acc) or []:
            g = find(lambda d: want in d and (avoid is None or avoid not in d), model)
            if g is not None:
                return g
        return None

    if acc in BUNDLED_PRICE:
        g = gpu_price()
        return None if g is None else round(g * shape["gpus"], 4)
    if shape["family"] == "n1":
        tokens = ["N1 Predefined"]
    else:
        # A3 Mega and A3 Ultra carry their own SKU names (A3Mega, A3Ultra); plain A3 is the fallback
        sub = {"megagpu": ["A3Mega", "A3Plus"], "ultragpu": ["A3Ultra"]}.get((shape["base"].split("-") + ["", ""])[1], [])
        tokens = sub + [fam]
    core = ram = None
    for tok in tokens:
        core_rx, ram_rx = re.compile(rf"\b{tok} (Instance )?Core\b"), re.compile(rf"\b{tok} (Instance )?Ram\b")
        core = find(lambda d: core_rx.search(d) and "Custom" not in d and "Sole Tenancy" not in d, model)
        ram = find(lambda d: ram_rx.search(d) and "Custom" not in d and "Sole Tenancy" not in d, model)
        if core is not None and ram is not None:
            break
    if core is None or ram is None:
        return None
    total = shape["vcpus"] * core + shape["mem_gib"] * ram
    if GPU_SKU.get(acc):
        g = gpu_price()
        if g is None:
            return None
        total += g * shape["gpus"] * shape["fraction"]
    return round(total, 4)


# ------------------------------------------------------------------ Google's capacity signals
def advise(ctx, shape, zone, count=1):
    """Google's capacity advisor score (0 to 1) for a shape in a zone; it scores Spot capacity, a signal not a promise."""
    key = f"{shape['name']}@{zone}#{count}"
    hit = ctx.advice.get(key)
    if hit and now() - hit["ts"] < ADVISOR_TTL_S:
        return hit
    sel = {"machineTypes": [shape["base"]]}
    if shape["attached"]:
        sel["guestAccelerators"] = [{"acceleratorType": shape["accel"], "acceleratorCount": shape["gpus"]}]
    body = {"size": count, "instanceProperties": {"scheduling": {"provisioningModel": "SPOT"}},
            "instanceFlexibilityPolicy": {"instanceSelections": {"s": sel}},
            "distributionPolicy": {"targetShape": "ANY_SINGLE_ZONE", "zones": [{"zone": f"zones/{zone}"}]}}
    try:
        # the v1 method refuses every provisioning model today; the beta method scores Spot capacity
        r = ctx.api.call("POST", f"{COMPUTE_BETA}/projects/{ctx.project}/regions/{region_of(zone)}/advice/capacity", body=body, retries=1)
        rec = (r.get("recommendations") or [{}])[0]
        sc = rec.get("scores") or {}
        out = {"ts": now(), "score": sc.get("obtainability"), "uptime": sc.get("estimatedUptime")}
    except ApiError as e:
        out = {"ts": now(), "score": None, "error": classify(e, ctx.project).title}
    ctx.advice[key] = out
    return out


def calendar_search(ctx, shape, region, count, start_after_s, start_before_s, min_s, max_s):
    """Calendar-mode availability in a region: recommended start and end per zone, or why not."""
    t0 = now()
    body = {"futureResourcesSpecs": {"spec": {
        "targetResources": {"specificSkuResources": {"instanceCount": str(count), "machineType": shape["base"]}},
        "timeRangeSpec": {"startTimeNotEarlierThan": iso(t0 + start_after_s), "startTimeNotLaterThan": iso(t0 + start_before_s),
                          "minDuration": f"{int(min_s)}s", "maxDuration": f"{int(max_s)}s"}}}}
    r = ctx.api.call("POST", f"{COMPUTE}/projects/{ctx.project}/regions/{region}/advice/calendarMode", body=body)
    out = []
    for rec in r.get("recommendations") or []:
        for spec, x in (rec.get("recommendationsPerSpec") or {}).items():
            if x.get("startTime"):
                out.append({"zone": tail(x.get("location")), "start": x.get("startTime"), "end": x.get("endTime"), "id": x.get("recommendationId")})
            for loc, o in (x.get("otherLocations") or {}).items():
                out.append({"zone": tail(loc), "status": o.get("status"), "details": o.get("details")})
    return out


# ------------------------------------------------------------------ NVIDIA workloads on Google Cloud
# Google pages about NVIDIA on Google Cloud: the only links this tool shows for NVIDIA products, GPUs and VM images.
DOCS = {
    "model_garden": ("Overview of Model Garden", "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-garden/explore-models"),
    "deploy_open": ("Deploy open models from Model Garden",
                    "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/open-models/deploy-model-garden"),
    "gpus": ("GPU machine types", "https://docs.cloud.google.com/compute/docs/gpus"),
    "gpu_regions": ("GPU regions and zones", "https://docs.cloud.google.com/compute/docs/regions-zones/gpu-regions-zones"),
    "accel": ("Accelerator-optimized machine family", "https://docs.cloud.google.com/compute/docs/accelerator-optimized-machines"),
    "provisioning": ("Compute Engine provisioning models", "https://docs.cloud.google.com/compute/docs/instances/provisioning-models"),
    "drivers": ("Install NVIDIA GPU drivers", "https://docs.cloud.google.com/compute/docs/gpus/install-drivers-gpu"),
    "os": ("Operating system details", "https://docs.cloud.google.com/compute/docs/images/os-details"),
    "dlvm": ("Deep Learning VM images", "https://docs.cloud.google.com/deep-learning-vm/docs/images"),
    "marketplace": ("Get products from Google Cloud Marketplace", "https://docs.cloud.google.com/marketplace/docs/get-products"),
    "nim": ("Serving inferences with NVIDIA NIM", "https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/predictions/deploy-genai"),
    "nim_gke": ("Deploy an AI model on GKE with NVIDIA NIM, Google codelab", "https://codelabs.developers.google.com/codelabs/nvidia-nim-google-cloud"),
    "omniverse": ("NVIDIA Omniverse on Google Cloud, Google Cloud solutions",
                  "https://googlecloudplatform.github.io/cloud-solutions/nvidia-omniverse-on-google-cloud/"),
    "kit_streaming": ("Deploy NVIDIA Omniverse Kit App Streaming on Google Cloud",
                      "https://googlecloudplatform.github.io/cloud-solutions/nvidia-omniverse-on-google-cloud/kit-app-streaming/"),
    "omniverse_gke": ("GKE platform for NVIDIA Omniverse applications",
                      "https://googlecloudplatform.github.io/cloud-solutions/nvidia-omniverse-on-google-cloud/gke-base-platform/"),
    "bionemo": ("NVIDIA BioNeMo on GKE, GKE AI Labs", "https://gke-ai-labs.dev/docs/blueprints/bionemo/"),
    "bionemo_blog": ("NVIDIA BioNeMo and GKE, Google Cloud blog",
                     "https://cloud.google.com/blog/products/ai-machine-learning/accelerate-ai-in-healthcare-nvidia-bionemo-gke"),
}
# NVIDIA products that Google documents for Google Cloud. No Google API lists Marketplace products, so each entry names the Google pages
# it comes from and the GPU rule those pages state. "g_series": the accelerator-optimized G series, which the GPU machine types page
# names for NVIDIA Omniverse and which carries the RTX GPUs Google's Omniverse GKE guide asks for; "min": the fewest GPUs of each type
# per unit that the page lists; "model": GPUs depend on the model served.
NVIDIA_SOLUTIONS = [
    {"key": "omniverse-dev-ws", "name": "NVIDIA Omniverse Development Workstation (Linux or Windows)", "where": "Compute Engine VM, Google Cloud Marketplace",
     "rule": "g_series", "unit": "workstation", "docs": ["omniverse", "gpus"]},
    {"key": "omniverse-ent-ws", "name": "NVIDIA Omniverse Enterprise Workstation (Linux or Windows)", "where": "Compute Engine VM, Google Cloud Marketplace",
     "rule": "g_series", "unit": "workstation", "docs": ["omniverse", "gpus"]},
    {"key": "isaac-sim-ws", "name": "NVIDIA Isaac Sim Development Workstation (Linux or Windows)", "where": "Compute Engine VM, Google Cloud Marketplace",
     "rule": "g_series", "unit": "workstation", "docs": ["omniverse", "gpus"]},
    {"key": "kit-streaming", "name": "NVIDIA Omniverse Kit App Streaming", "where": "GKE GPU node pool", "rule": "g_series", "unit": "GPU node",
     "docs": ["kit_streaming", "omniverse_gke", "gpus"]},
    {"key": "bionemo", "name": "NVIDIA BioNeMo Framework (ESM-2 training and fine-tuning)", "where": "GKE GPU node pool", "rule": "min", "unit": "job",
     "min": {"nvidia-l4": 2, "nvidia-tesla-a100": 1, "nvidia-a100-80gb": 1, "nvidia-h100-80gb": 1}, "docs": ["bionemo", "bionemo_blog"],
     "note": "Google's guide lists 2 x L4, 1 x A100 40GB or higher, or 1 x H100 80GB or higher per job"},
    {"key": "nim", "name": "NVIDIA NIM microservices", "where": "Agent Platform endpoint or GKE", "rule": "model", "unit": "copy",
     "docs": ["nim", "nim_gke"], "note": "the GPUs depend on the NIM model; for Nemotron and Cosmos, choose Model Garden for Google's tested sizes"},
]


def vertex_accel(name):
    """Agent Platform's accelerator name (NVIDIA_H100_80GB) as Compute Engine's accelerator type (nvidia-h100-80gb)."""
    return (name or "").lower().replace("_", "-")


def serving_args(args):
    """Google's tested serving settings in a Model Garden container: tensor parallel size, context length, concurrent sequences."""
    keys = {"tensor-parallel-size": "tp", "tp": "tp", "tp-size": "tp", "max-model-len": "max_len", "context-length": "max_len",
            "max-num-seqs": "max_seqs", "max-running-requests": "max_seqs"}
    out = {}
    for a in args or []:
        m = re.match(r"--([a-z-]+)=(\S+)$", str(a))
        if not m:
            continue
        k, v = m.groups()
        if k in keys and v.isdigit():
            out[keys[k]] = int(v)
        elif k == "kv-cache-dtype":
            out["kv_dtype"] = v.lower()
        elif k in ("gpu-memory-utilization", "mem-fraction-static") and re.fullmatch(r"\d*\.?\d+", v):
            out["mem_frac"] = float(v)
    return out


def parse_model_garden(models):
    """Model Garden publisher models as one entry per version, with every deployment configuration Google tested."""
    out = []
    for m in models:
        sa = m.get("supportedActions") or {}
        dep = sa.get("deploy") or {}
        multi = ((sa.get("multiDeployVertex") or {}).get("multiDeployVertex")) or ([dep] if dep else [])
        configs, env = [], {}
        for x in multi:
            spec = (x.get("dedicatedResources") or {}).get("machineSpec") or {}
            if not spec.get("machineType") or not spec.get("acceleratorType"):
                continue
            cs = x.get("containerSpec") or {}
            env = env or {v.get("name"): v.get("value") for v in cs.get("env") or []}
            configs.append(dict(machine=spec["machineType"], accel=vertex_accel(spec["acceleratorType"]), gpus=int(spec.get("acceleratorCount") or 1),
                                task=x.get("deployTaskName"), **serving_args(cs.get("args"))))
        if not configs:
            continue
        name = dep.get("modelDisplayName") or multi[0].get("modelDisplayName") or m.get("versionId")
        gen = str(env.get("DIFFUSION_MODEL", "")).lower() == "true" or bool(re.search(r"image|video", env.get("TASK") or ""))
        out.append({"key": m.get("versionId") or name, "model": m["name"].rsplit("/", 1)[-1], "name": name, "stage": m.get("launchStage"),
                    "source_id": env.get("MODEL_ID"), "kind": "generation" if gen else "llm",
                    "default_machine": ((dep.get("dedicatedResources") or {}).get("machineSpec") or {}).get("machineType"), "configs": configs,
                    "precision": None if gen else model_precision(name)})
    return sorted(out, key=lambda e: (e["model"], e["name"]))


def model_garden(ctx, s, refresh=False):
    """The publisher's models in Vertex AI Model Garden, read through the Agent Platform API and cached."""
    path = ctx.cache_path(f"model-garden-{MODEL_GARDEN_PUBLISHER}")
    cur = load_json(path, {})
    if from_cache(s, path, cur, CATALOG_TTL_S, refresh):
        return cur["models"], cur["read"]
    host = f"https://{MODEL_GARDEN_LOCATION}-aiplatform.googleapis.com/v1beta1"
    s.say(f"Agent Platform (Vertex AI) API in {MODEL_GARDEN_LOCATION}: publishers.models.list for publishers/{MODEL_GARDEN_PUBLISHER}, every version")
    raw = list(ctx.api.pages(f"{host}/publishers/{MODEL_GARDEN_PUBLISHER}/models", "publisherModels",
                             {"view": "PUBLISHER_MODEL_VIEW_FULL", "listAllVersions": "true", "pageSize": 300}))
    rec = {"fetched": now(), "read": iso(), "models": parse_model_garden(raw)}
    atomic_json(path, rec, 0o644)
    s.say(saved_where(path))
    return rec["models"], rec["read"]


def license_name(lic):
    """A Marketplace license as a product name: its description when it says more than its id."""
    d = (lic.get("description") or "").strip()
    n = lic.get("name") or ""
    if d and d != n:
        return re.sub(r"^License for\s+", "", d)
    words = {"nvidia": "NVIDIA", "vmi": "VMI", "gpu": "GPU", "ngc": "NGC", "hpc": "HPC", "sdk": "SDK", "ai": "AI"}
    return " ".join(words.get(w, w.capitalize()) for w in n.split("-"))


def group_marketplace(images, licenses=None, since=None):
    """NVIDIA Marketplace VM products: the newest current image of each NVIDIA license, from the publisher's image project."""
    prods = {}
    for im in images:
        if im.get("deprecated") or re.search(r"^internal-|-test", im.get("name", "")) or (since and im.get("creationTimestamp", "") < since):
            continue
        for url in im.get("licenses") or []:
            lname = url.rsplit("/", 1)[-1]
            if not lname.startswith("nvidia-") or "test" in lname:
                continue
            p = prods.get(url)
            if not p or im["creationTimestamp"] > p["created"]:
                os_ = [u.rsplit("/", 1)[-1] for u in im.get("licenses") or [] if not u.rsplit("/", 1)[-1].startswith("nvidia-")]
                link = im.get("selfLink") or ""
                image = ("projects/" + link.split("/projects/", 1)[1]) if "/projects/" in link else \
                    f"projects/{MARKETPLACE_IMAGE_PROJECT}/global/images/{im['name']}"
                prods[url] = {"license": url, "id": lname, "image": image, "created": im["creationTimestamp"], "arch": im.get("architecture"),
                              "disk_gb": int(im.get("diskSizeGb") or 0), "os": ", ".join(os_),
                              "gvnic": any(g.get("type") == "GVNIC" for g in im.get("guestOsFeatures") or [])}
    out = []
    for url, p in prods.items():
        lic = (licenses or {}).get(url) or {"name": p["id"]}
        p["name"] = license_name(lic)
        p["fee"] = lic.get("chargesUseFee")
        out.append(p)
    return sorted(out, key=lambda p: p["created"], reverse=True)


def marketplace_products(ctx, s, refresh=False):
    """NVIDIA's Marketplace VM images, read live from the publisher's public image project, with each license's name and fee flag."""
    path = ctx.cache_path(f"marketplace-{MARKETPLACE_IMAGE_PROJECT}")
    cur = load_json(path, {})
    if from_cache(s, path, cur, CATALOG_TTL_S, refresh):
        return cur["products"], cur["read"]
    s.say(f"Compute Engine API: images.list in the public project {MARKETPLACE_IMAGE_PROJECT}, then licenses.get for each NVIDIA license on a "
          f"current image (the license names the Marketplace product and says whether Google charges a fee)")
    imgs = list(ctx.api.pages(f"{COMPUTE}/projects/{MARKETPLACE_IMAGE_PROJECT}/global/images", "items",
                              {"maxResults": 500, "fields": "items(name,selfLink,licenses,architecture,diskSizeGb,creationTimestamp,deprecated/state,"
                                                            "guestOsFeatures/type),nextPageToken"}))
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now() - IMAGE_LOOKBACK_DAYS * 86400))
    lics = {}
    for p in group_marketplace(imgs, None, since):
        try:
            lics[p["license"]] = ctx.api.get(p["license"].replace("https://www.googleapis.com/compute/v1", COMPUTE))
        except ApiError as e:
            lics[p["license"]] = {"name": p["id"], "error": classify(e, ctx.project).title}
    rec = {"fetched": now(), "read": iso(), "products": group_marketplace(imgs, lics, since)}
    atomic_json(path, rec, 0o644)
    s.say(f"{len(imgs)} images read; the current products {saved_where(path)}")
    return rec["products"], rec["read"]


def image_group_label(project, fams):
    """A readable name for an image project from its own image descriptions: product (vendor), and whether the NVIDIA driver is in it."""
    descs = [f["desc"] for f in fams if f.get("desc")]
    parts = [[x.strip() for x in d.split(",")] for d in descs]
    vendor = parts[0][0] if parts and parts[0] else project
    prods = [p[1] for p in parts if len(p) > 1]
    product = os.path.commonprefix(prods).strip(" +-") if prods else project
    nvidia = all("nvidia" in f["family"] for f in fams)
    return f"{product or project} ({vendor})" + (", NVIDIA driver installed" if nvidia else ""), nvidia


def group_images(project, images, since=None):
    """The newest current image of each family in one public image project, families matching IMAGE_FAMILY_EXCLUDE left out."""
    fams = {}
    for im in images:
        fam = im.get("family")
        if im.get("deprecated") or not fam or re.search(IMAGE_FAMILY_EXCLUDE, fam) or (since and im.get("creationTimestamp", "") < since):
            continue
        f = fams.get(fam)
        if not f or im["creationTimestamp"] > f["created"]:
            fams[fam] = {"family": fam, "image": f"projects/{project}/global/images/family/{fam}", "created": im["creationTimestamp"],
                         "arch": im.get("architecture"), "disk_gb": int(im.get("diskSizeGb") or 0), "desc": im.get("description") or "",
                         "gvnic": any(g.get("type") == "GVNIC" for g in im.get("guestOsFeatures") or [])}
    if not fams:
        return None
    rows = sorted(fams.values(), key=lambda f: f["created"], reverse=True)
    label, nvidia = image_group_label(project, rows)
    return {"project": project, "label": label, "nvidia": nvidia, "families": rows}


def os_images(ctx, refresh=False):
    """Current image families of every project in IMAGE_PROJECTS, read live from Compute Engine and cached."""
    path = ctx.cache_path("os-images")
    with ctx.rep.step("Reading Google's public VM images", f"current image families in {len(csv_list(IMAGE_PROJECTS))} public image projects "
                                                          f"(GPUF_IMAGE_PROJECTS), published in the last {IMAGE_LOOKBACK_DAYS} days") as s:
        cur = load_json(path, {})
        if from_cache(s, path, cur, CATALOG_TTL_S, refresh):
            s.result(f"{sum(len(g['families']) for g in cur['groups'])} image families in {len(cur['groups'])} projects")
            return cur["groups"], cur["read"]
        since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now() - IMAGE_LOOKBACK_DAYS * 86400))
        groups = []
        for proj in csv_list(IMAGE_PROJECTS):
            imgs = list(ctx.api.pages(f"{COMPUTE}/projects/{proj}/global/images", "items",
                                      {"maxResults": 500, "filter": f'creationTimestamp > "{since[:10]}"',
                                       "fields": "items(name,family,description,architecture,diskSizeGb,creationTimestamp,deprecated/state,"
                                                 "guestOsFeatures/type),nextPageToken"}))
            g = group_images(proj, imgs, since)
            s.say(f"{proj}: Compute Engine API images.list, {len(imgs)} recent images, "
                  + (f"{len(g['families'])} current families ({g['label']})" if g else "no current family"))
            if g:
                groups.append(g)
        rec = {"fetched": now(), "read": iso(), "groups": groups}
        atomic_json(path, rec, 0o644)
        s.say(saved_where(path))
        s.result(f"{sum(len(g['families']) for g in groups)} image families in {len(groups)} projects")
    return groups, rec["read"]


def hf_get(path, params=None, ca_bundle=None):
    url = f"{HF}{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    ctx_ = ssl.create_default_context(cafile=ca_bundle) if ca_bundle else ssl.create_default_context()
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx_))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    t0 = now()
    try:
        with opener.open(req, timeout=HF_TIMEOUT_S) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        audit("http", m="GET", host="huggingface.co", path=path, query=urllib.parse.urlencode(params or {}), status=e.code, ms=int((now() - t0) * 1000),
              bytes=0, note=str(e.reason))
        raise
    except OSError as e:
        audit("http", m="GET", host="huggingface.co", path=path, status=0, ms=int((now() - t0) * 1000), bytes=0, note=f"{type(e).__name__}: {e}")
        raise
    audit("http", m="GET", host="huggingface.co", path=path, query=urllib.parse.urlencode(params or {}), status=status, ms=int((now() - t0) * 1000),
          bytes=len(raw), note="public metadata, no account or token sent")
    return json.loads(raw)


def model_precision(repo, dtypes=None):
    name = repo.rsplit("/", 1)[-1]
    for p in ("NVFP4", "FP8", "BF16"):
        if re.search(rf"-{p}(-|$)", name, re.I):
            return p
    m = re.search(r"-(\d+GB)$", name)
    if m:
        return f"LOWBIT-{m.group(1)}"
    d = set(dtypes or [])
    if "U8" in d and "F8_E4M3" in d:
        return "NVFP4"
    if "F8_E4M3" in d:
        return "FP8"
    return "BF16"


def model_details(ctx, repo, s):
    """Weight size and cache-relevant architecture of the repository a Model Garden model deploys (its MODEL_ID); failures are reported."""
    path = ctx.cache_path("arch-v2-" + safe_name(repo, limit=120))
    cur = load_json(path, {})
    if from_cache(s, path, cur, CATALOG_TTL_S, False):
        return cur["info"]
    s.say(f"huggingface.co, public metadata, no account or token sent: GET /api/models/{repo}?blobs=true (file sizes) and "
          f"GET /{repo}/resolve/main/config.json (layers)")
    info = {"repo": repo, "weights_gb": None, "precision": model_precision(repo), "errors": []}
    try:
        d = hf_get(f"/api/models/{repo}", {"blobs": "true"}, ctx.opts.get("ca_bundle"))
        size = sum(f.get("size") or 0 for f in d.get("siblings") or [] if f.get("rfilename", "").endswith(".safetensors"))
        st = d.get("safetensors") or {}
        info["weights_gb"] = round(size / 1e9, 1) if size else None
        info["params"] = st.get("total")
        info["precision"] = model_precision(repo, (st.get("parameters") or {}).keys())
        if not size:
            info["errors"].append(f"{repo} lists no weight files")
    except (OSError, ValueError) as e:
        info["errors"].append(f"weights of {repo} unreadable: {type(e).__name__}: {e}")
    try:
        cfg = hf_get(f"/{repo}/resolve/main/config.json", None, ctx.opts.get("ca_bundle"))
        info["kv"] = kv_profile(cfg)
        if not info["kv"].get("kv_per_token"):
            info["errors"].append(f"{repo} ({', '.join(cfg.get('architectures') or ['unknown architecture'])}) has no attention layout "
                                  f"this tool can size requests from")
    except (OSError, ValueError) as e:
        info["kv"] = kv_profile({})
        info["errors"].append(f"architecture of {repo} unreadable: {type(e).__name__}: {e}")
    info["read"] = iso()
    if not info["errors"]:
        atomic_json(path, {"fetched": now(), "info": info}, 0o644)
    return info


def kv_profile(cfg):
    """Bytes of KV cache per token and of Mamba state per sequence, from a model's config.json."""
    if not cfg:
        return {"kv_per_token": None, "ssm_per_seq": 0, "attn_layers": None, "max_context": None}
    heads = cfg.get("num_attention_heads") or 1
    hidden = cfg.get("hidden_size") or 0
    head_dim = cfg.get("head_dim") or (hidden // heads if hidden else 128)
    kvh = cfg.get("num_key_value_heads") or heads
    pat, lbt, blocks = cfg.get("hybrid_override_pattern"), cfg.get("layers_block_type"), cfg.get("block_configs")
    n_mamba = 0
    if pat:
        n_attn, n_mamba = pat.count("*"), pat.count("M")
        kv_elems = n_attn * kvh * head_dim
    elif lbt:
        n_attn, n_mamba = lbt.count("attention"), lbt.count("mamba")
        kv_elems = n_attn * kvh * head_dim
    elif blocks:
        n_attn, kv_elems = 0, 0
        for b in blocks:
            a = b.get("attention") or {}
            if a.get("no_op") or a.get("replace_with_linear"):
                continue
            n_attn += 1
            kv_elems += max(1, heads // (a.get("n_heads_in_group") or 1)) * head_dim
    else:
        n_attn = cfg.get("num_hidden_layers") or 0
        kv_elems = n_attn * kvh * head_dim
    ssm = n_mamba * (cfg.get("mamba_num_heads") or 0) * (cfg.get("mamba_head_dim") or 0) * (cfg.get("ssm_state_size") or 0) * FIT_SSM_BYTES
    return {"kv_per_token": 2 * kv_elems * FIT_KV_BYTES, "ssm_per_seq": ssm, "attn_layers": n_attn, "mamba_layers": n_mamba,
            "max_context": cfg.get("max_position_embeddings")}


def per_request_gb(info, context, cfg=None):
    """Cache memory one request of `context` tokens needs, in GB, from the model's architecture and the tested cache format; None when unknown."""
    kv = (info or {}).get("kv") or {}
    if not kv.get("kv_per_token"):
        return None
    # kv_per_token is counted at FIT_KV_BYTES per element; Google's tested config may store the cache in FP8 (one byte)
    scale = (1 / FIT_KV_BYTES) if str((cfg or {}).get("kv_dtype", "")).startswith("fp8") else 1.0
    return (kv["kv_per_token"] * scale * context + (kv.get("ssm_per_seq") or 0)) / 1e9


def copy_capacity(info, mem_gb, per_copy, context, cfg):
    """Requests one copy of the model holds at once: GPU memory left after the weights over the cache per request, capped by Google's tested setting."""
    seq, w = per_request_gb(info, context, cfg), (info or {}).get("weights_gb")
    if seq is None or not w or not mem_gb:
        return None
    room = per_copy * (mem_gb * (cfg.get("mem_frac") or FIT_USABLE_FRAC) - FIT_RUNTIME_GB) - w
    cap = int(room // seq) if room > 0 else 0
    return min(cap, cfg["max_seqs"]) if cfg.get("max_seqs") else cap


def fit_rows(ctx, per_unit, arch=None, family=None):
    """Machine types of the given GPUs that hold at least one unit; per_unit maps a GPU type to the GPUs one copy, workstation or job needs."""
    cat, rows = ctx.catalog, []
    for acc, n in per_unit.items():
        a = cat["accels"].get(acc)
        if not a or not n:
            continue
        for sname in a["shapes"]:
            s = cat["shapes"][sname]
            if s.get("fraction", 1.0) < 1.0 or (arch and s.get("cpu_arch") and s["cpu_arch"] != arch) or (family and not re.match(family, s["family"])):
                continue
            k = int(s["gpus"] // n)
            if k >= 1:
                rows.append({"accel": acc, "label": a["label"], "shape": sname, "gpus_vm": s["gpus"], "per_copy": n, "copies_vm": k,
                             "mem_gb": a.get("mem_gb"), "vcpus": s["vcpus"], "mem_gib": s["mem_gib"], "tested": False, "capacity": None})
    return rows


def mg_fit(ctx, entry, context, info=None):
    """Where a Model Garden model runs at this context: GPUs Google tested it on, and every VM size of those GPUs that holds a whole copy."""
    by_acc, notes, per_copy, cfg_of = {}, [], {}, {}
    for c in entry["configs"]:
        by_acc.setdefault(c["accel"], []).append(c)
    for acc, cfgs in by_acc.items():
        if acc not in ctx.catalog["accels"]:
            notes.append(f"Google also tested {', '.join(sorted({c['machine'] for c in cfgs}))}; this project cannot use that GPU in any zone")
            continue
        ok = [c for c in sorted(cfgs, key=lambda c: c["gpus"]) if not c.get("max_len") or c["max_len"] >= context]
        if not ok:
            notes.append(f"{ctx.catalog['accels'][acc]['label']}: Google tested up to {max(c.get('max_len') or 0 for c in cfgs)} tokens, "
                         f"fewer than the {context} asked for")
            continue
        per_copy[acc], cfg_of[acc] = ok[0]["gpus"], ok[0]
    tested = {c["machine"] for c in entry["configs"]}
    rows = fit_rows(ctx, per_copy)
    for r in rows:
        r["tested"], r["cfg"] = r["shape"] in tested, cfg_of[r["accel"]]
        if entry["kind"] == "llm":
            r["capacity"] = copy_capacity(info, r["mem_gb"], r["per_copy"], context, r["cfg"])
    short = sorted({r["label"] for r in rows if r["capacity"] == 0})
    if short:
        notes.append(f"at {context} tokens per request, a copy on {', '.join(short)} has no memory left for requests after its weights")
    return [r for r in rows if r["capacity"] != 0], notes


def plan_units(rows, units=None, peak=None):
    """Per machine type: model copies (or workstations, or jobs) needed, VM instances needed and GPUs in total; fewest GPUs first."""
    for r in rows:
        need = units
        if need is None and peak and r.get("capacity"):
            need = math.ceil(peak / r["capacity"])
        r["units"] = need
        r["vms"] = math.ceil(need / r["copies_vm"]) if need else None
        r["gpus_total"] = r["vms"] * r["gpus_vm"] if r["vms"] else None
    # fewest GPUs, then Google's tested machine type, then the smaller VM, which is usually easier to obtain
    return sorted(rows, key=lambda r: (r["gpus_total"] is None, r["gpus_total"] or 0, not r["tested"], r["gpus_vm"], r["vcpus"], r["shape"]))


# ------------------------------------------------------------------ the plan
def new_request():
    return {"accel": None, "goal": None, "shapes": [], "layout": "spread", "cluster_nodes": 1, "regions": [], "fallback": [], "exclude": [],
            "method": None, "image": None, "subnet": None, "boot_disk_gb": BOOT_DISK_GB, "flex_wait_s": FLEX_WAIT_S, "flex_run_s": FLEX_RUN_S,
            "spot_action": "DELETE", "reservation_ttl_s": None, "max_usd_h": None, "quota_request": "off", "quota_regions": [],
            "quota_split": {}, "contact": None, "justification": None, "use_case": None, "maintain": False, "advisor": True,
            "calendar": {"start_after_days": 1, "start_within_days": 30, "min_days": 1, "max_days": 7, "auto_submit": False},
            "workload": None, "image_label": None, "allow_overshoot": False, "vm_service_account": None}


def plan_regions(ctx, req):
    """Preferred regions in the customer's order, then fallbacks, minus exclusions and regions blocked by policy."""
    known = set(ctx.catalog["regions"])
    pref = expand_regions(req["regions"], known)
    fb = expand_regions(req["fallback"], known) if req["fallback"] else []
    excl = set(expand_regions(req["exclude"], known)) if req["exclude"] else set()
    offered = {r for s in req["shapes"] for r in ctx.catalog["shapes"][s]["regions"]}
    out, dropped, n_pref = [], [], 0
    for i, r in enumerate(pref + fb):
        if r in out:
            continue
        if r in excl:
            dropped.append((r, "excluded by you"))
        elif r in ctx.blocked_regions:
            dropped.append((r, "outside the organization's resourceLocations policy"))
        elif r not in offered:
            if i < len(pref):
                dropped.append((r, "none of the chosen machine sizes is offered there"))
        else:
            out.append(r)
            n_pref += i < len(pref)
    return out, n_pref, dropped


def build_targets(ctx, req, regions):
    """The ladder: preferred region and shape first, then other shapes, then fallback regions."""
    out = []
    method = req["method"]
    for ri, region in enumerate(regions):
        for si, sname in enumerate(req["shapes"]):
            shape = ctx.catalog["shapes"][sname]
            ok, why = method_allows(method, shape)
            zones = [z for z in shape["zones"] if region_of(z) == region]
            if not zones or not ok:
                continue
            if method in ("vms", "spot"):
                out.append({"key": f"{method}|{sname}|{region}", "shape": sname, "region": region, "zone": None, "zones": zones, "rank": (ri, si)})
            else:
                for z in zones:
                    out.append({"key": f"{method}|{sname}|{z}", "shape": sname, "region": region, "zone": z, "zones": [z], "rank": (ri, si)})
    return out


def rank_fallbacks(ctx, req, regions, n_pref):
    """Keep preferred regions in order; sort fallback regions by Google's capacity score, then price."""
    if len(regions) <= n_pref:
        return regions
    shape = ctx.catalog["shapes"][req["shapes"][0]]
    scored = []
    for r in regions[n_pref:]:
        best = None
        if req.get("advisor") and ctx.caps.get("advisor", {}).get("ok") is not False:
            for z in [z for z in shape["zones"] if region_of(z) == r][:3]:
                sc = advise(ctx, shape, z).get("score")
                if sc is not None:
                    best = max(best or 0, sc)
        price = price_of(ctx, shape, r, req["method"])
        scored.append((-(best if best is not None else -1), price if price is not None else 1e9, r))
    return regions[:n_pref] + [r for _, _, r in sorted(scored)]


def quota_summary(ctx, req, regions):
    """Per region: zones offering each shape, quota headroom in nodes and GPUs, the binding quota and price."""
    rows = []
    for r in regions:
        for sname in req["shapes"]:
            s = ctx.catalog["shapes"][sname]
            zones = [z for z in s["zones"] if region_of(z) == r]
            ok, why = method_allows(req["method"], s)
            if not zones:
                continue
            h = headroom(ctx, s, r, req["method"]) if ok else {"more": None, "binding": None, "rows": []}
            b = h["binding"] or {}
            rows.append({"region": r, "shape": sname, "zones": len(zones), "allowed": ok, "why": why, "nodes": h["more"],
                         "unknown": [L["label"] for L in h.get("unknown") or []],
                         "gpus": None if h["more"] is None else h["more"] * s["gpu_equiv"], "binding": b.get("label"),
                         "binding_qid": b.get("qid"), "binding_nums": f"{b.get('used')}/{b.get('limit')}" if b else "-",
                         "layers": h["rows"], "usd_h": price_of(ctx, s, r, req["method"])})
    return rows


def verdict(ctx, req, regions, rows, obtained=0.0):
    """One plain sentence on whether quota or capacity stands between the customer and the GPUs."""
    goal = req["goal"] - obtained
    if req["method"] == "calendar":
        return "info", "Calendar mode needs no quota; only Google's future availability decides, which the search below shows."
    gq = None
    for r in rows:
        for L in r["layers"]:
            if L["kind"] == "gpu_all" and L["limit"] is not None:
                gq = L
    global_free = None if not gq else (10 ** 6 if gq["limit"] < 0 else max(0, gq["limit"] - (gq["used"] or 0)))
    regional = 0.0
    binders = {}
    unknown = False
    for r in regions:
        best = 0.0
        for row in [x for x in rows if x["region"] == r and x["allowed"]]:
            s = ctx.catalog["shapes"][row["shape"]]
            reg_layers = [L for L in row["layers"] if L["scope"] != "all regions"]
            if any(L["more"] is None for L in reg_layers):
                unknown = True
            known = [L["more"] for L in reg_layers if L["more"] is not None]
            if not known:
                continue
            nodes = min(known)
            best = max(best, nodes * s["gpu_equiv"])
            if nodes * s["gpu_equiv"] < goal:
                for L in reg_layers:
                    if L["more"] is not None and L["more"] == nodes:
                        binders.setdefault((L["label"], L["limit"]), set()).add(r)
        regional += best
    cap = regional if global_free is None else min(regional, global_free)
    label = ctx.catalog["accels"][req["accel"]]["label"]
    parts = []
    if global_free is not None and global_free < goal:
        parts.append(f"GPUs (all regions): {fnum(global_free)} free of {gq['limit']}")
    for (lab, lim), rs in sorted(binders.items(), key=lambda kv: -len(kv[1])):
        where = f"{len(rs)} region(s)" if len(rs) > 2 else ", ".join(sorted(rs))
        parts.append(f"{lab} limit {lim} in {where}")
    blist = "; ".join(parts[:5])
    if cap >= goal - 1e-9:
        return "ok", (f"Quota allows the full {fnum(goal)} {label} GPUs in the allowed regions" +
                      (" as far as the readable limits show (some could not be read)" if unknown else "") +
                      ". What remains is capacity: the loop now looks for free hardware.")
    if cap <= 1e-9:
        return "quota", (f"Quota stops this plan before capacity matters: the project may hold 0 more {label} GPUs in the allowed regions "
                         f"({blist or 'see the quota panel'}). Capacity cannot be tested until quota rises." +
                         (" Some limits could not be read." if unknown else ""))
    return "partial", (f"Quota {'allows at most' if unknown else 'caps this plan at'} {fnum(cap)} of {fnum(goal)} {label} GPUs ({blist}). "
                       f"The loop hunts capacity for those {fnum(cap)}; the other {fnum(goal - cap)} need more quota." +
                       (" Some limits could not be read, so Google may allow fewer." if unknown else ""))


# ------------------------------------------------------------------ optional quota request (opt-in, minimal, one shot)
INELIGIBLE = {"NO_VALID_BILLING_ACCOUNT": "the project has no valid billing account",
              "NOT_SUPPORTED": "Google does not take increase requests for this quota",
              "NOT_ENOUGH_USAGE_HISTORY": "the project needs more usage history before Google considers an increase",
              "OTHER": "Google reports the project ineligible for this increase"}


def existing_pref(ctx, qid, dims):
    for p in ctx.prefs or []:
        if p.get("quotaId") == qid and (p.get("dimensions") or {}) == dims:
            return p
    return None


def quota_needs(ctx, req, regions_split, obtained=0.0):
    """Exactly the quota the chosen plan still needs: per binding layer, current usage plus the shortfall's need, nothing more."""
    method = req["method"]
    shape = None
    out = []
    totals = {"gpu_all": 0, "cpu_all": 0}
    rows = []
    for region, gpus in regions_split.items():
        shape = next((ctx.catalog["shapes"][s] for s in req["shapes"] if method_allows(method, ctx.catalog["shapes"][s])[0]
                      and any(region_of(z) == region for z in ctx.catalog["shapes"][s]["zones"])), None)
        if not shape or gpus <= 0:
            continue
        nodes = int(math.ceil(gpus / shape["gpu_equiv"] - 1e-9))
        for L in layers_for(ctx, shape, region, method):
            amount = nodes * L["need"]
            if L["scope"] == "all regions":
                totals[L["kind"]] += amount
                continue
            rows.append((L, amount, region, shape, nodes))
    glayers = {}
    if shape:
        for L in layers_for(ctx, shape, list(regions_split)[0], method):
            if L["scope"] == "all regions":
                glayers[L["kind"]] = L
    for kind in ("gpu_all", "cpu_all"):
        if kind in glayers and totals[kind]:
            rows.insert(0 if kind == "gpu_all" else 1, (glayers[kind], totals[kind], None, shape, None))
    for L, amount, region, s, nodes in rows:
        qid = L.get("qid")
        lim = ctx.book.limit(qid, L["dims"]) if qid else None
        used = ctx.book.used(L) if qid else None
        info = ctx.book.info(qid) if qid else {}
        display = (info.get("display") or qid or L["label"]) + (f" {L['dims']['gpu_family']}" if L["dims"].get("gpu_family") else "")
        rec = {"qid": qid, "dims": L["dims"], "label": L["label"], "kind": L["kind"], "limit": lim, "used": used, "need": amount,
               "preferred": None if used is None else used + amount, "region": region, "shape": s["name"] if s else None, "nodes": nodes,
               "display": display, "fixed": info.get("fixed"), "eligible": info.get("eligible"), "inelig": info.get("inelig"),
               "pre": L.get("pre", False)}
        if not qid:
            rec["action"], rec["why"] = "none", L.get("note") or "no quota to request"
        elif lim is None or used is None:
            rec["action"], rec["why"] = "unknown", "the limit or usage could not be read, so no exact value can be computed"
        elif lim < 0 or lim >= rec["preferred"]:
            rec["action"], rec["why"] = "enough", f"limit {lim} already covers usage {used} plus {amount}"
        elif rec["fixed"]:
            rec["action"], rec["why"] = "fixed", "Google does not allow changes to this quota"
        elif rec["eligible"] is False:
            rec["action"], rec["why"] = "ineligible", INELIGIBLE.get(rec["inelig"] or "OTHER", rec["inelig"] or "ineligible")
        else:
            p = existing_pref(ctx, qid, L["dims"])
            cfg = (p or {}).get("quotaConfig") or {}
            if p and p.get("reconciling"):
                rec["action"], rec["why"] = "pending", f"a request for {cfg.get('preferredValue')} is already under review; not filed again"
                rec["existing"] = p.get("name")
            elif p and cfg.get("grantedValue") is not None and int(cfg.get("grantedValue") or 0) < int(cfg.get("preferredValue") or 0):
                rec["action"], rec["why"] = "denied_before", (f"an earlier request for {cfg.get('preferredValue')} ended at {cfg.get('grantedValue')} "
                                                             f"({cfg.get('stateDetail') or 'denied'}); not re-filed automatically")
                rec["existing"] = p.get("name")
            else:
                rec["action"], rec["why"] = "file", f"usage {used} + needed {amount} = {used + amount}; limit is {lim}"
                if p:
                    # Google keeps one request per quota and location, so a decided one is updated rather than duplicated
                    rec["existing"] = p.get("name")
                    rec["why"] += f"; updates the existing request {tail(p.get('name'))} (was {cfg.get('preferredValue')})"
        out.append(rec)
    return out


def filing_set(recs):
    """What would be filed, and what blocks filing: every binding quota must be requestable, or nothing is filed."""
    todo = [r for r in recs if r["action"] == "file"]
    stuck = [r for r in recs if r["action"] in ("denied_before", "pending", "fixed", "ineligible", "unknown", "none")]
    return todo, stuck


def pref_id(run_id, rec):
    parts = [NAME_PREFIX, run_short(run_id), re.sub(r"-per-project.*$", "", rec["qid"] or "x").lower()]
    if rec["dims"].get("gpu_family"):
        parts.append(rec["dims"]["gpu_family"].lower().replace("nvidia_", ""))
    if rec["dims"].get("region"):
        parts.append(rec["dims"]["region"])
    return safe_name(*parts)


def pref_body(ctx, rec, contact, justification):
    body = {"service": "compute.googleapis.com", "quotaId": rec["qid"], "quotaConfig": {"preferredValue": str(rec["preferred"])},
            "justification": justification}
    if rec["dims"]:
        body["dimensions"] = rec["dims"]
    if contact:
        body["contactEmail"] = contact
    return body


UPDATE_MASK = "quotaConfig.preferredValue,justification,contactEmail"


def validate_request(ctx, run_id, rec, contact, justification):
    """Google's own validation of a request, without filing it."""
    try:
        if rec.get("existing"):
            cur = ctx.api.get(f"{QUOTAS}/{rec['existing']}")
            body = dict(pref_body(ctx, rec, contact, justification), name=rec["existing"], etag=cur.get("etag"))
            ctx.api.call("PATCH", f"{QUOTAS}/{rec['existing']}", params={"validateOnly": "true", "updateMask": UPDATE_MASK}, body=body, retries=1)
        else:
            name = f"projects/{ctx.project}/locations/global/quotaPreferences/{pref_id(run_id, rec)}"
            body = dict(pref_body(ctx, rec, contact, justification), name=name)
            ctx.api.call("PATCH", f"{QUOTAS}/{name}", params={"allowMissing": "true", "validateOnly": "true"}, body=body, retries=1)
        return True, "valid"
    except ApiError as e:
        return False, classify(e, ctx.project).title + f" ({e.short()[:200]})"


def file_requests(ctx, run_id, recs, contact, justification, state, save):
    """File each request once, all-regions GPU cap first; stop dependents if Google denies it at once; stop all on the daily limit."""
    filed = state.setdefault("quota_requests", [])
    done_ids = {f["id"] for f in filed}
    order = sorted([r for r in recs if r["action"] == "file"], key=lambda r: (r["kind"] != "gpu_all", r["kind"] != "cpu_all"))
    for rec in order:
        pid = tail(rec["existing"]) if rec.get("existing") else pref_id(run_id, rec)
        if pid in done_ids:
            continue
        if (state.get("quota_blocked_until") or 0) > now():
            rec["result"] = "not filed: Google's daily request limit was reached; next attempt not before " + iso(state["quota_blocked_until"])
            continue
        body = pref_body(ctx, rec, contact, justification)
        entry = {"id": pid, "qid": rec["qid"], "dims": rec["dims"], "preferred": rec["preferred"], "from": rec["limit"], "used": rec["used"],
                 "need": rec["need"], "filed": iso(), "state": "filing"}
        filed.append(entry)
        save()
        try:
            if rec.get("existing"):
                entry["updated_existing"] = True
                cur = ctx.api.get(f"{QUOTAS}/{rec['existing']}")
                p = ctx.api.call("PATCH", f"{QUOTAS}/{rec['existing']}", params={"updateMask": UPDATE_MASK},
                                 body=dict(body, name=rec["existing"], etag=cur.get("etag")), retries=2)
            else:
                p = ctx.api.call("POST", f"{QUOTAS}/projects/{ctx.project}/locations/global/quotaPreferences", params={"quotaPreferenceId": pid},
                                 body=body, retries=2)
        except ApiError as e:
            if e.status == 409:
                p = ctx.api.get(f"{QUOTAS}/projects/{ctx.project}/locations/global/quotaPreferences/{pid}")
            elif e.status == 429:
                state["quota_blocked_until"] = now() + 86400
                entry["state"] = "not filed: daily request limit"
                rec["result"] = entry["state"]
                ctx.ev.note("Google's daily quota-request limit was reached; no more requests are filed today", "warn")
                save()
                continue
            else:
                c = classify(e, ctx.project)
                entry["state"] = f"refused: {c.title}"
                rec["result"] = entry["state"]
                ctx.ev.note(f"quota request {pid} refused: {c.title}. {c.fix}", "warn")
                save()
                continue
        cfg = p.get("quotaConfig") or {}
        entry.update(state="under review" if p.get("reconciling") else (cfg.get("stateDetail") or "filed"), granted=cfg.get("grantedValue"),
                     trace=cfg.get("traceId"), name=p.get("name"))
        rec["result"] = entry["state"]
        ctx.ev.note(f"filed quota request {pid}: {rec['qid']} {rec['dims']} to {rec['preferred']} ({entry['state']})")
        save()
        if rec["kind"] == "gpu_all":
            p = wait_decision(ctx, p)
            cfg = p.get("quotaConfig") or {}
            entry.update(state=pref_state(p), granted=cfg.get("grantedValue"))
            rec["result"] = entry["state"]
            save()
            if not p.get("reconciling") and int(cfg.get("grantedValue") or 0) < rec["preferred"]:
                for other in order:
                    if other is not rec and "result" not in other:
                        other["result"] = "not filed: the all-regions GPU request was denied, so regional increases cannot be used"
                ctx.ev.note("the all-regions GPU request was denied; dependent regional requests were not filed", "warn")
                break
    ctx.prefs = None
    load_prefs(ctx)
    return filed


def pref_state(p):
    cfg = p.get("quotaConfig") or {}
    if p.get("reconciling"):
        return "under review"
    return cfg.get("stateDetail") or ("granted" if cfg.get("grantedValue") == cfg.get("preferredValue") else "decided")


def wait_decision(ctx, p):
    """Google often decides small requests within seconds; wait a bounded window, then leave it to the status poll."""
    end = now() + QUOTA_DECISION_WAIT_S
    while p.get("reconciling") and now() < end:
        ctx.api.sleep(10)
        try:
            p = ctx.api.get(f"{QUOTAS}/{p['name']}")
        except ApiError:
            break
    return p


def poll_requests(ctx, state):
    """Refresh the state of requests this run filed; returns True when any grant changed."""
    changed = False
    for f in state.get("quota_requests") or []:
        if not f.get("name") or f.get("final") or str(f.get("state", "")).startswith(("refused", "not filed")):
            continue
        try:
            p = ctx.api.get(f"{QUOTAS}/{f['name']}")
        except ApiError as e:
            ctx.ev.note(f"quota request {f['id']} unreadable: {classify(e, ctx.project).title}", "warn")
            continue
        cfg = p.get("quotaConfig") or {}
        st = pref_state(p)
        if st != f.get("state") or cfg.get("grantedValue") != f.get("granted"):
            changed = changed or (cfg.get("grantedValue") != f.get("granted"))
            ctx.ev.note(f"quota request {f['id']}: {st}, granted {cfg.get('grantedValue')} of {f['preferred']}")
            f.update(state=st, granted=cfg.get("grantedValue"), checked=iso())
        f["final"] = not p.get("reconciling")
    return changed


# ------------------------------------------------------------------ run state
def run_dir(run_id):
    return os.path.join(HOME, "runs", run_id)


def run_label(run_id):
    return safe_name(run_id)


def new_state(run_id, req, ctx):
    return {"run_id": run_id, "version": VERSION, "created": iso(), "project": ctx.project, "account": ctx.tokens.account, "status": "planned",
            "request": req, "regions": [], "holds": [], "pending": [], "templates": [], "migs": [], "targets": {}, "inflight": [],
            "totals": {"attempts": 0, "ok": 0, "stockout": 0, "quota": 0, "other": 0, "loops": 0, "verify": 0}, "quota_requests": [],
            "seq": 0, "notes": []}


class Saver:
    def __init__(self, path, st):
        self.path, self.st = path, st

    def __call__(self):
        self.st["updated"] = iso()
        atomic_json(self.path, self.st)


# ------------------------------------------------------------------ holding capacity
def vm_network(ctx, req, region, zonal=None):
    """The network interface for a VM: the subnet the customer named, the default network, or any subnet in the region."""
    sub = req.get("subnet")
    if sub:
        if sub.startswith("projects/"):
            return {"subnetwork": sub, "nicType": "GVNIC"}
        return {"subnetwork": f"projects/{ctx.project}/regions/{region}/subnetworks/{sub}", "nicType": "GVNIC"}
    subs = (ctx.subnets or {}).get(region)
    if ctx.subnets is not None and not subs:
        return None
    if subs and not any(tail(s.get("network")) == "default" for s in subs):
        return {"subnetwork": subs[0]["selfLink"], "nicType": "GVNIC"}
    return {"network": "global/networks/default", "nicType": "GVNIC"}


def scheduling_for(req, method):
    if method == "spot":
        return {"provisioningModel": "SPOT", "instanceTerminationAction": req.get("spot_action") or "DELETE", "onHostMaintenance": "TERMINATE",
                "automaticRestart": False}
    if method in ("flex", "flex-group"):
        return {"provisioningModel": "FLEX_START", "instanceTerminationAction": "DELETE", "onHostMaintenance": "TERMINATE",
                "maxRunDuration": {"seconds": str(int(req.get("flex_run_s") or FLEX_RUN_S))}}
    return {"onHostMaintenance": "TERMINATE", "automaticRestart": True}


def vm_props(ctx, req, shape, method, region, labels, zone=None):
    """Instance properties: zonal requests use URLs for machine, disk and accelerator types; bulk and templates use names."""
    net = vm_network(ctx, req, region)
    if net is None:
        raise ApiError(400, f"no subnet in {region} for VMs; pass --subnet or create one", {"error": {"status": "NO_SUBNET"}}, reason="NO_SUBNET")
    mt = f"zones/{zone}/machineTypes/{shape['base']}" if zone else shape["base"]
    disk = f"zones/{zone}/diskTypes/{shape['boot_disk']}" if zone else shape["boot_disk"]
    props = {"machineType": mt,
             "disks": [{"boot": True, "autoDelete": True, "initializeParams": {"sourceImage": req.get("image") or IMAGE, "diskType": disk,
                                                                                "diskSizeGb": str(int(req.get("boot_disk_gb") or BOOT_DISK_GB))}}],
             "networkInterfaces": [net], "scheduling": scheduling_for(req, method), "labels": labels}
    if req.get("vm_service_account"):
        # off by default: attaching one needs iam.serviceAccounts.actAs on it, which the preflight checks
        props["serviceAccounts"] = [{"email": req["vm_service_account"], "scopes": ["https://www.googleapis.com/auth/cloud-platform"]}]
    if shape["attached"]:
        at = f"zones/{zone}/acceleratorTypes/{shape['accel']}" if zone else shape["accel"]
        props["guestAccelerators"] = [{"acceleratorType": at, "acceleratorCount": shape["gpus"]}]
    return props


class Hunt:
    """The acquisition loop: walk the ladder, attempt, classify, back off, park, and keep the customer informed."""

    def __init__(self, ctx, req, st, save, regions, dry_run=False):
        self.ctx, self.req, self.st, self.save, self.regions = ctx, req, st, save, regions
        self.api, self.t, self.ev = ctx.api, ctx.t, ctx.ev
        self.dry = dry_run
        self.method = req["method"]
        self.targets = build_targets(ctx, req, regions)
        if self.method == "calendar":
            self.targets = self._calendar_targets()
        for tg in self.targets:
            st["targets"].setdefault(tg["key"], {"attempts": 0, "ok": 0, "last": None, "last_at": None, "next_at": 0, "backoff": TARGET_INTERVAL_S,
                                                 "chunk": min(RESERVATION_CHUNK_MAX, 4), "parked": None, "quota_bound": False, "verify_at": 0,
                                                 "last_ok_at": None})
        self.head = {}
        self.dirty_quota = True
        self.last = {"quota": now(), "holds": now(), "pending": 0, "prefs": now(), "park": now(), "sweep": now(), "plain": 0, "ui": 0}
        self.started = now()
        self.label = run_label(st["run_id"])
        self.short = run_short(st["run_id"])
        self.keys = KeyReader(self.t)
        self.ring_seen = 0
        self.notice = {}
        self.activity = {"what": "starting", "detail": None, "since": now()}
        self.sweeps = 1
        self._ui_stop = threading.Event()
        self._ui_thread = None
        self.ui_error = None

    def doing(self, what, detail=None, until=None):
        """Say what the run is doing right now; the dashboard shows it live, plain mode prints each change on its own line."""
        if self.activity.get("what") == what and self.activity.get("detail") == detail:
            if until:
                self.activity = dict(self.activity, until=until)
            return
        self.activity = {"what": what, "detail": detail, "since": now(), "until": until}
        if self.t.plain:
            eta = f", in {human_dur(max(0, until - now()))}" if until else ""
            self.t.line(self.t.s(time.strftime("%H:%M:%S") + " now: ", "c") + what + (self.t.s(f"  ({detail}{eta})", "gr") if detail or eta else ""))

    def _ui_loop(self):
        while not self._ui_stop.is_set():
            try:
                if self.t.in_dash:
                    self.t.dash_frame(self.render())
            except Exception as e:  # the view must never stop the run; the error is shown once on the events list
                if not self.ui_error:
                    self.ui_error = f"{type(e).__name__}: {e}"
                    self.note(f"live view could not draw a frame: {self.ui_error}", "warn")
            self._ui_stop.wait(UI_REFRESH_S)

    # ---------------------------------------------------------- bookkeeping
    def _calendar_targets(self):
        out, seen = [], set()
        for tg in self.targets:
            k = (tg["shape"], tg["region"])
            if k in seen:
                continue
            seen.add(k)
            zones = [x["zone"] for x in self.targets if (x["shape"], x["region"]) == k]
            out.append(dict(tg, key=f"calendar|{tg['shape']}|{tg['region']}", zone=None, zones=zones))
        return out

    def held(self):
        return [h for h in self.st["holds"] if h.get("state") == "held"]

    def obtained(self):
        return sum(h["gpus"] for h in self.held())

    def pending_gpus(self):
        return sum(p["gpus"] for p in self.st["pending"] if p.get("state") in ("queued", "submitted"))

    def remaining(self):
        return self.req["goal"] - self.obtained() - self.pending_gpus()

    def cost(self):
        return sum((h.get("usd_h") or 0) for h in self.held())

    def next_name(self, kind):
        self.st["seq"] += 1
        return safe_name(NAME_PREFIX, self.short, f"{kind}{self.st['seq']:04d}")

    def labels(self, extra=None):
        out = {"gpu-finder-run": self.label, "gpu-finder": "1"}
        out.update(extra or {})
        return out

    def note(self, msg, level="info"):
        self.ev.note(msg, level)

    def once(self, key, msg, level="info"):
        if self.notice.get(key) != msg:
            self.notice[key] = msg
            self.note(msg, level)

    def shape(self, name):
        return self.ctx.catalog["shapes"][name]

    def unit_gpus(self, shape):
        return shape["gpu_equiv"] * (self.req["cluster_nodes"] if self.req["layout"] == "cluster" else 1)

    def head_of(self, shape, region):
        key = (shape["name"], region)
        if key not in self.head:
            self.head[key] = headroom(self.ctx, shape, region, self.method)
        return self.head[key]

    # ---------------------------------------------------------- the loop
    def run(self):
        st = self.st
        st["status"] = "running"
        st["started"] = st.get("started") or iso()
        self.save()
        self.note(f"run {st['run_id']} started: {fnum(self.req['goal'])} x {self.req['accel']} via {METHOD_LABEL[self.method]}, "
                  f"{len(self.targets)} targets across {len(self.regions)} regions" + (" (dry run: no writes)" if self.dry else ""))
        self.ctx.stop.term = self.t
        self.ctx.stop.install()
        self.t.dash_start()
        self.keys.start()
        if self.t.in_dash:
            self._ui_thread = threading.Thread(target=self._ui_loop, name="live-view", daemon=True)
            self._ui_thread.start()
        outcome = "stopped"
        try:
            self.reconcile_inflight()
            if any(ts.get("parked") for ts in st["targets"].values()):
                self.unpark("the run was started again")
            outcome = self.loop()
        except Interrupted:
            outcome = "forced"
        except KeyboardInterrupt:
            outcome = "forced"
        finally:
            self._ui_stop.set()
            if self._ui_thread:
                self._ui_thread.join()
            self.keys.stop()
            self.t.dash_stop()
            self.ctx.stop.restore()
        return self.finish(outcome)

    def loop(self):
        while True:
            if self.ctx.stop.stopping:
                return "stopped"
            self.housekeeping()
            self.st["totals"]["loops"] += 1
            if self.obtained() >= self.req["goal"] - 1e-9 and not self.req.get("maintain"):
                return "done"
            if self.dry and self.st["totals"]["loops"] > 1:
                return "dry-run"
            b = self.blocked()
            if b:
                self.note(f"stopping: every option is blocked by: {b['why'].rstrip('.')}. Fix: {b['fix']}. Then: resume {self.st['run_id']}", "error")
                self.ctx.stop.reason = "blocked: " + b["why"]
                return "blocked"
            tg = None
            if self.remaining() > 1e-9:
                tg = self.next_target()
            if tg is None:
                if self.dry:
                    return "dry-run"
                self.idle(self.next_wake())
                continue
            self.attempt(tg)
            self.save()

    def next_wake(self):
        t = now()
        cands = [t + UI_REFRESH_S * 5]
        for tg in self.targets:
            ts = self.st["targets"][tg["key"]]
            if ts["parked"]:
                continue
            if ts["quota_bound"]:
                cands.append(ts["verify_at"])
            else:
                cands.append(ts["next_at"])
        if self.st["pending"]:
            cands.append(self.last["pending"] + PENDING_POLL_S)
        return max(t + 0.2, min(cands))

    def upcoming(self, n=None):
        """Targets that will be tried next, soonest first: (time due, target, why it waits)."""
        out = []
        for tg in self.targets:
            ts = self.st["targets"][tg["key"]]
            if ts["parked"]:
                continue
            if ts["quota_bound"]:
                out.append((ts["verify_at"], tg, "quota check"))
            else:
                why = {"stockout": "backoff after no capacity", "reservation_limit": "backoff after no capacity", "obtained": "after a success",
                       "queued": "a request is queued"}.get(ts["last"] or "", "first try" if not ts["attempts"] else "retry")
                out.append((ts["next_at"], tg, why))
        out.sort(key=lambda x: x[0])
        return out[:n] if n else out

    def idle(self, until):
        nxt = self.upcoming(1)
        if self.remaining() <= 1e-9 and self.req.get("maintain"):
            self.doing("goal reached; watching held capacity and replacing what Google reclaims")
        elif self.st["pending"] and self.pending_gpus() >= self.remaining() - 1e-9:
            self.doing(f"waiting for {len([p for p in self.st['pending'] if p.get('state') in ('queued', 'submitted')])} queued request(s) "
                       f"to be filled by Google", "next status check", until=self.last["pending"] + PENDING_POLL_S)
        elif nxt:
            due, tg, why = nxt[0]
            self.doing(f"waiting: next try is {tg['shape']} in {tg['zone'] or tg['region']}", why, until=due)
        else:
            self.doing("waiting: every option is parked or quota-bound", "press r to re-check parked options")
        while now() < until and not self.ctx.stop.stopping:
            self.tick_ui()
            k = self.keys.poll()
            if k in ("q", "Q"):
                self.ctx.stop.request("q pressed", True)
                return
            if k in ("r", "R"):
                self.unpark("re-check requested")
                return
            time.sleep(min(0.25, max(0.0, until - now())))

    def tick_ui(self, force=False):
        t = now()
        if self.t.in_dash:
            if self._ui_thread and self._ui_thread.is_alive():
                return
            if force or t - self.last["ui"] >= UI_REFRESH_S:
                self.last["ui"] = t
                self.t.dash_frame(self.render())
        else:
            ring = self.ev.ring
            new = [r for r in ring if r[0] > self.ring_seen]
            for ts, level, msg in new:
                style = {"warn": "y", "error": "r", "good": "g"}.get(level)
                self.t.line(f"{iso(ts)} " + (self.t.s(msg, style) if style else msg))
            if new:
                self.ring_seen = new[-1][0]
            if force or t - self.last["plain"] >= PLAIN_STATUS_S:
                self.last["plain"] = t
                self.t.line(self.status_line())

    def status_line(self):
        tt = self.st["totals"]
        return (f"{iso()} status: {fnum(self.obtained())}/{fnum(self.req['goal'])} GPUs held, {fnum(self.pending_gpus())} pending, "
                f"{tt['attempts']} attempts ({tt['ok']} ok, {tt['stockout']} no capacity, {tt['quota']} quota, {tt['other']} other), "
                f"cost {money(self.cost())}/h, elapsed {human_dur(now() - self.started)}")

    # ---------------------------------------------------------- periodic work
    def housekeeping(self):
        t = now()
        self.tick_ui()
        k = self.keys.poll()
        if k in ("q", "Q"):
            self.ctx.stop.request("q pressed", True)
        elif k in ("r", "R"):
            self.unpark("re-check requested")
        if (self.dirty_quota and t - self.last["quota"] >= QUOTA_MIN_REFRESH_S) or t - self.last["quota"] >= QUOTA_REFRESH_S:
            self.refresh_quota()
        if self.st["pending"] and t - self.last["pending"] >= PENDING_POLL_S:
            self.poll_pending()
        if self.held() and t - self.last["holds"] >= HOLD_CHECK_S:
            self.check_holds()
        if self.st.get("quota_requests") and t - self.last["prefs"] >= QUOTA_POLL_S:
            self.last["prefs"] = t
            self.doing(f"checking {len(self.st['quota_requests'])} filed quota request(s) with Google",
                       "Cloud Quotas API quotaPreferences.get, read only: " + ", ".join(f["qid"] for f in self.st["quota_requests"][:3]))
            try:
                if poll_requests(self.ctx, self.st):
                    self.dirty_quota = True
                    for ts in self.st["targets"].values():
                        ts["quota_bound"] = False
            except (ApiError, AuthError) as e:
                self.once("prefpoll", f"quota request status unreadable: {classify(e, self.ctx.project).title}", "warn")
        if t - self.last["park"] >= PARK_RECHECK_S:
            self.unpark("scheduled re-check")
        if t - self.last["sweep"] >= SWEEP_S:
            self.last["sweep"] = t
            self.sweeps += 1
            for ts in self.st["targets"].values():
                ts["backoff"] = TARGET_INTERVAL_S
                ts["next_at"] = min(ts["next_at"], t + jitter(TARGET_INTERVAL_S))
            self.note("fresh sweep: every target's backoff reset so changed capacity is noticed")

    def refresh_quota(self):
        self.last["quota"] = now()
        self.dirty_quota = False
        self.doing(f"re-reading quota limits and usage for {len(self.regions)} region(s)",
                   "Cloud Quotas API quotaInfos.list and Compute Engine API usage, read only: " + ", ".join(self.regions[:4])
                   + (" and more" if len(self.regions) > 4 else ""))
        try:
            refresh_quota(self.ctx, self.regions)
            self.head = {}
            for tg in self.targets:
                ts = self.st["targets"][tg["key"]]
                h = self.head_of(self.shape(tg["shape"]), tg["region"])
                if ts["quota_bound"] and (h["more"] is None or h["more"] > 0):
                    ts["quota_bound"] = False
                    self.note(f"quota now allows {tg['shape']} in {tg['region']} again")
        except (ApiError, AuthError) as e:
            c = classify(e, self.ctx.project)
            self.once("quota", f"quota refresh failed ({c.title}); the last known numbers stay in use", "warn")

    def unpark(self, why):
        self.last["park"] = now()
        n = 0
        for ts in self.st["targets"].values():
            if ts["parked"]:
                ts["parked"] = None
                ts["next_at"] = now()
                n += 1
        if n:
            self.note(f"{n} parked target(s) get another try: {why}")

    # ---------------------------------------------------------- choosing and attempting
    def next_target(self):
        t = now()
        rem = self.remaining()
        for tg in self.targets:
            ts = self.st["targets"][tg["key"]]
            if ts["parked"] or ts["next_at"] > t:
                continue
            shape = self.shape(tg["shape"])
            unit = self.unit_gpus(shape)
            if unit > rem + 1e-9 and not self.req.get("allow_overshoot"):
                continue
            if self.method != "calendar":
                h = self.head_of(shape, tg["region"])
                if h["more"] is not None and h["more"] < (self.req["cluster_nodes"] if self.req["layout"] == "cluster" else 1):
                    if not ts["quota_bound"]:
                        ts["quota_bound"] = True
                        ts["verify_at"] = t + QUOTA_VERIFY_S
                        self.once(f"qb|{tg['shape']}|{tg['region']}", f"{tg['shape']} in {tg['region']} is quota-bound "
                                  f"({(h['binding'] or {}).get('label')}); not attempted until quota changes", "warn")
                    if ts["verify_at"] > t:
                        continue
                    tg = dict(tg, verify=True)
            if self.method == "flex-group":
                live = [p for p in self.st["pending"] if p["kind"] == "flex-group" and p.get("state") == "queued"]
                if len(live) >= FLEX_GROUP_PARALLEL:
                    continue
            if self.req.get("max_usd_h"):
                p = price_of(self.ctx, shape, tg["region"], self.method)
                if p is None or self.cost() + p * (self.req["cluster_nodes"] if self.req["layout"] == "cluster" else 1) > self.req["max_usd_h"]:
                    self.once(f"cap|{tg['shape']}|{tg['region']}", f"{tg['shape']} in {tg['region']} skipped: it would pass the "
                              f"{money(self.req['max_usd_h'])}/h cap" + (" (price unknown)" if p is None else ""), "warn")
                    continue
            return tg
        return None

    def nodes_for(self, tg, shape):
        if self.req["layout"] == "cluster":
            return self.req["cluster_nodes"]
        units = int(math.floor(self.remaining() / shape["gpu_equiv"] + 1e-9))
        if units < 1 and self.req.get("allow_overshoot"):
            units = 1
        h = self.head_of(shape, tg["region"])
        if h["more"] is not None and not tg.get("verify"):
            units = min(units, h["more"])
        if self.req.get("max_usd_h"):
            p = price_of(self.ctx, shape, tg["region"], self.method)
            if p:
                units = min(units, int((self.req["max_usd_h"] - self.cost()) // p))
        if self.method == "reservation":
            units = min(units, self.st["targets"][tg["key"]]["chunk"])
        if self.method == "flex":
            units = min(units, FLEX_REQUEST_MAX_VMS)
        if self.method == "calendar":
            units = min(units, CALENDAR_REQUEST_MAX_VMS)
        return max(0, units)

    def attempt(self, tg):
        ts = self.st["targets"][tg["key"]]
        shape = self.shape(tg["shape"])
        nodes = self.nodes_for(tg, shape)
        where = tg["zone"] or tg["region"]
        if nodes < 1:
            ts["next_at"] = now() + jitter(TARGET_INTERVAL_S)
            return
        tot = self.st["totals"]
        ts["attempts"] += 1
        tot["attempts"] += 1
        if tg.get("verify"):
            tot["verify"] += 1
            ts["verify_at"] = now() + QUOTA_VERIFY_S
        ts["last_at"] = now()
        rank = next((i for i, x in enumerate(self.targets, 1) if x["key"] == tg["key"]), 0)
        verb = "dry run, not sent:" if self.dry else {"reservation": "reserving", "calendar": "searching calendar windows for"}.get(self.method, "creating")
        self.doing(f"{verb} {nodes} x {shape['name']} ({fnum(nodes * shape['gpu_equiv'])} x {self.ctx.catalog['accels'][shape['accel']]['label']}) "
                   f"in {where} as {METHOD_LABEL[self.method]}",
                   f"option {rank} of {len(self.targets)} in search order; try {ts['attempts']} of this option, {tot['attempts']} in total"
                   + ("; a single quota check" if tg.get("verify") else ""))
        if self.dry:
            ts["last"] = "dry run"
            ts["next_at"] = now() + jitter(TARGET_INTERVAL_S)
            self.note(f"dry run: would request {nodes} x {shape['name']} in {where} via {METHOD_LABEL[self.method]}")
            return
        try:
            got = getattr(self, "hold_" + self.method.replace("-", "_"))(tg, shape, nodes)
            if got:
                if got > 0:
                    ts["ok"] += 1
                    tot["ok"] += 1
                    ts["last_ok_at"] = now()
                ts["last"] = "obtained" if got > 0 else "queued"
                ts["backoff"] = TARGET_INTERVAL_S
                ts["quota_bound"] = False
                if self.method == "reservation":
                    ts["chunk"] = min(RESERVATION_CHUNK_MAX, ts["chunk"] * 2)
                self.dirty_quota = True
            else:
                ts["last"] = "nothing created"
            ts["next_at"] = now() + jitter(TARGET_INTERVAL_S)
        except (ApiError, OpStalled, AuthError) as e:
            self.on_failure(tg, ts, e, nodes)

    def on_failure(self, tg, ts, e, nodes):
        c = classify(e, self.ctx.project)
        tot = self.st["totals"]
        ts["last"] = c.kind
        t = now()
        where = tg["zone"] or tg["region"]
        if c.kind in ("stockout", "reservation_limit"):
            tot["stockout"] += 1
            if self.method == "reservation" and ts["chunk"] > 1 and nodes > 1:
                ts["chunk"] = max(1, ts["chunk"] // 2)
                ts["next_at"] = t + jitter(TARGET_INTERVAL_S)
            else:
                ts["backoff"] = min(BACKOFF_MAX_S, max(TARGET_INTERVAL_S, ts["backoff"] * 2))
                ts["next_at"] = t + jitter(ts["backoff"])
            self.ev.write("attempt", target=tg["key"], nodes=nodes, result=c.kind)
            if ts["attempts"] <= 1 or ts["attempts"] % 20 == 0:
                self.note(f"{tg['shape']} in {where}: no capacity ({plural(nodes, 'VM instance')}); next try in {human_dur(ts['next_at'] - t)}")
            elif self.t.plain:
                self.t.line(self.t.s(time.strftime("%H:%M:%S") + " result: ", "y") + f"{tg['shape']} in {where}: no capacity; next try in "
                            f"{human_dur(ts['next_at'] - t)}")
            return
        if c.kind == "quota":
            tot["quota"] += 1
            # a refusal on a target already known to be quota-bound teaches nothing new; a surprise one means the numbers moved
            if not tg.get("verify"):
                self.dirty_quota = True
            ts["quota_bound"] = True
            ts["verify_at"] = t + QUOTA_VERIFY_S
            ts["next_at"] = t + jitter(TARGET_INTERVAL_S)
            self.ev.write("attempt", target=tg["key"], nodes=nodes, result="quota", verify=bool(tg.get("verify")), quotas=c.extra.get("quotas"))
            self.once(f"q|{tg['key']}", f"{tg['shape']} in {where}: {c.title}", "warn")
            return
        tot["other"] += 1
        if c.transient:
            ts["next_at"] = t + jitter(TARGET_INTERVAL_S)
            self.once(f"tr|{c.kind}|{where}", f"{tg['shape']} in {where}: {c.title} ({c.fix})", "warn")
            return
        if c.kind in ("region_access", "no_subnet") or (c.kind == "org_policy" and c.extra.get("constraint") == "gcp.resourceLocations"):
            scope = [x for x in self.targets if x["region"] == tg["region"]]
        elif c.kind in PROJECT_WIDE:
            scope = self.targets
        else:
            scope = [x for x in self.targets if x["shape"] == tg["shape"] and x["region"] == tg["region"]]
        for x in scope:
            s = self.st["targets"][x["key"]]
            s["parked"] = {"kind": c.kind, "why": c.title, "fix": c.fix, "at": t}
        self.note(f"parked {len(scope)} target(s): {c.title.rstrip('.')}. Fix: {c.fix}", "error")

    def blocked(self):
        """Every target parked on a permanent error and nothing in flight or held to watch: waiting cannot help until someone fixes it.
        Quota-bound targets are not parked, so a run waiting for quota keeps running."""
        if any(p.get("state") in ("queued", "submitted") for p in self.st["pending"]) or (self.req.get("maintain") and self.held()):
            return None
        parked = [self.st["targets"][tg["key"]]["parked"] for tg in self.targets]
        if self.targets and all(parked):
            return next((p for p in parked if p["kind"] in PROJECT_WIDE), parked[0])
        return None

    # ---------------------------------------------------------- one method each
    def _track(self, entry):
        self.st["inflight"].append(entry)
        self.save()

    def _untrack(self, name):
        self.st["inflight"] = [x for x in self.st["inflight"] if x.get("name") != name]

    def _op(self, op):
        op = self.api.wait_op(op)
        err = op_error(op)
        if err:
            raise err
        return op

    def hold_reservation(self, tg, shape, nodes):
        zone = tg["zone"]
        name = self.next_name("r")
        props = {"machineType": shape["base"]}
        if shape["attached"]:
            props["guestAccelerators"] = [{"acceleratorType": shape["accel"], "acceleratorCount": shape["gpus"]}]
        body = {"name": name, "specificReservationRequired": True, "description": f"gcp-gpu-finder run {self.st['run_id']}",
                "specificReservation": {"count": str(nodes), "instanceProperties": props}}
        if self.req.get("reservation_ttl_s"):
            body["deleteAfterDuration"] = {"seconds": str(int(self.req["reservation_ttl_s"]))}
        self._track({"kind": "reservation", "name": name, "zone": zone, "at": iso()})
        try:
            op = self.api.call("POST", f"{COMPUTE}/projects/{self.ctx.project}/zones/{zone}/reservations", params={"requestId": str(uuid.uuid4())}, body=body)
            self._op(op)
        except ApiError:
            # Google answered, so nothing is left half-made; a forced exit or a stall keeps the record for reconciliation
            self._untrack(name)
            raise
        self._untrack(name)
        p = price_of(self.ctx, shape, tg["region"], "reservation")
        self.st["holds"].append({"kind": "reservation", "name": name, "zone": zone, "region": tg["region"], "shape": shape["name"], "nodes": nodes,
                                 "gpus": nodes * shape["gpu_equiv"], "method": "reservation", "created": iso(), "state": "held",
                                 "usd_h": None if p is None else round(p * nodes, 4),
                                 "expires": iso(now() + self.req["reservation_ttl_s"]) if self.req.get("reservation_ttl_s") else None})
        self.note(f"HELD: reservation {name} for {nodes} x {shape['name']} in {zone} ({fnum(nodes * shape['gpu_equiv'])} GPUs)", "good")
        return nodes

    def hold_vms(self, tg, shape, nodes, method=None):
        method = method or self.method
        region = tg["region"]
        batch = self.next_name("v")
        cluster = self.req["layout"] == "cluster"
        body = {"count": nodes, "minCount": nodes if cluster else 1, "namePattern": f"{batch}-####",
                "instanceProperties": vm_props(self.ctx, self.req, shape, method, region, self.labels({"gpu-finder-batch": batch})),
                "locationPolicy": {"targetShape": "ANY_SINGLE_ZONE" if cluster else "ANY"}}
        self._track({"kind": "vms", "name": batch, "region": region, "at": iso()})
        try:
            op = self.api.call("POST", f"{COMPUTE}/projects/{self.ctx.project}/regions/{region}/instances/bulkInsert",
                               params={"requestId": str(uuid.uuid4())}, body=body)
            self._op(op)
        except ApiError:
            self._untrack(batch)
            raise
        self._untrack(batch)
        made = self.api.aggregated("instances", params={"filter": f'labels.gpu-finder-batch = "{batch}"',
                                                         "fields": "items/*/instances(name,zone,status,machineType),nextPageToken"})
        n = 0
        p = price_of(self.ctx, shape, region, method)
        for zone, items in made.items():
            for i in items:
                n += 1
                self.st["holds"].append({"kind": "vm", "name": i["name"], "zone": zone, "region": region, "shape": shape["name"], "nodes": 1,
                                         "gpus": shape["gpu_equiv"], "method": method, "created": iso(), "state": "held", "usd_h": p, "batch": batch})
        if n:
            self.note(f"HELD: {n} {METHOD_LABEL[method]} of {shape['name']} in {region} (batch {batch})", "good")
        else:
            raise ApiError(0, "the bulk request finished but no VM carries its label", {"error": {"status": "UNKNOWN"}}, reason="EMPTY_BULK")
        return n

    def hold_spot(self, tg, shape, nodes):
        return self.hold_vms(tg, shape, nodes, "spot")

    def hold_flex(self, tg, shape, nodes):
        zone, region = tg["zone"], tg["region"]
        queued = 0
        wait_s = int(self.req.get("flex_wait_s") or FLEX_WAIT_S)
        for _ in range(nodes):
            name = self.next_name("f")
            body = vm_props(self.ctx, self.req, shape, "flex", region, self.labels(), zone=zone)
            body["name"] = name
            body["params"] = {"requestValidForDuration": {"seconds": str(wait_s)}}
            op = self.api.call("POST", f"{COMPUTE}/projects/{self.ctx.project}/zones/{zone}/instances", params={"requestId": str(uuid.uuid4())}, body=body)
            err = op_error(op)
            if err:
                if queued:
                    break
                raise err
            self.st["pending"].append({"kind": "flex", "name": name, "zone": zone, "region": region, "shape": shape["name"], "nodes": 1,
                                       "gpus": shape["gpu_equiv"], "op": op.get("selfLink"), "created": iso(), "expires": iso(now() + wait_s + 600),
                                       "state": "queued"})
            queued += 1
        if queued:
            self.note(f"queued {queued} flex-start request(s) for {shape['name']} in {zone}; each waits up to {human_dur(wait_s)} for capacity")
        self.last["pending"] = now()
        return -queued if queued else 0

    def hold_flex_group(self, tg, shape, nodes):
        zone, region = tg["zone"], tg["region"]
        tmpl = self.ensure_template(shape, region)
        mig = self.ensure_mig(shape, zone, tmpl)
        rr = self.next_name("q")
        body = {"name": rr, "resizeBy": nodes, "requestedRunDuration": {"seconds": str(int(self.req.get("flex_run_s") or FLEX_RUN_S))}}
        op = self.api.call("POST", f"{COMPUTE}/projects/{self.ctx.project}/zones/{zone}/instanceGroupManagers/{mig}/resizeRequests",
                           params={"requestId": str(uuid.uuid4())}, body=body)
        self._op(op)
        self.st["pending"].append({"kind": "flex-group", "name": rr, "mig": mig, "zone": zone, "region": region, "shape": shape["name"],
                                   "nodes": nodes, "gpus": nodes * shape["gpu_equiv"], "created": iso(), "state": "queued"})
        self.note(f"flex-start group request {rr}: {nodes} x {shape['name']} in {zone}, created all at once when all are free")
        self.last["pending"] = now()
        return -nodes

    def ensure_template(self, shape, region):
        name = safe_name(NAME_PREFIX, self.short, "t", shape["name"], region)
        if any(x["name"] == name for x in self.st["templates"]):
            return f"projects/{self.ctx.project}/regions/{region}/instanceTemplates/{name}"
        props = vm_props(self.ctx, self.req, shape, "flex-group", region, self.labels())
        props["reservationAffinity"] = {"consumeReservationType": "NO_RESERVATION"}
        body = {"name": name, "description": f"gcp-gpu-finder run {self.st['run_id']}", "properties": props}
        try:
            op = self.api.call("POST", f"{COMPUTE}/projects/{self.ctx.project}/regions/{region}/instanceTemplates", params={"requestId": str(uuid.uuid4())}, body=body)
            self._op(op)
        except ApiError as e:
            if e.status != 409:
                raise
        self.st["templates"].append({"name": name, "region": region})
        self.save()
        return f"projects/{self.ctx.project}/regions/{region}/instanceTemplates/{name}"

    def ensure_mig(self, shape, zone, tmpl):
        name = safe_name(NAME_PREFIX, self.short, "g", shape["name"].replace("-standard", ""), zone)
        if any(x["name"] == name for x in self.st["migs"]):
            return name
        body = {"name": name, "baseInstanceName": safe_name(NAME_PREFIX, self.short, "n"), "versions": [{"instanceTemplate": tmpl}], "targetSize": 0,
                "instanceLifecyclePolicy": {"defaultActionOnFailure": "DO_NOTHING"}, "description": f"gcp-gpu-finder run {self.st['run_id']}"}
        try:
            op = self.api.call("POST", f"{COMPUTE}/projects/{self.ctx.project}/zones/{zone}/instanceGroupManagers", params={"requestId": str(uuid.uuid4())}, body=body)
            self._op(op)
        except ApiError as e:
            if e.status != 409:
                raise
        self.st["migs"].append({"name": name, "zone": zone, "template": tmpl})
        self.save()
        return name

    def hold_calendar(self, tg, shape, nodes):
        cal = self.req["calendar"]
        recs = calendar_search(self.ctx, shape, tg["region"], nodes, cal["start_after_days"] * 86400, cal["start_within_days"] * 86400,
                               cal["min_days"] * 86400, cal["max_days"] * 86400)
        found = [r for r in recs if r.get("start")]
        if not found:
            why = "; ".join(sorted({f"{r['zone']}: {r.get('status')}" for r in recs if r.get("status")}))[:300]
            raise ApiError(0, f"no calendar-mode window for {nodes} x {shape['name']} in {tg['region']}" + (f" ({why})" if why else ""),
                           {"error": {"status": "NO_CAPACITY"}}, reason="ZONE_RESOURCE_POOL_EXHAUSTED")
        best = found[0]
        msg = f"calendar mode: {nodes} x {shape['name']} available in {best['zone']} from {best['start']} to {best['end']}"
        if not cal.get("auto_submit"):
            self.st.setdefault("calendar_found", []).append(dict(best, shape=shape["name"], nodes=nodes, at=iso()))
            self.note(msg + " (found; not submitted because you did not pre-approve submission)", "good")
            self.ctx.stop.request("calendar window found", False)
            return 0
        name = self.next_name("c")
        body = {"name": name, "autoDeleteAutoCreatedReservations": True, "deploymentType": "DENSE", "planningStatus": "SUBMITTED",
                "reservationMode": "CALENDAR", "reservationName": safe_name(name, "r"), "shareSettings": {"shareType": "LOCAL"},
                "specificReservationRequired": True, "description": f"gcp-gpu-finder run {self.st['run_id']}",
                "specificSkuProperties": {"totalCount": str(nodes), "instanceProperties": {"machineType": shape["base"]}},
                "timeWindow": {"startTime": best["start"], "endTime": best["end"]}}
        op = self.api.call("POST", f"{COMPUTE}/projects/{self.ctx.project}/zones/{best['zone']}/futureReservations", params={"requestId": str(uuid.uuid4())}, body=body)
        self._op(op)
        self.st["pending"].append({"kind": "calendar", "name": name, "zone": best["zone"], "region": tg["region"], "shape": shape["name"], "nodes": nodes,
                                   "gpus": nodes * shape["gpu_equiv"], "created": iso(), "start": best["start"], "end": best["end"], "state": "submitted"})
        self.note(msg + f"; submitted as {name}", "good")
        return -nodes

    # ---------------------------------------------------------- following what is queued and held
    def poll_pending(self):
        self.last["pending"] = now()
        p0 = self.ctx.project
        live = [p for p in self.st["pending"] if p.get("state") in ("queued", "submitted")]
        if live:
            self.doing(f"asking Google about {len(live)} queued request(s)", ", ".join(f"{p['name']} in {p['zone']}" for p in live[:3]))
        for p in self.st["pending"]:
            if p.get("state") not in ("queued", "submitted"):
                continue
            try:
                if p["kind"] == "flex":
                    self._poll_flex(p)
                elif p["kind"] == "flex-group":
                    self._poll_group(p)
                elif p["kind"] == "calendar":
                    self._poll_calendar(p)
            except (ApiError, AuthError) as e:
                c = classify(e, p0)
                self.once(f"poll|{p['name']}", f"cannot read {p['name']}: {c.title}", "warn")
        self.st["pending"] = [p for p in self.st["pending"] if p.get("state") in ("queued", "submitted")] + \
                             [p for p in self.st["pending"] if p.get("state") not in ("queued", "submitted")][-50:]
        self.save()

    def _poll_flex(self, p):
        try:
            inst = self.api.get(f"{COMPUTE}/projects/{self.ctx.project}/zones/{p['zone']}/instances/{p['name']}", fields="status,statusMessage")
        except ApiError as e:
            if e.status != 404:
                raise
            inst = None
        op = self.api.get(p["op"]) if p.get("op") else {}
        err = op_error(op) if op.get("status") == "DONE" else None
        status = (inst or {}).get("status")
        if status == "RUNNING":
            p["state"] = "held"
            shape = self.shape(p["shape"])
            self.st["holds"].append({"kind": "vm", "name": p["name"], "zone": p["zone"], "region": p["region"], "shape": p["shape"], "nodes": 1,
                                     "gpus": p["gpus"], "method": "flex", "created": iso(), "state": "held",
                                     "usd_h": price_of(self.ctx, shape, p["region"], "flex"),
                                     "expires": iso(now() + int(self.req.get("flex_run_s") or FLEX_RUN_S))})
            self.st["totals"]["ok"] += 1
            ts = self.st["targets"].get(f"flex|{p['shape']}|{p['zone']}")
            if ts:
                ts["ok"] += 1
                ts["last"] = "obtained"
                ts["last_ok_at"] = now()
            self.note(f"HELD: flex-start VM {p['name']} is running in {p['zone']}", "good")
            return
        if err or inst is None or status in ("TERMINATED", "STOPPED"):
            p["state"] = "failed"
            c = classify(err, self.ctx.project) if err else Cause("stockout", "the wait window ended without capacity")
            if inst is not None:
                self._delete_instance(p["zone"], p["name"])
            key = f"flex|{p['shape']}|{p['zone']}"
            ts = self.st["targets"].get(key)
            if ts:
                ts["last"] = c.kind
                ts["next_at"] = now() + jitter(TARGET_INTERVAL_S)
            self.note(f"flex-start request {p['name']} in {p['zone']} ended without capacity ({c.title}); it is re-queued on the next pass")

    def _poll_group(self, p):
        rr = self.api.get(f"{COMPUTE}/projects/{self.ctx.project}/zones/{p['zone']}/instanceGroupManagers/{p['mig']}/resizeRequests/{p['name']}")
        state = rr.get("state")
        p["rr_state"] = state
        if state == "SUCCEEDED":
            p["state"] = "held"
            self.st["totals"]["ok"] += 1
            shape = self.shape(p["shape"])
            price = price_of(self.ctx, shape, p["region"], "flex-group")
            self.st["holds"].append({"kind": "mig", "name": p["mig"], "zone": p["zone"], "region": p["region"], "shape": p["shape"], "nodes": p["nodes"],
                                     "gpus": p["gpus"], "method": "flex-group", "created": iso(), "state": "held",
                                     "usd_h": None if price is None else round(price * p["nodes"], 4), "request": p["name"]})
            self.note(f"HELD: flex-start group {p['mig']} created {p['nodes']} x {p['shape']} in {p['zone']}", "good")
        elif state in ("FAILED", "CANCELLED"):
            p["state"] = state.lower()
            errs = ((rr.get("status") or {}).get("error") or {}).get("errors") or []
            self.note(f"flex-start group request {p['name']} {state.lower()}: " + "; ".join(e.get("message", "") for e in errs)[:300], "warn")

    def _poll_calendar(self, p):
        fr = self.api.get(f"{COMPUTE}/projects/{self.ctx.project}/zones/{p['zone']}/futureReservations/{p['name']}")
        ps = (fr.get("status") or {}).get("procurementStatus")
        if ps != p.get("procurement"):
            p["procurement"] = ps
            self.note(f"calendar request {p['name']}: {ps}")
        if ps in ("APPROVED", "PROVISIONING", "FULFILLED", "COMMITTED", "PROCURING"):
            p["state"] = "held"
            self.st["holds"].append({"kind": "calendar", "name": p["name"], "zone": p["zone"], "region": p["region"], "shape": p["shape"],
                                     "nodes": p["nodes"], "gpus": p["gpus"], "method": "calendar", "created": iso(), "state": "held",
                                     "usd_h": None, "start": p.get("start"), "expires": p.get("end")})
            self.note(f"HELD: calendar reservation {p['name']} approved for {p['nodes']} x {p['shape']} from {p.get('start')}", "good")
        elif ps in ("DECLINED", "FAILED", "CANCELLED"):
            p["state"] = ps.lower()

    def check_holds(self):
        """Notice capacity that disappeared: preempted Spot VMs, flex-start VMs at their end, reservations deleted or expired."""
        self.last["holds"] = now()
        self.doing(f"checking that the {len(self.held())} held resource(s) still exist",
                   "Compute Engine API aggregatedList, read only, for this run's labelled VMs and named reservations, groups and requests")
        try:
            res = find_run_resources(self.ctx, self.st["run_id"])
        except (ApiError, AuthError) as e:
            self.once("holds", f"cannot check held capacity: {classify(e, self.ctx.project).title}", "warn")
            return
        vms = {i["name"]: i for i in res["instances"]}
        resv = {r["name"] for r in res["reservations"]}
        migs = {m["name"]: m for m in res["migs"]}
        for h in self.held():
            gone = None
            if h["kind"] == "vm":
                i = vms.get(h["name"])
                if not i:
                    gone = "deleted"
                elif i.get("status") in ("TERMINATED", "STOPPED", "SUSPENDED"):
                    gone = f"{i.get('status').lower()} (preempted or ended)"
            elif h["kind"] == "reservation" and h["name"] not in resv:
                gone = "deleted or expired"
            elif h["kind"] == "mig" and h["name"] not in migs:
                gone = "deleted"
            if gone:
                h["state"] = "lost"
                h["lost"] = iso()
                h["lost_why"] = gone
                self.note(f"lost: {h['kind']} {h['name']} in {h['zone']} is {gone}; {'hunting again' if self.req.get('maintain') else 'counted out'}", "warn")
        self.save()

    def reconcile_inflight(self):
        """After a crash or a forced exit, find what an unfinished request actually created."""
        if not self.st.get("inflight"):
            return
        names = [x["name"] for x in self.st["inflight"]]
        self.doing(f"an earlier session of this run stopped with {len(names)} request(s) unanswered; looking up what they created",
                   ", ".join(names[:3]) + (" and more" if len(names) > 3 else ""))
        try:
            res = find_run_resources(self.ctx, self.st["run_id"])
        except (ApiError, AuthError) as e:
            self.note(f"cannot look up what the unanswered request(s) {', '.join(names[:3])} created: {classify(e, self.ctx.project).title}; "
                      f"`status {self.st['run_id']}` lists everything this run holds", "warn")
            return
        known = {h["name"] for h in self.st["holds"]}
        for x in list(self.st["inflight"]):
            if x["kind"] == "reservation":
                for r in res["reservations"]:
                    if r["name"] == x["name"] and r["name"] not in known:
                        sr = r.get("specificReservation") or {}
                        mt = (sr.get("instanceProperties") or {}).get("machineType")
                        shape = self.ctx.catalog["shapes"].get(mt) or {"gpu_equiv": 1}
                        n = int(sr.get("count") or 0)
                        reg = region_of(tail(r.get("zone")))
                        p = price_of(self.ctx, shape, reg, "reservation") if shape.get("name") else None
                        self.st["holds"].append({"kind": "reservation", "name": r["name"], "zone": tail(r.get("zone")), "region": reg,
                                                 "shape": mt, "nodes": n, "gpus": n * shape["gpu_equiv"], "method": "reservation", "created": iso(), "state": "held",
                                                 "usd_h": None if p is None else round(p * n, 4), "recovered": True})
                        self.note(f"recovered reservation {r['name']} created by an interrupted request")
            if x["kind"] == "vms":
                for i in res["instances"]:
                    if (i.get("labels") or {}).get("gpu-finder-batch") == x["name"] and i["name"] not in known:
                        mt = tail(i.get("machineType"))
                        shape = self.ctx.catalog["shapes"].get(mt) or {"gpu_equiv": 1}
                        p = price_of(self.ctx, shape, region_of(i["_zone"]), self.method) if shape.get("name") else None
                        self.st["holds"].append({"kind": "vm", "name": i["name"], "zone": i["_zone"], "region": region_of(i["_zone"]), "shape": mt, "nodes": 1,
                                                 "gpus": shape["gpu_equiv"], "method": self.method, "created": iso(), "state": "held", "usd_h": p, "recovered": True})
                        self.note(f"recovered VM {i['name']} created by an interrupted request")
            self._untrack(x["name"])
        self.save()

    def _delete_instance(self, zone, name):
        try:
            op = self.api.call("DELETE", f"{COMPUTE}/projects/{self.ctx.project}/zones/{zone}/instances/{name}", params={"requestId": str(uuid.uuid4())})
            self._op(op)
        except ApiError as e:
            if e.status != 404:
                self.note(f"could not delete {name}: {classify(e, self.ctx.project).title}", "warn")

    # ---------------------------------------------------------- stopping
    def cancel_queued(self):
        """Cancel requests still waiting for capacity, so nothing is created after the run ends."""
        n = 0
        for p in self.st["pending"]:
            if p.get("state") not in ("queued",):
                continue
            try:
                if p["kind"] == "flex":
                    self._delete_instance(p["zone"], p["name"])
                elif p["kind"] == "flex-group":
                    url = f"{COMPUTE}/projects/{self.ctx.project}/zones/{p['zone']}/instanceGroupManagers/{p['mig']}/resizeRequests/{p['name']}"
                    try:
                        self._op(self.api.call("POST", url + "/cancel", params={"requestId": str(uuid.uuid4())}))
                    except ApiError as e:
                        if e.status not in (400, 404):
                            raise
                p["state"] = "cancelled"
                n += 1
            except (ApiError, AuthError, OpStalled) as e:
                self.note(f"could not cancel {p['name']}: {classify(e, self.ctx.project).title}", "warn")
        if n:
            self.note(f"cancelled {n} queued request(s)")
        self.save()

    def finish(self, outcome):
        st = self.st
        if outcome != "forced":
            try:
                if self.st["pending"] and not self.dry:
                    if outcome == "done" or self.ctx.stop.stopping:
                        self.cancel_queued()
                cleanup_empty_groups(self.ctx, st)
            except (ApiError, AuthError, OpStalled, Interrupted, KeyboardInterrupt) as e:
                self.note(f"cleanup incomplete: {e}", "warn")
        st["status"] = {"done": "done", "dry-run": "dry run", "blocked": "blocked"}.get(outcome, "stopped")
        reason = self.ctx.stop.reason or outcome
        if outcome == "forced":
            reason = "forced exit (second Ctrl-C); unfinished requests are reconciled on resume"
        st["stop"] = {"reason": reason, "at": iso()}
        st["elapsed_s"] = int(now() - self.started)
        self.save()
        lines = summary_lines(self.ctx, st, self.req)
        text = "\n".join(ANSI_RE.sub("", ln) for ln in lines)
        atomic_write(os.path.join(run_dir(st["run_id"]), "summary.txt"), text + "\n", 0o644)
        self.tick_ui(force=True)
        for ln in lines:
            self.t.line(ln)
        if outcome != "forced" and self.ctx.stop.stopping and self.ctx.stop.ask and self.held() and self.ctx.ask.interactive and not self.t.dead:
            try:
                keep = self.ctx.ask.choose("Keep the capacity this run obtained?", [
                    {"key": "keep", "label": "keep it (it keeps billing; release later with the release command)"},
                    {"key": "release", "label": "release it now"}], default="keep")
                if keep == "release":
                    release_run(self.ctx, st, Saver(os.path.join(run_dir(st["run_id"]), "state.json"), st), assume_yes=True)
            except (KeyboardInterrupt, SystemExit):
                self.t.line("kept; release later with: release " + st["run_id"])
        return {"done": 0, "dry-run": 0, "blocked": 3}.get(outcome, 2)

    # ---------------------------------------------------------- the dashboard
    def now_panel(self):
        """What the run is doing this second, the Google call and operation in flight, what comes next, and how far the sweep is."""
        t, a, st = self.t, self.activity, self.st["targets"]
        pad = "        "
        eta = f"  in {human_dur(max(0, a['until'] - now()))}" if a.get("until") else f"  for {human_dur(now() - a['since'])}"
        out = [t.s("NOW     ", "c", "b") + t.s(a["what"], "b") + t.s(eta, "c")]
        if a.get("detail"):
            out.append(pad + t.s(a["detail"], "gr"))
        op, cur = self.api.op, self.api.current
        if op:
            out.append(pad + t.s("Google operation  ", "gr") + f"{op.get('type') or ''} {op.get('target') or ''}: {op.get('status')}"
                       + (f", {op['progress']}%" if op.get("progress") is not None else "") + t.s(f"  for {human_dur(now() - op['since'])}", "gr"))
        if cur:
            u = urllib.parse.urlparse(cur["url"])
            path = re.sub(r"^/compute/(v1|beta)/projects/[^/]+/", "", u.path)
            out.append(pad + t.s("Google call       ", "gr") + f"{cur['m']} {u.netloc.split('.')[0]} {path}"
                       + t.s(f"  {cur['phase']}, {human_dur(now() - cur['t0'])}", "gr"))
        nxt = self.upcoming(4)
        if nxt:
            out.append(t.s("NEXT    ", "c", "b") + "   ".join(f"{tg['shape']} @ {tg['zone'] or tg['region']} "
                                                          + t.s("now" if due <= now() else "in " + human_dur(due - now()), "gr") for due, tg, _ in nxt))
        tried = sum(1 for x in self.targets if (st[x["key"]]["last_at"] or 0) >= self.last["sweep"])
        qb = sum(1 for x in self.targets if st[x["key"]]["quota_bound"] and not st[x["key"]]["parked"])
        pk = sum(1 for x in self.targets if st[x["key"]]["parked"])
        out.append(t.s("SEARCH  ", "c", "b") + f"sweep {self.sweeps}: {tried} of {len(self.targets)} options tried in the last "
                   f"{human_dur(now() - self.last['sweep'])}   "
                   + f"{len(self.targets) - qb - pk} active, " + t.s(f"{qb} quota-bound", "y" if qb else "gr") + ", "
                   + t.s(f"{pk} parked", "r" if pk else "gr"))
        out.append(pad + t.s("machine types ", "gr") + " > ".join(self.req["shapes"]) + t.s("   regions ", "gr") + " > ".join(self.regions[:8])
                   + (" ..." if len(self.regions) > 8 else ""))
        return out

    def render(self):
        t, req, st = self.t, self.req, self.st
        w = t.width()
        acc = self.ctx.catalog["accels"][req["accel"]]["label"]
        got, pend, goal = self.obtained(), self.pending_gpus(), req["goal"]
        lines = [t.s(f"GCP GPU Finder {VERSION}", "b") + f"  project {self.ctx.project}  account {self.ctx.tokens.account}  run {st['run_id']}",
                 f"elapsed {human_dur(now() - self.started)}  loop {st['totals']['loops']}  next sweep in {human_dur(SWEEP_S - (now() - self.last['sweep']))}"
                 + (t.s("  STOPPING: " + str(self.ctx.stop.reason), "y", "b") if self.ctx.stop.stopping else ""),
                 f"goal {t.s(fnum(goal), 'b')} x {acc} GPUs via {METHOD_LABEL[self.method]} ({req['layout']}"
                 + (f", {req['cluster_nodes']} VM instances per cluster" if req['layout'] == 'cluster' else "") + f")  regions {', '.join(self.regions[:6])}"
                 + (" ..." if len(self.regions) > 6 else ""), ""]
        lines += self.now_panel()
        lines.append("")
        bw = max(20, min(60, w - 50))
        lines.append(f"{t.bar(got / goal if goal else 0, bw)}  {t.s(fnum(got), 'g', 'b')} / {fnum(goal)} GPUs held"
                     + (f"  {fnum(pend)} pending" if pend else "") + f"  {len(self.held())} resource(s)  cost {money(self.cost())}/h")
        tt = st["totals"]
        lines.append(f"attempts {tt['attempts']}  obtained {tt['ok']}  no capacity {tt['stockout']}  quota {tt['quota']}  other {tt['other']}"
                     + (f"  quota checks {tt['verify']}" if tt["verify"] else ""))
        lines.append("")
        qrows = []
        seen = set()
        for tg in self.targets:
            k = (tg["shape"], tg["region"])
            if k in seen or self.method == "calendar":
                continue
            seen.add(k)
            h = self.head_of(self.shape(tg["shape"]), tg["region"])
            b = h.get("binding") or {}
            more = h.get("more")
            qrows.append([tg["region"], tg["shape"], "unknown" if more is None else str(more), b.get("label") or "-",
                          f"{b.get('used')}/{b.get('limit')}" if b else "-"])
            if len(qrows) >= 6:
                break
        if qrows:
            lines.append(t.s("QUOTA", "b") + t.s("  (a limit Google sets on the project; separate from free hardware)", "gr"))
            lines += table(["region", "machine type", "VMs allowed", "tightest quota", "used/limit"], qrows, w, right=(2,))
            lines.append("")
        lines.append(t.s("AVAILABILITY", "b") + t.s("  (Google's answer to each attempt; no capacity means the hardware is taken right now)", "gr"))
        arows = []
        for tg in self.targets:
            ts = st["targets"][tg["key"]]
            raw = ts["last"] or "-"
            last = {"stockout": "no capacity", "reservation_limit": "no reservation capacity", "quota": "quota limit"}.get(raw, raw.replace("_", " "))
            style = {"obtained": "g", "queued": "c", "stockout": "y", "reservation_limit": "y", "quota": "y"}.get(raw, "r" if ts["parked"] else None)
            nxt = "parked" if ts["parked"] else ("quota" if ts["quota_bound"] else ("now" if ts["next_at"] <= now() else "in " + human_dur(ts["next_at"] - now())))
            arows.append([tg["zone"] or tg["region"], tg["shape"], t.s(last, style) if style else last, ts["attempts"], ts["ok"],
                          ago(ts["last_ok_at"]) if ts["last_ok_at"] else "-", nxt])
        room = max(4, t.height() - len(lines) - 18)
        lines += table(["zone", "machine type", "last result", "tries", "ok", "last success", "next"], arows[:room], w, right=(3, 4))
        if len(arows) > room:
            lines.append(t.s(f"... {len(arows) - room} more targets", "gr"))
        parked = {}
        for tg in self.targets:
            p = st["targets"][tg["key"]]["parked"]
            if p:
                parked.setdefault((p["why"], p["fix"]), 0)
                parked[(p["why"], p["fix"])] += 1
        if parked:
            lines.append("")
            lines.append(t.s("PARKED", "r", "b") + t.s("  (permanent errors; press r after fixing)", "gr"))
            for (why, fix), n in list(parked.items())[:4]:
                lines.append(f"{n} target(s): {why}. Fix: {fix}")
        if self.held() or self.pending_gpus():
            lines.append("")
            lines.append(t.s("HELD", "g", "b"))
            hrows = [[h["kind"], h["name"], h["zone"], h["shape"], fnum(h["gpus"]), money(h.get("usd_h")), ago(parse_iso(h["created"])), h.get("expires") or "-"]
                     for h in self.held()[-6:]]
            hrows += [[p["kind"] + " (queued)", p["name"], p["zone"], p["shape"], fnum(p["gpus"]), "-", ago(parse_iso(p["created"])), p.get("expires") or "-"]
                      for p in st["pending"] if p.get("state") in ("queued", "submitted")][:4]
            lines += table(["kind", "name", "zone", "shape", "GPUs", "$/h", "since", "ends"], hrows, w)
        if st.get("quota_requests"):
            lines.append("")
            lines.append(t.s("QUOTA REQUESTS", "b"))
            for f in st["quota_requests"][-4:]:
                lines.append(f"{f['qid']} {f['dims']} to {f['preferred']}: {f.get('state')} (granted {f.get('granted')})")
        snap = self.ctx.gov.snapshot()
        busy = sorted(snap, key=lambda x: -x["used"])[:3]
        lines.append("")
        lines.append(t.s("API this minute: ", "gr") + "  ".join(f"{b['group']}{('@' + b['region']) if b['region'] else ''} {b['used']}/{b['budget']}" for b in busy)
                     + t.s(f"  rate-limit answers {sum(b['hits'] for b in snap)}  ({self.ctx.gov.source})", "gr"))
        lines.append(t.s("EVENTS", "b"))
        for ts_, level, msg in self.ev.ring[-6:]:
            style = {"warn": "y", "error": "r", "good": "g"}.get(level)
            lines.append(t.s(time.strftime("%H:%M:%S", time.localtime(ts_)), "gr") + " " + (t.s(msg, style) if style else msg))
        lines.append(t.s("q stop   r re-check parked targets   Ctrl-C stop", "gr"))
        return lines


class KeyReader:
    """Single key presses while the dashboard shows; never blocks, restores the terminal on exit."""

    def __init__(self, term):
        self.t = term
        self.old = None
        self.on = False

    def start(self):
        if self.t.plain or not self.t.tty:
            return
        if os.name == "nt":
            self.on = True
            return
        try:
            import termios
            import tty
            fd = sys.stdin.fileno()
            self.old = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            self.on = True
        except Exception:
            self.on = False

    def poll(self):
        if not self.on:
            return None
        try:
            if os.name == "nt":
                import msvcrt
                return msvcrt.getwch() if msvcrt.kbhit() else None
            import select
            r, _, _ = select.select([sys.stdin], [], [], 0)
            return sys.stdin.read(1) if r else None
        except Exception:
            return None

    def stop(self):
        if self.old is not None:
            try:
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old)
            except Exception:
                pass
            self.old = None
        self.on = False


# ------------------------------------------------------------------ finding and releasing what a run created
def find_run_resources(ctx, run_id):
    """Everything a run created: VMs by label; reservations, groups, templates and calendar requests by name prefix."""
    api, label = ctx.api, run_label(run_id)
    prefix = safe_name(NAME_PREFIX, run_short(run_id))
    ctx.rep.say(f"looking up this run in Google Cloud (Compute Engine API, aggregatedList, read only): VMs labelled gpu-finder-run={label}; "
                f"reservations, managed instance groups, instance templates and calendar-mode requests named {prefix}-*")
    out = {"instances": [], "reservations": [], "migs": [], "templates": [], "futures": []}
    for zone, items in api.aggregated("instances", params={"filter": f'labels.gpu-finder-run = "{label}"',
                                                            "fields": "items/*/instances(name,status,machineType,labels,zone),nextPageToken"}).items():
        out["instances"] += [dict(i, _zone=zone) for i in items]
    for kind, key, fields in (("reservations", "reservations", "name,zone,status,specificReservation"), ("instanceGroupManagers", "migs", "name,zone,targetSize"),
                              ("instanceTemplates", "templates", "name,region,selfLink"), ("futureReservations", "futures", "name,zone,status")):
        try:
            got = api.aggregated(kind, key="futureReservations" if kind == "futureReservations" else kind,
                                 params={"filter": f'name eq "{prefix}-.*"', "fields": f"items/*/{kind}({fields}),nextPageToken"})
        except ApiError as e:
            if e.status in (400, 404):
                ctx.ev.note(f"{kind} could not be listed in this project (HTTP {e.status}: {str(e)[:160]}); this run created none of them", "warn")
                continue
            raise
        for scope, items in got.items():
            out[key] += [dict(i, _scope=scope) for i in items]
    return out


def cleanup_empty_groups(ctx, st):
    """Delete this run's empty managed groups and unused templates, so a stopped run leaves nothing idle behind."""
    keep = {h["name"] for h in st["holds"] if h.get("kind") == "mig" and h.get("state") == "held"}
    left = []
    for m in st.get("migs") or []:
        if m["name"] in keep:
            left.append(m)
            continue
        try:
            op = ctx.api.call("DELETE", f"{COMPUTE}/projects/{ctx.project}/zones/{m['zone']}/instanceGroupManagers/{m['name']}", params={"requestId": str(uuid.uuid4())})
            ctx.api.wait_op(op)
        except ApiError as e:
            if e.status != 404:
                left.append(m)
                ctx.ev.note(f"could not delete group {m['name']}: {classify(e, ctx.project).title}", "warn")
    st["migs"] = left
    used = {m["template"].rsplit("/", 1)[-1] for m in left}
    tl = []
    for tp in st.get("templates") or []:
        if tp["name"] in used:
            tl.append(tp)
            continue
        try:
            op = ctx.api.call("DELETE", f"{COMPUTE}/projects/{ctx.project}/regions/{tp['region']}/instanceTemplates/{tp['name']}", params={"requestId": str(uuid.uuid4())})
            ctx.api.wait_op(op)
        except ApiError as e:
            if e.status != 404:
                tl.append(tp)
    st["templates"] = tl


def release_run(ctx, st, save, assume_yes=False):
    """Delete what one run created, after showing it; nothing without this run's label or name prefix is touched."""
    t = ctx.t
    res = find_run_resources(ctx, st["run_id"])
    rows = [["VM", i["name"], i["_zone"], i.get("status")] for i in res["instances"]]
    rows += [["reservation", r["name"], tail(r.get("zone")), r.get("status")] for r in res["reservations"]]
    rows += [["group", m["name"], m["_scope"], f"size {m.get('targetSize')}"] for m in res["migs"]]
    rows += [["template", x["name"], x["_scope"], ""] for x in res["templates"]]
    rows += [["calendar request", f["name"], tail(f.get("zone")), ((f.get("status") or {}).get("procurementStatus"))] for f in res["futures"]]
    if not rows:
        t.line("this run holds nothing in Google Cloud")
        for h in st["holds"]:
            if h.get("state") == "held":
                h["state"] = "gone"
        save()
        return 0
    for ln in table(["kind", "name", "where", "status"], rows, t.width()):
        t.line(ln)
    if not assume_yes and not ctx.ask.typed(f"Delete these {len(rows)} resource(s)? Billing stops when they are gone.", "delete"):
        t.line("nothing deleted")
        return 1
    fails = 0
    ops = []

    def go(method, url):
        nonlocal fails
        try:
            ops.append(ctx.api.call(method, url, params={"requestId": str(uuid.uuid4())}))
        except ApiError as e:
            if e.status != 404:
                fails += 1
                t.line(t.s(f"  {url.rsplit('/', 2)[-2:]}: {classify(e, ctx.project).title}", "r"))

    p = ctx.project
    for m in res["migs"]:
        go("DELETE", f"{COMPUTE}/projects/{p}/zones/{tail(m.get('zone') or m['_scope'])}/instanceGroupManagers/{m['name']}")
    for i in res["instances"]:
        go("DELETE", f"{COMPUTE}/projects/{p}/zones/{i['_zone']}/instances/{i['name']}")
    for r in res["reservations"]:
        go("DELETE", f"{COMPUTE}/projects/{p}/zones/{tail(r.get('zone'))}/reservations/{r['name']}")
    for f in res["futures"]:
        go("POST", f"{COMPUTE}/projects/{p}/zones/{tail(f.get('zone'))}/futureReservations/{f['name']}/cancel")
    for op in ops:
        try:
            e = op_error(ctx.api.wait_op(op))
            if e:
                fails += 1
                t.line(t.s(f"  {tail(op.get('targetLink'))}: {classify(e, ctx.project).title}", "r"))
        except (ApiError, OpStalled) as e:
            fails += 1
            t.line(t.s(f"  {tail(op.get('targetLink'))}: {e}", "r"))
    for x in res["templates"]:
        try:
            ctx.api.wait_op(ctx.api.call("DELETE", f"{COMPUTE}/projects/{p}/regions/{tail(x.get('region') or x['_scope'])}/instanceTemplates/{x['name']}",
                                         params={"requestId": str(uuid.uuid4())}))
        except ApiError as e:
            if e.status != 404:
                fails += 1
    for h in st["holds"]:
        if h.get("state") == "held":
            h["state"] = "released"
            h["released"] = iso()
    for pnd in st["pending"]:
        if pnd.get("state") in ("queued", "submitted"):
            pnd["state"] = "cancelled"
    st["migs"], st["templates"] = [], []
    st.setdefault("releases", []).append({"at": iso(), "resources": len(rows), "failures": fails})
    save()
    t.line(t.s(f"released {len(rows) - fails} of {len(rows)} resource(s)", "g" if not fails else "y"))
    return 0 if not fails else 1


def summary_lines(ctx, st, req):
    t = ctx.t
    held = [h for h in st["holds"] if h.get("state") == "held"]
    got = sum(h["gpus"] for h in held)
    tt = st["totals"]
    acc = (ctx.catalog or {}).get("accels", {}).get(req.get("accel"), {}).get("label", req.get("accel"))
    lines = ["", t.s(f"Run {st['run_id']} {st['status']}", "b") + f" ({(st.get('stop') or {}).get('reason', '')})",
             f"held {fnum(got)} of {fnum(req['goal'])} {acc} GPUs in {len(held)} resource(s); attempts {tt['attempts']} "
             f"(obtained {tt['ok']}, no capacity {tt['stockout']}, quota {tt['quota']}, other {tt['other']}); elapsed {human_dur(st.get('elapsed_s'))}"]
    for h in held:
        lines.append(f"  {h['kind']:12s} {h['name']:28s} {h['zone']:22s} {h['shape']:18s} {fnum(h['gpus']):>5s} GPUs  {money(h.get('usd_h'))}/h")
    lost = [h for h in st["holds"] if h.get("state") == "lost"]
    if lost:
        lines.append(f"  lost along the way: {len(lost)} ({', '.join(sorted({h.get('lost_why', '') for h in lost}))})")
    for f in st.get("quota_requests") or []:
        lines.append(f"  quota request {f['qid']} {f['dims']} to {f['preferred']}: {f.get('state')} (granted {f.get('granted')}); "
                     f"{CONSOLE}/iam-admin/quotas?project={st['project']}")
    for c in st.get("calendar_found") or []:
        lines.append(f"  calendar window found: {c['nodes']} x {c['shape']} in {c['zone']} from {c['start']} to {c['end']} (not submitted)")
    if held:
        lines.append(f"  it keeps billing until released: python3 {os.path.basename(sys.argv[0])} release {st['run_id']} --project {st['project']}")
    if SESSION["ephemeral"] or st.get("stateless"):
        lines.append(f"  nothing about this run is saved on this computer; everything it created in Google Cloud carries the label "
                     f"gpu-finder-run={run_label(st['run_id'])} or a name starting {safe_name(NAME_PREFIX, run_short(st['run_id']))}-, "
                     f"which is how `release` and `status` find it")
    else:
        lines.append(f"  state and logs: {run_dir(st['run_id'])}")
    return lines


# ------------------------------------------------------------------ screens
BILLING_NOTE = {
    "reservation": "A reservation bills like running VMs from the moment it exists, used or not, until it is deleted.",
    "vms": "VMs bill per second while they exist (compute while running, disks always).",
    "spot": "Spot VMs bill at Spot prices while running; Google may reclaim them at any time.",
    "flex": "Flex-start VMs bill from the moment they start, at discounted prices, and are deleted at the end of their run time.",
    "flex-group": "Flex-start group VMs bill from the moment they start, all at once, and are deleted at the end of their run time.",
    "calendar": "An approved calendar-mode reservation bills for the whole reserved period, used or not."}


def rule(t):
    """The line under a section heading, so each section reads as its own block."""
    return t.s(("\u2500" if t.utf else "-") * max(0, min(t.width() - 2, SECTION_RULE_MAX)), "gr")


def heading(ctx, text, sub=None):
    t = ctx.t
    t.line("")
    t.line(t.s(text, "h") + (t.s("  " + sub, "gr") if sub else ""))
    t.line(rule(t))


def link(t, title, url):
    """One Google Cloud documentation link, shown as a title and its full address."""
    return f"{title}: " + t.s(url, "c", "u")


def show_terms(ctx, unit):
    """The words Google Cloud uses, so GPUs, VM instances and copies are never confused."""
    t = ctx.t
    t.line(t.s(" How Google Cloud counts it", "c", "b"))
    t.line("   VM instance   one Compute Engine VM of one machine type, for example g4-standard-96; the machine type fixes how many GPUs are attached")
    if unit == "copy":
        t.line("   model copy    one running server of the model on the GPUs it needs, all inside one VM (tensor parallel never spans VMs);")
        t.line("                 Agent Platform (Vertex AI) calls each VM that serves a deployed model a replica")
    else:
        t.line(f"   {unit:<13s} one {unit} of this product, sized as Google's page for it states")
    t.line("   GPUs in total VM instances x GPUs per VM; quota, the goal and every count in this tool are in GPUs")
    t.line("")


def show_workload(ctx, title, sub, rows, notes, unit, docs, recommend=None, explain=None):
    """Only the machine types that fit, with what each needs to reach the target, cheapest in GPUs first."""
    t = ctx.t
    heading(ctx, title, sub)
    show_terms(ctx, unit)
    out = []
    for r in rows:
        p = min((x for x in (price_of(ctx, ctx.catalog["shapes"][r["shape"]], reg, "vms") for reg in ctx.catalog["shapes"][r["shape"]]["regions"])
                 if x is not None), default=None)
        mark = t.s(" recommended", "g", "b") if recommend is r else (t.s(" tested by Google", "c") if r.get("tested") else "")
        out.append([r["label"], r["shape"] + mark, r["gpus_vm"], r["per_copy"], r["copies_vm"], "-" if r.get("capacity") is None else r["capacity"],
                    "-" if r.get("vms") is None else r["vms"], "-" if r.get("gpus_total") is None else t.s(r["gpus_total"], "b"),
                    money(None if p is None or not r.get("vms") else p * r["vms"])])
    hdr = ["GPU", "machine type", "GPUs per VM", f"GPUs per {unit}", f"{plural_of(unit)} per VM", "requests per copy", "VM instances", "GPUs in total",
           "on-demand $/h from"]
    if unit != "copy":
        hdr.pop(5)
        out = [r[:5] + r[6:] for r in out]
    for ln in table(hdr, out, t.width(), right=tuple(range(2, len(hdr)))):
        t.line(ln)
    t.line(t.s(f"  only machine types that hold a whole {unit} are listed; $/h is the lowest on-demand price among regions offering it", "gr"))
    for n in notes:
        t.line(t.s("  note: " + n, "y"))
    if explain:
        t.line("")
        t.line(t.s("  " + explain, "c"))
    t.line("")
    for k in docs:
        title_, url = DOCS[k]
        t.line("  " + link(t, title_, url))


def choose_workload(ctx, req, args):
    """What the GPUs will run: an NVIDIA model in Model Garden, an NVIDIA product on Google Cloud, or the customer's own choice."""
    t, ask = ctx.t, ctx.ask
    wl = dict(req.get("workload") or {})
    prices(ctx)
    mg, mg_err, mg_read = [], None, None
    with ctx.rep.step("Reading NVIDIA models in Vertex AI Model Garden", f"publisher {MODEL_GARDEN_PUBLISHER}, with every machine type Google "
                                                                      f"tested each model on") as s:
        try:
            mg, mg_read = model_garden(ctx, s, refresh=args.refresh)
            s.result(f"{len(mg)} model versions: {', '.join(sorted({e['model'] for e in mg}))}")
        except (ApiError, AuthError) as e:
            c = classify(e, ctx.project)
            mg_err = c.title + ("; `setup` can turn it on" if c.kind == "api_disabled" else "")
            s.result(f"not readable: {mg_err}. The Model Garden choice is unavailable; fix: {c.fix}", "y")
    mp, mp_err = [], None
    with ctx.rep.step("Reading NVIDIA's Google Cloud Marketplace VM images", f"image project {MARKETPLACE_IMAGE_PROJECT}, current images only "
                                                                          f"(published in the last {IMAGE_LOOKBACK_DAYS} days)") as s:
        try:
            mp, _ = marketplace_products(ctx, s, refresh=args.refresh)
            s.result(f"{len(mp)} current product(s): {', '.join(p['name'] for p in mp) or 'none'}")
        except (ApiError, AuthError) as e:
            mp_err = classify(e, ctx.project).title
            s.result(f"not readable: {mp_err}", "y")
    ctx.rep.say(t.s("Omniverse, Isaac Sim, Kit App Streaming, BioNeMo and NIM come from Google's pages about them, built into this file "
                    "(no Google API lists Marketplace products); each shows its page", "gr"))
    fams = sorted({e["model"] for e in mg})
    prod_names = [s["name"].split(" (")[0] for s in NVIDIA_SOLUTIONS] + [p["name"] for p in mp]
    kinds = [{"key": "model", "label": "An NVIDIA model in Vertex AI Model Garden", "disabled": mg_err if not mg else None,
              "note": f"{len(mg)} versions of {', '.join(fams)}, with the machine types Google tested; read {mg_read}" if mg else ""},
             {"key": "product", "label": "An NVIDIA product on Google Cloud",
              "note": f"{', '.join(prod_names[:6])}{' ...' if len(prod_names) > 6 else ''}" + (f" (Marketplace images unreadable: {mp_err})" if mp_err else "")},
             {"key": "none", "label": "Something else: I will choose the GPUs myself"}]
    kind = ask.choose("What will these GPUs run?", kinds, default=args.workload or wl.get("kind") or ("model" if mg else "none"), flag="--workload",
                      help_text="NVIDIA models come from Model Garden; NVIDIA products from Google Cloud Marketplace and Google's NVIDIA guides.",
                      alt={"skip": ("none", "no workload sizing: every GPU this project can use is offered"),
                           "none": ("none", "no workload sizing: every GPU this project can use is offered"), "all": (None, "one workload per run")})
    if kind == "none":
        req["workload"] = {"kind": "none"}
        return None
    if kind == "model":
        return size_model(ctx, req, args, mg, mg_read, wl)
    return size_product(ctx, req, args, mp, wl)


def pick_by_fragment(items, frag, key="key", name="name"):
    if not frag:
        return None
    f = frag.lower()
    hits = [i for i in items if f == i[key].lower()] or [i for i in items if f in i[name].lower() or f in i[key].lower()]
    return hits[0][key] if hits else None


def size_model(ctx, req, args, mg, mg_read, wl):
    """Size a Model Garden model: where Google tested it, what fits at the customer's context, and how many copies the peak needs."""
    t, ask, cat = ctx.t, ctx.ask, ctx.catalog

    def tested(e):
        seen = []
        for c in e["configs"]:
            lab = (cat["accels"].get(c["accel"]) or {}).get("label") or c["accel"]
            s = f"{c['machine']} ({c['gpus']} x {lab})"
            if s not in seen:
                seen.append(s)
        return ", ".join(seen)

    opts = [{"key": e["key"], "label": e["name"], "note": f"{e['model']}; tested on {tested(e)}"} for e in mg]
    dflt = pick_by_fragment(mg, args.model) or (wl.get("key") if wl.get("kind") == "model" and any(e["key"] == wl.get("key") for e in mg) else None) \
        or mg[0]["key"]
    key = ask.choose(f"NVIDIA models in Model Garden (Agent Platform API, read {mg_read})", opts, default=dflt, flag="--model",
                     alt={"all": (None, "one model per run; run the finder again for another")})
    e = next(x for x in mg if x["key"] == key)
    info, peak, units = None, None, None
    tested_len = max((c.get("max_len") or 0 for c in e["configs"]), default=0)
    if e["kind"] == "llm":
        with ctx.rep.step(f"Reading the published architecture of {e['source_id'] or e['name']}",
                          "weight size and attention layout, to estimate how many requests one copy serves; Model Garden deploys this "
                          "repository (its MODEL_ID) and keeps its own copy in a bucket that is not readable") as s:
            if e.get("source_id"):
                info = model_details(ctx, e["source_id"], s)
            else:
                info = {"errors": ["Model Garden names no source repository for it"], "kv": {}}
            kvt = (info.get("kv") or {}).get("kv_per_token")
            s.result(f"{info.get('weights_gb')} GB of weights, {(info.get('kv') or {}).get('attn_layers')} attention layers, {kvt} bytes of cache "
                     f"per token" if not info.get("errors") else "; ".join(info["errors"]), "g" if not info.get("errors") else "y")
        maxc = (info.get("kv") or {}).get("max_context") or tested_len or None
        dctx = wl.get("context") or args.context or (min(FIT_CONTEXT, maxc) if maxc else FIT_CONTEXT)
        context = int(ask.ask("Longest prompt plus answer per request, in tokens", dctx, flag="--context",
                              check=lambda s: None if s.isdigit() and int(s) > 0 and (not maxc or int(s) <= maxc) else f"a whole number up to {maxc or 'the model limit'}"))
        if info.get("errors"):
            t.line(t.s(f" Requests per copy cannot be estimated: {'; '.join(info['errors'])}. Enter the number of copies instead.", "y"))
        else:
            peak = int(ask.ask("Peak requests in flight at the same time, across all copies", wl.get("peak") or args.peak or FIT_CONCURRENCY,
                               check=lambda s: None if s.isdigit() and int(s) > 0 else "a whole number above 0", flag="--peak"))
    else:
        context = None
        t.line(t.s(" This tool cannot estimate how many requests one copy of a generation model serves at once; plan copies from your own tests.", "c"))
    if peak is None:
        units = int(ask.ask("How many copies of the model should run at the same time?", wl.get("units") or args.units or 1,
                            check=lambda s: None if s.isdigit() and int(s) > 0 else "a whole number above 0", flag="--units"))
    rows, notes = mg_fit(ctx, e, context or 0, info)
    rows = plan_units(rows, units=units, peak=peak)
    if not rows:
        raise SystemExit(f"{e['name']} fits no GPU this project can use at {context} tokens: " + "; ".join(notes))
    best = rows[0]
    if e.get("default_machine") and best["gpus_total"] is not None:
        same = [r for r in rows if r["shape"] == e["default_machine"] and r["gpus_total"] == best["gpus_total"]]
        best = same[0] if same else best
    preq = per_request_gb(info, context, best.get("cfg")) if info and context else None
    sub = (f"{e['name']}" + (f", {info['weights_gb']} GB of weights" if info and info.get("weights_gb") else "")
           + (f", {preq:.2f} GB of cache per request at {context} tokens" if preq else ""))
    explain = None
    if best.get("vms"):
        why = (f"{peak} requests at once at up to {context} tokens need {plural(best['units'], 'copy')} of up to {best['capacity']} requests each"
               if peak else plural(best["units"], "copy"))
        explain = (f"Recommended: {best['gpus_total']} GPUs = {plural(best['vms'], 'VM instance')} of {best['shape']} with {best['gpus_vm']} x "
                   f"{best['label']} each, {plural(best['copies_vm'], 'copy')} per VM; {why}.")
    show_workload(ctx, "Where this model runs", sub, rows, notes, "copy", ["model_garden", "deploy_open", "gpus"], best, explain)
    if info and not info.get("errors"):
        t.line(t.s(f"  requests per copy: estimated from the model's architecture and weight size (MODEL_ID {e['source_id']}), "
                   f"capped by Google's tested --max-num-seqs where set", "gr"))
    return record_workload(req, "model", e["key"], e["name"], rows, best, "copy", context=context, peak=peak, units=units)


def size_product(ctx, req, args, mp, wl):
    """Size an NVIDIA product: the GPUs Google's page for it allows, or a Marketplace VM image used as the operating system."""
    t, ask, cat = ctx.t, ctx.ask, ctx.catalog
    opts = []
    for s in NVIDIA_SOLUTIONS:
        rule = {"g_series": "G series machine types (Google's GPU page names them for Omniverse)", "min": s.get("note", ""),
                "model": s.get("note", "")}[s["rule"]]
        opts.append({"key": s["key"], "label": s["name"], "note": f"{s['where']}; {rule}; from Google Cloud documentation"})
    for p in mp:
        opts.append({"key": "mp:" + p["id"], "label": p["name"],
                     "note": f"Marketplace VM image {p['image'].rsplit('/', 1)[-1]} ({p['os'] or p['arch']}), {p['created'][:10]}"
                             + ("; license fee charged by Google" if p.get("fee") else "") + "; read live"})
    items = [{"key": o["key"], "name": o["label"]} for o in opts]
    dflt = pick_by_fragment(items, args.product) or (wl.get("key") if wl.get("kind") == "product" and any(o["key"] == wl.get("key") for o in opts) else None) \
        or opts[0]["key"]
    key = ask.choose("NVIDIA products on Google Cloud", opts, default=dflt, flag="--product",
                     help_text="No Google API lists Marketplace products: the first entries come from Google's NVIDIA pages, the rest are read from "
                               f"NVIDIA's Marketplace image project {MARKETPLACE_IMAGE_PROJECT}.")
    if key.startswith("mp:"):
        p = next(x for x in mp if "mp:" + x["id"] == key)
        req["image"], req["image_label"] = p["image"], f"{p['name']} ({p['image'].rsplit('/', 1)[-1]})"
        req["boot_disk_gb"] = max(int(req.get("boot_disk_gb") or BOOT_DISK_GB), p["disk_gb"])
        heading(ctx, p["name"], "Google Cloud Marketplace VM image")
        t.line(f"  The VMs boot from {p['image']}; its disk needs at least {p['disk_gb']} GB. Google publishes no GPU sizing for this image, "
               f"so every GPU for its CPU architecture ({p['arch']}) is offered.")
        for k in ("marketplace", "gpus", "drivers"):
            t.line("  " + link(t, *DOCS[k]))
        req["workload"] = {"kind": "product", "key": key, "name": p["name"], "arch": p["arch"], "image": p["image"], "disk_gb": p["disk_gb"]}
        return {"rows": None, "arch": p["arch"]}
    s = next(x for x in NVIDIA_SOLUTIONS if x["key"] == key)
    if s["rule"] == "model":
        heading(ctx, s["name"], s["where"])
        t.line(t.s("  " + s["note"], "c"))
        for k in s["docs"]:
            t.line("  " + link(t, *DOCS[k]))
        req["workload"] = {"kind": "product", "key": key, "name": s["name"]}
        return None
    if s["rule"] == "g_series":
        rows = fit_rows(ctx, {a: 1 for a in cat["accels"]}, family=r"g\d")
        for r in rows:
            # one workstation or streaming node is one VM, whatever its GPU count
            r["per_copy"], r["copies_vm"] = r["gpus_vm"], 1
    else:
        rows = fit_rows(ctx, {a: n for a, n in s["min"].items() if a in cat["accels"]})
    if not rows:
        raise SystemExit(f"no GPU this project can use matches what Google's page for {s['name']} asks for")
    units = int(ask.ask(f"How many {s['unit']}s at the same time? (each is sized as Google's page states)", wl.get("units") or args.units or 1,
                        check=lambda v: None if v.isdigit() and int(v) > 0 else "a whole number above 0", flag="--units"))
    rows = plan_units(rows, units=units)
    best = rows[0]
    explain = (f"Recommended: {best['gpus_total']} GPUs = {plural(best['vms'], 'VM instance')} of {best['shape']} with {best['gpus_vm']} x "
               f"{best['label']} each, for {plural(units, s['unit'])}." + (f" {s['note']}." if s.get("note") else ""))
    show_workload(ctx, "Where this product runs", f"{s['name']}, {s['where']}", rows, [], s["unit"], s["docs"], best, explain)
    return record_workload(req, "product", key, s["name"], rows, best, s["unit"], units=units)


def record_workload(req, kind, key, name, rows, best, unit, **extra):
    """Keep the sizing in the request: which GPUs fit, on which machine types, and the recommendation."""
    fits, per_copy = {}, {}
    for r in rows:
        fits.setdefault(r["accel"], []).append(r["shape"])
        per_copy[r["accel"]] = min(per_copy.get(r["accel"], r["per_copy"]), r["per_copy"])
    rec = {k: best.get(k) for k in ("accel", "shape", "gpus_vm", "per_copy", "copies_vm", "capacity", "units", "vms", "gpus_total")}
    rec["unit"] = unit
    req["workload"] = dict(kind=kind, key=key, name=name, fits=fits, per_copy=per_copy,
                           copies_vm={r["shape"]: r["copies_vm"] for r in rows}, recommend=rec, rows=[{k: r.get(k) for k in rec if k != "unit"} for r in rows],
                           **extra)
    return {"rows": rows, "best": best}


def show_plan(ctx, req, regions, n_pref, dropped):
    t = ctx.t
    acc = ctx.catalog["accels"][req["accel"]]
    heading(ctx, "Plan", f"{fnum(req['goal'])} x {acc['label']} GPUs via {METHOD_LABEL[req['method']]}, "
                         + ("independent VM instances" if req["layout"] == "spread" else f"clusters of {req['cluster_nodes']} VM instances in one zone"))
    t.line(f" machine types, in order of preference: {', '.join(req['shapes'])}")
    wl = req.get("workload") or {}
    if wl.get("name"):
        rec = wl.get("recommend") or {}
        t.line(f" for {wl['name']}" + (f": {plural(rec['units'], rec['unit'])} of {plural(rec['per_copy'], 'GPU')}, recommended as "
                                       f"{plural(rec['vms'], 'VM instance')} of {rec['shape']} = {rec['gpus_total']} GPUs" if rec.get("vms") else ""))
    if req["method"] in ("vms", "spot", "flex", "flex-group"):
        t.line(f" VM image: {req.get('image_label') or req.get('image')}; boot disk {req.get('boot_disk_gb')} GB")
    t.line(f" regions, in order: {', '.join(regions[:n_pref])}" + (f"; then {', '.join(regions[n_pref:])}" if len(regions) > n_pref else ""))
    for r, why in dropped:
        t.line(t.s(f" dropped {r}: {why}", "gr"))
    if req["method"] in ("vms", "spot", "flex", "flex-group") and ctx.subnets is not None and not req.get("subnet"):
        bare = [r for r in regions if not ctx.subnets.get(r)]
        if bare:
            t.line(t.s(f" no subnet in {', '.join(bare)}: VMs cannot be created there until one exists (pass --subnet or create one)", "y"))
    rows = quota_summary(ctx, req, regions)
    heading(ctx, "Quota", "the limit Google sets on this project; separate from free hardware. VM instances the project may add now, per machine type")
    qr = []
    unknown_notes = set()
    sizes = [s.replace("-standard", "").replace("highgpu-", "") for s in req["shapes"]]
    for r in regions:
        mine = [x for x in rows if x["region"] == r]
        if not mine:
            continue
        cells, best = [], 0.0
        for sname, short in zip(req["shapes"], sizes):
            x = next((y for y in mine if y["shape"] == sname), None)
            if not x:
                cells.append(f"{short}:-")
            elif not x["allowed"]:
                cells.append(f"{short}:n/a")
            else:
                cells.append(f"{short}:{'?' if x['nodes'] is None else x['nodes']}")
                best = max(best, x["gpus"] or 0)
        first = next((y for y in mine if y["allowed"]), mine[0])
        style = "g" if best >= req["goal"] else ("y" if best else "r")
        unk = sorted({u for y in mine for u in y.get("unknown") or []})
        qr.append([r, max(y["zones"] for y in mine), "  ".join(cells), t.s(("at most " if unk else "") + fnum(best), style), first["binding"] or "-",
                   first["binding_nums"], money(first["usd_h"])])
        if unk:
            unknown_notes.add(f"{r}: {', '.join(unk)} could not be read")
    for ln in table(["region", "zones", "VM instances allowed by machine type", "GPUs allowed", f"tightest quota ({req['shapes'][0]})", "used/limit",
                     "$/h per VM"],
                    qr, t.width(), right=(1, 3)):
        t.line(ln)
    na = sorted({x["why"] for x in rows if not x["allowed"]})
    for why in na:
        t.line(t.s(f" n/a: {why}", "gr"))
    for n in sorted(unknown_notes):
        t.line(t.s(f" unknown limit, {n}; Google may still refuse for quota", "y"))
    if ctx.book and ctx.book.error:
        t.line(t.s(f" {ctx.book.source}: {ctx.book.error.title}. {ctx.book.error.fix}", "y"))
    if req.get("advisor") and req["method"] != "calendar" and ctx.caps.get("advisor", {}).get("ok") is not False:
        heading(ctx, "Availability signal", "Google's capacity advisor scores Spot capacity from 0 to 1; a hint, not a promise. Attempts are the ground truth.")
        ar = []
        shape = ctx.catalog["shapes"][req["shapes"][0]]
        for r in regions[: max(n_pref, 8)]:
            for z in [z for z in shape["zones"] if region_of(z) == r][:3]:
                a = advise(ctx, shape, z)
                sc = a.get("score")
                ar.append([z, shape["name"], "-" if sc is None else f"{sc:.2f}", a.get("uptime") or "-", a.get("error") or ""])
        for ln in table(["zone", "shape", "score", "expected uptime", "note"], ar, t.width()):
            t.line(ln)
    heading(ctx, f"Ways to reach {fnum(req['goal'])} GPUs", "smaller VMs are usually easier to obtain than large ones, and large regions easier than small")
    wr = []
    for sname in req["shapes"]:
        s = ctx.catalog["shapes"][sname]
        n = int(math.ceil(req["goal"] / s["gpu_equiv"] - 1e-9))
        p = price_of(ctx, s, regions[0], req["method"]) if regions else None
        wr.append([f"{n} x {sname}", f"{plural(s['gpu_equiv'], 'GPU')} each", f"{s['vcpus']} vCPU, {s['mem_gib']:.0f} GiB", len(s["regions"]),
                   money(None if p is None else p * n)])
    for ln in table(["VM instances", "GPUs per VM", "each VM", "regions offering it", f"$/h total ({regions[0] if regions else '-'})"], wr, t.width()):
        t.line(ln)
    kind, text = verdict(ctx, req, regions, rows)
    heading(ctx, "Verdict")
    t.line(t.s(" " + text, {"ok": "g", "quota": "r", "partial": "y", "info": "c"}[kind]))
    return kind, rows


def quota_request_flow(ctx, req, regions, st, save):
    """Offer the one exact quota request the plan still needs; nothing is filed without the typed yes."""
    t, ask = ctx.t, ctx.ask
    if req["quota_request"] == "off":
        t.line(t.s(" Quota requests are off for this run (allow them with --quota-request offer).", "gr"))
        return
    cap = ctx.caps.get("quota_request") or {}
    if cap.get("ok") is False:
        role, why = suggest_role(ctx, cap["missing"])
        t.line(t.s(f" Quota requests cannot be filed by {ctx.tokens.account}: missing {', '.join(cap['missing'])}"
                   + (f"; the smallest role that grants it is {why}" if role else "") + ". The numbers below show what to request by hand.", "y"))
    split = dict(req.get("quota_split") or {})
    if not split:
        opts = [{"key": r, "label": r} for r in regions]
        default = (req.get("quota_regions") or [regions[0]])[0]
        r = ask.choose("Which region should the quota request cover? (only one region is requested, for the whole goal)", opts,
                       default=default if default in [o["key"] for o in opts] else regions[0], flag="--quota-region")
        split = {r: req["goal"]}
    recs = quota_needs(ctx, req, split, obtained=0.0)
    heading(ctx, "Quota request", "only quotas that block the plan, at usage plus what the plan needs; never more")
    rows = []
    for r in recs:
        act = {"file": t.s("request", "c", "b"), "enough": t.s("enough", "g"), "pending": t.s("pending", "y"), "denied_before": t.s("denied before", "y"),
               "fixed": t.s("fixed", "r"), "ineligible": t.s("ineligible", "r"), "unknown": t.s("unknown", "gr"), "none": "-"}[r["action"]]
        rows.append([r["display"], r["region"] or "all regions", r["limit"], r["used"], r["need"], r["preferred"] if r["action"] == "file" else "-", act])
    for ln in table(["quota", "where", "limit", "used", "plan needs", "request", "action"], rows, t.width(), right=(2, 3, 4, 5)):
        t.line(ln)
    for r in recs:
        if r["action"] not in ("file", "enough"):
            t.line(t.s(f"  {r['display']} ({r['region'] or 'all regions'}): {r['why']}", "gr"))
    todo, stuck = filing_set(recs)
    if not todo:
        t.line(" Nothing to request: " + ("quota already covers the plan." if all(r["action"] == "enough" for r in recs) else "see the reasons above."))
        return
    if cap.get("ok") is False:
        t.line(" Nothing filed: this account cannot file quota requests (see above).")
        return
    if stuck:
        # a partial set cannot reach the goal, and every refused request makes the next one harder: file all or nothing
        names = ", ".join(f"{r['display']} ({r['region'] or 'all regions'}: {r['action'].replace('_', ' ')})" for r in stuck)
        t.line(t.s(f" Nothing filed: the plan also needs {names}, which this tool cannot request now. Raising the others alone would not "
                   f"let the plan run. Settle those first (console: {CONSOLE}/iam-admin/quotas?project={ctx.project}), then run again.", "y"))
        st.setdefault("quota_notes", []).append({"at": iso(), "blocked_by": [{"qid": r["qid"], "dims": r["dims"], "action": r["action"]} for r in stuck]})
        save()
        return
    for r in todo:
        if r.get("pre"):
            t.line(t.s(f"  note: once Google grants {r['display']}, Spot and flex-start VMs in {r['region']} draw only on preemptible quota.", "y"))
    acct = ctx.tokens.account or ""
    default_contact = req.get("contact") or (acct if ctx.tokens.is_person() else None)

    def email_ok(s):
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", s):
            return "enter an email address"
        if s.lower().endswith("gserviceaccount.com"):
            return "a service account cannot receive Google's questions; give a person's or team's address"
        return None

    contact = ask.ask("Contact email for Google's quota team", default_contact, check=email_ok, flag="--contact")
    label = ctx.catalog["accels"][req["accel"]]["label"]
    region0 = list(split)[0]
    shape0 = todo[-1].get("shape") or req["shapes"][0]
    nodes0 = next((r["nodes"] for r in todo if r.get("nodes")), None)
    default_just = req.get("justification") or (
        f"{req.get('use_case') or 'AI workloads'}: we need {fnum(req['goal'])} {label} GPUs"
        + (f" ({nodes0} x {shape0})" if nodes0 else "") + f" in {region0} via {METHOD_LABEL[req['method']]}; "
        f"this request covers exactly that shortfall above current usage.")
    just = ask.ask("Justification shown to Google (edit as needed)", default_just, flag="--justification")
    heading(ctx, "Validating with Google (nothing is filed yet)")
    ok_recs = []
    for r in todo:
        ok, msg = validate_request(ctx, st["run_id"], r, contact, just)
        t.line(f"  {r['display']} {r['region'] or ''} to {r['preferred']}: " + (t.s("valid", "g") if ok else t.s(msg, "r")))
        if ok:
            ok_recs.append(r)
    if not ok_recs:
        t.line(" No request passed validation; nothing filed.")
        return
    pre = req["quota_request"] == "file" and ctx.opts.get("yes")
    if not ask.typed(f"File {len(ok_recs)} quota request(s) exactly as shown, once each?", "yes", preapproved=pre):
        t.line(" No quota request filed.")
        return
    file_requests(ctx, st["run_id"], ok_recs, contact, just, st, save)
    ask.lock("quota requests were filed with Google for this run")
    for r in ok_recs:
        t.line(f"  {r['display']} {r['region'] or ''} to {r['preferred']}: {r.get('result')}")
    t.line(t.s(f" Status is tracked during the run and in `status {st['run_id']}`; console: {CONSOLE}/iam-admin/quotas?project={ctx.project}", "gr"))


# ------------------------------------------------------------------ the questions
def csv_list(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def wizard(ctx, req, args):
    """Every question, each with a default from flags or the config file; unattended runs take the defaults."""
    t, ask, cat = ctx.t, ctx.ask, ctx.catalog
    if not cat["accels"]:
        raise SystemExit("this project sees no NVIDIA GPU types in any zone; check the project and that Compute Engine is enabled")
    sizing = choose_workload(ctx, req, args)
    wl = req.get("workload") or {}
    rows = (sizing or {}).get("rows")
    arch = (sizing or {}).get("arch")
    if wl.get("name"):
        req["use_case"] = req.get("use_case") or wl["name"]
    fits = wl.get("fits") if rows else None
    accs = sorted(cat["accels"].values(), key=lambda a: (-(a.get("mem_gb") or 0), a["name"]))
    if arch:
        accs = [a for a in accs if any(cat["shapes"][s].get("cpu_arch") in (None, arch) for s in a["shapes"])]
    hidden = 0
    if fits:
        hidden = len([a for a in accs if a["name"] not in fits])
        accs = [a for a in accs if a["name"] in fits]
    opts = []
    for a in accs:
        note = f"{gb(a.get('mem_gb'))} each, {a.get('arch') or '?'}, in {len(a['regions'])} regions" + \
            ("; offered with NVIDIA RTX Virtual Workstation" if a.get("vws") else "")
        if fits:
            best_a = min((r for r in rows if r["accel"] == a["name"]), key=lambda r: (r["gpus_total"] or 0, not r["tested"]))
            note += (f"; {best_a['per_copy']} GPU(s) per {wl['recommend']['unit']}"
                     + (f", {best_a['gpus_total']} GPUs in total recommended ({best_a['vms']} x {best_a['shape']})" if best_a.get("gpus_total") else ""))
        opts.append({"key": a["name"], "label": a["label"], "note": note})
    if hidden:
        t.line(t.s(f" {hidden} other GPU type(s) are not listed: they do not fit this workload.", "gr"))
    rec = wl.get("recommend") or {}
    default_acc = (req.get("accel") if req.get("accel") in [o["key"] for o in opts] else None) or args.gpu or rec.get("accel") \
        or ("nvidia-rtx-pro-6000" if "nvidia-rtx-pro-6000" in [o["key"] for o in opts] else opts[0]["key"])
    req["accel"] = ask.choose("GPU model", opts, default=default_acc, flag="--gpu", help_text=f"Details: {DOCS['gpus'][1]}",
                              alt={"all": (None, "one GPU type per run: quota, prices and the GPU goal count GPUs of one type; run the finder again "
                                                 "for another type")})
    acc = cat["accels"][req["accel"]]
    minper = (wl.get("per_copy") or {}).get(req["accel"]) if fits else None
    mine = [r for r in rows or [] if r["accel"] == req["accel"]]
    best_mine = mine[0] if mine else None
    hint = None
    if best_mine and best_mine.get("gpus_total"):
        unit = rec.get("unit") or "copy"
        hint = (f"Recommended for {wl['name']}: {best_mine['gpus_total']} GPUs = {plural(best_mine['vms'], 'VM instance')} of {best_mine['shape']} "
                f"({plural(best_mine['gpus_vm'], 'GPU')} each, {plural(best_mine['copies_vm'], unit)} per VM) for {plural(best_mine['units'], unit)}"
                + (f" serving {wl['peak']} requests at once" if wl.get("peak") else "") + ".")

    def num_ok(s):
        try:
            v = float(s)
        except ValueError:
            return "enter a number of GPUs"
        if v <= 0:
            return "must be more than 0"
        if minper and abs(v / minper - round(v / minper)) > 1e-9:
            return f"use a multiple of {minper}: each {rec.get('unit') or 'copy'} needs {minper} GPUs in one VM"
        return None

    # with nothing to size from, the smallest whole-GPU VM of this type: enough to see whether any capacity is there
    whole = sorted(cat["shapes"][x]["gpu_equiv"] for x in acc["shapes"] if cat["shapes"][x]["fraction"] >= 1.0)
    one_vm = minper or (whole[0] if whole else 1)
    dgoal = req.get("goal") or args.count or (best_mine or {}).get("gpus_total") or one_vm
    goal_note = ("your earlier answer" if req.get("goal") or args.count else
                 "the recommendation for this workload" if (best_mine or {}).get("gpus_total") else "one VM of the smallest machine type")
    req["goal"] = float(ask.ask(f"How many {acc['label']} GPUs in total (all VM instances together)", dgoal, check=num_ok, flag="--count",
                                lead=[t.s(" " + hint, "c")] if hint else None, alt={"skip": (fnum(dgoal), goal_note)}))
    req["layout"] = ask.choose("Layout", [
        {"key": "spread", "label": "independent VM instances, anywhere allowed", "note": "each VM stands alone; easiest to obtain"},
        {"key": "cluster", "label": "clusters: groups of VM instances together in one zone", "note": "for multi-VM jobs; all of a group arrive at once"}],
        default=req.get("layout") or args.layout or "spread", flag="--layout")
    if req["layout"] == "cluster":
        req["cluster_nodes"] = int(ask.ask("VM instances per cluster", req.get("cluster_nodes") if req.get("cluster_nodes", 1) > 1 else (args.cluster_nodes or 2),
                                           check=lambda s: None if s.isdigit() and int(s) >= 2 else "2 or more", flag="--cluster-nodes"))
    shapes = [cat["shapes"][s] for s in acc["shapes"]]
    if arch:
        shapes = [s for s in shapes if s.get("cpu_arch") in (None, arch)]
    if fits:
        allowed = set(fits.get(req["accel"]) or [])
        gone = [s["name"] for s in shapes if s["name"] not in allowed]
        shapes = [s for s in shapes if s["name"] in allowed]
        if gone:
            t.line(t.s(f" {len(gone)} machine type(s) of this GPU are not listed ({', '.join(gone)}): one {rec.get('unit') or 'copy'} needs "
                       f"{fnum(minper)} GPU(s) in one VM.", "gr"))
    cv = wl.get("copies_vm") or {}
    sopts = []
    for s in shapes:
        extra = f"  {plural(cv[s['name']], rec.get('unit') or 'copy')} per VM" if s["name"] in cv else ""
        sopts.append({"key": s["name"], "label": f"{s['name']:24s} {fnum(s['gpu_equiv']):>5s} GPU  {s['vcpus']:4d} vCPU  {s['mem_gib']:6.0f} GiB{extra}",
                      "note": f"{len(s['regions'])} regions"})
    keys = [o["key"] for o in sopts]
    first = [best_mine["shape"]] if best_mine and best_mine["shape"] in keys else []
    dshapes = [x for x in (req.get("shapes") or csv_list(args.shapes)) if x in keys] or \
        first + [k for k in keys if k not in first and cat["shapes"][k]["fraction"] >= 1.0]
    req["shapes"] = ask.multi("Machine types allowed, in order of preference (smaller VMs are usually easier to get)", sopts, default=dshapes,
                              flag="--shapes", help_text=f"Each is one VM instance; details: {DOCS['accel'][1]}",
                              alt={"skip": ([k for k in keys if cat["shapes"][k]["fraction"] >= 1.0] or keys,
                                            "every machine type with whole GPUs, so any that is free counts")})
    archs = {cat["shapes"][s].get("cpu_arch") for s in req["shapes"]} - {None}
    if len(archs) > 1:
        raise SystemExit(f"the machine types chosen mix CPU architectures ({', '.join(sorted(archs))}); one VM image cannot boot both, so choose one kind")
    offered = sorted({r for s in req["shapes"] for r in cat["shapes"][s]["regions"]})
    by_geo = {}
    for r in offered:
        by_geo.setdefault(geo_of(r), []).append(r)
    heading(ctx, "Regions offering these machine types", ", ".join(req["shapes"]))
    for g, rs in sorted(by_geo.items()):
        t.line(f"  {g:14s} {', '.join(rs)}")

    def regions_ok(s):
        try:
            expand_regions(csv_list(s), set(cat["regions"]))
        except SystemExit as e:
            return str(e)
        return None

    every = (",".join(offered), f"all {len(offered)} regions offering these machine types")
    req["regions"] = csv_list(ask.ask("Preferred region(s), best first (names, groups like asia-pacific, or prefixes like asia)",
                                      ",".join(req.get("regions") or []) or args.region or (offered[0] if offered else None), check=regions_ok, flag="--region",
                                      alt={"skip": every, "all": every, "none": (None, "the search needs at least one region; skip takes them all")}))
    fb = ask.ask("Fallback regions or groups if the preferred ones have no capacity",
                 ",".join(req.get("fallback") or []) or args.fallback or "none", check=lambda s: None if s.strip().lower() == "none" else regions_ok(s), flag="--fallback",
                 alt={"skip": ("all", "any other region offering these machine types"), "all": ("all", "any other region offering these machine types"),
                      "none": ("none", "no fallback")})
    req["fallback"] = [] if fb.strip().lower() == "none" else csv_list(fb)
    ex = ask.ask("Regions or groups to exclude", ",".join(req.get("exclude") or []) or args.exclude or "none",
                 check=lambda s: None if s.strip().lower() == "none" else regions_ok(s), flag="--exclude",
                 alt={"skip": ("none", "exclude nothing"), "none": ("none", "exclude nothing"),
                      "all": (None, "excluding every region leaves nowhere to search")})
    req["exclude"] = [] if ex.strip().lower() == "none" else csv_list(ex)
    mopts = []
    for m in METHODS:
        dis = None
        cap = ctx.caps.get(METHOD_CAP[m]) or {}
        if cap.get("ok") is False:
            dis = "missing " + ", ".join(cap["missing"][:3])
        elif not any(method_allows(m, cat["shapes"][s])[0] for s in req["shapes"]):
            dis = method_allows(m, cat["shapes"][req["shapes"][0]])[1]
        elif ctx.cmek_required and m in ("vms", "spot", "flex", "flex-group"):
            dis = "organization policy requires customer-managed disk keys"
        note = BILLING_NOTE[m]
        if dis and ctx.opts.get("cmd") == "plan" and cap.get("ok") is False:
            # planning is analysis only: show the numbers, and say this account could not run it
            note = f"this account cannot run it ({dis}); planning only"
            dis = None
        mopts.append({"key": m, "label": METHOD_LABEL[m], "note": note, "disabled": dis})
    req["method"] = ask.choose("How should capacity be held?", mopts, default=req.get("method") or args.method, flag="--method",
                               help_text="Each method draws on a different pool of Google capacity and bills differently.",
                               alt={"all": (None, "one way of holding capacity per run: each uses its own quota and bills differently"),
                                    "skip": (req.get("method") or args.method, "your earlier choice") if req.get("method") or args.method else
                                    (None, "how capacity is held decides what you are billed for and when, so it is your choice")})
    m = req["method"]
    if m in ("vms", "spot", "flex", "flex-group"):
        choose_vm_options(ctx, req, args)
    elif m in ("reservation", "calendar"):
        t.line(t.s(" Reservations hold capacity with no VM running, so no operating system is chosen now: the VMs you later create to use the "
                   "reservation pick their own image. " + DOCS["provisioning"][1], "c"))
    if m == "spot":
        req["spot_action"] = ask.choose("When Google reclaims a Spot VM", [{"key": "DELETE", "label": "delete it (no disk charges after)"},
                                                                         {"key": "STOP", "label": "stop it (disk kept and billed)"}],
                                        default=req.get("spot_action") or args.spot_action or "DELETE", flag="--spot-action")
    if m in ("flex", "flex-group"):
        lo_h, hi_h = FLEX_RUN_MIN_S / 3600, FLEX_RUN_MAX_S / 3600
        hrs = ask.ask(f"Flex-start run time in hours (VMs are deleted after it; up to {hi_h:g})",
                      (req.get("flex_run_s") or FLEX_RUN_S) / 3600 if not args.flex_run_hours else args.flex_run_hours,
                      check=lambda s: None if re.fullmatch(r"\d+(\.\d+)?", s) and FLEX_RUN_MIN_S <= float(s) * 3600 <= FLEX_RUN_MAX_S
                      else f"between {lo_h:.2f} and {hi_h:g} hours", flag="--flex-run-hours")
        req["flex_run_s"] = int(float(hrs) * 3600)
    if m == "flex":
        w = ask.ask(f"How long each queued request waits in its zone, in seconds ({FLEX_WAIT_MIN_S} to {FLEX_WAIT_MAX_S})",
                    req.get("flex_wait_s") or args.flex_wait or FLEX_WAIT_S,
                    check=lambda s: None if s.isdigit() and FLEX_WAIT_MIN_S <= int(s) <= FLEX_WAIT_MAX_S else f"between {FLEX_WAIT_MIN_S} and {FLEX_WAIT_MAX_S}",
                    flag="--flex-wait")
        req["flex_wait_s"] = int(w)
    if m == "reservation":
        h = ask.ask("Delete the reservations automatically after this many hours (0 keeps them until you release)",
                    (req.get("reservation_ttl_s") or 0) / 3600 if args.reservation_hours is None else args.reservation_hours,
                    check=lambda s: None if re.fullmatch(r"\d+(\.\d+)?", s) else "a number of hours", flag="--reservation-hours")
        req["reservation_ttl_s"] = int(float(h) * 3600) or None
    if m == "calendar":
        cal = req["calendar"]
        d_lo, d_hi, s_hi = CALENDAR_DAYS_MIN, CALENDAR_DAYS_MAX, CALENDAR_START_MAX_DAYS
        cal["start_within_days"] = int(ask.ask(f"Latest start, in days from now (1 to {s_hi})", args.calendar_start_within_days or cal["start_within_days"],
                                               check=lambda s: None if s.isdigit() and 1 <= int(s) <= s_hi else f"1 to {s_hi}", flag="--calendar-start-within-days"))
        cal["min_days"] = int(ask.ask(f"Shortest reservation, in days ({d_lo} to {d_hi})", args.calendar_min_days or cal["min_days"],
                                      check=lambda s: None if s.isdigit() and d_lo <= int(s) <= d_hi else f"{d_lo} to {d_hi}", flag="--calendar-min-days"))
        cal["max_days"] = int(ask.ask(f"Longest reservation, in days ({d_lo} to {d_hi})", args.calendar_max_days or max(cal["max_days"], cal["min_days"]),
                                      check=lambda s: None if s.isdigit() and cal["min_days"] <= int(s) <= d_hi else f"{cal['min_days']} to {d_hi}",
                                      flag="--calendar-max-days"))
    cap = ask.ask("Hourly spending cap in USD for everything held",
                  req.get("max_usd_h") or (args.max_usd_per_hour if args.max_usd_per_hour is not None else "none"),
                  check=lambda s: None if s.lower() == "none" or re.fullmatch(r"\d+(\.\d+)?", s) else "a number, or none", flag="--max-usd-per-hour",
                  alt={"skip": ("none", "no cap"), "none": ("none", "no cap")})
    req["max_usd_h"] = None if cap.lower() == "none" else float(cap)
    if req["quota_request"] == "off" and args.quota_request is None:
        req["quota_request"] = "offer" if ask.yes("If quota turns out to be the limit, may this tool offer to file the exact quota request? (you confirm each time)",
                                                  False, alt={"skip": (False, "no offer"), "none": (False, "no offer")}) else "off"
    elif args.quota_request:
        req["quota_request"] = args.quota_request
    if m in ("spot", "flex", "flex-group"):
        req["maintain"] = req.get("maintain") or args.maintain or ask.yes("Keep running after the goal, replacing capacity Google reclaims?", False,
                                                                          alt={"skip": (False, "stop at the goal")})
    return req


def choose_vm_options(ctx, req, args):
    """The VM configuration Google offers for these machine types: operating system image, boot disk, network, shown together."""
    t, ask, cat = ctx.t, ctx.ask, ctx.catalog
    shapes = [cat["shapes"][s] for s in req["shapes"]]
    arch = next((s.get("cpu_arch") for s in shapes if s.get("cpu_arch")), None)
    wl = req.get("workload") or {}
    disk_min = BOOT_DISK_MIN_GB
    if args.image:
        req["image"], req["image_label"] = args.image, args.image
    elif wl.get("image"):
        t.line(t.s(f" Operating system: the NVIDIA Marketplace image chosen earlier, {req['image_label']}.", "c"))
    else:
        groups, read = os_images(ctx, refresh=args.refresh)
        usable = []
        for g in groups:
            fams = [f for f in g["families"] if (not arch or f["arch"] in (None, arch)) and f["gvnic"]]
            if fams:
                usable.append(dict(g, families=fams))
        if not usable:
            raise SystemExit(f"no public image in {IMAGE_PROJECTS} supports {arch} with gVNIC networking; pass --image")
        # an image set in GPUF_IMAGE or saved in the config is the default; otherwise the first group with the NVIDIA driver installed
        cur = req.get("image") or (IMAGE if os.environ.get("GPUF_IMAGE") else "")
        gopts = [{"key": g["project"], "label": g["label"],
                  "note": f"{len(g['families'])} version(s), newest {g['families'][0]['family']}"} for g in usable]
        gopts.append({"key": "custom", "label": "Another image: type its path"})
        dgroup = next((g["project"] for g in usable if f"projects/{g['project']}/" in cur), None) or \
            next((g["project"] for g in usable if g["nvidia"]), usable[0]["project"])
        newest = next(g for g in usable if g["project"] == dgroup)
        proj = ask.choose(f"Operating system for the VMs ({arch or 'any'} images that support gVNIC networking, read {read})", gopts, default=dgroup,
                          flag="--image", help_text=f"Images with the NVIDIA driver installed are ready for GPUs; others need it installed: {DOCS['drivers'][1]}",
                          alt={"skip": (dgroup, f"any operating system: the default, its newest version {newest['families'][0]['family']}; the version "
                                                f"question is skipped too"),
                               "none": (None, "every VM boots an image; skip takes the default"), "all": (None, "a VM boots one image")})
        os_skipped = ask.skipped
        if proj == "custom":
            req["image"] = ask.ask("Image path (projects/PROJECT/global/images/NAME or .../images/family/FAMILY)", cur or IMAGE, flag="--image")
            req["image_label"] = req["image"]
        else:
            g = next(x for x in usable if x["project"] == proj)
            fopts = []
            for f in g["families"]:
                detail = ", ".join(x.strip() for x in f["desc"].split(",")[2:5]) if f["desc"].count(",") >= 2 else f["desc"]
                fopts.append({"key": f["family"], "label": f["family"], "note": f"{detail[:90]}; published {f['created'][:10]}"})
            dfam = next((f["family"] for f in g["families"] if cur.endswith("/family/" + f["family"])), g["families"][0]["family"])
            if os_skipped:
                fam = g["families"][0]["family"]
            else:
                fam = ask.choose(f"{g['label']}: version", fopts, default=dfam, flag="--image",
                                 alt={"skip": (g["families"][0]["family"], "the newest version"), "all": (None, "a VM boots one image")})
            f = next(x for x in g["families"] if x["family"] == fam)
            req["image"], req["image_label"] = f["image"], f"{g['label']}, {fam}"
            disk_min = max(disk_min, f["disk_gb"])
    if wl.get("image"):
        disk_min = max(disk_min, int(wl.get("disk_gb") or 0))
    dsize = max(int(req.get("boot_disk_gb") or BOOT_DISK_GB), disk_min) if not args.boot_disk_gb else args.boot_disk_gb
    req["boot_disk_gb"] = int(ask.ask(f"Boot disk size in GB (the image needs at least {disk_min})", dsize, flag="--boot-disk-gb",
                                      check=lambda s: None if s.isdigit() and int(s) >= disk_min else f"{disk_min} or more",
                                      alt={"skip": (str(disk_min), "the smallest the image allows")}))
    sub = ask.ask("Subnet for the VMs (name, full path for shared VPC, or 'auto')", req.get("subnet") or args.subnet or "auto", flag="--subnet",
                  alt={"skip": ("auto", "any subnet in the region")})
    req["subnet"] = None if sub.strip().lower() == "auto" else sub.strip()
    heading(ctx, "VM options", "what each VM instance gets; Google decides the rest by machine type")
    rows = []
    for s in shapes:
        rows.append([s["name"], f"{fnum(s['gpu_equiv'])} x {cat['accels'][s['accel']]['label']}", s["vcpus"], f"{s['mem_gib']:.0f}",
                     s.get("cpu_arch") or "-", s["boot_disk"]])
    for ln in table(["machine type", "GPUs attached", "vCPU", "memory GiB", "CPU", "boot disk type"], rows, t.width()):
        t.line(ln)
    t.line("")
    t.line(f"  provisioning model  {METHOD_LABEL[req['method']]}: {BILLING_NOTE[req['method']]}")
    t.line(f"  operating system    {req['image_label'] or req['image']}")
    t.line(f"  boot disk           {req['boot_disk_gb']} GB, type set by the machine family as above")
    t.line(f"  network             {req['subnet'] or 'the default network, or any subnet in the region'}; gVNIC; no external IP address")
    t.line(f"  service account     {req.get('vm_service_account') or 'none attached'}")
    t.line("")
    for k in ("provisioning", "os", "drivers", "dlvm"):
        t.line("  " + link(t, *DOCS[k]))


def apply_args(req, args):
    """Flags override a loaded config; prompts then default to these values."""
    if args.gpu:
        req["accel"] = args.gpu
    if args.count:
        req["goal"] = args.count
    if args.shapes:
        req["shapes"] = csv_list(args.shapes)
    if args.layout:
        req["layout"] = args.layout
    if args.cluster_nodes:
        req["cluster_nodes"] = args.cluster_nodes
    if args.region:
        req["regions"] = csv_list(args.region)
    if args.fallback:
        req["fallback"] = [] if args.fallback.lower() == "none" else csv_list(args.fallback)
    if args.exclude:
        req["exclude"] = [] if args.exclude.lower() == "none" else csv_list(args.exclude)
    if args.method:
        req["method"] = args.method
    for k, a in (("image", "image"), ("subnet", "subnet"), ("contact", "contact"), ("justification", "justification"), ("use_case", "use_case"),
                 ("boot_disk_gb", "boot_disk_gb"), ("flex_wait_s", "flex_wait"), ("spot_action", "spot_action"), ("vm_service_account", "vm_service_account")):
        if getattr(args, a):
            req[k] = getattr(args, a)
    if args.subnet and args.subnet.lower() == "auto":
        req["subnet"] = None
    if args.flex_run_hours:
        req["flex_run_s"] = int(args.flex_run_hours * 3600)
    if args.reservation_hours is not None:
        req["reservation_ttl_s"] = int(args.reservation_hours * 3600) or None
    if args.max_usd_per_hour is not None:
        req["max_usd_h"] = args.max_usd_per_hour
    if args.maintain:
        req["maintain"] = True
    if args.quota_request:
        req["quota_request"] = args.quota_request
    cal = req["calendar"]
    for k, a in (("start_within_days", "calendar_start_within_days"), ("min_days", "calendar_min_days"), ("max_days", "calendar_max_days")):
        if getattr(args, a):
            cal[k] = getattr(args, a)
    if args.quota_region:
        req["quota_regions"] = csv_list(args.quota_region)
    if args.quota_split:
        req["quota_split"] = {k.strip(): float(v) for k, v in (x.split("=") for x in csv_list(args.quota_split))}
    if args.no_advisor:
        req["advisor"] = False
    if args.allow_overshoot:
        req["allow_overshoot"] = True
    if args.calendar_auto_submit:
        req["calendar"]["auto_submit"] = True
    return req


# ------------------------------------------------------------------ setup: install, sign in, and fix what is missing
class SetupError(Exception):
    def __init__(self, message, fix=""):
        super().__init__(message)
        self.message, self.fix = message, fix


def gcloud_archive_name(system=None, machine=None):
    """The official Google Cloud CLI archive for this computer, or None when Google publishes none."""
    system = (system or platform.system()).lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "arm", "arm64": "arm"}.get((machine or platform.machine()).lower())
    if not arch:
        return None
    if system in ("linux", "darwin"):
        return f"google-cloud-cli-{system}-{arch}.tar.gz"
    if system == "windows" and arch == "x86_64":
        return "google-cloud-cli-windows-x86_64-bundled-python.zip"
    return None


def download_file(term, url, dest, ca_bundle=None):
    """Stream url to dest with a progress bar; a read that waits longer than the stall window abandons it."""
    ctx = ssl.create_default_context(cafile=ca_bundle) if ca_bundle else ssl.create_default_context()
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    part, h, n, t0, last = dest + ".part", hashlib.sha256(), 0, now(), 0.0
    term.line(f" downloading {url}")
    try:
        with opener.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=DOWNLOAD_STALL_S) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                n += len(chunk)
                if now() - last >= (0.25 if not term.plain else 10.0):
                    last = now()
                    rate = n / max(0.001, now() - t0) / 1e6
                    msg = f"{n / 1e6:7.1f}" + (f" of {total / 1e6:.1f}" if total else "") + f" MB  {rate:5.1f} MB/s"
                    term.write(f"\r   {term.bar(n / total if total else None, 30)} {msg}\x1b[K" if not term.plain else f"   {msg}\n")
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        if os.path.exists(part):
            os.remove(part)
        u = urllib.parse.urlparse(url)
        audit("http", m="GET", host=u.netloc, path=u.path, status=getattr(e, "code", 0), ms=int((now() - t0) * 1000), bytes=n,
              note=f"{type(e).__name__}: {getattr(e, 'reason', e)}")
        raise SetupError(f"the download from {urllib.parse.urlparse(url).netloc} failed: {getattr(e, 'reason', e)}",
                         "check internet access to dl.google.com (HTTPS_PROXY, --ca-bundle), then run setup again")
    if not term.plain:
        term.write("\n")
    u = urllib.parse.urlparse(url)
    if total and n != total:
        os.remove(part)
        audit("http", m="GET", host=u.netloc, path=u.path, status=0, ms=int((now() - t0) * 1000), bytes=n, note=f"stopped at {n} of {total} bytes")
        raise SetupError(f"the download stopped at {n} of {total} bytes", "run setup again; a partial file is never used")
    os.replace(part, dest)
    sha = h.hexdigest()
    audit("http", m="GET", host=u.netloc, path=u.path, status=200, ms=int((now() - t0) * 1000), bytes=n, note=f"sha256 {sha}")
    audit("file", op="write", path=dest, bytes=n, note="downloaded archive")
    return n, sha


def safe_extract(archive, dest):
    """Unpack a tar or zip into dest after checking free space and that no entry lands outside dest."""
    root = os.path.realpath(dest)

    def inside(path):
        p = os.path.realpath(os.path.join(root, path))
        return p == root or p.startswith(root + os.sep)

    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            bad = [i.filename for i in infos if not inside(i.filename)]
            need = sum(i.file_size for i in infos)
            free = shutil.disk_usage(root).free
            if bad:
                raise SetupError(f"the archive has entries outside its folder: {', '.join(bad[:3])}", "the download is not a genuine Google archive; do not use it")
            if need > free:
                raise SetupError(f"unpacking needs {need / 1e9:.2f} GB but {root} has {free / 1e9:.2f} GB free", "free space there, or set GPUF_GCLOUD_DIR elsewhere")
            z.extractall(root)
        return need
    with tarfile.open(archive, "r:*") as tf:
        members = tf.getmembers()
        bad = []
        for m in members:
            if not inside(m.name):
                bad.append(m.name)
            elif m.issym() and (os.path.isabs(m.linkname) or not inside(os.path.join(os.path.dirname(m.name), m.linkname))):
                bad.append(f"{m.name} -> {m.linkname}")
            elif m.islnk() and not inside(m.linkname):
                bad.append(f"{m.name} => {m.linkname}")
        if bad:
            raise SetupError(f"the archive has entries outside its folder: {', '.join(bad[:3])}", "the download is not a genuine Google archive; do not use it")
        need = sum(m.size for m in members if m.isfile())
        free = shutil.disk_usage(root).free
        if need > free:
            raise SetupError(f"unpacking needs {need / 1e9:.2f} GB but {root} has {free / 1e9:.2f} GB free", "free space there, or set GPUF_GCLOUD_DIR elsewhere")
        if hasattr(tarfile, "data_filter"):
            tf.extractall(root, filter="data")
        else:
            tf.extractall(root)
    return need


def run_streaming(term, cmd, stall_s, cwd=None, env=None, show=None, log_path=None):
    """Run a command, echo the lines `show` selects dimmed and keep all of them in log_path; stopped only after a silent stall window."""
    t0 = now()
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=cwd, env=env)
    q = queue.Queue()

    def pump():
        for ln in p.stdout:
            q.put(ln)
        q.put(None)

    threading.Thread(target=pump, daemon=True).start()
    out, last = [], now()
    while True:
        try:
            ln = q.get(timeout=1.0)
        except queue.Empty:
            if now() - last >= stall_s:
                alive = p.poll() is None
                term.line(term.s(f"   no output for {human_dur(stall_s)}; process {'still running' if alive else 'exited'}, stopping it", "y"))
                p.kill()
                p.wait()
                raise SetupError(f"{os.path.basename(cmd[0])} stalled for {human_dur(stall_s)}", "run setup again; raise GPUF_INSTALL_STALL_S on a slow disk")
            continue
        if ln is None:
            break
        last = now()
        ln = ln.rstrip()
        out.append(ln)
        if ln.strip() and (show is None or show(ln)):
            term.line(term.s("   " + clip(ln.strip(), term.width() - 4), "gr"))
    rc = p.wait()
    audit("cmd", argv=[short_path(c) for c in cmd], rc=rc, ms=int((now() - t0) * 1000), stdout="\n".join(out[-20:]),
          withheld=f"whole output in {short_path(log_path)}" if log_path else None)
    if log_path:
        atomic_write(log_path, f"$ {' '.join(cmd)}\nexit {rc}\n" + "\n".join(out) + "\n", 0o644)
        term.line(term.s(f"   full output: {log_path}", "gr"))
    return rc, out


def gcloud_in(sdk):
    for name in gcloud_names():
        p = os.path.join(sdk, "bin", name)
        if is_exe(p):
            return p
    return None


def sdk_root(gcloud):
    return os.path.dirname(os.path.dirname(os.path.realpath(gcloud)))


def gcloud_works(gcloud, env_python=None):
    env = gcloud_env()
    if env_python:
        env["CLOUDSDK_PYTHON"] = env_python
    args = ["version", "--format=value(\"Google Cloud SDK\")"]
    t0 = now()
    try:
        r = subprocess.run([gcloud] + args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=GCLOUD_TIMEOUT_S, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        audit("cmd", argv=gcloud_argv(gcloud, args), rc=None, ms=int((now() - t0) * 1000), withheld=str(e))
        return None, str(e)
    out = (r.stdout or "").strip()
    audit("cmd", argv=gcloud_argv(gcloud, args) + ([f"(CLOUDSDK_PYTHON={env_python})"] if env_python else []), rc=r.returncode,
          ms=int((now() - t0) * 1000), stdout=out[-200:], stderr=(r.stderr or "").strip()[-400:])
    return (out.splitlines()[0] if r.returncode == 0 and out else None), (r.stderr or "").strip()


def offer_path_update(term, ask, gcloud, unattended):
    """Google's own installer adds gcloud to the shell profile; this asks once and remembers the answer."""
    if SESSION["ephemeral"]:
        term.line(term.s(f" gcloud at {short_path(gcloud)} is used for this session only; adding it to your shell profile is not offered, since "
                         f"this session saves nothing", "gr"))
        return
    sdk = sdk_root(gcloud)
    installer = os.path.join(sdk, "install.bat" if os.name == "nt" else "install.sh")
    if unattended or not os.path.isfile(installer) or load_setup().get("path_offered") == sdk:
        return
    save_setup(path_offered=sdk)
    if not ask.yes(f"Add {os.path.dirname(gcloud)} to PATH in your shell profile, as Google's installer does, so `gcloud` works in new terminals? "
                   "This tool does not need it.", default=True):
        return
    cmd = (["cmd", "/c", installer] if os.name == "nt" else [installer]) + ["--quiet", "--usage-reporting", "false", "--path-update", "true",
                                                                          "--command-completion", "true"]
    keep = re.compile(r"(?i)has been updated|new shell|error|warning|failed")
    log = os.path.join(HOME, "logs", f"gcloud-install-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.log")
    rc, out = run_streaming(term, cmd, INSTALL_STALL_S, cwd=sdk, env=gcloud_env(), show=keep.search, log_path=log)
    term.line(term.s(" profile updated; open a new terminal to use gcloud there" if rc == 0 else f" Google's installer exited with {rc}; PATH is unchanged",
                     "g" if rc == 0 else "y"))


def install_gcloud(term, ask, unattended=False, ca_bundle=None, target=None):
    """Download Google's Google Cloud CLI archive for this computer, unpack it to target (GCLOUD_DIR by default), and check that it runs."""
    name = gcloud_archive_name()
    if not name:
        raise SetupError(f"Google publishes no Google Cloud CLI archive for {platform.system()} {platform.machine()}",
                         "install it with your package manager: https://cloud.google.com/sdk/docs/install")
    target = os.path.abspath(os.path.expanduser(target or GCLOUD_DIR))
    if os.path.isdir(target):
        found = gcloud_in(target)
        if found:
            return found
        if os.listdir(target):
            raise SetupError(f"{target} exists but holds no gcloud", "move that folder aside, or set GPUF_GCLOUD_DIR to another folder")
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    url = f"{GCLOUD_ARCHIVE_BASE}/{name}"
    staging = os.path.join(parent, f".gpuf-gcloud-{uuid.uuid4().hex[:8]}")
    os.makedirs(staging)
    t0 = now()
    try:
        archive = os.path.join(staging, name)
        n, sha = download_file(term, url, archive, ca_bundle)
        expected = GCLOUD_SHA256.strip().lower()
        if expected and sha.lower() != expected:
            os.remove(archive)
            audit("file", op="delete", path=archive, bytes=n, note="sha256 does not match GPUF_GCLOUD_SHA256; the archive is not used")
            raise SetupError(f"the downloaded archive's sha256 is {sha}, not the expected {expected}",
                             "compare GPUF_GCLOUD_SHA256 with the checksum on https://cloud.google.com/sdk/docs/install; if it is current, do not use "
                             "this download and check the network path to dl.google.com")
        term.line(f"   received {n / 1e6:.1f} MB, sha256 {sha}" + (" (matches GPUF_GCLOUD_SHA256)" if expected else
                                                                   " (not compared: GPUF_GCLOUD_SHA256 is unset; trust rests on TLS to dl.google.com)"))
        term.line(f" unpacking into {target} ...")
        need = safe_extract(archive, staging)
        src = os.path.join(staging, "google-cloud-sdk")
        if not os.path.isdir(src):
            raise SetupError("the archive has no google-cloud-sdk folder", "run setup again; if it repeats, install from https://cloud.google.com/sdk/docs/install")
        if os.path.isdir(target):
            os.rmdir(target)
        os.replace(src, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    gcloud = gcloud_in(target)
    if not gcloud:
        raise SetupError(f"no gcloud under {target}/bin after unpacking", "install from https://cloud.google.com/sdk/docs/install")
    rec = {"url": url, "sha256": sha, "sha256_expected": expected or None, "bytes": n, "unpacked_bytes": need, "seconds": round(now() - t0, 1),
           "utc": iso()}
    ver, err = gcloud_works(gcloud)
    py = None
    if not ver and os.name != "nt":
        # Google's macOS archive ships without Python; gcloud then runs on the Python running this script
        ver, err = gcloud_works(gcloud, sys.executable)
        py = sys.executable if ver else None
    if not ver:
        raise SetupError(f"the installed gcloud does not run: {err.splitlines()[-1] if err else 'no message'}",
                         "install Python 3.9 to 3.13 and set CLOUDSDK_PYTHON to it, or install from https://cloud.google.com/sdk/docs/install")
    rec["version"] = ver
    save_setup(gcloud=gcloud, gcloud_install=rec, cloudsdk_python=py)
    term.line(term.s(f" Google Cloud CLI {ver} installed at {target}" + (f" (runs on {py})" if py else ""), "g"))
    offer_path_update(term, ask, gcloud, unattended)
    return gcloud


def headless():
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return True
    if sys.platform.startswith("linux"):
        return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return False


def read_cred_file(path):
    """Type, identity and project of a credential file; its secret is never read into anything printed or stored."""
    try:
        with open(path) as f:
            d = json.load(f)
    except OSError as e:
        return None, f"cannot read {path}: {e.strerror or e}"
    except ValueError:
        return None, f"{path} is not a JSON credential file"
    audit("file", op="read", path=path, bytes=os.path.getsize(path),
          note="credential file: only its type, account and project are used here; the key is passed to gcloud, never stored or shown")
    kind = d.get("type") if isinstance(d, dict) else None
    if kind == "service_account":
        if not d.get("client_email") or not d.get("private_key"):
            return None, f"{path} is an incomplete service-account key (no client_email or private_key)"
        return {"type": kind, "account": d["client_email"], "project": d.get("project_id")}, None
    if kind == "external_account":
        url = d.get("service_account_impersonation_url") or ""
        acct = url.rsplit("/", 1)[-1].split(":")[0] if url else "a workload identity federation principal"
        return {"type": kind, "account": acct, "project": None}, None
    return None, f"{path} is a {kind or 'unrecognized'} file; use a service-account key or a workload identity configuration file"


def sign_in(term, ask, gcloud, config, key_file=None, unattended=False):
    """Sign gcloud in as a person (browser) or with a credential file; returns the gcloud configuration and a project hint."""
    if key_file:
        choice = "key"
    elif unattended:
        raise SetupError("gcloud has no signed-in account and this run is unattended",
                         "pass --key-file KEY.json, or run `python3 gcp_gpu_finder.py setup` once in a terminal")
    else:
        choice = ask.choose("How should gcloud sign in?", [
            {"key": "browser", "label": "As a person, in a web browser (gcloud auth login)",
             "note": "on a machine without a browser it prints a link to open on any device"},
            {"key": "key", "label": "With a service-account key file (JSON)", "note": "best for runs of days: no session time limits"},
            {"key": "stop", "label": "Stop here; I will sign in myself"}], default="browser")
    if choice == "stop":
        raise SetupError("sign-in skipped", "run `gcloud auth login`, or `gcloud auth login --cred-file=KEY.json`, then start this tool again")
    if SESSION["ephemeral"]:
        term.line(term.s(f" this sign-in is kept in the session's memory folder ({SESSION['gcloud_config']}) and deleted when the session ends; "
                         f"{short_path(gcloud_config_dir())} is not changed", "c"))
    if choice == "browser":
        cmd = [gcloud, "auth", "login"] + (["--no-launch-browser"] if headless() else [])
        term.line(term.s(f" running: {' '.join(['gcloud'] + cmd[1:])}", "gr"))
        try:
            t0 = now()
            rc = subprocess.run(cmd, env=gcloud_env(config)).returncode
            audit("cmd", argv=gcloud_argv(gcloud, cmd[1:], config), rc=rc, ms=int((now() - t0) * 1000),
                  withheld="interactive: you saw everything it printed; gcloud keeps the sign-in in its own configuration")
        except OSError as e:
            raise SetupError(f"gcloud could not be started: {e}", INSTALL_HINT)
        if rc != 0:
            raise SetupError("gcloud auth login did not finish", "run setup again and complete the sign-in page, or choose a key file")
        return config, None
    path = key_file or ask.ask("Path to the key file", check=lambda s: read_cred_file(os.path.expanduser(s))[1], flag="--key-file")
    path = os.path.abspath(os.path.expanduser(path))
    info, err = read_cred_file(path)
    if err:
        raise SetupError(err, "download a key from the console (IAM, Service accounts, Keys), or pass a workload identity configuration")
    rc, cur, _ = run_gcloud(gcloud, ["config", "get-value", "account", "--quiet"], config)
    cur = cur.splitlines()[-1].strip() if rc == 0 and cur else ""
    use = config
    if cur and cur not in ("(unset)", info["account"]):
        # keep the person's own gcloud setup as it is; this tool signs in through its own configuration
        use = SETUP_GCLOUD_CONFIG
        if run_gcloud(gcloud, ["config", "configurations", "describe", use, "--quiet"])[0] != 0:
            rc, out, err = run_gcloud(gcloud, ["config", "configurations", "create", use, "--no-activate", "--quiet"])
            if rc != 0:
                raise SetupError(f"cannot create the gcloud configuration {use}: {(err or out).splitlines()[-1] if (err or out) else rc}", "run setup again")
        term.line(f" {cur} stays active in your own gcloud setup; this tool signs in through the gcloud configuration {use}")
    rc, out, err = run_gcloud(gcloud, ["auth", "login", f"--cred-file={path}", "--quiet"], use)
    if rc != 0:
        last = (err or out).splitlines()[-1] if (err or out) else f"exit {rc}"
        raise SetupError(f"gcloud could not sign in with {path}: {last}",
                         "check that the key is still valid in the console (IAM, Service accounts, Keys) and that the clock of this computer is right")
    term.line(term.s(f" signed in as {info['account']}", "g"))
    if use and use != config and info.get("project"):
        run_gcloud(gcloud, ["config", "set", "project", info["project"], "--quiet"], use)
    return use, info.get("project")


def bootstrap(term, ask, args, unattended, rep):
    """Make sign-in work: find or install gcloud, then sign in; each change is asked for first."""
    with rep.step("Signing in to Google Cloud", "finds the Google Cloud CLI (gcloud), then asks it for a short-lived access token") as s:
        tokens = _bootstrap(term, ask, args, unattended, rep)
        how = {"gcloud": "from `gcloud auth print-access-token`" + (f" acting as {tokens.impersonate}" if tokens.impersonate else "")
                         + (f" in gcloud configuration {tokens.config}" if tokens.config else ""),
               "metadata": "from this VM's metadata server", "env": "from the GPUF_ACCESS_TOKEN variable"}.get(tokens.source, tokens.source)
        s.say(f"access token: {how}; kept in memory only, never shown or written, renewed every {human_dur(TOKEN_REFRESH_S)}")
        s.result(f"signed in as {tokens.account or 'an unnamed account'}" + (f" with gcloud {tokens.gcloud_version}" if tokens.gcloud_version else ""))
    return tokens


def _bootstrap(term, ask, args, unattended, rep):
    src = args.token_source
    if SESSION["ephemeral"] and not SESSION["gcloud_ok"]:
        if src == "gcloud":
            raise SystemExit(f"--token-source gcloud is not possible in this session: {SESSION['why_no_gcloud']}")
        if src == "auto":
            src = "env" if os.environ.get("GPUF_ACCESS_TOKEN") else "metadata"
            rep.say(f"signing in without gcloud ({SESSION['why_no_gcloud']}): " + ("GPUF_ACCESS_TOKEN" if src == "env" else "this VM's metadata server"))
    wants_gcloud = src in ("auto", "gcloud")
    allowed = not unattended or getattr(args, "install_missing", False)
    gcloud, origin = find_gcloud(with_origin=True)
    if wants_gcloud:
        where = {"GPUF_GCLOUD": "named by GPUF_GCLOUD", "remembered by setup": f"remembered in {short_path(SETUP_FILE)}", "PATH": "found on PATH",
                 "installed, not on PATH": "found in a standard install folder, not on PATH"}.get(origin, origin)
        rep.say(f"Google Cloud CLI: {short_path(gcloud)} ({where})" if gcloud else
                "Google Cloud CLI: not found (looked at GPUF_GCLOUD, setup.json, PATH and the standard install folders)")
    if wants_gcloud and gcloud and origin == "installed, not on PATH":
        save_setup(gcloud=gcloud)
        offer_path_update(term, ask, gcloud, unattended)
    tried = set()
    while True:
        try:
            return Tokens(src, args.impersonate_service_account, gcloud=gcloud).resolve()
        except AuthError as e:
            if SESSION["ephemeral"] and not SESSION["gcloud_ok"]:
                term.line(term.s(f"cannot sign in: {e.message}", "r"))
                term.line("fix: set GPUF_ACCESS_TOKEN (for example from `gcloud auth print-access-token` run elsewhere), run on a Compute Engine VM, "
                          "or start a session that keeps files")
                raise SystemExit(1)
            can_fix = wants_gcloud and e.kind in ("gcloud_missing", "not_logged_in", "reauth") and e.kind not in tried
            term.line(term.s(f"cannot sign in: {e.message}", "y" if can_fix and allowed else "r"))
            if not can_fix or not allowed:
                term.line(f"fix: {e.fix}")
                if can_fix:
                    term.line("     unattended runs can do it themselves: add --install-missing, and --key-file KEY.json to sign in")
                raise SystemExit(1)
            tried.add(e.kind)
            try:
                if e.kind == "gcloud_missing":
                    if SESSION["ephemeral"]:
                        # installed in the session's memory folder, so it is gone with the session
                        target = os.path.join(SESSION["ram"], "google-cloud-sdk")
                        q = (f"Install the Google Cloud CLI into memory for this session only ({target})? It is Google's official archive, about "
                             f"100 MB to download and {fnum(GCLOUD_UNPACKED_MB)} MB unpacked in memory, deleted when the session ends.")
                    else:
                        target = os.path.abspath(os.path.expanduser(GCLOUD_DIR))
                        q = (f"Install the Google Cloud CLI into {target} now? It is Google's official archive, about 100 MB to download; "
                             f"no administrator rights are needed.")
                    if not unattended and not ask.yes(q, default=True):
                        term.line(f"fix: {e.fix}")
                        raise SystemExit(1)
                    gcloud = install_gcloud(term, ask, unattended, getattr(args, "ca_bundle", None), target=target)
                else:
                    config, hint = sign_in(term, ask, gcloud, load_setup().get("gcloud_config"), getattr(args, "key_file", None), unattended)
                    save_setup(gcloud=gcloud, gcloud_config=config, key_project=hint)
            except SetupError as se:
                term.line(term.s(f"setup stopped: {se.message}", "r"))
                if se.fix:
                    term.line(f"fix: {se.fix}")
                raise SystemExit(1)


def choose_project(term, ask, api, hint=None, unattended=False):
    """Pick the project from the ones this account can see; the answer is remembered for later runs."""
    projects = []
    try:
        projects = list(api.pages(f"{CRM1}/projects", "projects", {"filter": "lifecycleState:ACTIVE", "pageSize": 500}))
    except ApiError as e:
        term.line(term.s(f" cannot list projects ({classify(e).title}); type the id instead", "y"))
    ids = sorted(p["projectId"] for p in projects)
    if hint and hint not in ids and projects:
        hint = None
    if unattended:
        if hint or len(ids) == 1:
            return hint or ids[0]
        ask._need("Google Cloud project id", "--project")
    if not projects:
        return ask.ask("Google Cloud project id", hint, flag="--project")
    names = {p["projectId"]: p.get("name") for p in projects}
    options = [{"key": i, "label": i, "note": names.get(i) if names.get(i) != i else ""} for i in ids] + \
              [{"key": "", "label": "another project id (type it)"}]
    pick = ask.choose("Which project should the GPUs be in?", options, default=hint or ids[0], flag="--project")
    return pick or ask.ask("Google Cloud project id", None, flag="--project")


def fixable(checks):
    """What setup can act on in a preflight: disabled APIs, unlinked billing, a project with no network."""
    apis = [c.name.split(" ", 1)[1] for c in checks if c.name.startswith("api ") and c.status in ("fail", "warn") and c.detail.startswith("not enabled")]
    billing = any(c.name == "billing" and c.status == "fail" for c in checks)
    network = any(c.name == "networks" and c.status == "warn" and c.detail.startswith("no subnets") for c in checks)
    return apis, billing, network


def enable_services(ctx, services):
    """Enable APIs in one batch and follow Google's operation until it reports them on."""
    t, t0 = ctx.t, now()
    t.line(f" enabling {', '.join(services)} on {ctx.project} ...")
    op = ctx.api.call("POST", f"{SERVICEUSAGE}/projects/{ctx.project}/services:batchEnable", body={"serviceIds": services})
    shown = now()
    while not op.get("done"):
        if now() - t0 >= OP_STALL_S:
            t.line(t.s(f" Google is still enabling after {human_dur(now() - t0)}; it finishes on its own, and the next check sees it", "y"))
            return False
        ctx.api.sleep(SERVICE_POLL_S)
        op = ctx.api.get(f"{SERVICEUSAGE}/{op['name']}")
        if now() - shown >= 30:
            shown = now()
            t.line(t.s(f"   still enabling ({human_dur(now() - t0)})", "gr"))
    if op.get("error"):
        e = op["error"]
        raise ApiError(e.get("code") or 0, e.get("message") or "enabling failed", {"error": e}, url=f"{SERVICEUSAGE}/projects/{ctx.project}/services:batchEnable")
    t.line(t.s(f" enabled in {human_dur(now() - t0)}", "g"))
    ctx.ev.note(f"setup enabled {', '.join(services)} in {now() - t0:.1f} s")
    return True


def billing_guide(ctx):
    """Billing decides who pays, so setup shows how to link it and re-checks instead of linking it itself."""
    t, p = ctx.t, ctx.project
    accts = []
    try:
        accts = [a for a in ctx.api.pages(f"{BILLING}/billingAccounts", "billingAccounts", {"pageSize": 100}) if a.get("open")]
    except ApiError as e:
        ctx.ev.note(f"billing accounts not listed: {classify(e, p).title}")
    heading(ctx, "Billing", f"{p} has no open billing account linked")
    t.line(" Google creates no VM or reservation in a project without one. Linking decides who pays, so this tool shows how and checks again.")
    for a in accts:
        t.line(f"   {a['name'].split('/')[-1]}  {a.get('displayName', '')}")
    t.line(f" link one in the console: {CONSOLE}/billing/linkedaccount?project={p}")
    if accts:
        t.line(f" or run: gcloud billing projects link {p} --billing-account={accts[0]['name'].split('/')[-1]}")
    else:
        t.line(" this account sees no open billing account; ask your billing administrator to link one")
    while ctx.ask.interactive and ctx.ask.yes("Check billing again now?", default=True):
        if ctx.api.get(f"{BILLING}/projects/{p}/billingInfo").get("billingEnabled"):
            t.line(t.s(" billing is linked", "g"))
            return True
        t.line(t.s(" still not linked", "y"))
    return False


def create_network(ctx, name=None):
    """An auto-mode VPC network: one subnet per region and no firewall rules, so nothing outside can reach the VMs."""
    name = name or SETUP_NETWORK
    body = {"name": name, "autoCreateSubnetworks": True, "routingConfig": {"routingMode": "REGIONAL"},
            "description": "created by gcp_gpu_finder setup: auto-mode subnets, no firewall rules"}
    t0 = now()
    ctx.t.line(f" creating the VPC network {name} ...")
    op = ctx.api.wait_op(ctx.api.call("POST", f"{COMPUTE}/projects/{ctx.project}/global/networks", body=body))
    err = op_error(op)
    if err:
        raise err
    ctx.t.line(ctx.t.s(f" network {name} created in {human_dur(now() - t0)}", "g"))
    ctx.ev.note(f"setup created network {name}")
    return name


def fix_environment(ctx, checks):
    """Offer the fixes this tool can make; True when something changed and the checks should run again."""
    t, p = ctx.t, ctx.project
    unattended = not ctx.ask.interactive
    allowed = ctx.opts.get("install_missing")
    if unattended and not allowed:
        return False
    apis, billing, network = fixable(checks)
    changed = False
    if apis:
        uses = dict((s, u) for s, _, u in APIS)
        heading(ctx, "APIs to enable", p)
        for s in apis:
            t.line(f"   {s}  {t.s(uses.get(s, ''), 'gr')}")
        if ctx.caps.get("enable_apis", {}).get("ok") is False:
            t.line(t.s(f" {ctx.tokens.account} cannot enable APIs (serviceusage.services.enable is missing); an administrator runs:", "y"))
            t.line(f"   gcloud services enable {' '.join(apis)} --project {p}")
        elif unattended or ctx.ask.yes(f"Enable {'it' if len(apis) == 1 else 'them'} now? Enabling an API costs nothing; only use is billed.", default=True):
            try:
                changed |= enable_services(ctx, apis)
            except ApiError as e:
                c = classify(e, p)
                t.line(t.s(f" Google refused: {c.title}", "r"))
                t.line(f" fix: {c.fix if c.kind != 'permission' else 'roles/serviceusage.serviceUsageAdmin on the project grants it'}")
    if billing and not unattended:
        changed |= billing_guide(ctx)
    if network:
        heading(ctx, "Network", f"{p} has no VPC network")
        t.line(" VMs need a subnet in their region; reservations do not. setup can create an auto-mode network with one subnet per region and")
        t.line(" no firewall rules, so nothing outside can reach the VMs. Networks cost nothing.")
        if ctx.caps.get("network", {}).get("ok") is False:
            t.line(t.s(f" {ctx.tokens.account} cannot create networks (compute.networks.create is missing); an administrator runs:", "y"))
            t.line(f"   gcloud compute networks create {SETUP_NETWORK} --subnet-mode=auto --project {p}")
        elif unattended or ctx.ask.yes(f"Create the network {SETUP_NETWORK} now?", default=True):
            try:
                create_network(ctx)
                changed = True
            except ApiError as e:
                c = classify(e, p)
                t.line(t.s(f" Google refused: {c.title}", "r"))
                t.line(f" fix: {c.fix}")
    return changed


def checked_environment(ctx, regions=None, subnet=None, offer=True):
    """The preflight, with setup's fixes offered and the checks re-run after each change."""
    checks, fatal = preflight(ctx, regions=regions, subnet=subnet)
    for _ in range(3):
        if not offer or not any(fixable(checks)) or not fix_environment(ctx, checks):
            break
        ctx.t.line(ctx.t.s(" checking again...", "gr"))
        checks, fatal = preflight(ctx, regions=regions, subnet=subnet)
    return checks, fatal


# ------------------------------------------------------------------ the session: kept or ephemeral
def gcloud_config_dir():
    """The folder gcloud keeps its sign-in and settings in."""
    if os.environ.get("CLOUDSDK_CONFIG"):
        return os.path.abspath(os.path.expanduser(os.environ["CLOUDSDK_CONFIG"]))
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "gcloud")
    return os.path.expanduser("~/.config/gcloud")


def mount_types(path="/proc/mounts"):
    """Mount point -> file system type, where the system lists them."""
    out = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                parts = ln.split()
                if len(parts) >= 3:
                    out[parts[1].replace("\\040", " ")] = parts[2]
    except OSError:
        pass
    return out


def ram_base(mounts=None):
    """A folder held in memory that this user can write, as (path, how that is known), or (None, why there is none)."""
    mounts = mount_types() if mounts is None else mounts
    named = os.path.expanduser(EPHEMERAL_DIR) if EPHEMERAL_DIR else None
    for c in ([named] if named else ["/dev/shm", os.environ.get("XDG_RUNTIME_DIR") or ""]):
        if not c or not os.path.isdir(c) or not os.access(c, os.W_OK | os.X_OK):
            if named:
                return None, f"GPUF_EPHEMERAL_DIR={named} is not a folder this user can write"
            continue
        real = os.path.realpath(c)
        mp = max((m for m in mounts if real == m or real.startswith(m.rstrip("/") + "/")), key=len, default=None)
        fs = mounts.get(mp)
        if fs in ("tmpfs", "ramfs"):
            return real, f"{fs} mounted at {mp}, held in memory"
        if named:
            return (None, f"GPUF_EPHEMERAL_DIR={named} is on {fs}, a disk, not memory") if fs else \
                (real, "named by GPUF_EPHEMERAL_DIR; this system cannot confirm it is held in memory")
    return None, "no folder held in memory was found (/dev/shm and $XDG_RUNTIME_DIR are missing or on disk)"


def drop_ram(d):
    """Delete the session's memory folder: gcloud's configuration copy and anything installed for the session."""
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
        if os.path.exists(d):
            sys.stderr.write(f"the ephemeral session's memory folder {d} could not be removed; delete it by hand\n")


def sweep_ram(base):
    """Memory folders of this user's ephemeral sessions that were killed before they could remove their own."""
    gone = []
    for name in sorted(os.listdir(base)):
        m = re.fullmatch(r"gpuf-(\d+)-\w+", name)
        path = os.path.join(base, name)
        if not m or not os.path.isdir(path) or os.stat(path).st_uid != os.getuid():
            continue
        try:
            os.kill(int(m.group(1)), 0)
            continue
        except ProcessLookupError:
            pass
        except PermissionError:
            continue
        shutil.rmtree(path, ignore_errors=True)
        gone.append(name)
    return gone


def start_ephemeral(rep):
    """Make this session write nothing: no audit log, cache, state or report, and gcloud on a copy of its configuration held in memory."""
    SESSION.update(mode="ephemeral", ephemeral=True)
    with rep.step("Starting a session that saves nothing", "no audit log, cache, run state or report is written; gcloud gets a private copy "
                  "of its configuration in memory") as s:
        base, how = ram_base()
        audit("file", op="read", path="/proc/mounts", bytes=0, note="to find a file system held in memory")
        s.say("a folder held in memory: " + (f"{base} ({how})" if base else how))
        if not base:
            SESSION.update(gcloud_ok=False, why_no_gcloud=f"{how}, and gcloud writes its sign-in cache to {short_path(gcloud_config_dir())} each time it runs")
            s.result("gcloud will not be run, so nothing it would write reaches the disk; sign-in uses GPUF_ACCESS_TOKEN or this VM's metadata server", "y")
            return
        gone = sweep_ram(base) if hasattr(os, "getuid") else []
        if gone:
            s.say(f"removed {len(gone)} memory folder(s) left by ephemeral sessions that were killed: {', '.join(gone)}")
        d = tempfile.mkdtemp(prefix=f"gpuf-{os.getpid()}-", dir=base)
        atexit.register(drop_ram, d)
        for name in ("SIGTERM", "SIGHUP"):
            sig = getattr(signal, name, None)
            if sig is not None and signal.getsignal(sig) == signal.SIG_DFL and threading.current_thread() is threading.main_thread():
                def on_stop(signum, frame, name=name):
                    raise SystemExit(f"stopped by {name}; the session's memory folder is removed")
                signal.signal(sig, on_stop)
        cfg = os.path.join(d, "gcloud-config")
        src = gcloud_config_dir()
        if os.path.isdir(src):
            shutil.copytree(src, cfg, ignore=shutil.ignore_patterns("logs"))
            n = sum(len(f) for _, _, f in os.walk(cfg))
            s.say(f"copied gcloud's configuration from {short_path(src)} ({n} files, its sign-in included, its logs left out) to {cfg}; "
                  f"gcloud runs on the copy and {short_path(src)} is not changed")
        else:
            os.makedirs(cfg, mode=0o700)
            s.say(f"gcloud has no configuration at {short_path(src)}; a sign-in made in this session lives in {cfg} only")
        s.say("gcloud is told to write no logs, update checks, survey prompts or usage reports, and Python to write no compiled files")
        SESSION.update(ram=d, ram_how=how, gcloud_config=cfg)
        s.result(f"memory folder {d}, deleted when this session ends")


def choose_session(term, ask, args, cmd):
    """Before anything runs: may this session leave anything on this computer? Returns (logged or ephemeral, whether it was asked)."""
    mode = str(getattr(args, "session", None) or SESSION_MODE or "ask").lower()
    if mode not in ("ask", "logged", "ephemeral"):
        raise SystemExit(f"--session {mode!r} is not one of ask, logged, ephemeral")
    no_eph = ("resuming a saved run must keep its state on disk up to date, or a later resume would hunt again for capacity this session "
              "obtains" if cmd == "resume" else None)
    if mode == "ephemeral" and no_eph:
        raise SystemExit(f"--session ephemeral is not possible with resume: {no_eph}")
    if mode != "ask":
        return mode, False
    if not ask.interactive:
        raise SystemExit("before anything runs, an unattended session must say whether it may leave files on this computer: "
                         "pass --session logged or --session ephemeral, or set GPUF_SESSION")
    t = term
    base, how = ram_base()
    t.line(t.s(f"GCP GPU Finder {VERSION}", "h") + t.s(f"  {cmd}", "gr"))
    t.line(rule(t))
    t.line("  Before anything runs, choose whether this session may leave anything on this computer.")
    t.line("")
    t.line(t.s("  Keep logs and files", "b") + f": the audit log of every step, caches of what Google returned, and each run's state, in {short_path(HOME)}.")
    t.line(t.s("    A run can then be resumed after a stop or a crash, released or checked by its id, and its log read back with `log`.", "gr"))
    t.line("")
    t.line(t.s("  Ephemeral", "b") + ": this tool writes no file: no audit log, cache, run state or report. The screen is the only record.")
    if base:
        t.line(t.s(f"    gcloud runs on a private copy of its configuration in {base} ({how}): its sign-in cache, and a gcloud installed for", "gr"))
        t.line(t.s(f"    the session, never reach the disk, and {short_path(gcloud_config_dir())} is not changed. The copy is deleted when the session ends.", "gr"))
    else:
        t.line(t.s(f"    {how}. gcloud writes to its own folder each time it runs, so it is not run: sign-in uses GPUF_ACCESS_TOKEN or a VM's metadata server.", "gr"))
    t.line(t.s("    Caches from earlier sessions are read, never written. Capacity obtained is real and billed, and carries the label", "gr"))
    t.line(t.s("    gpu-finder-run=<run id>: `release RUN_ID --project P` finds and deletes it by that label. A stopped run cannot be resumed.", "gr"))
    opts = [{"key": "logged", "label": "Keep logs and files", "note": f"in {short_path(HOME)}"},
            {"key": "ephemeral", "label": "Ephemeral: save nothing, log nothing", "note": "everything lives in memory and is gone when this session ends",
             "disabled": no_eph}]
    return ask.choose("Before anything runs: may this session leave anything on this computer?", opts, default=None, flag="--session"), True


# ------------------------------------------------------------------ commands
def setup(args, cmd):
    term = Term(plain=args.plain, theme=getattr(args, "theme", None))
    atexit.register(term.restore)
    if term.tty and not args.yes:
        term.paint_screen()
    interactive = term.tty and not args.yes and not (cmd in ("run",) and args.config and args.yes)
    if args.config and args.yes:
        interactive = False
    ask = Prompter(term, interactive)
    verbosity, log_level = screen_level(args), args.log_level or LOG_LEVEL
    if log_level not in ("normal", "detailed", "trace"):
        raise SystemExit(f"GPUF_LOG_LEVEL={log_level!r} is not one of normal, detailed, trace")
    # the first question, before anything is read, written or called
    mode, asked = choose_session(term, ask, args, cmd)
    SESSION["mode"] = mode
    stop = Stopper(term)
    log_path = None if mode == "ephemeral" else os.path.join(HOME, "logs", f"{cmd}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{os.getpid()}.jsonl")
    events = Events(log_path, log_level=log_level)
    AUDIT[0] = events
    rep = Report(term, events, verbosity)
    events.write("session", cmd=cmd, version=VERSION, argv=sys.argv[1:], python=sys.version.split()[0], platform=sys.platform,
                 user=os.environ.get("USER") or os.environ.get("USERNAME"), cwd=os.getcwd(), home=HOME, verbosity=verbosity, log_level=log_level,
                 session=mode)
    show_session(term, rep, cmd, log_path, verbosity, log_level, titled=not asked)
    if mode == "ephemeral":
        start_ephemeral(rep)
    tokens = bootstrap(term, ask, args, unattended=not interactive, rep=rep)
    gov = Governor()
    up = False if args.no_user_project else (True if args.user_project else None)
    api = Api(tokens, gov, events, project=None, ca_bundle=args.ca_bundle or os.environ.get("GPUF_CA_BUNDLE") or os.environ.get("REQUESTS_CA_BUNDLE"),
              user_project=up, stopper=stop)
    remembered = load_setup()
    if args.project:
        project, why = args.project, "from --project"
    elif tokens.default_project:
        project, why = tokens.default_project, "gcloud's default project, from `gcloud config get-value project`" if tokens.source == "gcloud" \
            else f"the project of the {tokens.source} credentials"
    elif remembered.get("project"):
        project, why = remembered["project"], f"remembered in {short_path(SETUP_FILE)}"
    else:
        with rep.step("Choosing the project", "lists the projects this account can see (Resource Manager API, projects.list)") as s:
            project = choose_project(term, ask, api, hint=remembered.get("key_project"), unattended=not interactive)
            save_setup(project=project)
            s.result(f"{project}, " + (f"remembered in {short_path(SETUP_FILE)} for later runs" if not SESSION["ephemeral"] else
                                       "for this session only") + "; --project overrides it")
        why = "chosen now"
    rep.say(f"project: {project}, {why}")
    if up is not False and tokens.is_person():
        rep.say(t_dim(term, "API calls name this project as their quota project (X-Goog-User-Project), as Google requires for a person's sign-in"))
    api.project = project
    opts = {"yes": args.yes, "image": getattr(args, "image", None), "ca_bundle": args.ca_bundle, "suggest_roles": True,
            "vm_service_account": getattr(args, "vm_service_account", None), "cmd": cmd,
            "install_missing": getattr(args, "install_missing", False)}
    ctx = Ctx(term, ask, tokens, api, gov, events, project, stop, opts)
    ctx.rep = rep
    return ctx


def t_dim(term, text):
    return term.s(text, "gr")


def screen_level(args):
    """The screen verbosity from --verbosity, -q or -v (repeatable), or GPUF_VERBOSITY."""
    if getattr(args, "verbosity", None):
        v = args.verbosity
    elif getattr(args, "quiet", False):
        v = "quiet"
    elif getattr(args, "v", 0):
        v = "trace" if args.v >= 2 else "detailed"
    else:
        v = VERBOSITY
    if v not in LEVELS:
        raise SystemExit(f"GPUF_VERBOSITY={v!r} is not one of {', '.join(LEVELS)}")
    return v


def show_session(term, rep, cmd, log_path, verbosity, log_level, titled=True):
    """Where this session's audit trail goes and how much the screen shows, before anything else happens."""
    what = {"normal": "steps, checks and notes", "detailed": "steps, checks, notes, and every Google call, file read or written, and command run",
            "trace": "steps, checks, notes, every Google call, file and command, and what each write call sent"}
    screen = {"quiet": "questions, results and problems only", "normal": "every step: what it does, where it reads from, what it found",
              "detailed": "every step, plus each Google call, file and command", "trace": "every step, call, file and command, plus what each write sends"}
    if titled:
        term.line(term.s(f"GCP GPU Finder {VERSION}", "h") + term.s(f"  {cmd}", "gr"))
        term.line(rule(term))
    else:
        term.line("")
    if log_path:
        term.line(f"  session     logged: the audit log, caches and run state are kept in {short_path(HOME)} (--session ephemeral saves nothing)")
        term.line(f"  audit log   {short_path(log_path)}")
    else:
        term.line(f"  session     {term.s('ephemeral', 'c', 'b')}: nothing is saved and nothing is logged; the screen is the only record of this session")
    if rep.level >= 1:
        if log_path:
            term.line(term.s(f"              log level {log_level}: {what[log_level]}", "gr"))
        term.line(f"  screen      {verbosity}: {screen[verbosity]}")
        term.line(term.s("              change with --verbosity quiet|normal|detailed|trace (-q, -v, -vv)"
                         + (f" and --log-level normal|detailed|trace; read a log back with: python3 {os.path.basename(sys.argv[0])} log" if log_path
                            else "; this session keeps no log to read back"), "gr"))
        for i, ln in enumerate(["Google Cloud APIs (*.googleapis.com), each named in the step that calls it",
                                "huggingface.co: a chosen model's public architecture, read with no account or token",
                                "dl.google.com: only when setup installs the Google Cloud CLI",
                                "169.254.169.254, the VM metadata server: only on a Compute Engine VM that signs in without gcloud"]):
            term.line(term.s(("  contacts    " if i == 0 else " " * 14) + ln, "gr"))
        term.line(term.s("  never       an access token, key or password on screen or in a log; credential files are read for their account "
                         "and project only", "gr"))


def cmd_doctor(args):
    ctx = setup(args, "doctor")
    checks, fatal = preflight(ctx, subnet=args.subnet)
    path = os.path.join(HOME, "logs", f"doctor-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json")
    atomic_json(path, ctx.report, 0o644)
    ctx.t.line("")
    if any(fixable(checks)):
        ctx.t.line(f" setup can fix some of these after asking: python3 {os.path.basename(sys.argv[0])} setup")
    where = f"report: {short_path(path)}" if not SESSION["ephemeral"] else "the report was kept in memory only; nothing is saved"
    ctx.t.line(ctx.t.s("Blocking problems found; fix them first." if fatal else "Ready.", "r" if fatal else "g") + f"  {where}")
    return 1 if fatal else 0


def cmd_setup(args):
    ctx = setup(args, "setup")
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    checks, fatal = checked_environment(ctx, subnet=args.subnet)
    path = os.path.join(HOME, "logs", f"setup-{stamp}.json")
    atomic_json(path, dict(ctx.report, setup=load_setup()), 0o644)
    ctx.t.line("")
    where = f"report: {path}" if not SESSION["ephemeral"] else "nothing was saved: what setup chose and installed lasts for this session only"
    if fatal:
        ctx.t.line(ctx.t.s("Blocking problems remain; each FAIL above names its fix.", "r") + f"  {where}")
        return 1
    ctx.t.line(ctx.t.s("Ready.", "g") + f" Start with: python3 {os.path.basename(sys.argv[0])}   {where}")
    return 0


def prepare(args, cmd, confirm=None):
    """Sign in, run the preflight, load the catalog and ask the questions; returns the context, request, run state and, given confirm, its answer."""
    ctx = setup(args, cmd)
    t = ctx.t
    req = new_request()
    if args.config:
        loaded = load_json(args.config)
        if not loaded:
            raise SystemExit(f"cannot read the config file {args.config}")
        req.update(loaded.get("request", loaded))
        ctx.rep.say(f"answers loaded from {short_path(args.config)}; flags given now override them")
    apply_args(req, args)
    run_id = new_run_id()
    rdir = run_dir(run_id)
    ctx.ev.path = os.path.join(rdir, "events.jsonl")
    heading(ctx, f"Run {run_id}", f"project {ctx.project}")
    ctx.rep.say(t.s("this run keeps its state and answers in memory only; nothing is written" if SESSION["ephemeral"] else
                    f"this run's own files go to {short_path(rdir)}: state.json (what is held), config.json (your answers), "
                    f"events.jsonl (its audit trail)", "gr"))
    checks, fatal = checked_environment(ctx, regions=None, subnet=req.get("subnet"))
    if fatal:
        raise SystemExit("blocking problems above; fix them and run again (`doctor` shows the full report)")
    catalog(ctx, refresh=args.refresh)
    # every pass starts from the answers as they were here; going back replays the ones kept on top of this copy
    start = copy.deepcopy(req)
    nav = ctx.ask.begin()
    ctx.ask.dest = "search" if cmd == "run" else "plan"
    while True:
        # skipping to the search is itself an answer, so each pass learns it again from the answers replayed
        ctx.ask.skipping = False
        try:
            out = plan_session(ctx, copy.deepcopy(start), args, run_id, rdir, confirm)
            break
        except GoBack:
            q = nav.rewind()
            rewind_screen(ctx, run_id, f"Back to question {len(nav.replay) + 1}", q, nav)
        except StartOver:
            nav.restart()
            rewind_screen(ctx, run_id, "The questions start over", None, nav)
    ctx.ask.end()
    return (ctx,) + out


def rewind_screen(ctx, run_id, what, question, nav):
    """A clean screen that says where the questions resume; the answers kept are replayed below it."""
    t = ctx.t
    ctx.ev.write("say", msg=f"{what}" + (f": {question}" if question else "") + f"; {len(nav.replay)} earlier answer(s) replayed")
    t.clear()
    heading(ctx, what, question)
    t.line(t.s(f"  Sign-in and the environment checks are unchanged and not repeated (the session log {short_path(ctx.ev.paths[0])} has them). "
               + (f"Your {plural(len(nav.replay), 'earlier answer')} are replayed below; then this question is asked again, with your answer "
                  f"as its default." if question else "Every question is asked again with its usual default."), "gr"))


def plan_session(ctx, req, args, run_id, rdir, confirm):
    """The questions, the plan they lead to and, for a run, the go-ahead: one pass, replayed from the start when the person goes back."""
    req = wizard(ctx, req, args)
    regions, n_pref, dropped = plan_regions(ctx, req)
    if not regions:
        raise SystemExit("no region is left after exclusions and policies")
    refresh_quota(ctx, regions)
    if ctx.blocked_regions:
        regions = [r for r in regions if r not in ctx.blocked_regions]
    prices(ctx)
    regions = rank_fallbacks(ctx, req, regions, n_pref)
    st = new_state(run_id, req, ctx)
    st["regions"] = regions
    with ctx.rep.step("Keeping the plan in memory" if SESSION["ephemeral"] else "Saving the plan",
                      "this session saves nothing" if SESSION["ephemeral"] else f"writes this run's files under {short_path(rdir)}") as s:
        save = Saver(os.path.join(rdir, "state.json"), st)
        save()
        atomic_json(os.path.join(rdir, "config.json"), {"request": req, "project": ctx.project, "version": VERSION}, 0o644)
        s.result("state and answers kept in memory; nothing written" if SESSION["ephemeral"] else f"state.json and config.json in {short_path(rdir)}")
    kind, rows = show_plan(ctx, req, regions, n_pref, dropped)
    st["verdict"] = kind
    mcap = ctx.caps.get(METHOD_CAP[req["method"]]) or {}
    if mcap.get("ok") is False:
        ctx.t.line(ctx.t.s(f" This account cannot run {METHOD_LABEL[req['method']]}: missing {', '.join(mcap['missing'])}. "
                           f"`doctor` names the role to ask for.", "y"))
    if kind in ("quota", "partial"):
        quota_request_flow(ctx, req, regions, st, save)
        if st.get("quota_requests"):
            refresh_quota(ctx, regions)
    save()
    go = confirm(ctx, req, st, save, regions, args) if confirm else None
    return req, st, save, regions, go


def cmd_plan(args):
    ctx, req, st, save, regions, _ = prepare(args, "plan")
    ctx.t.line("")
    if SESSION["ephemeral"]:
        ctx.t.line(f" Plan {st['run_id']} lived in this session only; nothing was saved. To hunt, run the finder again (`python3 "
                   f"{os.path.basename(sys.argv[0])}`) and answer the same questions, or skip them with >>.")
        return 0
    ctx.t.line(f" Saved as run {st['run_id']}. Start hunting with:  python3 {os.path.basename(sys.argv[0])} resume {st['run_id']}")
    ctx.t.line(f" or replay later with:  python3 {os.path.basename(sys.argv[0])} run --config {os.path.join(run_dir(st['run_id']), 'config.json')} --yes --session logged")
    return 0


def confirm_start(ctx, req, st, save, regions, args):
    """The Ready block and the typed go-ahead; False leaves the run saved as planned."""
    t = ctx.t
    shape = ctx.catalog["shapes"][req["shapes"][0]]
    p = price_of(ctx, shape, regions[0], req["method"])
    n = int(math.ceil(req["goal"] / shape["gpu_equiv"] - 1e-9))
    heading(ctx, "Ready")
    t.line(f" {BILLING_NOTE[req['method']]}")
    if p is not None:
        t.line(f" At the goal with {shape['name']} in {regions[0]}: about {money(p * n)}/h" + (f", capped at {money(req['max_usd_h'])}/h" if req.get("max_usd_h") else ""))
    if req["method"] == "calendar" and ctx.ask.interactive:
        req["calendar"]["auto_submit"] = ctx.ask.typed("Submit a calendar-mode reservation automatically when a window is found? "
                                                       "It is a commitment to pay for the whole period.", "commit")
    if args.dry_run:
        t.line(t.s(" dry run: the loop makes one pass and creates nothing", "y"))
    elif not ctx.ask.typed("Start the run now?", "yes", preapproved=args.yes):
        st["status"] = "planned"
        save()
        t.line(" Not started. Nothing was saved: this session keeps no files." if SESSION["ephemeral"] else
               f" Not started. Saved as run {st['run_id']}; start later with: resume {st['run_id']}")
        return False
    return True


def launch(ctx, req, st, save, regions, args):
    """The hunt itself, under the run's lock."""
    lock = RunLock(os.path.join(run_dir(st["run_id"]), "lock")).acquire()
    # the hunt prints its own notes, live on the dashboard or one per line in plain mode
    ctx.rep.hunting = True
    try:
        return Hunt(ctx, req, st, save, regions, dry_run=args.dry_run).run()
    finally:
        ctx.rep.hunting = False
        lock.release()


def start_hunt(ctx, req, st, save, regions, args):
    if not confirm_start(ctx, req, st, save, regions, args):
        return 0
    return launch(ctx, req, st, save, regions, args)


def cmd_run(args):
    ctx, req, st, save, regions, go = prepare(args, "run", confirm=confirm_start)
    return launch(ctx, req, st, save, regions, args) if go else 0


def load_run(args, need_state=True):
    path = os.path.join(run_dir(args.run_id), "state.json")
    st = load_json(path)
    if st:
        if not args.project:
            args.project = st["project"]
        return st, Saver(path, st)
    if need_state:
        raise SystemExit(f"no run {args.run_id} under {os.path.join(HOME, 'runs')}")
    if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{4}", args.run_id):
        raise SystemExit(f"{args.run_id!r} is not a run id (they look like 20261107T191408Z-6a84)")
    # an ephemeral run saved no state; Google Cloud still knows what it created by its label and name prefix
    return {"run_id": args.run_id, "holds": [], "project": args.project, "stateless": True}, (lambda: None)


def cmd_resume(args):
    st, save = load_run(args)
    ctx = setup(args, "resume")
    ctx.ev.path = os.path.join(run_dir(st["run_id"]), "events.jsonl")
    req = st["request"]
    heading(ctx, f"GCP GPU Finder {VERSION}: resume", f"run {st['run_id']}, project {ctx.project}")
    checks, fatal = checked_environment(ctx, regions=st["regions"], subnet=req.get("subnet"))
    if fatal:
        raise SystemExit("blocking problems above")
    catalog(ctx)
    refresh_quota(ctx, st["regions"])
    prices(ctx)
    if st.get("quota_requests"):
        with ctx.rep.step("Checking the quota requests this run filed", "Cloud Quotas API, quotaPreferences.get for each") as s:
            poll_requests(ctx, st)
            s.result(f"{len(st['quota_requests'])} request(s): " + ", ".join(f"{f['qid']} {f.get('state')}" for f in st["quota_requests"]))
    return start_hunt(ctx, req, st, save, st["regions"], args)


def cmd_status(args):
    st, save = load_run(args, need_state=False)
    ctx = setup(args, "status")
    if st.get("stateless"):
        st["project"] = ctx.project
        ctx.rep.say(f"no saved state for run {st['run_id']} on this computer (an ephemeral run keeps none); what Google Cloud holds for it in "
                    f"project {ctx.project} is looked up by its label and name prefix", always=True)
    else:
        ctx.ev.path = os.path.join(run_dir(st["run_id"]), "events.jsonl")
        try:
            catalog(ctx)
        except ApiError as e:
            ctx.rep.say(f"the summary below names GPUs without the catalog: {classify(e, ctx.project).title}", "y", always=True)
        for ln in summary_lines(ctx, st, st["request"]):
            ctx.t.line(ln)
    try:
        if st.get("quota_requests"):
            poll_requests(ctx, st)
            save()
        res = find_run_resources(ctx, st["run_id"])
        heading(ctx, "Live in Google Cloud now")
        rows = [["VM", i["name"], i["_zone"], i.get("status")] for i in res["instances"]]
        rows += [["reservation", r["name"], tail(r.get("zone")), r.get("status")] for r in res["reservations"]]
        rows += [["group", m["name"], m["_scope"], f"size {m.get('targetSize')}"] for m in res["migs"]]
        rows += [["calendar request", f["name"], tail(f.get("zone")), (f.get("status") or {}).get("procurementStatus")] for f in res["futures"]]
        for ln in table(["kind", "name", "where", "status"], rows, ctx.t.width()) if rows else ["  nothing"]:
            ctx.t.line(ln)
    except (ApiError, AuthError) as e:
        ctx.t.line(f" live check failed: {classify(e, ctx.project).title}")
    return 0


def cmd_release(args):
    st, save = load_run(args, need_state=False)
    ctx = setup(args, "release")
    if st.get("stateless"):
        st["project"] = ctx.project
        ctx.rep.say(f"no saved state for run {st['run_id']} on this computer (an ephemeral run keeps none); what it created in project "
                    f"{ctx.project} is found by its label and name prefix", always=True)
    else:
        ctx.ev.path = os.path.join(run_dir(st["run_id"]), "events.jsonl")
    return release_run(ctx, st, save, assume_yes=args.yes)


def audit_logs():
    """Every audit log on this computer: one per session under logs/, one per run under runs/, newest last."""
    found = []
    for d in (os.path.join(HOME, "logs"), os.path.join(HOME, "runs")):
        for root, _, files in os.walk(d):
            found += [os.path.join(root, f) for f in files if f.endswith(".jsonl")]
    return sorted(found, key=lambda p: os.path.getmtime(p))


def cmd_log(args):
    """An audit log, shown as the screen shows it at trace detail, with each record's time."""
    t = Term(plain=False)
    logs = audit_logs()
    if args.list:
        for p in logs:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(p)))}  {size_text(os.path.getsize(p)):>9s}  {short_path(p)}")
        print(f"{len(logs)} audit log(s) under {short_path(HOME)}")
        return 0
    if args.target == "latest":
        sessions = [p for p in logs if os.path.dirname(p) == os.path.join(HOME, "logs")]
        if not sessions:
            raise SystemExit(f"no session audit log under {short_path(os.path.join(HOME, 'logs'))} yet")
        path = sessions[-1]
    elif os.path.isfile(args.target):
        path = args.target
    elif os.path.isfile(os.path.join(run_dir(args.target), "events.jsonl")):
        path = os.path.join(run_dir(args.target), "events.jsonl")
    else:
        raise SystemExit(f"{args.target} is neither latest, a run id under {short_path(os.path.join(HOME, 'runs'))}, nor a log file")
    base = path[: -len(".jsonl")]
    parts = sorted((p for p in os.listdir(os.path.dirname(path)) if os.path.join(os.path.dirname(path), p).startswith(base + ".")
                    and p.endswith(".jsonl.gz")), key=lambda p: int(re.search(r"\.(\d+)\.jsonl\.gz$", p).group(1)))
    lines = []
    for p in parts:
        with gzip.open(os.path.join(os.path.dirname(path), p), "rt", encoding="utf-8") as fh:
            lines += fh.read().splitlines()
    with open(path, encoding="utf-8") as fh:
        lines += fh.read().splitlines()
    kinds = set(csv_list(args.kinds))
    recs, bad = [], 0
    for ln in lines:
        try:
            rec = json.loads(ln)
        except ValueError:
            bad += 1
            continue
        if rec.get("kind") in kinds:
            recs.append(rec)
    if args.last:
        recs = recs[-args.last:]
    t.line(t.s(f"audit log {short_path(path)}", "h") + t.s(f"  {len(recs)} record(s) shown of {len(lines)}; kinds {', '.join(sorted(kinds))}", "gr"))
    if bad:
        t.line(t.s(f"  {bad} line(s) are not valid JSON and are not shown; a line cut short by a crash looks like this", "y"))
    sym = ("\u25b8", "\u2713", "\u00b7") if t.utf else (">", "+", "-")
    for rec in recs:
        when = (rec.get("ts") or "")[11:19]
        t.line(t.s(when, "gr") + "  " + format_record(t, rec, sym, body_chars=0))
    return 0


def cmd_knobs(args):
    for name, (val, default, doc) in sorted(KNOBS.items()):
        print(f"GPUF_{name}={val!r}" + ("" if val == default else f"  (default {default!r})") + f"\n    {doc}")
    return 0


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    g = common.add_argument_group("sign-in and environment")
    g.add_argument("--project", help="Google Cloud project id (default: gcloud's project)")
    g.add_argument("--token-source", default="auto", choices=["auto", "gcloud", "metadata", "env"], help="where access tokens come from")
    g.add_argument("--impersonate-service-account", metavar="SA_EMAIL", help="act as this service account (recommended for runs of days)")
    g.add_argument("--key-file", metavar="KEY_JSON", help="sign gcloud in with this service-account key or workload identity file when it has no account")
    g.add_argument("--install-missing", action="store_true",
                   help="unattended runs install the Google Cloud CLI, sign in with --key-file, enable APIs and create a network when missing "
                        "(interactive runs ask instead)")
    g.add_argument("--ca-bundle", help="CA bundle for HTTPS inspection proxies")
    g.add_argument("--no-user-project", action="store_true", help="never send the X-Goog-User-Project header")
    g.add_argument("--user-project", action="store_true", help="always send X-Goog-User-Project (bill API calls to this project)")
    g.add_argument("--plain", action="store_true", help="line-by-line output instead of the live dashboard")
    g.add_argument("--session", choices=["ask", "logged", "ephemeral"], default=None,
                   help="whether this session may leave files on this computer: logged keeps the audit log, caches and run state; ephemeral saves "
                        "nothing and logs nothing; ask (the default, GPUF_SESSION) asks before anything runs, and unattended runs must name one")
    g.add_argument("--verbosity", choices=list(LEVELS), help="screen detail: quiet, normal (default), detailed (each Google call, file and command), "
                                                             "trace (also what each write sends)")
    g.add_argument("-q", "--quiet", action="store_true", help="same as --verbosity quiet")
    g.add_argument("-v", action="count", default=0, help="-v detailed, -vv trace")
    g.add_argument("--log-level", choices=["normal", "detailed", "trace"], help="audit log detail (default trace: everything, tokens and keys excepted)")
    g.add_argument("--yes", action="store_true", help="unattended: take defaults and flags, confirm the start and pre-approved quota filing")
    g.add_argument("--refresh", action="store_true", help="re-read the catalog now instead of using the cache")
    r = common.add_argument_group("what to find")
    r.add_argument("--config", help="replay a saved config.json")
    r.add_argument("--gpu", help="accelerator type, e.g. nvidia-rtx-pro-6000, nvidia-h100-80gb, nvidia-l4")
    r.add_argument("--count", type=float, help="total GPUs wanted")
    r.add_argument("--shapes", help="allowed machine types, best first, comma separated")
    r.add_argument("--layout", choices=["spread", "cluster"])
    r.add_argument("--cluster-nodes", type=int)
    r.add_argument("--region", help="preferred regions or groups, best first (e.g. asia-southeast1)")
    r.add_argument("--fallback", help="fallback regions or groups (e.g. asia-pacific), or none")
    r.add_argument("--exclude", help="regions or groups never to use (e.g. us,europe), or none")
    r.add_argument("--method", choices=METHODS)
    r.add_argument("--image")
    r.add_argument("--subnet")
    r.add_argument("--vm-service-account", metavar="SA_EMAIL", help="attach this service account to created VMs (default: none attached)")
    r.add_argument("--boot-disk-gb", type=int)
    r.add_argument("--flex-wait", type=int, help=f"seconds one flex-start request waits ({FLEX_WAIT_MIN_S} to {FLEX_WAIT_MAX_S})")
    r.add_argument("--flex-run-hours", type=float, help=f"flex-start run time in hours (up to {FLEX_RUN_MAX_S / 3600:g})")
    r.add_argument("--spot-action", choices=["DELETE", "STOP"])
    r.add_argument("--reservation-hours", type=float, help="auto-delete reservations after this many hours (0 keeps them)")
    r.add_argument("--max-usd-per-hour", type=float)
    r.add_argument("--maintain", action="store_true", help="keep running after the goal, replacing reclaimed capacity")
    r.add_argument("--allow-overshoot", action="store_true", help="allow a node larger than the remaining need")
    r.add_argument("--no-advisor", action="store_true", help="skip Google's capacity advisor scores")
    r.add_argument("--dry-run", action="store_true", help="one pass, no writes")
    r.add_argument("--calendar-start-within-days", type=int)
    r.add_argument("--calendar-min-days", type=int)
    r.add_argument("--calendar-max-days", type=int)
    r.add_argument("--calendar-auto-submit", action="store_true", help="submit a found calendar window without asking (a commitment)")
    q = common.add_argument_group("quota requests (opt-in)")
    q.add_argument("--quota-request", choices=["off", "offer", "file"], help="off; offer (asks before filing); file (with --yes, files unattended)")
    q.add_argument("--quota-region", help="region the request covers (default: the preferred region)")
    q.add_argument("--quota-split", help="split the goal across regions, e.g. asia-southeast1=24,asia-northeast1=16")
    q.add_argument("--contact", help="contact email for Google's quota team")
    q.add_argument("--justification")
    q.add_argument("--use-case", help="one line on what the GPUs are for")
    n = common.add_argument_group("what the GPUs run (sizes the GPU count)")
    n.add_argument("--workload", choices=["model", "product", "none"], help="an NVIDIA model in Model Garden, an NVIDIA product on Google Cloud, or none")
    n.add_argument("--model", "--nemotron", dest="model", help="Model Garden version id or name fragment, e.g. super-120b-a12b-fp8")
    n.add_argument("--product", help="NVIDIA product key or name fragment, e.g. omniverse-dev-ws, bionemo, or a Marketplace image name")
    n.add_argument("--context", type=int, help="longest prompt plus answer per request, in tokens")
    n.add_argument("--peak", "--concurrency", dest="peak", type=int, help="peak requests in flight at the same time, across all copies")
    n.add_argument("--units", type=int, help="model copies, workstations or jobs to run at the same time (when requests cannot be sized)")
    g.add_argument("--theme", choices=["nvidia", "terminal"], help="nvidia: dark grey background with NVIDIA green; terminal: your terminal's colors")
    p = argparse.ArgumentParser(prog="gcp_gpu_finder.py", description="Find NVIDIA GPU capacity on Google Cloud and keep trying until it is held. "
                                "Run with no command for the interactive wizard.", parents=[common])
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("run", parents=[common], help="ask, plan, then hunt until the GPUs are held (the default)")
    sub.add_parser("plan", parents=[common], help="ask and show quota, availability and options; save the plan without hunting")
    sub.add_parser("doctor", parents=[common], help="environment, permission and policy report")
    sub.add_parser("setup", parents=[common], help="install the Google Cloud CLI, sign in, pick the project, enable APIs and create a network, asking first")
    for name, h in (("status", "what a run holds and filed"), ("resume", "continue a saved or stopped run"), ("release", "delete what a run created")):
        sp = sub.add_parser(name, parents=[common], help=h)
        sp.add_argument("run_id")
    sub.add_parser("self-test", help="offline checks of this file's logic")
    sub.add_parser("knobs", help="every GPUF_ setting with its value and default")
    lg = sub.add_parser("log", help="show an audit log as a readable list: the latest session, a run id, or a log file")
    lg.add_argument("target", nargs="?", default="latest", help="latest (default), a run id, or a path to a .jsonl audit log")
    lg.add_argument("--kinds", default="session,step,check,say,note,answer,nav,api,http,file,cmd,body",
                    help="which records to show, comma separated: session, step, check, say, note, answer, nav, api, http, file, cmd, body, attempt")
    lg.add_argument("--last", type=int, default=0, help="only the last N records")
    lg.add_argument("--list", action="store_true", help="list the audit logs on this computer instead")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    cmd = args.cmd or "run"
    if cmd == "self-test":
        return run_self_test()
    if cmd == "knobs":
        return cmd_knobs(args)
    if cmd == "log":
        return cmd_log(args)
    fn = {"run": cmd_run, "plan": cmd_plan, "doctor": cmd_doctor, "setup": cmd_setup, "status": cmd_status, "resume": cmd_resume,
          "release": cmd_release}[cmd]
    try:
        return fn(args)
    except KeyboardInterrupt:
        print("\ncancelled" + ("; nothing was created after the last confirmed step (see the run's state.json)" if cmd in ("run", "resume", "plan") else ""))
        return 130
    except AuthError as e:
        print(f"sign-in problem: {e.message}\nfix: {e.fix}")
        return 1
    except ApiError as e:
        c = classify(e, getattr(args, "project", None))
        print(f"Google refused a request: {c.title}\nfix: {c.fix}")
        return 1


# ------------------------------------------------------------------ self-test (offline; samples are real Google responses, trimmed)
SAMPLE_QUOTA_INFOS = [
    {"quotaId": "GPUS-ALL-REGIONS-per-project", "metric": "compute.googleapis.com/gpus_all_regions", "dimensions": [],
     "quotaIncreaseEligibility": {"isEligible": True}, "dimensionsInfos": [{"details": {"value": "1"}, "applicableLocations": ["global"]}]},
    {"quotaId": "GPUS-PER-GPU-FAMILY-per-project-region", "metric": "compute.googleapis.com/gpus_per_gpu_family", "dimensions": ["gpu_family", "region"],
     "quotaIncreaseEligibility": {"isEligible": True},
     "dimensionsInfos": [{"dimensions": {"gpu_family": "NVIDIA_RTX_PRO_6000", "region": "asia-southeast1"}, "details": {}},
                         {"dimensions": {"gpu_family": "NVIDIA_RTX_PRO_6000"}, "details": {}}, {"details": {"value": "0"}}]},
    {"quotaId": "PREEMPTIBLE-NVIDIA-RTX-PRO-6000-GPUS-per-project-region", "dimensions": ["region"], "quotaIncreaseEligibility": {"isEligible": True},
     "dimensionsInfos": [{"dimensions": {"region": "asia-southeast1"}, "details": {"value": "1"}}, {"details": {"value": "0"}}]},
    {"quotaId": "PREEMPTIBLE-CPUS-per-project-region", "dimensions": ["region"], "quotaIncreaseEligibility": {"isEligible": True},
     "dimensionsInfos": [{"dimensions": {"region": "asia-southeast1"}, "details": {}}]},
    {"quotaId": "CPUS-per-project-region", "dimensions": ["region"], "quotaIncreaseEligibility": {"isEligible": True},
     "dimensionsInfos": [{"dimensions": {"region": "asia-southeast1"}, "details": {"value": "100"}}]},
    {"quotaId": "CPUS-ALL-REGIONS-per-project", "dimensions": [], "quotaIncreaseEligibility": {"isEligible": True},
     "dimensionsInfos": [{"details": {"value": "400"}}]},
    {"quotaId": "HDB-TOTAL-GB-per-project-region", "dimensions": ["region"], "quotaIncreaseEligibility": {"isEligible": True},
     "dimensionsInfos": [{"dimensions": {"region": "asia-southeast1"}, "details": {"value": "4096"}}]},
    {"quotaId": "NVIDIA-L4-GPUS-per-project-region", "dimensions": ["region"], "quotaIncreaseEligibility": {"isEligible": True},
     "dimensionsInfos": [{"details": {"value": "1"}}]},
    {"quotaId": "NVIDIA-T4-GPUS-per-project-region", "dimensions": ["region"], "isFixed": True,
     "quotaIncreaseEligibility": {"isEligible": False, "ineligibilityReason": "NOT_ENOUGH_USAGE_HISTORY"}, "dimensionsInfos": [{"details": {"value": "1"}}]},
    {"quotaId": "ReadsPerMinutePerProjectPerRegion", "dimensions": ["region"], "refreshInterval": "minute",
     "dimensionsInfos": [{"details": {"value": "6000"}}]},
    {"quotaId": "WritesPerMinutePerProjectPerRegion", "dimensions": ["region"], "refreshInterval": "minute",
     "dimensionsInfos": [{"details": {"value": "1500"}}]}]
SAMPLE_SUPER_FP8_CONFIG = {"num_hidden_layers": 88, "num_attention_heads": 32, "num_key_value_heads": 2, "head_dim": 128, "hidden_size": 4096,
                           "max_position_embeddings": 262144, "mamba_num_heads": 128, "mamba_head_dim": 64, "ssm_state_size": 128,
                           "hybrid_override_pattern": "MEMEMEM*EMEMEMEM*EMEMEMEM*EMEMEMEMEM*EMEMEMEMEM*EMEMEMEMEM*EMEMEMEMEM*EMEMEMEM*EMEMEMEME"}
# one Model Garden publisher model version as the Agent Platform API returned it on 2026-11-07, trimmed to the fields this file reads
_MG_ARGS = ["--kv-cache-dtype=fp8", "--gpu-memory-utilization=0.9", "--max-num-seqs=512"]
_MG_ENV = [{"name": "MODEL_ID", "value": "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8"}]


def _mg_cfg(machine, accel, n):
    return {"modelDisplayName": "NVIDIA-Nemotron-3-Super-120B-A12B-FP8", "containerSpec": {"args": [f"--tensor-parallel-size={n}"] + _MG_ARGS, "env": _MG_ENV},
            "dedicatedResources": {"machineSpec": {"machineType": machine, "acceleratorType": accel, "acceleratorCount": n}}}


SAMPLE_MODEL_GARDEN = {"name": "publishers/nvidia/models/nemotron-3", "versionId": "nemotron-3-super-120b-a12b-fp8", "launchStage": "GA",
                       "supportedActions": {"deploy": _mg_cfg("a3-highgpu-2g", "NVIDIA_H100_80GB", 2),
                                            "multiDeployVertex": {"multiDeployVertex": [_mg_cfg("a3-highgpu-2g", "NVIDIA_H100_80GB", 2),
                                                                                        _mg_cfg("a3-ultragpu-8g", "NVIDIA_H200_141GB", 8),
                                                                                        _mg_cfg("g4-standard-96", "NVIDIA_RTX_PRO_6000", 2)]}}}
SAMPLE_ERRORS = {
    "stockout": (200, "ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS: The zone 'projects/p/zones/asia-southeast1-a' does not have enough resources "
                      "available to fulfill the request.  '(resource type:compute)'.", "ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS"),
    "quota": (403, "Quota 'GPUS_ALL_REGIONS' exceeded.  Limit: 1.0 globally.", "QUOTA_EXCEEDED"),
    "rate": (403, "Rate Limit Exceeded", "rateLimitExceeded"),
    "api_disabled": (403, "Cloud Quotas API has not been used in project 1 before or it is disabled.", "SERVICE_DISABLED"),
    "billing": (403, "This API method requires billing to be enabled. Please enable billing on project p.", "BILLING_DISABLED"),
    "permission": (403, "Required 'compute.reservations.create' permission for 'projects/p/zones/us-central1-a/reservations/x'", "forbidden"),
    "region_access": (403, "Permission denied on 'locations/me-central2' (or it may not exist).", "forbidden"),
    "org_policy": (412, "Constraint constraints/gcp.resourceLocations violated for project p. Use of asia-southeast1-a is not allowed.", "conditionNotMet"),
    "vpc_sc": (403, "Request is prohibited by organization's policy. vpcServiceControlsUniqueIdentifier: AbC123", "SECURITY_POLICY_VIOLATED"),
    "user_project": (403, "Caller does not have required permission to use project p.", "USER_PROJECT_DENIED"),
    "reservation_limit": (200, "RESERVATION_CAPACITY_LIMIT_EXCEEDED: Failed to reserve additional capacity for 'G4'.", "RESERVATION_CAPACITY_LIMIT_EXCEEDED"),
    "not_found": (404, "The resource 'projects/p/zones/x-1-a' was not found", "notFound"),
    "invalid": (400, "Invalid value for field 'resource.machineType'.", "invalid"),
    "not_offered": (400, "The service is not available for this project.", "badRequest")}


def _test_ctx():
    """A context with no network: a two-family catalog and the sample quota book."""
    t = Term(plain=True)
    ctx = Ctx(t, Prompter(t, False), None, None, Governor(), Events(None), "p", Stopper(), {})
    shapes = {}

    def add(name, accel, gpus, frac, vcpus, mem, zones, family=None):
        shapes[name] = {"name": name, "base": name, "family": family or name.split("-")[0], "vcpus": vcpus, "mem_gib": mem, "accel": accel, "gpus": gpus,
                        "fraction": frac, "attached": False, "zones": zones, "regions": sorted({region_of(z) for z in zones}),
                        "gpu_equiv": gpus * frac, "boot_disk": BOOT_DISK.get(name.split("-")[0], "pd-balanced"),
                        "gpu_mem_gb": {"nvidia-rtx-pro-6000": 96, "nvidia-h100-80gb": 80, "nvidia-l4": 24}[accel] * gpus * frac}
    z = ["asia-southeast1-a", "asia-southeast1-b"]
    for n, g, f, v in (("g4-standard-24", 1, 0.5, 24), ("g4-standard-48", 1, 1.0, 48), ("g4-standard-96", 2, 1.0, 96), ("g4-standard-192", 4, 1.0, 192),
                       ("g4-standard-384", 8, 1.0, 384)):
        add(n, "nvidia-rtx-pro-6000", g, f, v, v * 3.75, z)
    for n, g in (("a3-highgpu-1g", 1), ("a3-highgpu-2g", 2), ("a3-highgpu-4g", 4), ("a3-highgpu-8g", 8)):
        add(n, "nvidia-h100-80gb", g, 1.0, 26 * g, 234 * g, z)
    add("g2-standard-8", "nvidia-l4", 1, 1.0, 8, 32, z)
    accels = {}
    for a, label, mem, arch in (("nvidia-rtx-pro-6000", "NVIDIA RTX PRO 6000", 96, "Blackwell"), ("nvidia-h100-80gb", "NVIDIA H100", 80, "Hopper"),
                                ("nvidia-l4", "NVIDIA L4", 24, "Ada")):
        accels[a] = {"name": a, "label": label, "mem_gb": mem, "arch": arch, "max_per_vm": 8, "zones": z, "regions": ["asia-southeast1"],
                     "vws": a != "nvidia-h100-80gb",
                     "shapes": sorted((s for s in shapes if shapes[s]["accel"] == a), key=lambda s: shapes[s]["gpu_equiv"])}
    ctx.catalog = {"accels": accels, "shapes": shapes, "regions": ["asia-southeast1", "asia-northeast1", "us-central1", "europe-west4", "australia-southeast2"]}
    book = QuotaBook()
    book.infos = QuotaBook.parse_infos(SAMPLE_QUOTA_INFOS)
    book.families = {"NVIDIA_RTX_PRO_6000"}
    book.caps = {"GPUS_ALL_REGIONS": (1, 0), "CPUS_ALL_REGIONS": (400, 0)}
    book.legacy = {"asia-southeast1": {"CPUS": (100, 0), "PREEMPTIBLE_CPUS": (0, 0), "NVIDIA_L4_GPUS": (1, 0), "PREEMPTIBLE_NVIDIA_L4_GPUS": (1, 0)}}
    ctx.book = book
    ctx.prefs = []
    return ctx


class SelfTest(unittest.TestCase):
    def test_quota_values(self):
        b = _test_ctx().book
        self.assertEqual(b.limit("GPUS-ALL-REGIONS-per-project", {}), 1)
        # Google omits zeros from JSON: an empty details object is a limit of 0, not unknown
        self.assertEqual(b.limit("GPUS-PER-GPU-FAMILY-per-project-region", {"region": "asia-southeast1", "gpu_family": "NVIDIA_RTX_PRO_6000"}), 0)
        self.assertEqual(b.limit("GPUS-PER-GPU-FAMILY-per-project-region", {"region": "us-central1", "gpu_family": "NVIDIA_RTX_PRO_6000"}), 0)
        self.assertIsNone(b.limit("NO-SUCH-QUOTA", {}))
        self.assertTrue(b.info("NVIDIA-T4-GPUS-per-project-region")["fixed"])

    def test_layers_and_headroom(self):
        ctx = _test_ctx()
        g48 = ctx.catalog["shapes"]["g4-standard-48"]
        h = headroom(ctx, g48, "asia-southeast1", "reservation")
        self.assertEqual(h["more"], 0)
        self.assertEqual(h["binding"]["qid"], "GPUS-PER-GPU-FAMILY-per-project-region")
        sp = {L["kind"]: L for L in layers_for(ctx, g48, "asia-southeast1", "spot")}
        self.assertEqual(sp["gpu"]["qid"], "PREEMPTIBLE-NVIDIA-RTX-PRO-6000-GPUS-per-project-region")
        # preemptible CPU quota is 0 here, so spot falls back to standard CPU quota (observed on a live project)
        self.assertEqual(sp["cpu"]["qid"], "CPUS-per-project-region")
        self.assertIn("disk", sp)
        l4 = {L["kind"]: L for L in layers_for(ctx, ctx.catalog["shapes"]["g2-standard-8"], "asia-southeast1", "vms")}
        self.assertEqual(l4["gpu"]["qid"], "NVIDIA-L4-GPUS-per-project-region")
        self.assertEqual(layers_for(ctx, g48, "asia-southeast1", "calendar"), [])

    def test_minimal_quota_request(self):
        ctx = _test_ctx()
        req = dict(new_request(), accel="nvidia-rtx-pro-6000", goal=40.0, shapes=["g4-standard-48"], method="reservation", regions=["asia-southeast1"])
        recs = {r["qid"]: r for r in quota_needs(ctx, req, {"asia-southeast1": 40.0})}
        self.assertEqual(recs["GPUS-ALL-REGIONS-per-project"]["preferred"], 40)
        self.assertEqual(recs["GPUS-ALL-REGIONS-per-project"]["action"], "file")
        self.assertEqual(recs["GPUS-PER-GPU-FAMILY-per-project-region"]["preferred"], 40)
        self.assertEqual(recs["CPUS-per-project-region"]["preferred"], 40 * 48)
        self.assertEqual(recs["CPUS-ALL-REGIONS-per-project"]["preferred"], 40 * 48)
        ctx.prefs = [{"name": "x", "quotaId": "GPUS-PER-GPU-FAMILY-per-project-region", "dimensions": {"region": "asia-southeast1", "gpu_family": "NVIDIA_RTX_PRO_6000"},
                      "reconciling": True, "quotaConfig": {"preferredValue": "8"}}]
        recs = {r["qid"]: r for r in quota_needs(ctx, req, {"asia-southeast1": 40.0})}
        self.assertEqual(recs["GPUS-PER-GPU-FAMILY-per-project-region"]["action"], "pending")
        ctx.prefs[0].update(reconciling=None, quotaConfig={"preferredValue": "8", "grantedValue": "0", "stateDetail": "Quota request denied"})
        recs = {r["qid"]: r for r in quota_needs(ctx, req, {"asia-southeast1": 40.0})}
        self.assertEqual(recs["GPUS-PER-GPU-FAMILY-per-project-region"]["action"], "denied_before")
        todo, stuck = filing_set(list(recs.values()))
        self.assertTrue(todo and stuck)
        ctx.prefs = [{"name": "projects/p/locations/global/quotaPreferences/old", "quotaId": "GPUS-ALL-REGIONS-per-project", "dimensions": {},
                      "quotaConfig": {"preferredValue": "1", "grantedValue": "1"}}]
        recs = {r["qid"]: r for r in quota_needs(ctx, req, {"asia-southeast1": 40.0})}
        self.assertEqual(recs["GPUS-ALL-REGIONS-per-project"]["existing"], "projects/p/locations/global/quotaPreferences/old")
        self.assertEqual(filing_set(list(recs.values()))[1], [])
        req1 = dict(req, goal=1.0)
        recs = {r["qid"]: r for r in quota_needs(_test_ctx(), req1, {"asia-southeast1": 1.0})}
        self.assertEqual(recs["GPUS-ALL-REGIONS-per-project"]["action"], "enough")
        self.assertEqual(recs["CPUS-per-project-region"]["action"], "enough")

    def test_classifier(self):
        for kind, (status, msg, reason) in SAMPLE_ERRORS.items():
            body = {"error": {"message": msg, "errors": [{"reason": reason, "message": msg}]}}
            c = classify(ApiError(status, msg, body, url="https://compute.googleapis.com/compute/v1/projects/p/zones/z/x", reason=None), "p")
            self.assertEqual(c.kind, kind, f"{kind}: got {c.kind} for {msg}")
        c = classify(ApiError(403, SAMPLE_ERRORS["permission"][1], {}, reason="forbidden"), "p")
        self.assertEqual(c.extra.get("perms"), ["compute.reservations.create"])
        self.assertTrue(classify(ApiError(0, "x", {}, reason="NETWORK")).transient)

    def test_bucket(self):
        b = Bucket(("writes", "r"), 100)
        self.assertEqual(b.budget(), int(100 * RATE_FRACTION))
        t0 = 6000.0
        for _ in range(b.budget()):
            self.assertEqual(b.take(t0), 0.0)
        wait = b.take(t0)
        self.assertGreater(wait, 59.0)
        b.penalize(t0 + 1)
        self.assertEqual(b.scale, 0.5)
        self.assertGreater(b.take(t0 + 2), 0)
        self.assertEqual(b.take(t0 + 65), 0.0)

    def test_route(self):
        self.assertEqual(route(f"{COMPUTE}/projects/p/zones/asia-southeast1-a/reservations", "POST"), ("writes", "asia-southeast1"))
        self.assertEqual(route(f"{COMPUTE}/projects/p/zones/asia-southeast1-a/operations/o/wait", "POST"), ("reads", "asia-southeast1"))
        self.assertEqual(route(f"{COMPUTE}/projects/p/aggregated/instances", "GET"), ("greads", ""))
        self.assertEqual(route("https://www.googleapis.com/compute/v1/projects/p/zones/us-central1-b/operations/o", "GET"), ("reads", "us-central1"))
        self.assertEqual(route(f"{QUOTAS}/projects/p/locations/global/quotaPreferences", "POST"), ("api:cloudquotas.googleapis.com", ""))

    def test_model_garden_fit(self):
        kv = kv_profile(SAMPLE_SUPER_FP8_CONFIG)
        self.assertEqual(kv["attn_layers"], 8)
        self.assertEqual(kv["kv_per_token"], 2 * 8 * 2 * 128 * FIT_KV_BYTES)
        ctx = _test_ctx()
        e = parse_model_garden([SAMPLE_MODEL_GARDEN])[0]
        self.assertEqual((e["name"], e["kind"], e["precision"], e["default_machine"]), ("NVIDIA-Nemotron-3-Super-120B-A12B-FP8", "llm", "FP8", "a3-highgpu-2g"))
        self.assertEqual({(c["machine"], c["accel"], c["gpus"]) for c in e["configs"]},
                         {("a3-highgpu-2g", "nvidia-h100-80gb", 2), ("a3-ultragpu-8g", "nvidia-h200-141gb", 8), ("g4-standard-96", "nvidia-rtx-pro-6000", 2)})
        self.assertEqual((e["configs"][0]["kv_dtype"], e["configs"][0]["mem_frac"], e["configs"][0]["max_seqs"]), ("fp8", 0.9, 512))
        info = {"weights_gb": 128.4, "kv": kv}
        rows, notes = mg_fit(ctx, e, 32768, info)
        # one copy needs 2 GPUs in one VM: 1-GPU and half-GPU machine types drop out; H200 is not in this project's catalog
        self.assertEqual(sorted(r["shape"] for r in rows), ["a3-highgpu-2g", "a3-highgpu-4g", "a3-highgpu-8g", "g4-standard-192", "g4-standard-384",
                                                            "g4-standard-96"])
        self.assertTrue(any("a3-ultragpu-8g" in n for n in notes))
        g96 = next(r for r in rows if r["shape"] == "g4-standard-96")
        self.assertEqual((g96["per_copy"], g96["copies_vm"], g96["tested"]), (2, 1, True))
        self.assertEqual(next(r for r in rows if r["shape"] == "g4-standard-384")["copies_vm"], 4)
        seq = per_request_gb(info, 32768, g96["cfg"])
        self.assertAlmostEqual(seq, (kv["kv_per_token"] / FIT_KV_BYTES * 32768 + kv["ssm_per_seq"]) / 1e9)
        self.assertEqual(g96["capacity"], int((2 * (96 * 0.9 - FIT_RUNTIME_GB) - 128.4) // seq))
        plan = plan_units(rows, peak=g96["capacity"] * 3)
        g96 = next(r for r in plan if r["shape"] == "g4-standard-96")
        g384 = next(r for r in plan if r["shape"] == "g4-standard-384")
        self.assertEqual((g96["units"], g96["vms"], g96["gpus_total"]), (3, 3, 6))
        self.assertEqual((g384["vms"], g384["gpus_total"]), (1, 8))
        self.assertEqual(plan[0]["gpus_total"], 6)
        # a context longer than every length Google tested on a GPU removes that GPU
        e2 = dict(e, configs=[dict(c, max_len=4096) if c["accel"] == "nvidia-h100-80gb" else c for c in e["configs"]])
        rows2, notes2 = mg_fit(ctx, e2, 32768, info)
        self.assertFalse(any(r["accel"] == "nvidia-h100-80gb" for r in rows2))
        self.assertTrue(any("4096" in n for n in notes2))
        self.assertEqual(model_precision("nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4"), "NVFP4")

    def test_products_and_images(self):
        ctx = _test_ctx()
        g_series = fit_rows(ctx, {a: 1 for a in ctx.catalog["accels"]}, family=r"g\d")
        self.assertEqual({r["accel"] for r in g_series}, {"nvidia-rtx-pro-6000", "nvidia-l4"})
        self.assertNotIn("g4-standard-24", {r["shape"] for r in g_series})
        bio = plan_units(fit_rows(ctx, {"nvidia-l4": 2, "nvidia-h100-80gb": 1}), units=2)
        self.assertEqual((bio[0]["shape"], bio[0]["vms"], bio[0]["gpus_total"]), ("a3-highgpu-1g", 2, 2))
        self.assertFalse(any(r["accel"] == "nvidia-l4" for r in bio))
        lic = "https://www.googleapis.com/compute/v1/projects/nvidia-ngc-public/global/licenses/nvidia-gpu-optimized-vmi"
        osl = "https://www.googleapis.com/compute/v1/projects/ubuntu-os-cloud/global/licenses/ubuntu-2404-lts"
        imgs = [{"name": "nvidia-gpu-cloud-vmi-base-2026-6-1-x86-64", "licenses": [osl, lic], "creationTimestamp": "2026-06-23T00:00:00", "diskSizeGb": "128",
                 "architecture": "X86_64", "selfLink": "https://www.googleapis.com/compute/v1/projects/nvidia-ngc-public/global/images/a"},
                {"name": "nvidia-gpu-cloud-vmi-base-2026-11-1-x86-64", "licenses": [osl, lic], "creationTimestamp": "2026-11-05T00:00:00", "diskSizeGb": "128",
                 "architecture": "X86_64", "selfLink": "https://www.googleapis.com/compute/v1/projects/nvidia-ngc-public/global/images/b"},
                {"name": "internal-nvidia-canary-vmi-1-0-0-x86-64", "licenses": [lic], "creationTimestamp": "2026-11-06T00:00:00"}]
        p = group_marketplace(imgs, {lic: {"name": "nvidia-gpu-optimized-vmi", "description": "nvidia-gpu-optimized-vmi", "chargesUseFee": False}})
        self.assertEqual((len(p), p[0]["image"], p[0]["name"], p[0]["disk_gb"], p[0]["os"]),
                         (1, "projects/nvidia-ngc-public/global/images/b", "NVIDIA GPU Optimized VMI", 128, "ubuntu-2404-lts"))
        g = group_images("deeplearning-platform-release", [
            {"family": "common-cu129-ubuntu-2404-nvidia-580", "creationTimestamp": "2026-10-29", "architecture": "X86_64", "guestOsFeatures": [{"type": "GVNIC"}],
             "description": "Google, Deep Learning VM with CUDA, M132, Ubuntu 24.04, CUDA 12.9"},
            {"family": "pytorch-2-9-cu129-ubuntu-2404-nvidia-580", "creationTimestamp": "2026-10-30", "architecture": "X86_64", "guestOsFeatures": [{"type": "GVNIC"}],
             "description": "Google, Deep Learning VM with CUDA + Pytorch, M132, Ubuntu 24.04"},
            {"family": "tpu-thing", "creationTimestamp": "2026-10-30"}])
        self.assertEqual((g["label"], len(g["families"]), g["families"][0]["image"]),
                         ("Deep Learning VM with CUDA (Google), NVIDIA driver installed", 2,
                          "projects/deeplearning-platform-release/global/images/family/pytorch-2-9-cu129-ubuntu-2404-nvidia-580"))
        self.assertEqual(serving_args(["--tp=4", "--context-length=262144", "--x=y"]), {"tp": 4, "max_len": 262144})

    def test_theme(self):
        self.assertEqual(xterm256(hex_rgb("#76b900")), 106)
        self.assertEqual(xterm256(hex_rgb("#1a1a1a")), 234)
        t = Term(plain=True)
        self.assertEqual(t.s("x", "g"), "x")
        t.color, t.depth = True, 24
        t.base = RESET + f"\x1b[{t._sgr(48, '#1a1a1a')}m"
        t.painted, t.codes = True, dict(t.CODES, g=t._sgr(38, "#76b900"))
        self.assertEqual(t.s("ok", "g"), "\x1b[38;2;118;185;0mok" + t.base)
        self.assertEqual(visible_len(t.s("ok", "g")), 2)

    def test_navigation(self):
        t = Term(plain=True)
        t.out = io.StringIO()
        feed = []
        ask = Prompter(t, True, reader=lambda prompt: feed.pop(0))
        opts = [{"key": "x", "label": "x"}, {"key": "y", "label": "y"}]

        def session():
            a = ask.choose("first", opts, default="x")
            b = ask.ask("second", "5")
            c = ask.yes("third", False) if b == "6" else None
            return a, b, c

        def run(lines):
            feed[:] = lines
            nav = ask.begin()
            while True:
                try:
                    return session(), nav
                except GoBack:
                    nav.rewind()
                except StartOver:
                    nav.restart()
        # back from the third question replays the first answer and offers 6 again; 7 then skips the third question
        res, nav = run(["2", "6", "<", "7"])
        self.assertEqual(res, ("y", "7", None))
        self.assertEqual(nav.answers, [("first", "y"), ("second", "7")])
        # Enter at the question gone back to keeps the earlier answer
        res, nav = run(["2", "6", "<", "", "y"])
        self.assertEqual(res, ("y", "6", True))
        # back at the first question is refused in place; start over discards everything
        res, nav = run(["<", "1", "?", "<<", "2", "8"])
        self.assertEqual((res, nav.answers), (("y", "8", None), [("first", "y"), ("second", "8")]))
        self.assertIn("this is the first question", t.out.getvalue())
        self.assertIn("Your answers so far", t.out.getvalue())
        # once something was done in Google Cloud, neither back nor start over can pass it
        feed[:] = ["1", "<", "<<", "6", "n"]
        nav = ask.begin()
        ask.choose("first", opts, default="x")
        ask.lock("quota requests were filed")
        self.assertEqual(ask.ask("second", "5"), "6")
        self.assertEqual(t.out.getvalue().count("not possible here: quota requests were filed"), 2)
        # a replayed answer that no longer fits stops the replay and the question is asked again
        nav = ask.begin()
        nav.replay = [("first", "z")]
        feed[:] = ["2"]
        self.assertEqual(ask.choose("first", opts, default="x"), "y")
        self.assertEqual((nav.replay, nav.answers), ([], [("first", "y")]))
        self.assertIn("no longer fits", t.out.getvalue())
        ask.end()
        self.assertIsNone(ask.nav)

    def test_skip_words(self):
        t = Term(plain=True)
        t.out = io.StringIO()
        feed = []
        ask = Prompter(t, True, reader=lambda prompt: feed.pop(0))
        opts = [{"key": "x", "label": "X one"}, {"key": "y", "label": "Y two"}, {"key": "z", "label": "Z off", "disabled": "not here"}]
        alt_none = {"none": ("y", "no workload"), "all": (None, "one per run")}

        def session():
            a = ask.choose("kind", opts, default="x", alt=alt_none)
            b = ask.ask("disk", "100", check=lambda v: None if v.isdigit() else "a number", alt={"skip": ("20", "the smallest")})
            c = ask.multi("shapes", opts, default=["x"])
            d = ask.ask("contact", None)
            e = ask.yes("keep", False)
            return a, b, c, d, e

        def run(lines):
            feed[:] = lines
            nav = ask.begin()
            while True:
                try:
                    return session(), nav
                except GoBack:
                    nav.rewind()
        # all is refused where not offered, none and skip take what the question declares, all at a list takes every enabled option
        res, nav = run(["all", "none", "skip", "all", "me@x.org", ">"])
        self.assertEqual(res, ("y", "20", ["x", "y"], "me@x.org", False))
        self.assertIn("all: one per run", t.out.getvalue())
        self.assertEqual([a for _, a in nav.answers], ["none", "skip", "all", "me@x.org", "skip"])
        # skip to search answers every later question with its skip answer, stops at one without any, then goes on
        res, nav = run(["1", ">>", "you@x.org"])
        self.assertEqual(res, ("x", "20", ["x"], "you@x.org", False))
        self.assertTrue(ask.skipping)
        self.assertIn("skip to search stops at this question (this question has no default; answer it)", t.out.getvalue())
        self.assertEqual([a for _, a in nav.answers], ["x", ">>", "you@x.org"])
        # going back from the question that stopped the skip returns to where >> was typed, asked with its usual default
        feed[:] = ["1", ">>", "<", "", "", "c@x.org", ""]
        nav = ask.begin()
        out = None
        while out is None:
            try:
                out = session()
            except GoBack:
                nav.rewind()
                ask.skipping = False
        self.assertEqual(out, ("x", "100", ["x"], "c@x.org", False))
        self.assertEqual([a for _, a in nav.answers], ["x", "100", "x", "c@x.org", "n"])
        # a confirmation is never skipped
        feed[:] = ["skip", ">>", "yes"]
        ask.begin()
        self.assertTrue(ask.typed("Start?", "yes"))
        self.assertEqual(t.out.getvalue().count("this confirmation is never skipped"), 2)
        # outside the planning questions the words are ordinary answers unless the question offers them
        ask.end()
        feed[:] = ["skip"]
        self.assertEqual(ask.ask("name", None), "skip")

    def test_footer(self):
        t = Term(plain=True)
        t.out = io.StringIO()
        t.tty, t.plain, t.utf = True, False, False
        t._size = lambda: (30, 100)
        ask = Prompter(t, True, reader=lambda prompt: "")
        ask.begin()
        lines = ask.footer_lines(100)
        self.assertEqual(lines[0], "-" * 99)
        self.assertIn("< back", lines[1])
        self.assertIn(">> skip to search", lines[1])
        self.assertTrue(lines[1].rstrip().endswith("question 1"))
        t.footer_ensure()
        out = t.out.getvalue()
        # the last two rows are fenced off from scrolling and the bar is drawn there, cursor saved and restored around it
        self.assertIn("\x1b7\x1b[1;28r\x1b8", out)
        self.assertIn("\x1b[29;1H", out)
        self.assertEqual(t.footer_rows, (30, 2))
        t.dash_start()
        self.assertIsNone(t.footer_rows)
        self.assertIn("\x1b7\x1b[r\x1b[29;1H", t.out.getvalue())
        t.dash_stop()
        t.footer_ensure()
        t.restore()
        self.assertIsNone(t.footer_rows)

    def test_session(self):
        saved, named = dict(SESSION), globals()["EPHEMERAL_DIR"]
        try:
            with tempfile.TemporaryDirectory() as d:
                SESSION.update(ephemeral=True, ram=None, mem={}, gcloud_ok=True)
                p = os.path.join(d, "sub", "x.json")
                atomic_json(p, {"a": 1})
                # an ephemeral session writes nothing outside its memory folder: the file lives in SESSION["mem"] and reads back from there
                self.assertFalse(os.path.exists(os.path.join(d, "sub")))
                self.assertEqual(load_json(p), {"a": 1})
                self.assertIn("kept in memory", saved_where(p))
                atomic_json(SETUP_FILE, {"gcloud": "/m/gcloud"})
                self.assertEqual(load_setup()["gcloud"], "/m/gcloud")
                ram = os.path.join(d, "ram")
                os.makedirs(ram)
                SESSION.update(ram=ram, gcloud_config=os.path.join(ram, "gcloud-config"))
                atomic_json(os.path.join(ram, "y.json"), {"b": 2})
                self.assertTrue(os.path.exists(os.path.join(ram, "y.json")))
                ev = Events(None)
                ev.path = os.path.join(d, "run", "events.jsonl")
                ev.note("x")
                self.assertEqual((ev.paths, os.path.exists(os.path.join(d, "run"))), ([], False))
                env = gcloud_env()
                self.assertEqual((env["CLOUDSDK_CONFIG"], env["CLOUDSDK_CORE_DISABLE_FILE_LOGGING"], env["PYTHONDONTWRITEBYTECODE"]),
                                 (os.path.join(ram, "gcloud-config"), "true", "1"))
                SESSION.update(gcloud_ok=False, why_no_gcloud="no memory folder")
                self.assertRaises(AuthError, gcloud_env)
                self.assertTrue(RunLock(os.path.join(d, "lock", "x")).acquire())
                self.assertFalse(os.path.exists(os.path.join(d, "lock")))
                # only a memory file system is accepted for the session's folder
                globals()["EPHEMERAL_DIR"] = d
                real = os.path.realpath(d)
                self.assertEqual(ram_base({real: "tmpfs"})[0], real)
                self.assertIsNone(ram_base({real: "ext4"})[0])
                self.assertIn("cannot confirm", ram_base({})[1])
                os.makedirs(os.path.join(d, "gpuf-999999999-abc"))
                self.assertEqual(sweep_ram(d), ["gpuf-999999999-abc"])
                self.assertEqual(sweep_ram(d), [])
            t = Term(plain=True)
            t.out = io.StringIO()
            ask = Prompter(t, False)
            self.assertRaises(SystemExit, choose_session, t, ask, argparse.Namespace(session="ask"), "run")
            self.assertRaises(SystemExit, choose_session, t, ask, argparse.Namespace(session="ephemeral"), "resume")
            self.assertEqual(choose_session(t, ask, argparse.Namespace(session="ephemeral"), "plan"), ("ephemeral", False))
        finally:
            SESSION.clear()
            SESSION.update(saved)
            globals()["EPHEMERAL_DIR"] = named

    def test_audit_trail(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "session.jsonl"), os.path.join(d, "run", "events.jsonl")
            ev = Events(a, log_level="normal")
            seen = []
            ev.printer = seen.append
            ev.write("step", phase="start", title="Reading")
            ev.write("api", m="GET", host="compute.googleapis.com", path="/compute/v1/projects/p/zones", status=200, ms=5, bytes=10)
            ev.path = b
            ev.note("hello")
            kinds = [json.loads(x)["kind"] for x in open(a)]
            # log level normal keeps steps and notes but not each call; the screen still sees every record
            self.assertEqual(kinds, ["step", "session", "note"])
            self.assertEqual([json.loads(x)["kind"] for x in open(b)], ["session", "note"])
            self.assertEqual([r["kind"] for r in seen], ["step", "api", "session", "note"])
            blocker = os.path.join(d, "a-file")
            open(blocker, "w").close()
            ev.paths.append(os.path.join(blocker, "events.jsonl"))
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                ev.write("note", msg="x")
                ev.write("note", msg="y")
            self.assertEqual(len(ev.broken), 1)
            self.assertEqual(err.getvalue().count("audit log cannot be written"), 1)
            if os.name != "nt":
                # the log and the folders made for it belong to this user alone; a rotation keeps that and leaves the live file empty
                self.assertEqual(os.stat(a).st_mode & 0o777, 0o600)
                self.assertEqual(os.stat(os.path.dirname(b)).st_mode & 0o777, 0o700)
                ev.rotate(b)
                gz = os.path.join(d, "run", "events.1.jsonl.gz")
                self.assertEqual(os.stat(gz).st_mode & 0o777, 0o600)
                self.assertEqual(os.path.getsize(b), 0)
                with gzip.open(gz, "rt") as fh:
                    self.assertEqual([json.loads(x)["kind"] for x in fh], ["session", "note", "note", "note"])
                lock = RunLock(os.path.join(d, "lock", "run.lock")).acquire()
                self.assertEqual(os.stat(lock.path).st_mode & 0o777, 0o600)
                lock.release()
        t = Term(plain=True)
        line = format_record(t, {"kind": "api", "m": "POST", "host": "cloudresourcemanager.googleapis.com",
                                 "path": "/v1/projects/p:getEffectiveOrgPolicy", "sent": '{"constraint":"constraints/gcp.resourceLocations"}',
                                 "status": 404, "ms": 3, "bytes": 0})
        self.assertIn('p:getEffectiveOrgPolicy  sent {"constraint":"constraints/gcp.resourceLocations"}  404', line)
        self.assertIn("! Reading: none", format_record(t, {"kind": "step", "phase": "done", "title": "Reading", "result": "none", "outcome": "warning"}))
        self.assertIn("ran   gcloud auth print-access-token", format_record(t, {"kind": "cmd", "argv": ["gcloud", "auth", "print-access-token"], "rc": 0,
                                                                                 "withheld": "output not recorded"}))
        self.assertEqual(api_path("compute.googleapis.com", "/compute/v1/projects/p/zones/a/reservations"), "zones/a/reservations")
        self.assertEqual(check_source("api compute.googleapis.com"), "Service Usage API, services.get")
        self.assertEqual(check_source("networks"), "Compute Engine API, subnetworks.aggregatedList")
        self.assertEqual(check_source("network"), "Resource Manager API, projects.get")
        self.assertEqual(check_source("nothing like it"), "")

    def test_regions_and_policy(self):
        known = {"asia-southeast1", "asia-northeast1", "australia-southeast2", "us-central1", "europe-west4"}
        self.assertEqual(expand_regions(["asia-southeast1", "asia-pacific"], known), ["asia-southeast1", "asia-northeast1", "australia-southeast2"])
        self.assertEqual(expand_regions(["us"], known), ["us-central1"])
        self.assertRaises(SystemExit, expand_regions, ["mars"], known)
        pol = {"listPolicy": {"allowedValues": ["in:asia-locations"]}}
        self.assertTrue(location_allowed("asia-southeast1", pol))
        self.assertFalse(location_allowed("us-central1", pol))
        self.assertTrue(location_allowed("us-central1", {"listPolicy": {"allValues": "ALLOW"}}))

    def test_methods_and_names(self):
        ctx = _test_ctx()
        s = ctx.catalog["shapes"]
        self.assertFalse(method_allows("vms", s["a3-highgpu-1g"])[0])
        self.assertTrue(method_allows("spot", s["a3-highgpu-1g"])[0])
        self.assertTrue(method_allows("calendar", s["a3-highgpu-8g"])[0])
        self.assertFalse(method_allows("calendar", s["g4-standard-48"])[0])
        self.assertFalse(method_allows("flex", s["a3-highgpu-8g"])[0])
        rid = "20261107T031114Z-ab12"
        self.assertEqual(run_short(rid), "11070311ab12"[-8:])
        n = pref_id(rid, {"qid": "GPUS-PER-GPU-FAMILY-per-project-region", "dims": {"region": "australia-southeast2", "gpu_family": "NVIDIA_RTX_PRO_6000"}})
        self.assertLessEqual(len(n), 63)
        self.assertRegex(n, r"^[a-z][a-z0-9-]*$")
        self.assertEqual(safe_name("Gpuf", "--A_b", limit=63), "gpuf-a-b")

    def test_targets_and_verdict(self):
        ctx = _test_ctx()
        req = dict(new_request(), accel="nvidia-rtx-pro-6000", goal=40.0, shapes=["g4-standard-48", "g4-standard-96"], method="reservation",
                   regions=["asia-southeast1"])
        tg = build_targets(ctx, req, ["asia-southeast1"])
        self.assertEqual([x["key"] for x in tg][:2], ["reservation|g4-standard-48|asia-southeast1-a", "reservation|g4-standard-48|asia-southeast1-b"])
        rows = quota_summary(ctx, req, ["asia-southeast1"])
        kind, text = verdict(ctx, req, ["asia-southeast1"], rows)
        self.assertEqual(kind, "quota")
        req["method"] = "spot"
        kind, text = verdict(ctx, req, ["asia-southeast1"], quota_summary(ctx, req, ["asia-southeast1"]))
        self.assertEqual(kind, "partial")

    def test_setup_helpers(self):
        self.assertEqual(gcloud_archive_name("Linux", "x86_64"), "google-cloud-cli-linux-x86_64.tar.gz")
        self.assertEqual(gcloud_archive_name("Linux", "aarch64"), "google-cloud-cli-linux-arm.tar.gz")
        self.assertEqual(gcloud_archive_name("Darwin", "arm64"), "google-cloud-cli-darwin-arm.tar.gz")
        self.assertEqual(gcloud_archive_name("Windows", "AMD64"), "google-cloud-cli-windows-x86_64-bundled-python.zip")
        self.assertIsNone(gcloud_archive_name("Linux", "i686"))
        checks = [Check("api compute.googleapis.com", "fail", "not enabled: everything"), Check("api iam.googleapis.com", "ok", "enabled: role suggestions"),
                  Check("api cloudquotas.googleapis.com", "warn", "not enabled: quota limits"), Check("billing", "fail", "billing is not enabled"),
                  Check("networks", "warn", "no subnets: VMs cannot be created")]
        self.assertEqual(fixable(checks), (["compute.googleapis.com", "cloudquotas.googleapis.com"], True, True))
        self.assertFalse(any(fixable([Check("networks", "ok", "3 subnet(s) in 3 region(s)")])))
        e = gcloud_auth_error("ERROR: (gcloud.auth.print-access-token) Your current active account [nobody@example.com] does not have any valid "
                              "credentials\nPlease run:\n\n  $ gcloud auth login\n\nto obtain new credentials.\n\nFor service account, please activate "
                              "it first:\n\n  $ gcloud auth activate-service-account ACCOUNT", None)
        self.assertEqual((e.kind, "nobody@example.com" in e.message), ("not_logged_in", True))
        self.assertTrue(gcloud_auth_error("ERROR: (gcloud.x) boom\nhint line", None).message.endswith("boom"))
        if os.name != "nt":
            # a token call that fails after printing something token-like on stdout must not carry that text into the printed error
            with tempfile.TemporaryDirectory() as d:
                fake = os.path.join(d, "gcloud")
                with open(fake, "w") as fh:
                    fh.write("#!/bin/sh\necho ya29.not-a-real-token-but-shaped-like-one\necho 'ERROR: (gcloud.auth.print-access-token) boom' >&2\nexit 1\n")  # gitleaks:allow
                os.chmod(fake, 0o700)
                with self.assertRaises(AuthError) as cm:
                    Tokens(source="gcloud", gcloud=fake, config="")._gcloud_token()
                self.assertNotIn("ya29.", cm.exception.message)
                self.assertIn("boom", cm.exception.message)

    def test_safe_extract(self):
        import tempfile

        def tar_with(entries):
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tf:
                for name, link in entries:
                    ti = tarfile.TarInfo(name)
                    if link:
                        ti.type, ti.linkname = tarfile.SYMTYPE, link
                        tf.addfile(ti)
                    else:
                        data = b"#!/bin/sh\n"
                        ti.size, ti.mode = len(data), 0o755
                        tf.addfile(ti, io.BytesIO(data))
            return buf.getvalue()

        with tempfile.TemporaryDirectory() as d:
            for i, (entries, ok) in enumerate([([("google-cloud-sdk/bin/gcloud", None), ("google-cloud-sdk/bin/g2", "gcloud")], True),
                                               ([("../outside", None)], False),
                                               ([("google-cloud-sdk/bin/py", "/usr/bin/python3")], False),
                                               ([("google-cloud-sdk/x", "../../../etc/passwd")], False)]):
                path = os.path.join(d, f"a{i}.tar.gz")
                with open(path, "wb") as f:
                    f.write(tar_with(entries))
                out = os.path.join(d, f"out{i}")
                os.makedirs(out)
                if ok:
                    safe_extract(path, out)
                    self.assertTrue(is_exe(os.path.join(out, "google-cloud-sdk", "bin", "gcloud")))
                else:
                    self.assertRaises(SetupError, safe_extract, path, out)
            p = os.path.join(d, "k.json")
            for body, good in [({"type": "service_account", "client_email": "a@p.iam.gserviceaccount.com", "private_key": "x", "project_id": "p"}, True),
                               ({"type": "service_account", "client_email": "a@p.iam.gserviceaccount.com"}, False),
                               ({"type": "authorized_user"}, False)]:
                with open(p, "w") as f:
                    json.dump(body, f)
                info, err = read_cred_file(p)
                self.assertEqual(bool(info), good, err)
            self.assertEqual(read_cred_file(p + ".missing")[0], None)

    def test_parser(self):
        a = build_parser().parse_args(["plan", "--gpu", "nvidia-l4", "--count", "2", "--region", "us-central1", "--method", "spot", "--quota-request", "offer"])
        req = apply_args(new_request(), a)
        self.assertEqual((req["accel"], req["goal"], req["regions"], req["method"]), ("nvidia-l4", 2.0, ["us-central1"], "spot"))
        a = build_parser().parse_args(["run", "--quota-split", "asia-southeast1=24,asia-northeast1=16"])
        self.assertEqual(apply_args(new_request(), a)["quota_split"], {"asia-southeast1": 24.0, "asia-northeast1": 16.0})
        a = build_parser().parse_args(["setup", "--install-missing", "--key-file", "k.json"])
        self.assertEqual((a.cmd, a.install_missing, a.key_file), ("setup", True, "k.json"))


def run_self_test():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SelfTest)
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1

if __name__ == "__main__":
    sys.exit(main())
