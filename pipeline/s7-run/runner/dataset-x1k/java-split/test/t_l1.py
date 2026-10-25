#!/usr/bin/env python3
"""t_l1.py: L1-launch-jv.sh with a fake aws command (no AWS call).

On-demand by default: the fleet request (no SpotOptions, OnDemandOptions lowest-price, 2 types x 4
subnets, the tags), DRY_RUN calls create-fleet only with --dry-run, the on-demand vCPU check
against the quota, a launch (instances.txt line, a used name refused), an id of the refuse list
refused, a mix of the type pairs refused, and ON_DEMAND=0 (the spot request).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t_jv import KIT, run, write  # noqa: E402

FAKE_AWS = r'''#!/usr/bin/env python3
"""fake aws for L1: answers from FAKE_* variables, logs each call to FAKE_LOG."""
import json, os, shutil, sys
a = sys.argv[1:]
log = os.environ["FAKE_LOG"]
with open(log, "a") as f:
    f.write(" ".join(a) + "\n")
s = " ".join(a)
if a[:2] == ["service-quotas", "get-service-quota"]:
    q = os.environ.get("FAKE_QUOTA", "1152.0")
    if q == "fail":
        sys.exit(255)
    print(q)
elif a[:2] == ["s3", "ls"]:
    sys.exit(0 if os.environ.get("FAKE_INPUT") == "1" else 1)
elif a[:2] == ["ec2", "describe-instances"]:
    if "Name=instance-id,Values=" in s:
        print("${RUNNER_EC2_X1K_LONG_A4}\trunning\n${RUNNER_EC2_BIG}\tstopped")
    elif "Name=tag:Run,Values=java-split" in s:
        print(os.environ.get("FAKE_LIVE", ""))
    elif "Name=tag:Name,Values=" in s:
        print(os.environ.get("FAKE_USED", ""))
    elif "InstanceLifecycle][]" in s:
        n = int(os.environ.get("FAKE_OD_EXTRA", "0"))
        print("m6a.48xlarge\t96\t2")
        for _ in range(n):
            print("c7a.48xlarge\t192\t1")
        print("p5.48xlarge\t96\t2")   # not a standard family: not counted
    elif "instance-lifecycle,Values=spot" in s:
        print(os.environ.get("FAKE_SPOT", ""))
    elif "--instance-ids" in a:
        print("c7a.48xlarge\t${RUNNER_AWS_REGION}b\t${RUNNER_AMI_SPOT}\tNone")
    else:
        sys.exit("fake aws: unknown describe-instances " + s)
elif a[:2] == ["ec2", "create-fleet"]:
    src = a[a.index("--cli-input-json") + 1][len("file://"):]
    shutil.copy(src, os.environ["FAKE_LOG"] + ".req-%d.json" % len(open(log).read().splitlines()))
    if "--dry-run" in a:
        sys.stderr.write("An error occurred (DryRunOperation) when calling the CreateFleet operation: Request would have succeeded, but DryRun flag is set.\n")
        sys.exit(254)
    iid = os.environ.get("FAKE_ID", "i-0aaaaaaaaaaaaaaa1")
    print(json.dumps({"FleetId": "fleet-x", "Errors": [], "Instances": [{"InstanceIds": [iid], "InstanceType": "c7a.48xlarge",
          "LaunchTemplateAndOverrides": {"Overrides": {"InstanceType": "c7a.48xlarge", "SubnetId": "${RUNNER_SUBNET_AZ_B}"}}}]}))
elif a[:2] == ["ec2", "describe-spot-price-history"]:
    print("3.70")
else:
    sys.exit("fake aws: unknown call " + s)
'''


class TL1(unittest.TestCase):
    def setUp(self):
        self.d = d = tempfile.mkdtemp()
        self.home = d + "/kit"
        os.makedirs(self.home)
        write(d + "/aws", FAKE_AWS)
        os.chmod(d + "/aws", 0o755)
        self.log = d + "/aws.log"
        self.env = dict(os.environ, JV_AWS=d + "/aws", JV_HOME=self.home, FAKE_LOG=self.log)
        for v in ("KS", "TYPES", "ON_DEMAND", "DRY_RUN", "REPLACE", "ROOT_GB", "OD_QUOTA"):
            self.env.pop(v, None)

    def tearDown(self):
        shutil.rmtree(self.d)

    def l1(self, **kw):
        return run(["bash", KIT + "/L1-launch-jv.sh"], env=dict(self.env, **kw))

    def calls(self):
        return open(self.log).read().splitlines() if os.path.exists(self.log) else []

    def fleet_calls(self):
        return [c for c in self.calls() if c.startswith("ec2 create-fleet")]

    def test_dry_run_on_demand_default(self):
        r = self.l1(DRY_RUN="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("on-demand quota L-1216C47A: 1152 vCPU", r.stdout)
        self.assertEqual(r.stdout.count("Request would have succeeded"), 4, "4 parts by default")
        self.assertIn("on-demand vCPU in use 192 of 1152", r.stdout)
        fc = self.fleet_calls()
        self.assertEqual(len(fc), 4)
        self.assertTrue(all("--dry-run" in c for c in fc), "DRY_RUN must not launch")
        for k in range(1, 5):
            req = json.load(open(self.home + "/fleet/fleet-dataset-java-split-%d.json" % k))
            self.assertNotIn("SpotOptions", req)
            self.assertEqual(req["Type"], "instant")
            self.assertEqual(req["TargetCapacitySpecification"], {"TotalTargetCapacity": 1, "DefaultTargetCapacityType": "on-demand"})
            self.assertEqual(req["OnDemandOptions"], {"AllocationStrategy": "lowest-price", "MaxTotalPrice": "12.00"})
            ov = req["LaunchTemplateConfigs"][0]["Overrides"]
            self.assertEqual(sorted({o["InstanceType"] for o in ov}), ["c7a.48xlarge", "m7a.48xlarge"])
            self.assertEqual(len({o["SubnetId"] for o in ov}), 4)
            self.assertEqual(len(ov), 8)
            tags = {t["Key"]: t["Value"] for t in req["TagSpecifications"][0]["Tags"]}
            self.assertEqual(tags, {"Project": "cregit-dataset", "Owner": "${RUNNER_USER}", "Run": "java-split",
                                    "Name": "dataset-java-split-%d" % k, "Part": str(k)})
        self.assertFalse(any(c.startswith("s3 ls") for c in self.calls()), "DRY_RUN does not need the input")
        self.assertEqual(open(self.home + "/instances.txt").read(), "")

    def test_quota_refused(self):
        # 192 (A) + 5 x 192 (other on-demand machines) + 192 > 1152
        r = self.l1(DRY_RUN="1", FAKE_OD_EXTRA="5")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ABORT: on-demand vCPU in use 1152 + 192 > quota 1152 (part 1 not launched)", r.stdout)
        self.assertEqual(self.fleet_calls(), [])
        # a smaller quota from service-quotas wins over the default
        r = self.l1(DRY_RUN="1", FAKE_QUOTA="384.0")
        self.assertIn("on-demand vCPU in use 192 of 384", r.stdout)
        # the quota read fails: OD_QUOTA
        r = self.l1(DRY_RUN="1", FAKE_QUOTA="fail", OD_QUOTA="300", KS="1")
        self.assertIn("ABORT: on-demand vCPU in use 192 + 192 > quota 300", r.stdout)

    def test_launch_and_used_name(self):
        r = self.l1(KS="1")
        self.assertIn("ABORT: no java-split/input/SHA256SUMS", r.stdout)
        self.assertEqual(self.fleet_calls(), [])
        r = self.l1(KS="1", FAKE_INPUT="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = open(self.home + "/instances.txt").read()
        self.assertRegex(line, r"^dataset-java-split-1=i-0aaaaaaaaaaaaaaa1 c7a.48xlarge\t${RUNNER_AWS_REGION}b\t${RUNNER_AMI_SPOT}\tNone part=1 price=on-demand launched=")
        self.assertFalse(any("describe-spot-price-history" in c for c in self.calls()))
        r = self.l1(KS="1", FAKE_INPUT="1")
        self.assertIn("ABORT: dataset-java-split-1 is in instances.txt (used); REPLACE=1 launches a replacement", r.stdout)
        r = self.l1(KS="1", FAKE_INPUT="1", REPLACE="1", FAKE_ID="i-0aaaaaaaaaaaaaaa2")
        self.assertIn("dataset-java-split-1-r1=i-0aaaaaaaaaaaaaaa2", open(self.home + "/instances.txt").read())
        r = self.l1(KS="2", FAKE_INPUT="1", FAKE_LIVE="i-0bbbbbbbbbbbbbbb1\tdataset-java-split-2")
        self.assertIn("ABORT: part 2 has a machine", r.stdout)

    def test_refuse_list_id(self):
        for iid in ("${RUNNER_EC2_X1K_LONG_A4}", "${RUNNER_EC2_BIG}", "${RUNNER_EC2_RUST_SPLIT_5_R2}"):
            r = self.l1(KS="3", FAKE_INPUT="1", FAKE_ID=iid)
            self.assertIn("ABORT: the fleet returned an id of the refuse list: " + iid, r.stdout)
        self.assertEqual(open(self.home + "/instances.txt").read(), "")

    def test_type_mix_and_bad_values(self):
        r = self.l1(DRY_RUN="1", TYPES="c7a.48xlarge m6a.48xlarge")
        self.assertIn("ABORT: TYPES mixes the 6a and 7a pairs", r.stdout)
        r = self.l1(DRY_RUN="1", ON_DEMAND="yes")
        self.assertIn("ABORT: ON_DEMAND 'yes'", r.stdout)
        r = self.l1(DRY_RUN="1", KS="0")
        self.assertIn("ABORT: bad part '0'", r.stdout)
        self.assertEqual(self.fleet_calls(), [])

    def test_spot_still_possible(self):
        r = self.l1(DRY_RUN="1", ON_DEMAND="0", KS="2", TYPES="m7a.48xlarge", ROOT_GB="400")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("spot vCPU in use 0 of 1152", r.stdout)
        self.assertFalse(any(c.startswith("service-quotas") for c in self.calls()))
        req = json.load(open(self.home + "/fleet/fleet-dataset-java-split-2.json"))
        self.assertNotIn("OnDemandOptions", req)
        self.assertEqual(req["SpotOptions"]["MaxTotalPrice"], "5.00")
        self.assertEqual(req["TargetCapacitySpecification"]["DefaultTargetCapacityType"], "spot")
        self.assertEqual({o["InstanceType"] for o in req["LaunchTemplateConfigs"][0]["Overrides"]}, {"m7a.48xlarge"})
        self.assertEqual(req["LaunchTemplateConfigs"][0]["Overrides"][0]["BlockDeviceMappings"][0]["Ebs"]["VolumeSize"], 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
