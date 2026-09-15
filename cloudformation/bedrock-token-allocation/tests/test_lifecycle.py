"""Ownership regression tests that prevent modifying customer logging."""
from __future__ import annotations

import copy
import unittest

from botocore.session import get_session
from botocore.validate import validate_parameters

from bedrock_demo.core.lifecycle import (
    logging_change,
    managed_logging_config,
    needs_logging_read,
    one_vantage_role,
    owned_resource_id,
)


STACK = "arn:aws:cloudformation:us-east-1:111111111111:stack/demo/unique-stack-id"
PROPERTIES = {"BucketName": "source-logs", "KeyPrefix": "bedrock/", "LoggingMode": "Managed",
              "LoggingConfigurationVersion": "2"}
CONFIG = managed_logging_config("source-logs", "bedrock/")
PRE_AUDIO_PROPERTIES = {key: value for key, value in PROPERTIES.items()
                        if key != "LoggingConfigurationVersion"}
PRE_AUDIO_CONFIG = {key: value for key, value in CONFIG.items()
                    if key != "audioDataDeliveryEnabled"}


class LoggingLifecycleTests(unittest.TestCase):
    """Exercise ownership transitions using literal configurations."""

    def test_fresh_create_records_ownership(self) -> None:
        """A fresh stack can create logging and receives its own ownership marker."""
        result = logging_change("Create", None, PROPERTIES, {}, "", STACK)
        self.assertEqual(result["action"], "put")
        self.assertEqual(result["physical_id"], owned_resource_id(STACK))
        self.assertTrue(result["configuration"]["audioDataDeliveryEnabled"])

    def test_managed_config_enables_all_delivery_types_in_the_sdk_schema(self) -> None:
        """Validate the complete fresh configuration against Bedrock's SDK model offline."""
        wanted = {"s3Config": {"bucketName": "source-logs", "keyPrefix": "bedrock/"},
                  "textDataDeliveryEnabled": True, "imageDataDeliveryEnabled": True,
                  "embeddingDataDeliveryEnabled": True, "videoDataDeliveryEnabled": True,
                  "audioDataDeliveryEnabled": True}
        self.assertEqual(CONFIG, wanted)
        shape = get_session().get_service_model("bedrock").shape_for("LoggingConfig")
        validate_parameters(CONFIG, shape)

    def test_matching_existing_logging_is_not_owned_on_create(self) -> None:
        """Matching bucket names do not grant ownership of customer configuration."""
        with self.assertRaisesRegex(ValueError, "will not overwrite"):
            logging_change("Create", CONFIG, PROPERTIES, {}, "", STACK)

    def test_lost_response_retry_accepts_only_a_stack_owned_bucket(self) -> None:
        """A successful Put can be acknowledged again after its first response was lost."""
        props = {**PROPERTIES, "OwnsLogBucket": "true"}
        result = logging_change("Create", CONFIG, props, {}, "", STACK)
        self.assertEqual(result["action"], "noop")
        self.assertEqual(result["physical_id"], owned_resource_id(STACK))
        reused = {**props, "LoggingMode": "Reuse", "OwnsLogBucket": "false"}
        result = logging_change("Create", CONFIG, reused, {}, "", STACK)
        self.assertNotEqual(result["physical_id"], owned_resource_id(STACK))

    def test_reuse_preserves_cloudwatch_and_modality_choices(self) -> None:
        """Explicit reuse reads matching S3 logging without replacing any settings."""
        current = {**CONFIG, "textDataDeliveryEnabled": False,
                   "cloudWatchConfig": {"logGroupName": "customer-observability"}}
        before = copy.deepcopy(current)
        props = {**PROPERTIES, "LoggingMode": "Reuse"}
        result = logging_change("Create", current, props, {}, "", STACK)
        self.assertEqual(result["action"], "noop")
        self.assertNotEqual(result["physical_id"], owned_resource_id(STACK))
        self.assertEqual(current, before)

    def test_reuse_requires_existing_exact_destination(self) -> None:
        """Reuse cannot silently create logging or redirect another destination."""
        props = {**PROPERTIES, "LoggingMode": "Reuse"}
        for current in (None, managed_logging_config("other-logs", "bedrock/"),
                        managed_logging_config("source-logs", "other/")):
            with self.subTest(current=current), \
                    self.assertRaisesRegex(ValueError, "Reuse requires"):
                logging_change("Create", current, props, {}, "", STACK)

    def test_default_delete_retains_managed_logging(self) -> None:
        """Stack removal does not turn off logging unless explicitly requested."""
        result = logging_change("Delete", CONFIG, PROPERTIES, {}, owned_resource_id(STACK),
                                STACK)
        self.assertEqual(result["action"], "noop")
        self.assertFalse(needs_logging_read("Delete", PROPERTIES, owned_resource_id(STACK), STACK))

    def test_deliberate_delete_requires_unchanged_owned_configuration(self) -> None:
        """An explicit cleanup deletes only the original unchanged managed configuration."""
        props = {**PROPERTIES, "RetainLoggingOnDelete": "false"}
        result = logging_change("Delete", CONFIG, props, {}, owned_resource_id(STACK), STACK)
        self.assertEqual(result["action"], "delete")
        for current in ({**CONFIG, "cloudWatchConfig": {"logGroupName": "new-owner"}},
                        {**CONFIG, "audioDataDeliveryEnabled": False},
                        {**CONFIG, "imageDataDeliveryEnabled": False}):
            with self.subTest(current=current):
                change = logging_change("Delete", current, props, {},
                                        owned_resource_id(STACK), STACK)
                self.assertEqual(change["action"], "noop")

    def test_reused_failed_and_legacy_resources_cannot_delete_logging(self) -> None:
        """Failure and legacy physical IDs never count as explicit ownership evidence."""
        props = {**PROPERTIES, "RetainLoggingOnDelete": "false"}
        foreign = ("", "bedrock-mil-unowned", "old-lambda-log-stream",
                   owned_resource_id("other-stack"))
        for physical_id in foreign:
            with self.subTest(physical_id=physical_id):
                change = logging_change("Delete", CONFIG, props, {}, physical_id, STACK)
                self.assertEqual(change["action"], "noop")
                self.assertFalse(needs_logging_read("Delete", props, physical_id, STACK))

    def test_explicit_reuse_never_deletes_even_with_managed_marker(self) -> None:
        """Changing to reuse relinquishes deletion authority."""
        props = {**PROPERTIES, "LoggingMode": "Reuse", "RetainLoggingOnDelete": "false"}
        result = logging_change("Delete", CONFIG, props, {}, owned_resource_id(STACK), STACK)
        self.assertEqual(result["action"], "noop")

    def test_idempotent_update_preserves_legacy_ownership(self) -> None:
        """A safe old-template upgrade does not retroactively claim configuration ownership."""
        result = logging_change("Update", CONFIG, PROPERTIES, PROPERTIES, "legacy-stream", STACK)
        self.assertEqual(result["action"], "noop")
        self.assertEqual(result["physical_id"], "legacy-stream")

    def test_update_does_not_overwrite_external_changes(self) -> None:
        """An owned stack must still preserve changes made by another logging owner."""
        current = {**CONFIG, "cloudWatchConfig": {"logGroupName": "keep-me"}}
        with self.assertRaisesRegex(ValueError, "will not overwrite"):
            logging_change("Update", current, PROPERTIES, PROPERTIES, owned_resource_id(STACK),
                           STACK)

    def test_owned_update_can_change_its_previous_prefix(self) -> None:
        """A deliberate stack update can move only its unchanged managed configuration."""
        props = {**PROPERTIES, "KeyPrefix": "new-prefix/"}
        result = logging_change("Update", CONFIG, props, PROPERTIES, owned_resource_id(STACK),
                                STACK)
        self.assertEqual(result["action"], "put")
        self.assertEqual(result["configuration"]["s3Config"]["keyPrefix"], "new-prefix/")

    def test_owned_pre_audio_configuration_upgrades_without_changing_ownership(self) -> None:
        """Enable audio for an unchanged version-one configuration owned by this stack."""
        for current in (PRE_AUDIO_CONFIG, {**PRE_AUDIO_CONFIG, "audioDataDeliveryEnabled": False}):
            with self.subTest(current=current):
                before = copy.deepcopy(current)
                result = logging_change("Update", current, PROPERTIES, PRE_AUDIO_PROPERTIES,
                                        owned_resource_id(STACK), STACK)
                self.assertEqual(result["action"], "put")
                self.assertEqual(result["configuration"], CONFIG)
                self.assertEqual(result["physical_id"], owned_resource_id(STACK))
                self.assertEqual(current, before)

    def test_retried_audio_upgrade_acknowledges_the_completed_write(self) -> None:
        """A lost upgrade response does not repeat the write or replace the physical ID."""
        result = logging_change("Update", CONFIG, PROPERTIES, PRE_AUDIO_PROPERTIES,
                                owned_resource_id(STACK), STACK)
        self.assertEqual(result["action"], "noop")
        self.assertEqual(result["physical_id"], owned_resource_id(STACK))

    def test_unowned_pre_audio_configuration_is_not_upgraded(self) -> None:
        """Legacy or foreign ownership markers cannot authorize enabling audio."""
        for physical_id in ("", "legacy-stream", owned_resource_id("another-stack")):
            with self.subTest(physical_id=physical_id), \
                    self.assertRaisesRegex(ValueError, "will not overwrite"):
                logging_change("Update", PRE_AUDIO_CONFIG, PROPERTIES, PRE_AUDIO_PROPERTIES,
                               physical_id, STACK)

    def test_version_two_disabled_audio_is_preserved_as_external_drift(self) -> None:
        """Missing or disabled audio after version two cannot be overwritten or deleted."""
        for current in (PRE_AUDIO_CONFIG, {**CONFIG, "audioDataDeliveryEnabled": False}):
            with self.subTest(current=current):
                with self.assertRaisesRegex(ValueError, "will not overwrite"):
                    logging_change("Update", current, PROPERTIES, PROPERTIES,
                                   owned_resource_id(STACK), STACK)
                props = {**PROPERTIES, "RetainLoggingOnDelete": "false"}
                result = logging_change("Delete", current, props, {}, owned_resource_id(STACK),
                                        STACK)
                self.assertEqual(result["action"], "noop")

    def test_pre_audio_delete_accepts_only_its_unchanged_declared_schema(self) -> None:
        """An explicit version-one cleanup handles omitted and default-false audio safely."""
        props = {**PRE_AUDIO_PROPERTIES, "RetainLoggingOnDelete": "false"}
        for current in (PRE_AUDIO_CONFIG, {**PRE_AUDIO_CONFIG, "audioDataDeliveryEnabled": False}):
            with self.subTest(current=current):
                result = logging_change("Delete", current, props, {}, owned_resource_id(STACK),
                                        STACK)
                self.assertEqual(result["action"], "delete")
        changed = logging_change("Delete", CONFIG, props, {}, owned_resource_id(STACK), STACK)
        self.assertEqual(changed["action"], "noop")

    def test_audio_upgrade_does_not_overwrite_other_preexisting_changes(self) -> None:
        """The schema upgrade still respects changes to older delivery flags and destinations."""
        for current in ({**PRE_AUDIO_CONFIG, "textDataDeliveryEnabled": False},
                        {**PRE_AUDIO_CONFIG, "cloudWatchConfig": {"logGroupName": "keep-me"}}):
            with self.subTest(current=current), \
                    self.assertRaisesRegex(ValueError, "will not overwrite"):
                logging_change("Update", current, PROPERTIES, PRE_AUDIO_PROPERTIES,
                               owned_resource_id(STACK), STACK)

    def test_rollback_can_restore_the_previous_declared_schema(self) -> None:
        """A rollback of our unchanged audio upgrade can restore the prior managed settings."""
        result = logging_change("Update", CONFIG, PRE_AUDIO_PROPERTIES, PROPERTIES,
                                owned_resource_id(STACK), STACK)
        self.assertEqual(result["action"], "put")
        self.assertEqual(result["configuration"], PRE_AUDIO_CONFIG)
        self.assertEqual(result["physical_id"], owned_resource_id(STACK))

    def test_ambiguous_vantage_roles_require_selection(self) -> None:
        """Read access is never sprayed across stale integrations found by name."""
        roles = ["ConnectToVantage-old-CrossAccountRole-a",
                 "ConnectToVantage-new-CrossAccountRole-b"]
        with self.assertRaisesRegex(ValueError, "Set VantageCrossAccountRole"):
            one_vantage_role(roles)
        with self.assertRaisesRegex(ValueError, "No ConnectToVantage"):
            one_vantage_role(["unrelated-role"])
        self.assertEqual(one_vantage_role([roles[0], "other-role"]), roles[0])

    def test_stackset_vantage_role_is_discovered(self) -> None:
        """Current organization onboarding role names work without a manual override."""
        name = "StackSet-ConnectToVantage10-12345-CrossAccountRole-EXAMPLE1234567"
        self.assertEqual(one_vantage_role([name, "unrelated"]), name)
        with self.assertRaisesRegex(ValueError, "Several Vantage roles"):
            one_vantage_role([name, "ConnectToVantage-old-CrossAccountRole-a"])


if __name__ == "__main__":
    unittest.main()
