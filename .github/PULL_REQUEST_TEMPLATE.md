## What changed and why

## How I checked it

- [ ] `cd backend && python -m pytest tests`
- [ ] `cd ui && npm run build`
- [ ] `cd infra && npm test`
- [ ] If a pipeline step changed: I looked for the output file (`<sequence>-<size>/analysis.json`), not just a green run

## Claims

- [ ] No invented numbers; anything estimated is labelled
- [ ] AI output still never changes a depth, score or drainage figure
- [ ] If a validation result or limit changed, the README section "What the results do and do not show" is updated
- [ ] No data, keys, `.env.production` or passcode committed
