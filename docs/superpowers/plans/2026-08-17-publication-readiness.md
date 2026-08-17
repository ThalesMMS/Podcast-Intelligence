# Public Repository Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current repository safe, reproducible, and accurately documented before changing its GitHub visibility to public.

**Architecture:** Keep the application architecture unchanged. Update only dependency locks and the existing CommonJS compatibility adapter, remove GitHub Actions CI while retaining Dependabot, replace machine-specific onboarding with a provider-neutral Docker workflow, and refresh delivery documentation from fresh validation evidence.

**Tech Stack:** Python 3.12 with uv, Next.js 16 with npm, Docker Compose v2, Make, Markdown, and Git.

**Spec:** User request in this task dated 2026-08-17; no standalone design specification was supplied.

## Global Constraints

- Resolve the open high-severity advisories for `brace-expansion`, `js-yaml`, `nanoid`, and `cryptography` using their first patched releases.
- Remove GitHub Actions CI because hosted runner credits are unavailable; retain `.github/dependabot.yml` for update visibility.
- Remove the private network address, tailnet assumptions, private gateway models, known personal episode, and machine-specific performance claims from public documentation.
- Bind all development Compose ports to loopback by default, with an explicit
  override only for intentional remote access.
- Do not change repository visibility. The user explicitly authorized commits,
  history rewriting, and a force-push of `main` after validation.
- Validate the documented Docker demo path without external AI credentials.

---

### Task 1: Capture failing publication gates

**Files:**
- Inspect: `.github/workflows/ci.yml`
- Inspect: `GETTING_STARTED.md`
- Inspect: `VALIDATION.md`
- Inspect: `frontend/package-lock.json`
- Inspect: `backend/uv.lock`

**Interfaces:**
- Consumes: the current private-repository checkout and installed dependency trees.
- Produces: reproducible red checks for the security audit, GitHub workflow presence, infrastructure-specific documentation, and stale validation claims.

- [ ] Run `npm audit --audit-level=low` in `frontend` and confirm it fails on the four known advisory families.
- [ ] Assert that `.github/workflows/ci.yml` exists and record this as the CI-removal red check.
- [ ] Search tracked documentation for tailnet-specific values, `<REPOSITORY-URL>`, `Podcast-Intelligence-dev`, and stale July 22 validation claims.
- [ ] Run `docker version` and `docker compose version` before any Compose mutation.

### Task 2: Update vulnerable dependency locks

**Files:**
- Modify: `frontend/vendor/brace-expansion-cjs/package.json`
- Modify mechanically: `frontend/package-lock.json`
- Modify mechanically: `backend/uv.lock`
- Test: `frontend/tests/dependency-security.test.ts`

**Interfaces:**
- Consumes: the existing `brace-expansion` CommonJS adapter and npm/uv lockfiles.
- Produces: `brace-expansion` 5.0.9, `js-yaml` 4.3.1 or later within the current major, `nanoid` 3.3.18 or later within the current major, and `cryptography` 50.0.0 or later within the allowed resolver graph.

- [ ] Change the adapter metadata and aliased dependency from 5.0.8 to 5.0.9.
- [ ] Refresh only the affected npm lock entries with npm, then reinstall from the lock using `npm ci`.
- [ ] Refresh only `cryptography` in `backend/uv.lock` with uv 0.11.32 and synchronize the backend environment from the frozen lock.
- [ ] Run the focused dependency adapter test.
- [ ] Run `npm audit --audit-level=low` and confirm zero vulnerabilities.

### Task 3: Remove hosted CI while retaining dependency monitoring

**Files:**
- Delete: `.github/workflows/ci.yml`
- Keep: `.github/dependabot.yml`
- Modify: `FILE_MANIFEST.sha256`

**Interfaces:**
- Consumes: the current GitHub Actions workflow and tracked-file manifest.
- Produces: a repository with no hosted CI workflow and a manifest containing only current tracked files.

- [ ] Delete `.github/workflows/ci.yml`.
- [ ] Confirm no active workflow remains under `.github/workflows`.
- [ ] Confirm `.github/dependabot.yml` remains present and parseable.

### Task 4: Replace private onboarding with a public Docker guide

**Files:**
- Modify: `GETTING_STARTED.md`
- Modify: `SECURITY.md`

**Interfaces:**
- Consumes: `.env.example`, `README.md`, `docs/providers.md`, and the Compose demo profile.
- Produces: a clone-to-demo guide that works without a tailnet or private AI gateway, plus provider-neutral instructions for optional real integrations.

- [ ] Rewrite `GETTING_STARTED.md` around the public clone URL, `.env.example`, Docker demo profile, seed command, smoke test, and links to provider documentation.
- [ ] Use only RFC example endpoints when demonstrating optional OpenAI-compatible or WebSocket providers.
- [ ] Remove the known personal episode, private model names, private gateway limits, and machine-specific duration estimates.
- [ ] Change `SECURITY.md` wording from publishing the repository to deploying the service on a public network.
- [ ] Run a tracked-file scan and confirm the private infrastructure literals are absent from the current tree.

### Task 5: Repair delivery metadata and source packaging

**Files:**
- Modify: `Makefile`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify after verification: `VALIDATION.md`
- Modify mechanically: `FILE_MANIFEST.sha256`

**Interfaces:**
- Consumes: fresh local and Docker validation results.
- Produces: a repository-name-independent source archive command and a dated, evidence-based validation report.

- [ ] Replace the directory-name-dependent `zip` target with deterministic `git archive` packaging of the committed tree.
- [ ] Run all backend lint, formatting, typing, and test gates.
- [ ] Run all frontend formatting, lint, type, unit-test, production-build, and audit gates.
- [ ] Run Compose configuration, image build, demo stack startup, seed, readiness, and integrated smoke validation.
- [ ] Confirm every expanded Compose port binds to `127.0.0.1` by default.
- [ ] Update `VALIDATION.md` with exact commands, versions, pass counts, skipped tests, and explicitly untested external-provider flows.
- [ ] Regenerate `FILE_MANIFEST.sha256` from sorted tracked files excluding the manifest itself, and verify every checksum.

### Task 6: Final scope and integrity review

**Files:**
- Review: all changed files

**Interfaces:**
- Consumes: Tasks 1 through 5.
- Produces: a cleanly scoped working-tree diff ready for the user's review.

- [ ] Run `git diff --check`, `git fsck --full --no-dangling`, and a high-confidence credential scan over the current tree.
- [ ] Confirm no GitHub Actions workflow remains, Dependabot remains configured, no private infrastructure literals remain in the current tree, and all four patched dependency versions are locked.
- [ ] Review `git status` and `git diff --stat` before the authorized history
  rewrite and force-push.

### Task 7: Sanitize and publish the rewritten main history

**Files:**
- Purge from historical commits: `GETTING_STARTED.md`
- Restore at the rewritten tip: `GETTING_STARTED.md`
- Refresh at the rewritten tip: `FILE_MANIFEST.sha256`

**Interfaces:**
- Consumes: the verified public-ready working tree, the current remote `main`
  object ID, and a private local Git bundle backup.
- Produces: a rewritten `main` whose reachable history contains neither the old
  infrastructure guide nor the personal author email, force-pushed with an
  exact lease against the previously inspected remote object ID.

- [ ] Confirm GitHub CLI authentication, remote URL, branch, tags, remote heads,
  and the exact remote `main` object ID.
- [ ] Create and verify a private bundle backup outside the repository before
  rewriting any ref.
- [ ] Commit the validated publication-readiness changes with explicit paths.
- [ ] Run `git filter-repo` to purge all historical versions of
  `GETTING_STARTED.md` and map the personal email to the GitHub noreply address.
- [ ] Restore only the sanitized guide at the rewritten tip, regenerate and
  verify the manifest, and commit with the noreply identity.
- [ ] Scan every commit reachable from rewritten `main` for the private address,
  private guide path history, and personal email.
- [ ] Restore the validated `origin` URL if `git filter-repo` removes it, then
  force-push `main` with `--force-with-lease` pinned to the pre-rewrite remote
  object ID.
- [ ] Fetch the remote `main` object ID and verify it equals the rewritten local
  tip. Do not change repository visibility.
