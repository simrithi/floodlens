# Security

Varshik is a decision-support research project, not a hardened service.

## What is exposed

Three AWS Lambda Function URLs (frame check, officer brief, officer log) are public because the browser calls them. CORS restricts browsers to the app's origin; it does not stop other callers. The server-side limits are 30 fresh frame checks and 20 fresh briefs per hour overall (cached results are free), and officer-log writes require a passcode held in AWS Systems Manager Parameter Store as a SecureString. Reading the officer log needs no passcode. Anyone can use up the hourly quota, which pauses new generations; it does not remove cached results or let cost grow without bound.

All Lambda functions currently share one IAM role.

## Reporting a problem

Please open a private security advisory on this repository's GitHub page rather than a public issue. Do not post credentials or the officer passcode anywhere.

## Out of scope

Model and forecast accuracy are documented in the README's "What the results do and do not show". They are limitations, not vulnerabilities.
