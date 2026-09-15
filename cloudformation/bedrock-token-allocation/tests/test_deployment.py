"""Account separation, intent preservation, and encryption pairing regressions."""
from __future__ import annotations

from copy import deepcopy
import unittest

from bedrock_demo.core.deployment import (
    config_problems,
    deployment_units,
    logging_conflict,
    manifest_problems,
    new_manifest,
    original_bucket_handoff,
    resolved_parameters,
    template_hashes,
)
from bedrock_demo.core.planning import deployment_blocks, stackset_create_command

BODIES = {"bedrock-central-bucket.yaml": "central template",
          "bedrock-logging.yaml": "source template"}


def rollout() -> dict:
    """Return two independent source scopes and a distinct central account."""
    return {"version": 1, "deployment_id": "bedrock-test", "central": {
        "account_id": "111111111111", "region": "us-east-1", "stack_name": "central",
        "bucket_name": "central-demo-logs"}, "sources": [
        {"account_id": "222222222222", "region": "us-east-1", "stack_name": "source-east",
         "bucket_name": "source-east-demo-logs", "key_prefix": "team/"},
        {"account_id": "333333333333", "region": "us-west-2", "stack_name": "source-west",
         "bucket_name": "source-west-demo-logs"}]}


def saved_manifest(config: dict) -> dict:
    """Return a manifest planned from the config with placeholder observations and templates."""
    return new_manifest(config, template_hashes(BODIES), [{}, {}, {}], "2026-09-14", BODIES)


class DeploymentTests(unittest.TestCase):
    """Protect original GA inputs while adding only the central copy."""

    def test_sources_keep_their_account_region_and_prefix(self) -> None:
        """Each Vantage handoff refers to its original account-specific bucket."""
        config = rollout()
        before = deepcopy(config)
        self.assertEqual(config_problems(config), [])
        units = deployment_units(config)
        self.assertEqual(units[0]["kind"], "central")
        handoff = original_bucket_handoff(units[1])
        self.assertEqual(handoff["bucket"], "source-east-demo-logs")
        self.assertEqual(handoff["prefix"],
                         "team/AWSLogs/222222222222/BedrockModelInvocationLogs/us-east-1/")
        self.assertEqual(units[2]["parameters"]["ReplicationDestinationAccountId"], "111111111111")
        self.assertEqual(config, before)

    def test_duplicate_source_scope_or_bucket_is_rejected(self) -> None:
        """A rollout cannot replace one account's logging twice or share its bucket."""
        config = rollout()
        config["sources"].append(deepcopy(config["sources"][0]))
        self.assertIn("only one source per account and region is allowed", config_problems(config))
        config = rollout()
        config["sources"][0]["bucket_name"] = config["central"]["bucket_name"]
        self.assertIn("source and central bucket names must all differ", config_problems(config))

    def test_destination_kms_does_not_silently_claim_encrypted_replicas(self) -> None:
        """KMS central defaults require explicitly encrypted source buckets too."""
        config = rollout()
        config["central"]["kms"] = True
        self.assertTrue(any("KMS replication" in p for p in config_problems(config)))
        config["sources"] = [
            {**s, "kms_key_arn": f"arn:aws:kms:{s['region']}:{s['account_id']}:key/example"}
            for s in config["sources"]]
        self.assertEqual(config_problems(config), [])

    def test_optional_source_strings_are_type_checked_before_any_stack_exists(self) -> None:
        """A null role or boolean key ARN fails planning, not the source create after central."""
        config = rollout()
        config["sources"][0]["vantage_role"] = None
        self.assertTrue(any("vantage_role" in p for p in config_problems(config)))
        config = rollout()
        config["central"]["kms"] = True
        config["sources"] = [{**s, "kms_key_arn": True} for s in config["sources"]]
        self.assertTrue(any("kms_key_arn" in p for p in config_problems(config)))
        config = rollout()
        config["sources"][0]["vantage_role"] = "ConnectToVantage-CrossAccountRole-example"
        self.assertEqual(config_problems(config), [])
        parameters = resolved_parameters(deployment_units(config)[1],
                                         {"ReplicationDestinationKmsKeyArn": ""})
        self.assertIn({"ParameterKey": "VantageCrossAccountRole",
                       "ParameterValue": "ConnectToVantage-CrossAccountRole-example"}, parameters)

    def test_existing_logging_is_never_taken_over_by_new_stack(self) -> None:
        """Matching existing destinations still require explicit owner adoption."""
        source = deployment_units(rollout())[1]
        matching = {"s3Config": {"bucketName": source["bucket_name"]}}
        cloudwatch = {"cloudWatchConfig": {"logGroupName": "existing"}}
        self.assertTrue(logging_conflict(source, matching))
        self.assertTrue(logging_conflict(source, cloudwatch))
        self.assertEqual(logging_conflict(source, None), "")

    def test_manifest_copies_intent_and_requires_actual_central_outputs(self) -> None:
        """Saved plans remain separate from caller data and do not guess KMS outputs."""
        config = rollout()
        manifest = new_manifest(config, {}, [{}, {}, {}], "2026-09-14T00:00:00Z")
        config["central"]["bucket_name"] = "changed-after-plan"
        self.assertEqual(manifest["config"]["central"]["bucket_name"], "central-demo-logs")
        self.assertFalse(manifest["vantage_verified"])
        with self.assertRaises(KeyError):
            resolved_parameters(manifest["units"][1], {})

    def test_fixed_accounts_do_not_enable_future_account_rollout(self) -> None:
        """Only explicit OU mode turns on StackSet auto-deployment."""
        self.assertIn("Enabled=false", stackset_create_command("demo", "source.yaml"))
        self.assertIn("Enabled=true", stackset_create_command("demo", "source.yaml", True))
        blocks = deployment_blocks({"targets": [], "regions": []}, "r-root", "", "demo",
                                   "source.yaml")
        self.assertNotIn("create-stack-instances", str(blocks))

    def test_template_snapshots_preserve_reviewed_payloads_and_detect_edits(self) -> None:
        """A saved plan uses its own templates and rejects tampered snapshots."""
        bodies = dict(BODIES)
        manifest = new_manifest(rollout(), template_hashes(bodies), [{}, {}, {}], "2026-09-14",
                                bodies)
        bodies["bedrock-logging.yaml"] = "changed working tree"
        self.assertEqual(manifest_problems(manifest), [])
        manifest["template_bodies"]["bedrock-logging.yaml"] = "edited saved plan"
        self.assertIn("Saved template snapshots changed after planning",
                      manifest_problems(manifest))

    def test_per_stack_account_tampering_cannot_bypass_expected_profile_guard(self) -> None:
        """Stack intents must still match the original source config when resuming."""
        manifest = saved_manifest(rollout())
        manifest["units"][1]["account_id"] = "999999999999"
        self.assertIn("Manifest stack intent changed", manifest_problems(manifest))

    def test_generated_role_prefix_and_retention_fit_template_constraints(self) -> None:
        """Invalid naming and expiry settings fail before a central stack is created."""
        config = rollout()
        config["deployment_id"] = "a" * 29
        self.assertTrue(config_problems(config))
        config["deployment_id"] = "a" * 28
        self.assertEqual(config_problems(config), [])
        config["central"]["retention_days"] = 3651
        self.assertTrue(config_problems(config))


if __name__ == "__main__":
    unittest.main()
