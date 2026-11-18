# Game Day 05: Terraform state file lost

| | |
|---|---|
| Date | 2026-11-18 |
| Type | Controlled drill (game day), state file deleted by me |
| Target | `watchdog/terraform.tfstate` in the state bucket (the Hello World stack). The org stack's file, `org/terraform.tfstate`, was not touched |
| Result | Restored from S3 versioning in about half a minute. Restored file byte-for-byte identical to a backup taken beforehand, and `terraform plan` back to `No changes` |
| Related | Runbook `docs/runbooks/state-file-lost.md`, D-014 (org stack state in the same bucket) |

Times are SAST (UTC+2). AWS records UTC.

## Scenario

The state file is Terraform's inventory: it links every block of code to the real resource it built. If it disappears, Terraform believes nothing exists. The next plan proposes building the whole account again, and an apply would collide with every resource that is already there.

Ways it happens for real: someone tidies the bucket, a script deletes the wrong key, an object is overwritten by a broken write.

The state bucket has had versioning on since it was created. On a versioned bucket a plain delete does not remove data: S3 adds a delete marker on top, and the older versions stay underneath. Goal: prove that, and prove the recovery steps.

## Steps

Round 1, check (read only):

```
aws s3api get-bucket-versioning --bucket <state-bucket>
aws s3api list-object-versions --bucket <state-bucket> --prefix watchdog/terraform.tfstate
aws s3 cp s3://<state-bucket>/watchdog/terraform.tfstate <backup outside the repo>
Get-FileHash <backup>
terraform plan
```

Versioning `Enabled`, 23 versions of the state file, latest version `rns_u0tmPd...` (137,791 bytes), backup hash `AC683F...35B3`, plan `No changes`.

Round 2, break:

```
aws s3 rm s3://<state-bucket>/watchdog/terraform.tfstate
aws s3api list-object-versions ... --query "DeleteMarkers[?Key=='watchdog/terraform.tfstate']"
terraform plan
```

Round 3, recover:

```
aws s3api delete-object --bucket <state-bucket> --key watchdog/terraform.tfstate --version-id <delete-marker-id>
aws s3api list-object-versions ...
aws s3 cp s3://<state-bucket>/watchdog/terraform.tfstate <restored copy>
Get-FileHash <restored copy>
terraform plan
```

## Timeline

| Time (SAST) | Event | Since delete |
|---|---|---|
| 15:44:24 | Delete started (T0) | |
| 15:44:26 | Delete marker created (S3 timestamp) | 0 |
| 15:44 | `terraform plan`: 65 to add, 0 to change, 0 to destroy | |
| 15:44:58 | Recovery started: delete marker removed by its version ID | 32 s |
| 15:45 | Latest version `rns_u0tmPd...`, 137,791 bytes, no delete marker | |
| 15:45 | Restored file hash `AC683F...35B3`, identical to the backup | |
| 15:45 | `terraform plan`: No changes | about 1 min |

## Findings

1. **Versioning turns a delete into an undo.** The state was never gone, only hidden under a delete marker. Removing the marker brought back the exact same version (same version ID, same size, same hash).
2. **Without the state, Terraform wanted to build all 65 resources again.** That is the real danger of a lost state file: not the missing file, but an apply that follows it.
3. **The manual approval gate is the last line of defence.** If the pipeline had run during those 32 seconds, its plan would have shown 65 to add, and the production approval would have stopped it (D-009). The nightly drift check would also have opened an issue showing everything as new.
4. **Nothing alerted, and nothing recorded who did it.** Deleting an S3 object is a data event. The organisation trail records management events only, so CloudTrail has no record of this delete. Recording S3 data events for one bucket is possible but billed per event.
5. **Recovery needs the delete marker's version ID.** Listing the versions first is what makes the fix one command.
6. **The lock file is separate and was unaffected.** Its many delete markers are normal: Terraform removes the lock after every run.

## Follow-up

- [ ] Bucket policy that denies `s3:DeleteObject` on the two state keys. Terraform overwrites its state but never deletes it, so nothing legitimate needs that permission. Recovery uses `s3:DeleteObjectVersion`, which stays allowed. The bucket was made by hand, so this would be a D-017 change
- [x] Runbook written: `docs/runbooks/state-file-lost.md`

## Lessons

1. A backup you have never restored is a hope, not a backup. The hash comparison is what turns "it looks fine" into proof.
2. Know which permission does what: `DeleteObject` hides, `DeleteObjectVersion` truly removes. That difference is both the recovery path and the way to lock the door.
