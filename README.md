# NextAI Vision: private YouTube automation handover

This is a private code/data backup and handover package. It is **not** a newly deployed independent service. GitHub holds code; another Base44 agent still needs authorized tools, its execution environment and available account/workspace credits. Creating another agent does not guarantee additional credits.

Start with [AGENT_HANDOVER.md](AGENT_HANDOVER.md), [current status](docs/CURRENT_STATUS.md) and [known limitations](docs/KNOWN_LIMITATIONS.md). Owner communication is Bengali. Executable source scripts are copied unchanged from the active factory; no live YouTube upload, production workflow change or cutover is authorized by merely cloning.

## Runtime setup

Python3.11+, ffmpeg/ffprobe with x264 and the existing filters; libsndfile and DejaVu fonts. On Debian/Ubuntu: `apt-get install ffmpeg libsndfile1 fonts-dejavu-core`. Install Python dependencies in a virtual environment with `pip install -r requirements.txt`. Pins reflect the source environment, not a successful clean-install certification.

Retrieve the private release asset bundle using `python3 tools/restore_assets.py` with an authorized GitHub token injected as GITHUB_ACCESS_TOKEN. The tool verifies the archive SHA256 and rejects unsafe tar paths/links. It restores local footage, Kokoro model/voice files and the two current uploaded runs awaiting thumbnail completion. No credentials are in the archive.

Obtain owner-approved YouTube authorization securely and write the real token JSON outside git at `yt-auth/token_nextai.json`, using the **empty schema** in docs/token_nextai.example.json. It must contain client_id/client_secret/refresh_token; it is refreshed headlessly when valid. Tokens can still be revoked. Never paste them into chat or commit them. The old owner's credentials were intentionally NOT transferred in GitHub.

For thumbnails, the new agent must have its own authorized Browserbase session logged into the owner's existing ChatGPT account. Cookies/session tokens cannot be copied from this repository. Account rotation is cancelled. Use `--no-switch` for chatgpt_thumb.py. Do not use an invented or expired WSS URL.

## Offline verification

`python3 tools/preflight.py` checks JSON/source syntax, current slot calculation, assets, ffmpeg and optional credential readiness without uploading anything. It intentionally does not produce videos, generate thumbnails or authenticate accounts. Then have the new agent report blockers before any live run.

## Production commands (only after explicit cutover)

`python3 factory/factory.py --next --schedule-bd`

`python3 factory/factory.py --next --short --schedule-bd`

Existing CLI also supports --publish, --setthumb and comment options. Preserve --schedule-bd for fresh uploads; do not use old direct-public commands. Read source syntax before setting an already-uploaded thumbnail. Comment/reply workflows stay paused.

Workflow files in workflow_templates are **reconstructed portable templates**, not exact exports of the live platform definitions. Read their metadata, recreate via the destination's native workflow tools with its guide, initially PAUSED, and exclude migration_metadata from create arguments. Old and new producers must never run concurrently. The repo does not auto-install schedules; there is deliberately no GitHub Actions video-production workflow.

## Third-party assets

Footage is the existing licensed Pexels working pool. Manifests contain source links where retained. Kokoro ONNX weights/voices are existing third-party runtime files. Their original licenses/terms still apply; ownership was not reassigned by this repository. Do not make the private repo/release public or redistribute it as a stock-footage/model collection. Some original asset provenance needs verification before any redistribution. This backup is for the owner's private project continuation.
