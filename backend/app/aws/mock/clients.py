"""Canned boto3-style clients for CLOUDSAGE_AWS_MODE=mock.

They answer the same read-only calls the tools make, with responses shaped like the real AWS
APIs, so tools run unchanged in local development. The data is a fixed sample story (an API
worker whose root volume filled up) and is clearly not real infrastructure.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.aws.mock import _RESOURCES

_EC2 = [r for r in _RESOURCES if r[0] == "ec2"]
_STATUS = {
    "unhealthy": ("impaired", "ok"),
    "degraded": ("initializing", "ok"),
    "healthy": ("ok", "ok"),
}


class _NotFound(Exception):
    pass


class _Exceptions:
    ResourceNotFoundException = _NotFound


def mock_client_factory(account_id: str, region: str, now: datetime):
    now = now.astimezone(UTC)

    def factory(service: str) -> Any:
        if service == "ec2":
            return _Ec2(account_id, region, now)
        if service == "cloudwatch":
            return _CloudWatch(region, now)
        if service == "logs":
            return _Logs(region, now)
        if service == "ecs":
            return _Ecs(account_id, region, now)
        if service == "rds":
            return _Rds(region, now)
        if service == "lambda":
            return _Lambda(account_id, region, now)
        raise NotImplementedError(f"No mock client for {service}")

    return factory


def _instances(region: str) -> list[tuple]:
    return [r for r in _EC2 if r[4] == region]


class _Ec2:
    def __init__(self, account_id: str, region: str, now: datetime) -> None:
        self.account_id, self.region, self.now = account_id, region, now

    def _select(self, ids: list[str] | None, filters: list[dict] | None = None) -> list[tuple]:
        rows = _instances(self.region)
        if ids:
            rows = [r for r in rows if r[2] in ids]
        for f in filters or []:
            if f["Name"] == "tag:Name":
                needle = f["Values"][0].strip("*").lower()
                rows = [r for r in rows if needle in r[3].lower()]
            if f["Name"] == "instance-state-name" and "running" not in f["Values"]:
                rows = []
        return rows

    def describe_instances(self, InstanceIds=None, Filters=None, **_: Any) -> dict:  # noqa: N803
        out = []
        for i, (_s, _t, ident, name, region, _h, _m) in enumerate(
            self._select(InstanceIds, Filters)
        ):
            out.append(
                {
                    "InstanceId": ident,
                    "State": {"Name": "running"},
                    "InstanceType": "m6i.large" if "api" in name else "c6i.xlarge",
                    "Placement": {"AvailabilityZone": f"{region}{'abc'[i % 3]}"},
                    "LaunchTime": self.now - timedelta(days=12 + i),
                    "PrivateIpAddress": f"10.0.{i + 1}.{20 + i}",
                    "ImageId": "ami-0abc1234def567890",
                    "VpcId": "vpc-0a1b2c3d",
                    "SubnetId": f"subnet-0{i}a1b2c3",
                    "SecurityGroups": [{"GroupId": "sg-0a1b2c3d4e5f6a7b8"}],
                    "Tags": [{"Key": "Name", "Value": name}, {"Key": "env", "Value": "prod"}],
                }
            )
        return {"Reservations": [{"Instances": out}] if out else []}

    def describe_instance_status(self, InstanceIds=None, **_: Any) -> dict:  # noqa: N803
        statuses = []
        for _s, _t, ident, _n, region, health, _mins in self._select(InstanceIds):
            inst, system = _STATUS.get(health, ("ok", "ok"))
            details = [
                {"Name": "reachability", "Status": "failed" if inst == "impaired" else "passed"}
            ]
            if inst == "impaired":
                details[0]["ImpairedSince"] = self.now - timedelta(minutes=52)
            statuses.append(
                {
                    "InstanceId": ident,
                    "AvailabilityZone": f"{region}a",
                    "InstanceState": {"Name": "running"},
                    "InstanceStatus": {"Status": inst, "Details": details},
                    "SystemStatus": {
                        "Status": system,
                        "Details": [{"Name": "reachability", "Status": "passed"}],
                    },
                    "Events": [],
                }
            )
        return {"InstanceStatuses": statuses}


def _profile(metric: str, dims: dict[str, str]) -> tuple[float, float] | None:
    """(baseline, incident level) for a metric on a sample resource, or None for no data."""
    instance = dims.get("InstanceId")
    sick = instance == "i-0a1b2c3d4e5f67890"
    busy = instance == "i-0fedcba9876543210"
    if instance and instance not in {r[2] for r in _EC2}:
        return None
    return {
        "CPUUtilization": (22.0, 98.9 if sick else 71.0 if busy else 24.0),
        "disk_used_percent": (61.0, 100.0 if sick else 64.0),
        "mem_used_percent": (48.0, 52.0),
        "StatusCheckFailed": (0.0, 1.0 if sick else 0.0),
        "StatusCheckFailed_Instance": (0.0, 1.0 if sick else 0.0),
        "StatusCheckFailed_System": (0.0, 0.0),
        "NetworkIn": (2.1e7, 1.2e6 if sick else 2.3e7),
    }.get(metric)


class _CloudWatch:
    def __init__(self, region: str, now: datetime) -> None:
        self.region, self.now = region, now

    def get_metric_data(self, MetricDataQueries, StartTime, EndTime, **_: Any) -> dict:  # noqa: N803
        q = MetricDataQueries[0]
        stat = q["MetricStat"]
        metric = stat["Metric"]
        dims = {d["Name"]: d["Value"] for d in metric.get("Dimensions", [])}
        period = stat["Period"]
        profile = _profile(metric["MetricName"], dims)
        if profile is None or self.region != "us-east-1":
            return {
                "MetricDataResults": [
                    {"Id": q["Id"], "Timestamps": [], "Values": [], "StatusCode": "Complete"}
                ]
            }
        base, peak = profile
        onset = self.now - timedelta(minutes=55)
        ts, vals = [], []
        t = StartTime
        n = 0
        while t <= EndTime and n < 500:
            ramp = min(1.0, max(0.0, (t - onset).total_seconds() / 600))
            wobble = math.sin(n / 3.0) * (0.02 * max(base, 1.0))
            vals.append(round(base + (peak - base) * ramp + (0 if ramp >= 1 else wobble), 2))
            ts.append(t)
            t += timedelta(seconds=period)
            n += 1
        return {
            "MetricDataResults": [
                {
                    "Id": q["Id"],
                    "Label": metric["MetricName"],
                    "Timestamps": ts,
                    "Values": vals,
                    "StatusCode": "Complete",
                }
            ]
        }

    def describe_alarms(self, StateValue=None, AlarmNamePrefix=None, **_: Any) -> dict:  # noqa: N803
        if self.region != "us-east-1":
            return {"MetricAlarms": []}
        alarms = [
            (
                "api-worker-3-status-check",
                "ALARM",
                "StatusCheckFailed",
                "i-0a1b2c3d4e5f67890",
                "Threshold Crossed: 1 datapoint [1.0] was >= the threshold (1.0).",
                50,
                1.0,
            ),
            (
                "api-worker-3-disk-high",
                "ALARM",
                "disk_used_percent",
                "i-0a1b2c3d4e5f67890",
                "Threshold Crossed: 3 datapoints were greater than the threshold (90.0).",
                53,
                90.0,
            ),
            (
                "batch-runner-1-cpu-high",
                "OK",
                "CPUUtilization",
                "i-0fedcba9876543210",
                "Threshold Crossed: no datapoints were greater than the threshold (85.0).",
                180,
                85.0,
            ),
        ]
        out = []
        for name, state, metric, instance, reason, mins, threshold in alarms:
            if StateValue and state != StateValue:
                continue
            if AlarmNamePrefix and not name.startswith(AlarmNamePrefix):
                continue
            out.append(
                {
                    "AlarmName": name,
                    "StateValue": state,
                    "StateReason": reason,
                    "StateUpdatedTimestamp": self.now - timedelta(minutes=mins),
                    "Namespace": "CWAgent" if metric == "disk_used_percent" else "AWS/EC2",
                    "MetricName": metric,
                    "Dimensions": [{"Name": "InstanceId", "Value": instance}],
                    "Statistic": "Maximum",
                    "ComparisonOperator": "GreaterThanOrEqualToThreshold",
                    "Threshold": threshold,
                    "Period": 60,
                    "EvaluationPeriods": 3,
                }
            )
        return {"MetricAlarms": out}


_LOGS = {
    "/platform/api-worker": [
        (58, "api-worker-3/app", "WARN log volume /var/log/app at 96% capacity"),
        (55, "api-worker-3/app", "ERROR write failed: No space left on device (errno 28)"),
        (
            54,
            "api-worker-3/app",
            "ERROR failed to rotate /var/log/app/requests.log: No space left on device",
        ),
        (52, "api-worker-3/app", "ERROR health endpoint returned 503: cannot write session file"),
        (40, "api-worker-3/app", "ERROR write failed: No space left on device (errno 28)"),
        (35, "api-worker-1/app", "INFO request completed status=200 duration_ms=41"),
        (20, "api-worker-3/app", "ERROR write failed: No space left on device (errno 28)"),
    ],
    "/platform/batch-runner": [
        (90, "batch-runner-1/jobs", "INFO nightly export started"),
        (30, "batch-runner-1/jobs", "WARN export taking longer than usual (rows=4.1M)"),
    ],
}


def _matches(pattern: str, message: str) -> bool:
    if not pattern:
        return True
    terms = re.findall(r'\?"[^"]+"|\?\S+|"[^"]+"|\S+', pattern)
    optional = [t[1:].strip('"') for t in terms if t.startswith("?")]
    required = [t.strip('"') for t in terms if not t.startswith("?")]
    lower = message.lower()
    if any(r.lower() not in lower for r in required):
        return False
    return not optional or any(o.lower() in lower for o in optional)


class _Logs:
    exceptions = _Exceptions

    def __init__(self, region: str, now: datetime) -> None:
        self.region, self.now = region, now

    def _groups(self) -> dict[str, list]:
        return _LOGS if self.region == "us-east-1" else {}

    def filter_log_events(
        self, logGroupName, startTime, endTime, limit=50, filterPattern="", **_: Any
    ) -> dict:  # noqa: N803,E501
        groups = self._groups()
        if logGroupName not in groups:
            raise _NotFound(logGroupName)
        events = []
        for i, (mins, stream, message) in enumerate(groups[logGroupName]):
            ts = int((self.now - timedelta(minutes=mins)).timestamp() * 1000)
            if startTime <= ts <= endTime and _matches(filterPattern, message):
                events.append(
                    {
                        "timestamp": ts,
                        "logStreamName": stream,
                        "message": message,
                        "eventId": str(i),
                    }
                )
        return {"events": events[:limit]}

    def describe_log_groups(self, logGroupNamePrefix=None, limit=50, **_: Any) -> dict:  # noqa: N803
        created = int((self.now - timedelta(days=200)).timestamp() * 1000)
        return {
            "logGroups": [
                {
                    "logGroupName": g,
                    "retentionInDays": 30,
                    "storedBytes": 52_428_800,
                    "creationTime": created,
                }
                for g in self._groups()
                if not logGroupNamePrefix or g.startswith(logGroupNamePrefix)
            ][:limit]
        }


# ---------- ECS, RDS, Lambda (Phase 6) ----------


class _EcsExceptions:
    class ClusterNotFoundException(Exception):
        pass


class _Ecs:
    exceptions = _EcsExceptions

    def __init__(self, account_id: str, region: str, now: datetime) -> None:
        self.account_id, self.region, self.now = account_id, region, now

    def _arn(self, kind: str, path: str) -> str:
        return f"arn:aws:ecs:{self.region}:{self.account_id}:{kind}/{path}"

    def _services(self) -> dict[str, dict[str, dict]]:
        if self.region == "us-east-1":
            return {
                "prod-core": {
                    "payments-api": {
                        "desired": 4,
                        "running": 2,
                        "pending": 1,
                        "td": "payments-api:42",
                        "deployments": [
                            ("PRIMARY", "IN_PROGRESS", "payments-api:43", 4, 1, 6, 18),
                            ("ACTIVE", "COMPLETED", "payments-api:42", 4, 2, 0, 1440),
                        ],
                        "events": [
                            (2, "(service payments-api) has started 1 tasks: (task 9f1c...)."),
                            (
                                4,
                                "(service payments-api) deployment ecs-svc/4417 has 6 failed "
                                "tasks; tasks stopped with exit code 137 (OutOfMemoryError).",
                            ),
                            (
                                18,
                                "(service payments-api) has begun a deployment of "
                                "task definition payments-api:43.",
                            ),
                        ],
                    },
                    "checkout": {
                        "desired": 3,
                        "running": 3,
                        "pending": 0,
                        "td": "checkout:17",
                        "deployments": [("PRIMARY", "COMPLETED", "checkout:17", 3, 3, 0, 4000)],
                        "events": [(12, "(service checkout) has reached a steady state.")],
                    },
                }
            }
        if self.region == "eu-west-1":
            return {
                "prod-eu": {
                    "auth-service": {
                        "desired": 2,
                        "running": 2,
                        "pending": 0,
                        "td": "auth-service:9",
                        "deployments": [("PRIMARY", "COMPLETED", "auth-service:9", 2, 2, 0, 9000)],
                        "events": [(30, "(service auth-service) has reached a steady state.")],
                    }
                }
            }
        return {}

    def list_clusters(self, **_: Any) -> dict:
        return {"clusterArns": [self._arn("cluster", c) for c in self._services()]}

    def list_services(self, cluster: str, **_: Any) -> dict:
        name = cluster.rsplit("/", 1)[-1]
        if name not in self._services():
            raise _EcsExceptions.ClusterNotFoundException(cluster)
        return {
            "serviceArns": [self._arn("service", f"{name}/{s}") for s in self._services()[name]]
        }

    def describe_services(self, cluster: str, services: list[str], **_: Any) -> dict:
        cname = cluster.rsplit("/", 1)[-1]
        known = self._services().get(cname, {})
        out, failures = [], []
        for ref in services:
            sname = ref.rsplit("/", 1)[-1]
            s = known.get(sname)
            if not s:
                failures.append(
                    {"arn": self._arn("service", f"{cname}/{sname}"), "reason": "MISSING"}
                )
                continue
            out.append(
                {
                    "serviceName": sname,
                    "serviceArn": self._arn("service", f"{cname}/{sname}"),
                    "status": "ACTIVE",
                    "launchType": "FARGATE",
                    "desiredCount": s["desired"],
                    "runningCount": s["running"],
                    "pendingCount": s["pending"],
                    "taskDefinition": self._arn("task-definition", s["td"]),
                    "deployments": [
                        {
                            "status": st,
                            "rolloutState": ro,
                            "taskDefinition": self._arn("task-definition", td),
                            "desiredCount": d,
                            "runningCount": r,
                            "failedTasks": f,
                            "createdAt": self.now - timedelta(minutes=m),
                            "updatedAt": self.now - timedelta(minutes=min(m, 2)),
                            "rolloutStateReason": "ECS deployment ecs-svc/4417 in progress."
                            if ro == "IN_PROGRESS"
                            else None,
                        }
                        for st, ro, td, d, r, f, m in s["deployments"]
                    ],
                    "events": [
                        {"createdAt": self.now - timedelta(minutes=m), "message": msg}
                        for m, msg in s["events"]
                    ],
                }
            )
        return {"services": out, "failures": failures}

    def list_tasks(self, cluster: str, serviceName: str | None = None, **_: Any) -> dict:  # noqa: N803
        cname = cluster.rsplit("/", 1)[-1]
        if cname not in self._services():
            raise _EcsExceptions.ClusterNotFoundException(cluster)
        if cname == "prod-core" and serviceName in (None, "payments-api"):
            return {"taskArns": [self._arn("task", f"prod-core/{i:032x}") for i in (0xA1, 0xB2)]}
        return {"taskArns": []}

    def describe_tasks(self, cluster: str, tasks: list[str], **_: Any) -> dict:
        return {
            "tasks": [
                {
                    "taskArn": t,
                    "group": "service:payments-api",
                    "taskDefinitionArn": self._arn("task-definition", "payments-api:43"),
                    "lastStatus": "STOPPED",
                    "stopCode": "EssentialContainerExited",
                    "stoppedReason": "Essential container in task exited",
                    "startedAt": self.now - timedelta(minutes=9 + i * 4),
                    "stoppedAt": self.now - timedelta(minutes=6 + i * 4),
                    "containers": [
                        {
                            "name": "app",
                            "lastStatus": "STOPPED",
                            "exitCode": 137,
                            "reason": "OutOfMemoryError: Container killed due to memory usage",
                        }
                    ],
                }
                for i, t in enumerate(tasks)
            ]
        }


class _RdsExceptions:
    class DBInstanceNotFoundFault(Exception):
        pass


class _Rds:
    exceptions = _RdsExceptions
    _DBS = {
        "orders-db": ("available", "db.r6g.large", 500, None, ["reporting-replica"]),
        "reporting-replica": ("storage-optimization", "db.r6g.large", 500, "orders-db", []),
    }

    def __init__(self, region: str, now: datetime) -> None:
        self.region, self.now = region, now

    def describe_db_instances(self, DBInstanceIdentifier: str | None = None, **_: Any) -> dict:  # noqa: N803
        dbs = self._DBS if self.region == "us-east-1" else {}
        if DBInstanceIdentifier and DBInstanceIdentifier not in dbs:
            raise _RdsExceptions.DBInstanceNotFoundFault(DBInstanceIdentifier)
        return {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": k,
                    "DBInstanceStatus": st,
                    "Engine": "postgres",
                    "EngineVersion": "16.4",
                    "DBInstanceClass": cls,
                    "AllocatedStorage": gb,
                    "MaxAllocatedStorage": 1000,
                    "StorageType": "gp3",
                    "MultiAZ": src is None,
                    "AvailabilityZone": "us-east-1a",
                    "ReadReplicaSourceDBInstanceIdentifier": src,
                    "ReadReplicaDBInstanceIdentifiers": reps,
                    "PendingModifiedValues": {},
                    "PreferredMaintenanceWindow": "sun:04:00-sun:04:30",
                    "InstanceCreateTime": self.now - timedelta(days=400),
                }
                for k, (st, cls, gb, src, reps) in dbs.items()
                if not DBInstanceIdentifier or k == DBInstanceIdentifier
            ]
        }

    def describe_events(self, SourceIdentifier: str, StartTime, EndTime, **_: Any) -> dict:  # noqa: N803
        events = (
            {
                "reporting-replica": [
                    (50, "Storage optimization started.", ["notification"]),
                    (49, "Replica lag exceeded 300 seconds.", ["read replica"]),
                ],
                "orders-db": [(300, "Finished DB Instance backup", ["backup"])],
            }.get(SourceIdentifier, [])
            if self.region == "us-east-1"
            else []
        )
        return {
            "Events": [
                {
                    "Date": self.now - timedelta(minutes=m),
                    "Message": msg,
                    "EventCategories": cats,
                    "SourceIdentifier": SourceIdentifier,
                }
                for m, msg, cats in events
                if StartTime <= self.now - timedelta(minutes=m) <= EndTime
            ]
        }


class _LambdaExceptions:
    class ResourceNotFoundException(Exception):
        pass


class _Lambda:
    exceptions = _LambdaExceptions
    _FNS = {
        "us-west-2": {"order-processor": ("python3.12", 512, 30, 137)},
        "us-east-1": {
            "invoice-renderer": ("nodejs20.x", 1024, 60, 60),
            "audit-event-archiver": ("python3.12", 256, 120, 75),
        },
    }

    def __init__(self, account_id: str, region: str, now: datetime) -> None:
        self.account_id, self.region, self.now = account_id, region, now

    def _cfg(self, name: str, spec: tuple) -> dict:
        runtime, mem, timeout, mins = spec
        return {
            "FunctionName": name,
            "FunctionArn": f"arn:aws:lambda:{self.region}:{self.account_id}:function:{name}",
            "Runtime": runtime,
            "Handler": "app.handler",
            "MemorySize": mem,
            "Timeout": timeout,
            "PackageType": "Zip",
            "Architectures": ["arm64"],
            "LastModified": (self.now - timedelta(minutes=mins)).strftime(
                "%Y-%m-%dT%H:%M:%S.000+0000"
            ),
            "Version": "$LATEST",
            "State": "Active",
            "LastUpdateStatus": "Successful",
            "Environment": {"Variables": {"DB_PASSWORD": "never-returned"}},
        }

    def get_function_configuration(self, FunctionName: str, **_: Any) -> dict:  # noqa: N803
        name = FunctionName.rsplit(":", 1)[-1] if FunctionName.startswith("arn:") else FunctionName
        spec = self._FNS.get(self.region, {}).get(name)
        if not spec:
            raise _LambdaExceptions.ResourceNotFoundException(FunctionName)
        return self._cfg(name, spec)

    def list_functions(self, **_: Any) -> dict:
        return {"Functions": [self._cfg(n, s) for n, s in self._FNS.get(self.region, {}).items()]}
