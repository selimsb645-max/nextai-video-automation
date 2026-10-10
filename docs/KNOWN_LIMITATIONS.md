# Findings retained, not silently fixed

1. GitHub is a private repository/asset backup, not a free always-on rendering server. Another agent still requires compute, scheduler, valid authorization and AI credits. No GitHub Actions production jobs or cloud migration were installed.
2. factory.py's header describes historical Pollinations/Edge-TTS behavior although current active rendering uses Pexels/Kokoro. Source includes an Edge-TTS fallback on Kokoro failure; owner now requires Kokoro. Destination must not proceed if Kokoro is unavailable and must obtain permission for any fallback-removal fix. Source was not rewritten under a backup request.
3. chatgpt_thumb.py documents PIL fallback and has optional account-switching logic. The owner-approved contract overrides this: ChatGPT only, no PIL silent replacement, existing single account, --no-switch, no repeated login attempts. Source help is not new owner permission.
4. Thumbnail generation needs a live authenticated Browserbase session. There are no browser/session credentials in this repo. New agent cannot assume old session access.
5. Production's web research/script composition and native workflow setup are still agent-driven. The repository is not a self-contained autonomous AI-service replacement.
6. Destination dependency install and full render/upload were not retested; only offline verification was performed. Model/footage authenticity and third-party license provenance require preservation and verification for redistribution.
7. A library snapshot and production history can become stale while old workflows continue. At cutover freeze old producers and reconcile new reservations/uploads before activation. Never reset state.json or published_log.json.
8. Some owner-desired captions/infographics are not newly implemented by adopting reference styling. Do not claim features that are absent from renderer code.
