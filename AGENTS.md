# Project direction

Build a practical event-vision simulator without requiring an event camera. A shader or interactive experiment is sufficient; a game is an optional medium. Preserve the distinction between optical intensity changes, sensor behavior, processing, and visualization. Read `docs/README.md` and `docs/godot-prototype.md` for the current implementation and its limits.

# Feedback and history

- Use GitHub Issues as the durable record of feedback, bugs, experiments, and development decisions. Keep the original observation and subsequent reasoning explicit so the project's history can be understood later.
- Before implementing feedback, read its issue and discussion. Reuse a relevant issue rather than creating duplicates. Record meaningful decisions, changed assumptions, implementation results, and validation evidence in the issue as work progresses.
- Link issue-driven commits to their issue numbers, for example `refs #12`. Distinguish an implemented change from a validated outcome; close an issue only when its stated resolution criteria are met.
- Keep `docs/` accurate about the current design, setup, and measured limitations. Issues hold the feedback/discussion history; documentation describes the current result. Small maintenance changes may be explained in their commit without creating an artificial issue.
- The user is preparing the initial feedback issues. Do not invent or prepopulate those issues on their behalf.

# Branches and pull requests

- **Use the existing single branch, currently `main`, for ordinary incremental development.** Commit and push authorized work directly to it. A new branch or PR is not required for each issue, fix, or feature.
- Branches represent development forks when work actually needs to diverge, such as the Windows notebook implementation versus a TITAN RTX/Ubuntu implementation. They are not mandatory review wrappers.
- Working on a different machine does not by itself require a branch. Continue on the shared branch when the work remains compatible; create a descriptively named branch when an environment-specific implementation or experiment needs independent development.
- Use PRs when requested or when integrating divergent work would benefit from an explicit review. Do not impose a branch-per-issue or mandatory-PR workflow.
- Before changing shared history, inspect the current branch and working tree. Fetch and reconcile remote updates before pushing. Preserve uncommitted user changes; avoid simultaneous writers to the same checkout. Do not force-push or rewrite shared history without explicit authorization.

# Validation and repository hygiene

- Run checks appropriate to the change. The GPU sensor checks use `./run-lab.ps1 -Validate` on Windows and require a real graphics context; headless import checks do not validate GPU execution.
- Record hardware, settings, and the scope of performance measurements. Do not generalize the analytic shader's results to a calibrated camera or a richer renderer.
- Keep Godot downloads, caches, compiled build products, and live runtime logs out of Git. Retain deliberately recorded evidence and source needed to reproduce experiments.
- Current development is on Windows. Ubuntu/TITAN RTX work on `vilab204` is deferred until requested; do not treat its capabilities as verified.
