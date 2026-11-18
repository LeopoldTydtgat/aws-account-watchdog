# Runbook: Terraform state file lost or damaged

Use when Terraform no longer knows what it built: the state file was deleted, overwritten with something wrong, or will not load.

Proven in Game Day 05 (docs/game-days/game-day-05.md).

## Signs

- `terraform plan` wants to add many resources that already exist (Game Day 05: 65 to add)
- A drift issue that lists everything as new
- An apply failing with "already exists" errors
- `terraform init` or `plan` failing to read or parse the state

## 1. Stop first

- Do not run `terraform apply`, locally or in the pipeline.
- If a deploy is waiting for approval, reject it.
- Do not run `terraform state` commands or `terraform import` yet: they write a new state on top of the problem.

## 2. Look at the versions

State bucket: `watchdog-tfstate-<account-id>` (eu-north-1). Keys: `watchdog/terraform.tfstate` (Hello World stack, pipeline) and `org/terraform.tfstate` (management-account stack, applied locally, D-014). Use the key for the stack that is broken.

```
aws s3api get-bucket-versioning --bucket <state-bucket>
aws s3api list-object-versions --bucket <state-bucket> --prefix <key> --query "{versions: Versions[?Key=='<key>'].[VersionId,LastModified,Size,IsLatest], markers: DeleteMarkers[?Key=='<key>'].[VersionId,LastModified,IsLatest]}"
```

The prefix also matches `<key>.tflock`, the lock file. Its delete markers are normal (Terraform removes the lock after every run); the query above filters them out.

## 3a. Deleted: a delete marker is the latest

Remove the delete marker by its version ID. The previous version becomes the latest again.

```
aws s3api delete-object --bucket <state-bucket> --key <key> --version-id <delete-marker-id>
```

## 3b. Overwritten or damaged: a bad version is the latest

Pick the last good version: the newest one from before the incident, with a size close to the versions around it. Copy it on top as a new version. Nothing is deleted, so the bad version stays available for investigation.

```
aws s3api copy-object --bucket <state-bucket> --key <key> --copy-source "<state-bucket>/<key>?versionId=<good-version-id>"
```

## 4. Verify

```
aws s3api list-object-versions --bucket <state-bucket> --prefix <key> --query "Versions[?Key=='<key>' && IsLatest].[VersionId,Size]"
terraform plan
```

Expect `No changes`, or only changes that were merged after the restored version was written. If the plan shows changes you cannot explain, stop and compare with a newer version before applying anything.

If a stale lock is left behind (plan says the state is locked and nothing is running), release it with `terraform force-unlock <lock-id>`.

## 5. If there are no usable versions

Last resort: rebuild the state by hand with `terraform import` for each resource, using the IDs from the console or CLI. Slow, and every import must be checked with a plan. This is why the bucket keeps versions.

## 6. Afterwards

- Find out what happened. S3 object deletes are data events and are not in the organisation trail (management events only), so the bucket's own versions and timestamps may be the only record.
- Write it up under `docs/incidents/`.
