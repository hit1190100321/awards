# Cloud verification of the eleven-point proof

The `十一点证明云端核验` workflow runs in `hit1190100321/awards`. It starts when the relevant proof or verifier files on `main` change, and can also be started manually from the Actions page.

Each run checks the source hashes, runs the unmodified repository validators and tests with Python 3.12, installs the official Lean 4.34.0 Linux release after checking its SHA-256, and obtains the Mathlib dependency cache for the imported modules. The dependencies are pinned by the submitted lock file. The project's proof modules are recompiled from source and the explicit public statements are finally checked with `--trust=0` and the stated axiom allowlist.

The workflow uses read-only repository permissions and retains its logs and machine-readable result for 30 days in the `jsp404-verification` artifact. Discovery solvers are not invoked. It verifies the scoped eleven-point formalization; it does not determine official prize eligibility, priority or payment.

To receive GitHub email notifications for your triggered runs, enable **Email** for **Actions** in your [notification settings](https://github.com/settings/notifications). Disable the failed-runs-only filter if successful runs should also generate email. Delivery depends on the account settings and email service.

The source submission remains [official PR 647](https://github.com/TheJustinSunPrize/awards/pull/647). Runs in this fork are submitter-operated verification and do not replace the organizer's approval or independent review.
