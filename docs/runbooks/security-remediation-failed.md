# Runbook: security remediation failed

Use when a security group was opened to the internet on an admin port and the Watchdog did not alert, or when there is evidence the remediator failed.

## Signs

- A security group is open to 0.0.0.0/0 or ::/0 on 22 or 3389 and no `[Watchdog]` email arrived within 10 minutes
- Messages in the dead-letter queue `watchdog-sg-remediator-dlq`
- `SgRemediatorFailure` metric in the `Watchdog` namespace
- An `ERROR` line in `/aws/lambda/watchdog-sg-remediator`

## 1. Contain first

If a real group is exposed, close it by hand before investigating. The Watchdog can be fixed afterwards; the exposure cannot wait.

```
aws ec2 revoke-security-group-ingress --group-id <sg-id> --protocol tcp --port 22 --cidr 0.0.0.0/0
```

Use `--port 3389` for RDP. For an IPv6 rule use `--ip-permissions IpProtocol=tcp,FromPort=22,ToPort=22,Ipv6Ranges=[{CidrIpv6=::/0}]`.

## 2. Find the broken link

The chain is: change → Config records it → Config rule judges it → EventBridge rule → Lambda → DynamoDB and SES. Check in that order and stop at the first link that did not happen.

**Is Config recording?**

```
aws configservice describe-configuration-recorder-status
```

Expect `"recording": true` and `"lastStatus": "SUCCESS"`. If not, the recorder is stopped or its delivery to S3 is failing.

**Did the rule judge the group?**

```
aws configservice get-compliance-details-by-config-rule --config-rule-name watchdog-restricted-admin-ports --compliance-types NON_COMPLIANT
```

If the group is not listed, Config has not evaluated it yet (allow up to 10 minutes) or the rule does not cover the case. The rule checks TCP on the blocked ports only.

**Did the function run?**

```
aws logs tail /aws/lambda/watchdog-sg-remediator --since 1h
```

- `sg remediation handled` with an action: the function worked. Check the email: SES sandbox, spam folder, the SSM parameter `/watchdog/report-email`.
- `DUPLICATE`: this exact verdict was already handled. Look for the earlier run.
- `NO_ACTION`: the group was already closed when the function looked.
- `ERROR`: read the error. `AccessDenied` means the role is missing a permission; compare with docs/iam-matrix.md.
- Nothing at all: EventBridge did not deliver. Check the dead-letter queue.

**Is anything in the dead-letter queue?**

```
aws sqs get-queue-url --queue-name watchdog-sg-remediator-dlq
aws sqs get-queue-attributes --queue-url <url> --attribute-names ApproximateNumberOfMessages
aws sqs receive-message --queue-url <url> --max-number-of-messages 10 --attribute-names All --message-attribute-names All
```

Two kinds of message land here:

- From Lambda (the function failed three times): the body has `requestPayload` (the original event) and `responsePayload` (the error).
- From EventBridge (delivery itself failed): the body is the original event; the message attributes carry the error code.

## 3. Fix and replay

Fix the cause first (permission, configuration, code), deploy through the pipeline, then replay the original event. Replay is safe: a verdict that was already fully handled is skipped as a duplicate.

Save the original event to `event.json`, then:

```
aws lambda invoke --function-name watchdog-sg-remediator --cli-binary-format raw-in-base64-out --payload fileb://event.json out.json
```

Check `out.json` and the log for the expected action. Delete the replayed message from the queue with `aws sqs delete-message --queue-url <url> --receipt-handle <handle>`.

## 4. Record it

A real failure gets an incident report in `docs/incidents/`, using INC-001 as the template.
