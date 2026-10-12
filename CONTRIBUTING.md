# Contributing

Thanks for looking. Varshik is a research project, so changes are judged by whether they keep its claims true.

## Ground rules

- **Real data only.** No invented numbers. Anything estimated is labelled as an estimate, in the UI and in the docs.
- **AI output is evidence, never an input.** Bedrock text (frame checks, briefs) must not change a depth, a score or a drainage figure. A brief must still fail verification if a number or a spot id is wrong.
- **Check for the output, not just the status.** A pipeline change should be checked by looking for `<sequence>-<size>/analysis.json`, not only for a green run.
- **Do not commit data or secrets.** `data/` is git-ignored. Never commit AWS keys, `.env.production`, or the officer passcode.

## Set up

```bash
# backend
uv venv backend/.venv && uv pip install -r backend/requirements.txt pytest
cd backend && python -m pytest tests      # Lambda logic and scripts, no AWS or GPU needed

# web app
cd ui && npm install && npm run dev

# infrastructure
cd infra && npm install && npm test
```

CI (`.github/workflows/ci.yaml`) builds the UI, runs the infra tests and runs the backend tests on every push and pull request.

## Making a change

1. Open an issue first for anything that changes how a number is computed, or what the AI features are allowed to do.
2. Add or update a test when you change Lambda logic or a script. The Lambda handlers load without AWS (see `backend/tests/conftest.py`).
3. If you change a deployed Lambda, update `backend/lambdas/README.md` and say how you redeployed it.
4. If you change a validation result or a limit, update the README section "What the results do and do not show" in the same pull request.
5. Keep UI copy plain and free of em-dashes.

## Reporting a security problem

See [SECURITY.md](SECURITY.md).
