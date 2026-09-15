"""Validate generated template contracts, policy boundaries, and unsafe input failures."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

from render_templates import render_all


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "arn:aws:s3:::archive"
SOURCE_KEY = "arn:aws:kms:us-east-1:111111111111:key/source"
TARGET_KEY = "arn:aws:kms:us-west-2:222222222222:key/target"


class CloudFormationLoader(yaml.SafeLoader):
    """Preserve CloudFormation intrinsics as ordinary dictionaries."""


def cloudformation_tag(loader: yaml.SafeLoader, tag: str, node: yaml.Node) -> dict:
    """Return an intrinsic without resolving resources or contacting AWS."""
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return {tag if tag == "Ref" else f"Fn::{tag}": value}


CloudFormationLoader.add_multi_constructor("!", cloudformation_tag)


def load_template(name: str) -> dict:
    """Return a generated template with CloudFormation intrinsic syntax preserved."""
    return yaml.load((ROOT / f"{name}.yaml").read_text(), Loader=CloudFormationLoader)


def rule_value(value: object, parameters: dict) -> object:
    """Evaluate the finite rule functions used to reject unsafe parameter combinations."""
    if isinstance(value, list):
        return [rule_value(item, parameters) for item in value]
    if not isinstance(value, dict):
        return value
    name, arguments = next(iter(value.items()))
    if name == "Ref":
        return parameters[arguments]
    args = rule_value(arguments, parameters)
    operations = {
        "Fn::Equals": lambda: args[0] == args[1],
        "Fn::And": lambda: all(args),
        "Fn::Or": lambda: any(args),
        "Fn::Not": lambda: not args[0],
        "Fn::Contains": lambda: args[1] in args[0],
        "Fn::EachMemberEquals": lambda: all(item == args[1] for item in args[0]),
    }
    if name not in operations:
        raise ValueError(f"Unsupported CloudFormation rule function: {name}")
    return operations[name]()


def parameter_default(item: dict) -> object:
    """Return a parameter's default as the rule evaluator sees it, lists split on commas."""
    if item.get("Default") is None:
        return []
    if item["Type"] == "CommaDelimitedList":
        return str(item["Default"]).split(",")
    return item["Default"]


def rejected_parameters(template: dict, overrides: dict) -> list[str]:
    """Return failed assertion messages for the supplied stack parameters."""
    defaults = {name: parameter_default(item) for name, item in template["Parameters"].items()}
    values = {**defaults, **overrides}
    assertions = [assertion for rule in template.get("Rules", {}).values()
                  for assertion in rule["Assertions"]]
    return [assertion["AssertDescription"] for assertion in assertions
            if not rule_value(assertion["Assert"], values)]


class TemplateSafetyTests(unittest.TestCase):
    """Exercise actual generated templates, not a separate copied policy fixture."""

    def test_generated_templates_match_modules_and_fit_inline_deployment(self) -> None:
        """The standalone templates must contain exactly the reviewed module sources."""
        render_all(ROOT, check=True)
        for name in ("bedrock-logging", "bedrock-central-bucket"):
            with self.subTest(name=name):
                self.assertLessEqual((ROOT / f"{name}.yaml").stat().st_size, 51_200)

    def test_each_embedded_lambda_imports_and_compiles_without_local_package(self) -> None:
        """Generated index modules work without publishing a Python package to AWS."""
        resources = load_template("bedrock-logging")["Resources"].values()
        functions = [resource for resource in resources
                     if resource["Type"] == "AWS::Lambda::Function"]
        for function in functions:
            source = function["Properties"]["Code"]["ZipFile"]
            namespace = {}
            exec(compile(source, "index.py", "exec"), namespace)
            self.assertTrue(callable(namespace["handler"]))
            self.assertNotIn("from bedrock_demo.", source)

    def test_existing_bucket_requires_reuse_and_owner_managed_replication(self) -> None:
        """Adoption cannot overwrite a customer's logging or bucket replication rules."""
        template = load_template("bedrock-logging")
        self.assertFalse(rejected_parameters(template, {}))
        self.assertTrue(rejected_parameters(template, {"ExistingLogBucket": "customer-logs"}))
        reuse = {"ExistingLogBucket": "customer-logs", "LoggingMode": "Reuse"}
        self.assertFalse(rejected_parameters(template, reuse))
        self.assertTrue(rejected_parameters(template, {
            **reuse, "ReplicationDestinationBucketArn": ARCHIVE,
            "ReplicationDestinationAccountId": "222222222222"}))
        self.assertTrue(rejected_parameters(template, {**reuse, "LogBucketName": "replace-me"}))
        self.assertEqual(template["Resources"]["LoggingBucket"]["Condition"], "CreateBucket")
        self.assertEqual(template["Resources"]["LoggingBucketPolicy"]["Condition"], "CreateBucket")

    def test_generated_resource_requests_audio_on_create_and_owned_upgrade(self) -> None:
        """The template must send the schema change that makes CloudFormation enable audio."""
        resources = load_template("bedrock-logging")["Resources"]
        namespace = {}
        exec(compile(resources["EnableLoggingFunction"]["Properties"]["Code"]["ZipFile"],
                     "index.py", "exec"), namespace)
        properties = {**resources["LoggingConfiguration"]["Properties"],
                      "BucketName": "source-logs", "KeyPrefix": "demo/",
                      "LoggingMode": "Managed", "OwnsLogBucket": "true"}
        stack_id = "arn:aws:cloudformation:us-east-1:111111111111:stack/demo/unique-id"
        create = namespace["logging_change"]("Create", None, properties, {}, "", stack_id)
        self.assertTrue(create["configuration"]["audioDataDeliveryEnabled"])
        old_properties = {key: value for key, value in properties.items()
                          if key != "LoggingConfigurationVersion"}
        old_config = {"s3Config": {"bucketName": "source-logs", "keyPrefix": "demo/"},
                      "textDataDeliveryEnabled": True, "imageDataDeliveryEnabled": True,
                      "embeddingDataDeliveryEnabled": True, "videoDataDeliveryEnabled": True}
        update = namespace["logging_change"]("Update", old_config, properties, old_properties,
                                              create["physical_id"], stack_id)
        self.assertEqual(update["action"], "put")
        self.assertTrue(update["configuration"]["audioDataDeliveryEnabled"])
        self.assertEqual(update["physical_id"], create["physical_id"])

    def test_replication_requires_destination_account_and_paired_kms_keys(self) -> None:
        """Incomplete destination and SSE-S3-to-KMS configurations fail before creation."""
        template = load_template("bedrock-logging")
        destination = {"ReplicationDestinationBucketArn": ARCHIVE}
        self.assertTrue(rejected_parameters(template, destination))
        destination["ReplicationDestinationAccountId"] = "222222222222"
        self.assertFalse(rejected_parameters(template, destination))
        self.assertTrue(rejected_parameters(template, {**destination, "LogKmsKeyArn": SOURCE_KEY}))
        self.assertTrue(rejected_parameters(template, {
            **destination, "ReplicationDestinationKmsKeyArn": TARGET_KEY}))
        self.assertFalse(rejected_parameters(template, {
            **destination, "LogKmsKeyArn": SOURCE_KEY,
            "ReplicationDestinationKmsKeyArn": TARGET_KEY}))

    def test_archive_requires_one_account_or_organization_scope(self) -> None:
        """A broad archive permission cannot be created with an empty or ambiguous scope."""
        template = load_template("bedrock-central-bucket")
        self.assertTrue(rejected_parameters(template, {}))
        self.assertFalse(rejected_parameters(template, {"SourceAccountIds": ["111111111111"]}))
        self.assertFalse(rejected_parameters(template, {"SourceOrganizationId": "o-1234567890"}))
        self.assertTrue(rejected_parameters(template, {
            "SourceAccountIds": ["111111111111"], "SourceOrganizationId": "o-1234567890"}))
        self.assertTrue(rejected_parameters(template, {"SourceAccountIds": ["111111111111", ""]}))

    def test_archive_permissions_require_scoped_replication_roles_and_origin_paths(self) -> None:
        """Archive writers cannot use an arbitrary role or another account's native prefix."""
        resources = load_template("bedrock-central-bucket")["Resources"]
        policy = resources["CentralBucketPolicy"]["Properties"]["PolicyDocument"]
        allow = next(item for item in policy["Statement"] if item["Effect"] == "Allow")
        self.assertEqual(set(allow["Action"]), {"s3:ReplicateObject", "s3:ReplicateTags"})
        self.assertIn("aws:PrincipalArn", allow["Condition"]["ArnLike"])
        self.assertIn("aws:PrincipalAccount", json.dumps(allow["Condition"]))
        self.assertIn("aws:PrincipalOrgID", json.dumps(allow["Condition"]))
        self.assertTrue(all("${!aws:PrincipalAccount}" in item["Fn::Sub"]
                            for item in allow["Resource"]))

    def test_original_bucket_remains_the_only_vantage_read_target(self) -> None:
        """Replication does not silently switch GA enrichment to the central bucket."""
        resources = load_template("bedrock-logging")["Resources"]
        policy = resources["VantageManagedReadPolicy"]["Properties"]["PolicyDocument"]
        vantage_policy = json.dumps(policy)
        self.assertNotIn("ReplicationDestinationBucketArn", vantage_policy)
        self.assertIn("ExistingLogBucket", vantage_policy)
        self.assertIn("LoggingBucket", vantage_policy)
        self.assertNotIn("VantageManagedReadPolicy",
                         load_template("bedrock-central-bucket")["Resources"])

    def test_vantage_grant_does_not_consume_the_external_roles_inline_quota(self) -> None:
        """Adding a source must not exhaust the Vantage role's 10,240-byte inline quota."""
        template = load_template("bedrock-logging")
        resources = template["Resources"]
        grants = [resource for resource in resources.values()
                  if any(name in json.dumps(resource.get("Properties", {}).get("Roles", []))
                         for name in ("VantageCrossAccountRole", "VantageRoleLookup"))]
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0]["Type"], "AWS::IAM::ManagedPolicy")
        self.assertNotIn("ManagedPolicyName", grants[0]["Properties"])
        self.assertNotIn("VantageReadPolicy", resources)
        self.assertIn("VantageManagedReadPolicy", resources["LoggingConfiguration"]["DependsOn"])
        self.assertEqual(template["Outputs"]["VantageReadPolicyArn"]["Value"],
                         {"Ref": "VantageManagedReadPolicy"})

    def test_native_bucket_location_check_has_no_list_prefix_condition(self) -> None:
        """Native Check Permissions can locate the bucket before sending a list prefix."""
        resources = load_template("bedrock-logging")["Resources"]
        policy = resources["VantageManagedReadPolicy"]["Properties"]["PolicyDocument"]
        statements = policy["Statement"]
        location = [item for item in statements if item.get("Action") == "s3:GetBucketLocation"]
        self.assertEqual(len(location), 1)
        self.assertNotIn("Condition", location[0])
        self.assertEqual(location[0]["Resource"]["Fn::Sub"][0],
                         "arn:${AWS::Partition}:s3:::${Bucket}")
        self.assertNotIn("ReplicationDestinationBucketArn", json.dumps(location[0]))

    def test_retained_buckets_keep_delivery_and_replication_dependencies(self) -> None:
        """Retained logging must not point at a bucket stripped of its delivery permissions."""
        resources = load_template("bedrock-logging")["Resources"]
        for name in ("LoggingBucket", "LoggingBucketPolicy", "ReplicationRole"):
            with self.subTest(name=name):
                self.assertEqual(resources[name]["DeletionPolicy"], "Retain")
                self.assertEqual(resources[name]["UpdateReplacePolicy"], "Retain")
        role = json.dumps(resources["ReplicationRole"])
        self.assertNotIn('"Fn::GetAtt": "LoggingBucket.Arn"', role)
        self.assertNotIn('"Ref": "LoggingBucket"', role)

    def test_replication_toggle_keeps_the_role_owned_with_permissions_only_when_enabled(self) -> None:
        """Disabling replication cannot orphan the retained role or leave it able to replicate."""
        template = load_template("bedrock-logging")
        defaults = {name: parameter_default(item)
                    for name, item in template["Parameters"].items()}
        role = template["Resources"]["ReplicationRole"]
        policies = role["Properties"]["Policies"]["Fn::If"]
        replication = template["Resources"]["LoggingBucket"]["Properties"][
            "ReplicationConfiguration"]["Fn::If"]
        cases = [(destination, source_key) for destination in ("", ARCHIVE)
                 for source_key in ("", SOURCE_KEY)]
        for destination, source_key in cases:
            with self.subTest(destination=destination, source_key=source_key):
                values = {**defaults, "ReplicationDestinationBucketArn": destination,
                          "ReplicationDestinationAccountId": "222222222222" if destination else "",
                          "LogKmsKeyArn": source_key,
                          "ReplicationDestinationKmsKeyArn": TARGET_KEY
                          if destination and source_key else ""}
                self.assertFalse(rejected_parameters(template, values))
                conditions = {name: rule_value(value, values)
                              for name, value in template["Conditions"].items()}
                self.assertTrue(conditions[role["Condition"]])
                selected_policies = policies[1 if conditions[policies[0]] else 2]
                selected_replication = replication[1 if conditions[replication[0]] else 2]
                if not destination:
                    self.assertEqual(selected_policies, {"Ref": "AWS::NoValue"})
                    self.assertEqual(selected_replication, {"Ref": "AWS::NoValue"})
                    continue
                self.assertEqual(len(selected_policies), 1)
                self.assertEqual(selected_replication["Role"],
                                 {"Fn::GetAtt": "ReplicationRole.Arn"})
                statements = selected_policies[0]["PolicyDocument"]["Statement"]
                self.assertTrue(any(item.get("Action") == ["s3:ReplicateObject", "s3:ReplicateTags"]
                                    for item in statements))
        self.assertNotIn("ManagedPolicyArns", role["Properties"])
        self.assertEqual(role["DeletionPolicy"], "Retain")
        self.assertEqual(role["UpdateReplacePolicy"], "Retain")

    def test_reused_bucket_does_not_create_an_idle_replication_role(self) -> None:
        """Reusing customer logging does not introduce a role for an unmanaged bucket."""
        template = load_template("bedrock-logging")
        role = template["Resources"]["ReplicationRole"]
        defaults = {name: parameter_default(item)
                    for name, item in template["Parameters"].items()}
        values = {**defaults, "ExistingLogBucket": "customer-logs", "LoggingMode": "Reuse"}
        self.assertFalse(rule_value(template["Conditions"][role["Condition"]], values))


if __name__ == "__main__":
    unittest.main()
