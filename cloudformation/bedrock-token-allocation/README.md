# Enable Bedrock token allocation across your AWS organization

Vantage splits Amazon Bedrock spend by team, application, and environment using
[Model Invocation Logs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-invocation-logging.html):
token counts per request, plus any `requestMetadata` your code attaches. Logging is
off by default, it is a per-account per-region setting, and Bedrock will only write
to a bucket in the same account and region as the caller. There is no native
CloudFormation resource and no org-wide switch.

This demo is that switch. One template, deployed as a StackSet from the management
account, gives every current and future account a log bucket, the delivery policy
Bedrock needs, logging turned on, and read access for the Vantage role you already
have.

- `bedrock-logging.yaml` is the stack.
- `preflight.py` prints where Bedrock actually ran and the StackSet commands to deploy.
- `verify.py` proves one account is ingestible, then prints the Vantage Connect values.
- `bedrock.py` is the shared logic. `python3 test_bedrock.py` tests it and the
  template's embedded Lambdas (stdlib only).

## Prerequisites

- An AWS Organization with the [Vantage AWS integration](https://docs.vantage.sh/connecting_aws)
  in each account you want to allocate (`ConnectToVantage...`). The template finds
  that role by name.
- Bedrock Token Allocation enabled on your Vantage account (Settings -> AWS
  integration -> Model Invocation Logs). Ask Vantage support if you don't see the tab.
- Scripts: Python 3.10+ and `pip install boto3`. The template needs nothing installed.
- For the org rollout, [StackSets trusted access](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-activate-trusted-access.html)
  once in the management account.

## One account first

With credentials for any account that uses Bedrock:

```bash
aws cloudformation create-stack \
  --stack-name bedrock-token-allocation \
  --template-body file://bedrock-logging.yaml \
  --capabilities CAPABILITY_IAM
```

Make one `bedrock-runtime` call (`Converse`, `InvokeModel`, or your app), then:

```bash
python3 verify.py
```

Region is whatever the AWS CLI would use (`--region`, then `AWS_REGION`, then
`AWS_DEFAULT_REGION`, then your profile). Logging is per-region, so a missing
region is a hard error, not a guess. It looks at the last two days of log
partitions; pass `--days` if the account has been quiet.

`verify.py` checks four things, in order, and stops at the first failure: logging
points at the expected bucket, records are arriving, keys sit where Vantage reads,
and a sample has every field the reader filters and dedupes on. Bedrock also writes
permission-check markers and a `data/` folder for bodies over 100 KB. Those are
ignored.

On success it prints the bucket, prefix, and region to select in Vantage
(Settings -> AWS integration -> Model Invocation Logs -> Connect). Matching CUR
rows start splitting by token share within a day or so. There is no backfill for
spend before logging was on.

## The rest of the organization

From the management account:

```bash
python3 preflight.py
```

Read-only. It asks Cost Explorer where Bedrock ran in the last 30 days (marketplace
models included), names the accounts from Organizations, and prints a
`create-stack-set` plus two ways to add instances.

The targeted form is one `create-stack-instances` per region, listing only the
accounts that spent there, so you don't get empty buckets in unused regions. A
StackSet runs one operation at a time, so wait for each of those commands to
finish. The org-wide form covers every account, including ones created later
(auto-deployment), and accepts empty buckets as the cost of that coverage.

Service-managed StackSets skip the management account. If it runs Bedrock, deploy
the single-account stack there separately.

Then `verify.py` per account, and Connect each one in the Vantage UI. There is no
bulk Connect API yet. If an account runs Bedrock in several regions, Vantage
reads one of them today: connect the highest-spend region first (`preflight.py`
flags those accounts).

## What the stack will and won't do

These are tested (`test_bedrock.py` extracts the Lambda from the template):

| Situation | Verdict |
| --- | --- |
| Logging already on, other bucket or CloudWatch | Fail. Nothing is overwritten. Adopt with `ExistingLogBucket` (and `KeyPrefix` if it has one), or remove the other config first. |
| Logging already on, this stack's bucket | No-op. Re-running is safe. |
| Stack deleted | Logging config is removed only if it is this stack's. The bucket and logs are retained. |
| Redeploy after delete or rollback | The retained name collides. Adopt with `ExistingLogBucket`. Adoption does not attach a bucket policy: a rollback leaves the name and drops the policy, so delete that bucket or restore delivery first. |
| Several `ConnectToVantage` roles | Grants read to all of them. Pin one with `VantageCrossAccountRole`. |
| No `ConnectToVantage` role | Fail. Deploy the Vantage integration first. |

The config is S3 only, all four modalities (text, image, embedding, video). AWS's
[reference pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/configure-bedrock-invocation-logging-cloudformation.html)
always adds CloudWatch too. Vantage reads S3 only, and at Bedrock volume CloudWatch
is a second storage bill for logs nothing here uses.

`PutModelInvocationLoggingConfiguration` is last-writer-wins, with no error. If
Terraform (`aws_bedrock_model_invocation_logging_configuration`) or a console click
also owns this setting, pick one owner per account and region. Someone turning
logging off in the console is not self-healing: re-run the StackSet operation, or
use `verify.py` to detect it.

## Tag the requests

Without `requestMetadata`, spend still splits by model and calling principal. With
it, each key becomes a `bedrock:` tag you can group, filter, budget, and alert on.

```python
bedrock.converse(
    modelId=model_id,
    messages=messages,
    requestMetadata={"team": "growth", "application": "checkout",
                     "environment": "prod"},
)
```

`InvokeModel` takes the same map as the `X-Amzn-Bedrock-Request-Metadata` header
(SigV4-signed; the SDK does that). At most 16 pairs, 256 characters each. Bedrock
does not require the field, so put it on a shared client rather than hoping every
caller remembers. Low-cardinality values only (`team`, `application`,
`environment`), never user ids or timestamps. `verify.py` warns when a sample has
none.

## Terraform shops

The AWS provider has `aws_bedrock_model_invocation_logging_configuration`, so you
don't need the Lambda. What it lacks is StackSets' auto-deploy to accounts that
join later, which is why this demo leads with CloudFormation. If account vending
already enables logging, deploy this template with `ExistingLogBucket` just to
attach the Vantage read policy, or attach that policy in Terraform and skip the
template.

The generated StackSet commands set `ConcurrencyMode=SOFT_FAILURE_TOLERANCE` with
`FailureToleranceCount=1,MaxConcurrentCount=10`, so operations are not stuck at
one account at a time. Tune those if you want.
