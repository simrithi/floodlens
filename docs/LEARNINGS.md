# What I learned building Varshik

Written from what actually went wrong and right while building it. Each lesson names the event it came from.

## About building on AWS

**1. A green run proves nothing.** A 422-frame run ended SUCCEEDED in Step Functions and produced no output. My failure handler recorded `failed` in DynamoDB and then finished normally, so every dashboard said success. A failed run now ends in a Fail state, and I treat the existence of `<sequence>-<size>/analysis.json` as the only real success signal.

**2. Learn the service limits before the long job, not after it.** I met five limits only when something broke:
- Step Functions limits a state to 256 KB. A Map over 422 frames collected about 2 KB per frame and failed with `States.DataLimitExceeded` after about 45 minutes of GPU time. The fix was to save each record to S3 and pass a pointer.
- A Lambda that read the saved records, the rasters and 5,890 drain lines timed out at 60 seconds using 499 of its 512 MB. It now has 3 GB and 15 minutes.
- A public Function URL needs two permissions (`InvokeFunctionUrl`, and `InvokeFunction` via the URL). With one it returns a bare 403.
- S3 answers a missing key with AccessDenied, not NoSuchKey, if the caller lacks `s3:ListBucket`, so a cache miss looked like a permissions bug.
- Lambda rejects container images built with Docker BuildKit's attestation manifests ("media type not supported"). `--provenance=false` fixes it.

**3. Cost shapes the architecture.** One real-time SageMaker endpoint on a GPU instance costs about US$0.74 an hour while idle and cannot scale to zero. That is why frames run one at a time, why the endpoint should be deleted when it is not in use, and why asynchronous inference is on the roadmap.

**4. Data must be where the app looks.** The map worked on my machine. The live site served nothing under `/analysis/`, because the data was in a different bucket. I should have written the publish script first. It now exists (`backend/scripts/publish_site.sh`).

**5. Public does not mean unprotected, and CORS is not authentication.** Three Function URLs are public because the browser calls them. The real protection is server-side: strict input validation, per-hour limits on fresh AI calls, cached results served free, and a passcode for writes. Any secret that has been copied into a chat or a document should be rotated.

## About testing

**6. Test against the shapes the system really produces.** The forecast alert and the frame check both looked for a field called `stretches`. Real findings call it `cells`. Every spot was skipped without an error, and a forced 100 mm/hr cloudburst flagged nothing. I had written them against the data I expected and never run them on real output. The backend tests now use the real layout, and a failing input must produce a visible failure.

**7. Silence is the expensive failure.** Every one of the bugs above was quiet: a skipped loop, a clean exit, a 403 with no detail. A crash is fixed in ten minutes; a quiet skip costs hours.

## About AI

**8. Make the model unable to change facts.** The first Kannada brief translated "Connaught Place" as "Kanyakumari Place". Every number in it was correct, because numbers are checked, but nothing checked names. Asking the model nicely worked for Delhi and failed for Bengaluru. The fix was structural: the model refers to spots only by id and code adds the exact names. Anything a model writes is checked against the data before it is shown, and rejected otherwise.

**9. Do not ship what I cannot read.** I cannot judge Kannada, and the machine translation had real errors (it rendered "ward" as "ordinary"). I removed it and listed Kannada and local-language printing as future scope, to be added with a fluent reviewer.

**10. AI is evidence, not an input.** The frame check says what is visible at a drain, for an engineer to verify on site. It never changes a depth, a score or a drainage figure. That boundary kept the physical model explainable.

## About the science

**11. Say the weak numbers.** Terrain alone separated reported hotspots from ordinary roads with an AUC of 0.57, and its interval (0.46 to 0.68) includes chance. The stretch-level test against the same hotspots gave 0.45. The water model scored 0.66 and the phone road profile 0.69 against 0.47 for satellite elevation. All of them are in the README, because a reader who finds the weak ones for themselves stops trusting the strong ones.

**12. Resolution decides what a dataset is good for.** A 30 m elevation model is right for catchments and blind to a kerb or a sag a few centimetres deep. That gap is why the phone's tilt sensor and the dashcam frames exist: each source is used for what it can reliably show, and none is treated as proof alone.

## About how to work

**13. Get the real data early.** The official Bengaluru drain network was missing from the Lambda image, and the 4K frames had never been uploaded to AWS. Both surfaced only when I ran the real surveys. Run the real thing end to end as soon as there is something to run.

**14. Write down what was verified.** The README records every test and live check with its result and its date, and also what was not verified. It made me find real gaps (CloudFront has no security headers; the alert email path was untested) instead of assuming.

## Why it matters to me

Growing up in Tamil Nadu I saw what floods do to families, and I lost friends to them. Varshik is my attempt to make risk visible before the rain, with evidence an engineer can check. These lessons are what separate a demo that looks right from a tool someone could trust.
