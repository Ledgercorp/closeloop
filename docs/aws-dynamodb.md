# AWS DynamoDB integration

Milestone 5 adds Amazon DynamoDB as an optional authoritative repository for resolution state,
confirmation state, evidence, timestamps, owner identity, optimistic version, and terminal outcome.
It is not a telemetry copy: when selected, every lifecycle read and write uses DynamoDB.

## Why this is the only AWS service in Milestone 5

CloseLoop needs durable state shared by independent server instances. A single DynamoDB table
provides that product capability with atomic conditional writes and no continuously running
compute. Bedrock, AgentCore, Strands, Lambda, Step Functions, and EventBridge would not improve the
current synchronous demo lifecycle. Adding them now would enlarge the control plane without
improving verification, so they are intentionally excluded.

No AWS service, SDK response, or future agent may write or override `PASS`, `FAIL`, or
`INCONCLUSIVE`. Only `verify_cancellation` produces a terminal verdict.

## Data and concurrency model

- Partition key: `owner_id`; sort key: `resolution_id`.
- `GetItem` and `Query` use strongly consistent reads.
- Creation uses a conditional `PutItem` requiring both key attributes not to exist.
- Each transition uses one conditional `PutItem` requiring the expected numeric version and an
  allowed predecessor state. The application validates the complete target record first.
- A failed condition is followed by one consistent diagnostic read to distinguish missing,
  terminal, stale, and illegal-transition errors. That read never authorizes a retry.
- Terminal predecessor states are never allowed, so terminal outcomes remain immutable.
- Persisted records are decoded through the same invariant checks as SQL records. Malformed or
  contradictory evidence fails as unavailable storage.
- A conservative 350 KiB serialized-record guard leaves headroom below DynamoDB's 400 KB item
  limit.

Open-resolution listing must read and paginate the complete owner's partition, discard terminal
records, sort by `created_at`, and then apply the caller's limit. This preserves the existing SQL
contract, but its read cost grows with that owner's history. If that becomes material, a later
design can add an access pattern deliberately; a global secondary index cannot provide the same
strongly consistent read guarantee.

## Provisioning

The runtime never creates a table. The checked-in CloudFormation template owns provisioning:

```bash
aws cloudformation deploy \
  --stack-name closeloop-m5 \
  --template-file infra/aws/closeloop-dynamodb.json \
  --parameter-overrides TableName=closeloop-resolutions \
  --region us-east-1
```

Configure the application through the normal AWS SDK credential chain; never put access keys in
the repository:

```bash
export CLOSELOOP_DYNAMODB_TABLE=closeloop-resolutions
export AWS_REGION=us-east-1
```

`CLOSELOOP_DYNAMODB_TABLE` takes precedence over SQL URL variables. An explicitly present but
blank value fails closed. `CLOSELOOP_DYNAMODB_ENDPOINT_URL` exists only for a deliberately selected
local-compatible endpoint; omit it in AWS.

The runtime identity needs only this table-scoped data policy (substitute the output table ARN):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:Query"
      ],
      "Resource": "arn:aws:dynamodb:REGION:ACCOUNT_ID:table/TABLE_NAME"
    }
  ]
}
```

The application does not need `Scan`, `DeleteItem`, table-management, stream, or index access.
Deployment operators separately need CloudFormation/table-management permissions.

## Cost and cleanup

The template creates one single-region `PAY_PER_REQUEST` table with server-side encryption and no
streams, indexes, provisioned throughput, or running compute. DynamoDB charges vary by Region and
usage; request, storage, and AWS managed KMS charges can apply, so the expected hackathon cost is
low but not claimed as zero. Point-in-time recovery is omitted for minimal demo cost; production
should evaluate it.

Delete the stack when it is no longer needed:

```bash
aws cloudformation delete-stack --stack-name closeloop-m5 --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name closeloop-m5 --region us-east-1
```

The template's deletion policy deletes the table with the stack. Export any evidence that must be
retained before cleanup.

## Failure and recovery boundary

Credential, region, endpoint, authorization, throttling, missing-table, validation, and internal
AWS errors map to `ResolutionStorageUnavailableError`; they cannot create optimistic success.
Conditional persistence before execution prevents two stale instances from both starting the
action. CloseLoop does not claim exactly-once completion: a crash after external execution can
truthfully leave `EXECUTING` or `VERIFYING` persisted until a future reconciliation design is
implemented. It must not blindly re-execute that action.

Milestone 5 was verified with boto3 against Moto's in-memory DynamoDB simulation. No AWS account,
live table, official DynamoDB Local process, or CloudFormation API was exercised.
