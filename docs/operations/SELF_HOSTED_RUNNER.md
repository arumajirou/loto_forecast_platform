# Self-hosted GPU Runner v1

## Status

- Repository-side configuration: `EXECUTED` after this change is merged.
- Local runner registration: `EXECUTION_PENDING` until the owner runs the generated GitHub registration commands on the GPU PC.
- End-to-end GPU CI: `EXECUTION_PENDING` until one manual workflow run finishes with `VERIFIED` probe evidence.

## Decision

Keep the normal `.github/workflows/ci.yml` on GitHub-hosted runners. Use the local PC only for an owner-triggered, GPU-specific workflow:

- workflow: `.github/workflows/self-hosted-gpu-ci.yml`
- trigger: `workflow_dispatch` only
- owner gate: `github.actor == github.repository_owner`
- runner labels: `self-hosted`, `linux`, `x64`, `loto-ci`, `gpu`, `cuda`
- token permissions: `contents: read`; checkout credentials are not persisted
- concurrency: one GPU job for this repository at a time
- timeout: 360 minutes
- evidence: preflight/postflight JSON plus command logs, retained for 14 days

The workflow does not run on `pull_request`, `pull_request_target`, or `push`. This prevents an ordinary PR from automatically executing arbitrary repository code on the local PC.

## Fact-check corrections

1. A self-hosted runner can execute GitHub Actions jobs on a local physical PC and use its CPU, RAM, disks, GPU, and installed software.
2. For GitHub.com, the runner initiates outbound HTTPS connections on port 443. Port forwarding and a public inbound listener are not normally required. Firewall allowlists may need GitHub domains used for actions, logs, artifacts, packages, and runner updates.
3. Self-hosted jobs do not consume billable GitHub-hosted runner minutes. Electricity, maintenance, storage, and network costs remain the owner's responsibility.
4. A private repository is safer than a public repository, but it is not a clean security boundary. Self-hosted runners are persistent machines and can retain malicious changes, leaked tokens, modified caches, or data from prior jobs.
5. The existing cloud CI currently installs CPU-only PyTorch on `ubuntu-latest`. It should remain the default portability gate; the new workflow is an additional hardware-certification lane.

## Prerequisites on the Linux GPU PC

Use a dedicated, non-root Linux account that does not hold unrelated SSH keys, browser profiles, cloud credentials, personal documents, or production secrets.

Required commands:

```bash
git --version
curl --version
tar --version
sha256sum --version
uv --version
nvidia-smi
python3 --version
```

Required network access includes outbound HTTPS/443 to GitHub's runner, action download, artifact, and update endpoints. Corporate proxies must be configured before runner registration.

## Register the runner

1. Open the private repository.
2. Go to **Settings → Actions → Runners → New self-hosted runner**.
3. Select **Linux** and **x64**.
4. Copy the exact runner download URL, archive SHA-256, and one-hour registration token shown by GitHub.
5. On the dedicated GPU account, run:

```bash
cd /absolute/path/to/loto_forecast_platform

export RUNNER_DOWNLOAD_URL='PASTE_THE_GITHUB_GENERATED_DOWNLOAD_URL'
export RUNNER_SHA256='PASTE_THE_GITHUB_GENERATED_SHA256'
export RUNNER_DIR="$HOME/actions-runner-loto"
export RUNNER_NAME="$(hostname)-loto-gpu"
export RUNNER_LABELS='loto-ci,gpu,cuda'
export INSTALL_SERVICE=1

bash scripts/self_hosted_runner/bootstrap_linux.sh
```

The script prompts for the time-limited token without echoing it. Do not commit the token, paste it into an issue, or save it in shell history.

The bootstrap script:

- refuses root execution;
- verifies Linux x64, required tools, GitHub connectivity, and `nvidia-smi`;
- verifies the downloaded runner archive against the SHA-256 copied from GitHub;
- registers the repository-level runner with custom labels;
- installs and starts the official `svc.sh` systemd service;
- saves setup logs and a separate exit-code file;
- waits for Enter before closing an interactive terminal.

## Verify the service

```bash
cd "$HOME/actions-runner-loto"
sudo ./svc.sh status
nvidia-smi
df -h .
```

Then confirm the runner is **Online / Idle** in **Actions → Runners** and that it has:

```text
self-hosted
linux
x64
loto-ci
gpu
cuda
```

## Run the GPU workflow

The workflow becomes dispatchable after it exists on the default branch.

1. Open **Actions → self-hosted-gpu-ci → Run workflow**.
2. Keep `require_cuda=true`.
3. Start with `suite=smoke`.
4. Review `preflight.json`, `postflight.json`, `nvidia-smi` data, PyTorch CUDA runtime, device name, finite matrix result, and uploaded logs.
5. Only after smoke passes, run `suite=full`.

Acceptance evidence:

```text
preflight.status  = VERIFIED
postflight.status = VERIFIED
torch.cuda_available = true
torch.execution_device = cuda:0
torch.finite = true
smoke import/device check = pass
full pytest = pass
tracked git diff = clean
```

## Operational safeguards

- Do not add PR or push triggers to the GPU workflow.
- Do not use `pull_request_target` with a self-hosted runner.
- Keep `permissions: contents: read` unless a reviewed use case requires more.
- Do not store personal or production secrets on the runner account.
- Keep the official runner auto-update enabled. Node 24 actions require a sufficiently recent runner.
- Stop the service before maintenance or when the PC should not accept jobs.
- Run one GPU job at a time; the workflow concurrency key enforces this repository-wide.
- Treat persistent caches and work directories as untrusted after a failed or suspicious job.
- For stronger isolation, move later to an ephemeral VM/container/JIT runner rather than running directly on the daily-use desktop account.

## Stop or remove

Temporary stop:

```bash
cd "$HOME/actions-runner-loto"
sudo ./svc.sh stop
sudo ./svc.sh status
```

Restart:

```bash
cd "$HOME/actions-runner-loto"
sudo ./svc.sh start
sudo ./svc.sh status
```

Permanent removal must use the current removal token displayed by GitHub:

1. **Settings → Actions → Runners → runner name → Remove**.
2. Run the generated removal command on the PC.
3. Confirm the service and runner entry are gone.

## Rollback of this repository change

Remove or revert:

```text
.github/workflows/self-hosted-gpu-ci.yml
scripts/ci/self_hosted_runner_probe.py
scripts/self_hosted_runner/bootstrap_linux.sh
docs/operations/SELF_HOSTED_RUNNER.md
```

The existing GitHub-hosted `ci.yml` remains unchanged, so rollback does not affect the standard CI lane.

## Official references

- https://docs.github.com/en/actions/concepts/runners/self-hosted-runners
- https://docs.github.com/en/actions/reference/runners/self-hosted-runners
- https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners
- https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application
- https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow
- https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/apply-labels
- https://docs.github.com/en/actions/reference/security/secure-use
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
