# Enable Bedrock token allocation across your AWS organization

Vantage splits your Amazon Bedrock bill by team, application, and environment using
[Model Invocation Logs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-invocation-logging.html):
per-request token counts plus the `requestMetadata` your code attaches. The catch is
operational. Logging is off by default, it is a per-account, per-region setting, AWS
offers no native CloudFormation resource and no org-wide switch for it, and the log
bucket must live in the same account and region as the caller ("Only destinations from
the same account and Region are supported"). Turning it on by hand in every account is
exactly the kind of work nobody does.

This demo is that switch. One CloudFormation template, deployed once as a StackSet from
your management account, gives every current and future account: a log bucket, the
bucket policy Bedrock requires, logging switched on, and read access for the Vantage
role you already have. Two scripts bookend it: `preflight.py` tells you where Bedrock
actually runs before you deploy, and `verify.py` proves each account works afterward.

- `bedrock-logging.yaml` is the template: bucket, bucket policy, a small Lambda-backed
  custom resource that calls `PutModelInvocationLoggingConfiguration` (that is the part
  CloudFormation cannot do natively), and an IAM policy attached to your Vantage
  cross-account role.
- `bedrock.py` holds the pure logic both scripts share; `test_bedrock.py` tests it plus
  the template's embedded Lambda with the stdlib alone: `python3 test_bedrock.py`.
- `preflight.py` and `verify.py` are the before and after: plan the rollout, then prove it.

## Prerequisites

- An AWS Organization, with the [Vantage AWS integration](https://docs.vantage.sh/connecting_aws)
  deployed in each account you want to allocate (the `ConnectToVantage...` stack, usually
  via Vantage's own StackSet). The template finds that role by name in each account.
- The Bedrock Token Allocation feature enabled on your Vantage account (Settings ->
  AWS integration -> Model Invocation Logs tab; ask Vantage support if you don't see it).
- For the scripts only: Python 3.10+ and `pip install boto3`. The template needs nothing
  installed; it is plain CloudFormation.
- [StackSets trusted access](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-activate-trusted-access.html)
  activated once in the management account, for the org-wide rollout.

## Quick start: one account first

Prove the loop in a single account before touching the organization. With credentials
for any account that uses Bedrock:

```bash
aws cloudformation create-stack \
  --stack-name bedrock-token-allocation \
  --template-body file://bedrock-logging.yaml \
  --capabilities CAPABILITY_IAM
```

Make one model call so there is something to log (any `bedrock-runtime` call works:
`Converse`, `InvokeModel`, or just use your application), then:

```bash
python3 verify.py
```

Region comes from the same places the AWS CLI reads it: `--region`, then `AWS_REGION`,
then `AWS_DEFAULT_REGION`, then your profile's default. Logging is a per-region setting,
so verify tells you which region it is checking and refuses to guess when it cannot
work one out. It looks at the last two days of log partitions; widen that with `--days`
if you are checking an account that has been quiet.

Verify checks four things in order and stops at the first failure: the logging
configuration points at the expected bucket, log objects are arriving, the keys sit at
the exact prefix Vantage reads, and a sample of records carries every field Vantage
filters and dedupes on. Objects Bedrock writes that are not invocation records, the
permission-check markers and the `data/` subfolder holding bodies over 100 KB, are
counted and ignored rather than treated as failures. When all four pass it prints the bucket, prefix, and region to
select in Vantage (Settings -> AWS integration -> Model Invocation Logs -> Connect).
Costs from matching CUR rows start splitting by token share within a day or so of
connecting.

## Roll out to the organization

From the management account:

```bash
python3 preflight.py
```

Preflight is read-only. It asks Cost Explorer which accounts and regions actually ran
Bedrock in the last 30 days (marketplace models included), names them from your
Organization, and prints ready-to-run commands: one `create-stack-set`, then
`create-stack-instances` in a targeted form (one command per region, each listing only
the accounts that showed spend in that region) and an org-wide form (every account,
including ones created later, thanks to auto-deployment). Run whichever you prefer,
wait for the operations to finish, then run `verify.py` per account and connect each
one in Vantage.

The targeted form exists because the logging setting is per-region: a stack in a region
an account never uses creates an empty bucket and waits for traffic that never comes.
Per-region commands avoid that cross product; the org-wide form accepts it in exchange
for covering accounts and regions that start using Bedrock later.

## What the template refuses to do

The custom resource is deliberately cautious, and these behaviors are tested (see
`test_bedrock.py`, which extracts the Lambda straight out of the template):

| Situation | Behavior |
| --- | --- |
| Logging already ON, pointing at another bucket or CloudWatch | **Fails loudly.** Nothing is overwritten. Pass that bucket as `ExistingLogBucket` (and its prefix as `KeyPrefix`, if it has one) to adopt it, or remove the other config first. |
| Logging already ON, pointing at this stack's bucket | No-op. Re-running is safe. |
| Stack deleted | The logging config is removed only if it is exactly this stack's; the bucket and its logs are always retained. |
| Redeploying after a delete or a rollback | The retained bucket still holds the fixed name, so a fresh deploy collides. Adopt it with `ExistingLogBucket`, but note that adoption attaches no bucket policy: it assumes the bucket is already a working Bedrock destination. A bucket left behind by a **rollback** kept its name and lost its policy, so either delete it or re-add the delivery policy first. |
| Multiple `ConnectToVantage` roles in one account | Grants read to all of them. A StackSet cannot pass a per-account role name, and accounts often carry several from earlier onboardings. Pin one with `VantageCrossAccountRole`. |
| No `ConnectToVantage` role | Fails: deploy the Vantage integration first. |

The config Bedrock is asked for is S3-only, with all four modalities delivered (text,
image, embedding, video). AWS's own [reference pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/configure-bedrock-invocation-logging-cloudformation.html)
always logs to CloudWatch *and* S3 with no way to choose; at Bedrock volume that is a
second storage bill for logs nothing reads. Vantage reads the S3 side only.

One AWS constraint to know: `PutModelInvocationLoggingConfiguration` writes a single
per-account, per-region config, and the last writer wins with no error. If you also
manage this setting with Terraform (`aws_bedrock_model_invocation_logging_configuration`)
or by hand, pick one owner per account and region.

## Tag your requests, or the split is generic

Without `requestMetadata`, Vantage still splits Bedrock spend by model and calling
principal. With it, every dimension your code attaches becomes a `bedrock:` tag you can
group, filter, budget, and alert on. Attach it at the call site:

```python
# Converse API: a top-level requestMetadata field
bedrock.converse(
    modelId=model_id,
    messages=messages,
    requestMetadata={"team": "growth", "application": "checkout",
                     "environment": "prod"},
)

# InvokeModel: a JSON header instead (it must be SigV4-signed; SDKs handle that)
bedrock.invoke_model(
    modelId=model_id,
    body=body,
    # X-Amzn-Bedrock-Request-Metadata: {"team":"growth","application":"checkout"}
)
```

Rules worth pinning to a wall: at most 16 pairs, 256 characters each, and Bedrock does
not enforce presence, so route calls through a shared client wrapper or gateway rather
than trusting every team to remember. Keep values low-cardinality (`team`,
`application`, `environment`, `feature`, `cost_center`), never user ids or timestamps.
`verify.py` warns when sampled records carry no metadata.

## Why a bucket per account, and not one central bucket

You cannot have the central bucket, and it turns out you don't want it. Bedrock will
only deliver logs to a bucket in the same account and region as the caller; the API has
no cross-account option to configure. The patterns that centralize afterwards do it
with S3 replication, which exists to feed single-bucket analytics stacks (Glue, Athena,
QuickSight). Vantage is the analytics stack here, and it joins each account's logs to
your Cost and Usage Report payer-wide, so per-account buckets are not a compromise, they
are the design. No replication rules, no cross-account bucket policies, no double
storage.

## What you'll see in Vantage, and current limits

After connecting an account, Bedrock line items in your CUR split proportionally by
token share, and `requestMetadata` keys appear as `bedrock:`-prefixed tags in Cost
Reports, Virtual Tags, Segments, and Alerts. Attribution starts from when logging was
enabled; there is no backfill for spend before that.

Honest limits, current as of August 2026:

- **Connecting is per account, in the UI.** There is no Vantage API to bulk-create
  Model Invocation Logs sources yet, so the last step of the rollout is one Connect
  click per account.
- **One bucket, one region per account** is what Vantage reads today. If an account
  runs Bedrock in several regions, connect the region with the most spend first
  (`preflight.py` flags exactly these accounts and lists each region's spend, largest
  first).
- **Drift is not self-healing.** If someone disables logging in the console,
  CloudFormation will not notice; re-running the StackSet operation (or an update)
  re-asserts it. `verify.py` is the cheap detector.
- **Service-managed StackSets never deploy to the management account.** If it runs
  Bedrock, deploy the single-account stack there separately.

If a check fails in `verify.py`, the message says which of the four stages broke and
what to do; the usual suspects are running it before the first model call (no objects
yet) and running it in a different region than the stack.

---

# Going further

**Terraform shops:** the AWS provider has a native resource for this,
`aws_bedrock_model_invocation_logging_configuration`, no Lambda shim needed. What
Terraform lacks is StackSets' automatic deployment to accounts that join the org later,
which is the reason this demo leads with CloudFormation. If your account vending is
already Terraform (Account Factory, aft-account-customizations), enable logging there
and still deploy this template with an `ExistingLogBucket` so the Vantage read policy
gets attached, or attach the policy in Terraform and skip the template entirely.

**Continuous enforcement:** if "someone turned it off" is a real risk in your org, an
SSM State Manager association running on a schedule against your org root re-asserts
the setting and picks up new accounts on every run. That is beyond what this demo
ships, but the custom resource's decide logic (get, compare, put only when needed) is
the exact shape such an automation wants.

**Rollout speed:** StackSet operations default to one account at a time, and under the
default strict failure mode the effective concurrency is `FailureToleranceCount + 1`
regardless of `MaxConcurrentCount`. The generated commands therefore set
`ConcurrencyMode=SOFT_FAILURE_TOLERANCE` alongside
`FailureToleranceCount=1,MaxConcurrentCount=10`; tune all three to taste.
