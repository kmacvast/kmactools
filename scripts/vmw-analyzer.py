#!/usr/bin/env python3
################################################################################
# Script Name: vmw-analyzer.py
# Description: Analyze vCenter VMs for downsizing, power-off, and delete candidates.
#
# Author: KMac kmac@vastdata.com
# Version: 0.2
################################################################################

import argparse
import getpass
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim

# Thresholds (override via CLI)
DEFAULT_IDLE_DAYS = 30
CPU_DOWNSIZE_PCT = 25.0
MEM_DOWNSIZE_PCT = 40.0
CPU_IDLE_PCT = 5.0
MEM_IDLE_PCT = 10.0
DISK_NET_IDLE_KBPS = 50.0  # combined avg KB/s over lookback

DEFAULT_PROGRESS_INTERVAL_SEC = 60


class Progress:
    """Print phase progress periodically with ETA."""

    def __init__(self, phase: str, total: int, interval_sec: int = DEFAULT_PROGRESS_INTERVAL_SEC):
        self.phase = phase
        self.total = max(total, 1)
        self.interval_sec = interval_sec
        self.done = 0
        self.t0 = time.monotonic()
        self.last_report = 0.0
        print(f"[{phase}] 0/{total} (0%) starting...", flush=True)

    def tick(self, n: int = 1, detail: str = "") -> None:
        self.done += n
        now = time.monotonic()
        if self.done >= self.total or (now - self.last_report) >= self.interval_sec:
            self._report(detail)
            self.last_report = now

    def finish(self, detail: str = "") -> None:
        self.done = self.total
        self._report(detail or "done")

    def _report(self, detail: str) -> None:
        elapsed = time.monotonic() - self.t0
        pct = min(100.0, 100.0 * self.done / self.total)
        rate = self.done / elapsed if elapsed > 0 else 0.0
        eta_sec = (self.total - self.done) / rate if rate > 0 and self.done < self.total else 0.0
        msg = f"[{self.phase}] {self.done}/{self.total} ({pct:.0f}%) elapsed {elapsed / 60:.1f}m"
        if eta_sec > 0:
            msg += f" ETA {eta_sec / 60:.1f}m"
        if detail:
            msg += f" | {detail}"
        print(msg, flush=True)


def build_host_name_map(content) -> dict[str, str]:
    """Map HostSystem moId -> name; fall back to moId when System.View is denied."""
    view = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)
    names: dict[str, str] = {}
    for host in view.view:
        try:
            names[host._moId] = host.name
        except vim.fault.NoPermission:
            names[host._moId] = host._moId
    view.Destroy()
    return names


PERF_COUNTERS = (
    ("cpu", "usage", "average"),
    ("mem", "usage", "average"),
    ("disk", "read", "average"),
    ("disk", "write", "average"),
    ("net", "received", "average"),
    ("net", "transmitted", "average"),
)


def connect_vcenter(host: str, user: str, password: str, port: int = 443):
    """Connect to vCenter; pyvmomi 9.x removed SmartConnectNoSSL."""
    return SmartConnect(
        host=host,
        user=user,
        pwd=password,
        port=port,
        disableSslCertValidation=True,
    )


def build_counter_map(perf_manager) -> dict[str, int]:
    """Map 'group.name.rollup' -> counterId."""
    wanted = {f"{g}.{n}.{r}" for g, n, r in PERF_COUNTERS}
    out = {}
    for counter in perf_manager.perfCounter:
        key = f"{counter.groupInfo.key}.{counter.nameInfo.key}.{counter.rollupType}"
        if key in wanted:
            out[key] = counter.key
    missing = wanted - set(out.keys())
    if missing:
        print(f"Warning: performance counters not found: {', '.join(sorted(missing))}")
    return out


def interval_retention_seconds(interval) -> int:
    """vCenter PerfInterval.length is retention window in seconds (not sample count)."""
    return interval.length


def align_time(dt: datetime, period: int) -> datetime:
    """Round down to sampling-period boundary (QueryPerf requirement)."""
    ts = int(dt.timestamp())
    return datetime.fromtimestamp(ts - (ts % period), tz=timezone.utc).replace(tzinfo=None)


def pick_historical_interval(perf_manager, lookback_days: int) -> vim.PerformanceManager.HistoricalInterval:
    """Pick finest enabled interval that retains at least lookback_days of data."""
    target_seconds = lookback_days * 86400
    enabled = [i for i in perf_manager.historicalInterval if i.enabled]
    if not enabled:
        enabled = list(perf_manager.historicalInterval)
    candidates = [i for i in enabled if interval_retention_seconds(i) >= target_seconds]
    if candidates:
        return min(candidates, key=lambda i: i.samplingPeriod)
    return max(enabled, key=interval_retention_seconds)


def average_series(values: list[int]) -> float | None:
    """Average perf samples; VMware uses -1 for unavailable."""
    good = [v for v in values if v is not None and v >= 0]
    if not good:
        return None
    return sum(good) / len(good)


def to_percent(raw: float | None) -> float | None:
    """Normalize CPU/mem counters (often hundredths of a percent)."""
    if raw is None:
        return None
    return raw / 100.0 if raw > 100 else raw


def _parse_perf_results(perf_data, counter_map: dict[str, int], id_to_name: dict[int, str]) -> dict[str, dict[str, float | None]]:
    parsed: dict[str, dict[str, float | None]] = {}
    for entity_result in perf_data:
        vm_id = entity_result.entity._moId
        metrics: dict[str, list[int]] = {name: [] for name in counter_map}
        for series in entity_result.value:
            name = id_to_name.get(series.id.counterId)
            if name and series.value:
                metrics[name].extend(series.value)
        parsed[vm_id] = {name: average_series(samples) for name, samples in metrics.items()}
    return parsed


def _query_perf_batch(
    perf_manager,
    batch: list[vim.VirtualMachine],
    metric_ids,
    interval_id: int,
    start: datetime,
    end: datetime,
    max_sample: int,
):
    """QueryPerf with start/end; fall back to maxSample on interval errors."""
    specs = [
        vim.PerformanceManager.QuerySpec(
            entity=vm,
            metricId=metric_ids,
            startTime=start,
            endTime=end,
            intervalId=interval_id,
            format="normal",
        )
        for vm in batch
    ]
    try:
        return perf_manager.QueryPerf(querySpec=specs)
    except (vim.fault.RestrictedByAdministrator, vim.fault.InvalidArgument):
        specs = [
            vim.PerformanceManager.QuerySpec(
                entity=vm,
                metricId=metric_ids,
                intervalId=interval_id,
                maxSample=max_sample,
                format="normal",
            )
            for vm in batch
        ]
        return perf_manager.QueryPerf(querySpec=specs)


def query_vm_performance(
    perf_manager,
    counter_map: dict[str, int],
    vms: list[vim.VirtualMachine],
    lookback_days: int,
    chunk_size: int = 8,
    progress_interval_sec: int = DEFAULT_PROGRESS_INTERVAL_SEC,
) -> dict[str, dict[str, float | None]]:
    """Batch QueryPerf for powered-on VMs. Returns vm._moId -> metric averages."""
    interval = pick_historical_interval(perf_manager, lookback_days)
    interval_id = interval.samplingPeriod
    retention_seconds = interval_retention_seconds(interval)
    span_seconds = min(lookback_days * 86400, retention_seconds)
    max_sample = max(1, span_seconds // interval_id)

    end = align_time(datetime.now(timezone.utc).replace(tzinfo=None), interval_id)
    start = align_time(end - timedelta(seconds=span_seconds), interval_id)

    print(
        f"Using perf interval '{interval.name}' "
        f"(intervalId={interval_id}s, query span={span_seconds // 86400}d, batch={chunk_size})"
    )

    metric_ids = [
        vim.PerformanceManager.MetricId(counterId=cid, instance="*")
        for cid in counter_map.values()
    ]
    id_to_name = {cid: name for name, cid in counter_map.items()}

    powered_on = [vm for vm in vms if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn]
    results: dict[str, dict[str, float | None]] = {}
    batch_count = (len(powered_on) + chunk_size - 1) // chunk_size
    progress = Progress("perf metrics", batch_count, progress_interval_sec)

    for batch_idx, i in enumerate(range(0, len(powered_on), chunk_size)):
        batch = powered_on[i : i + chunk_size]
        batch_names = ", ".join(vm.name for vm in batch[:3])
        if len(batch) > 3:
            batch_names += f", +{len(batch) - 3} more"
        try:
            perf_data = _query_perf_batch(
                perf_manager, batch, metric_ids, interval_id, start, end, max_sample
            )
            results.update(_parse_perf_results(perf_data, counter_map, id_to_name))
        except vim.fault.RestrictedByAdministrator:
            for vm in batch:
                try:
                    perf_data = _query_perf_batch(
                        perf_manager, [vm], metric_ids, interval_id, start, end, max_sample
                    )
                    results.update(_parse_perf_results(perf_data, counter_map, id_to_name))
                except Exception as exc:
                    print(f"Warning: perf skipped {vm.name}: {exc}", flush=True)
        except Exception as exc:
            print(f"Warning: perf batch {i} failed: {exc}", flush=True)
        progress.tick(1, f"{len(results)} VMs sampled | batch: {batch_names}")

    progress.finish(f"{len(results)} powered-on VMs with metrics")
    return results


def last_powered_off_time(content, vm: vim.VirtualMachine) -> datetime | None:
    """Most recent VmPoweredOffEvent for this VM."""
    filt = vim.event.EventFilterSpec(
        entity=vim.event.EventFilterSpec.ByEntity(entity=vm, recursion="self"),
        eventTypeId=["VmPoweredOffEvent"],
        maxCount=1,
    )
    try:
        events = content.eventManager.QueryEvents(filt)
    except Exception:
        return None
    return events[0].createdTime if events else None


def folder_path(vm: vim.VirtualMachine) -> str:
    path = getattr(vm.summary.config, "vmPathName", None) if vm.summary else None
    if path:
        return path.rsplit("/", 1)[0]
    parts = []
    obj = vm.parent
    while obj and getattr(obj, "name", None):
        parts.append(str(obj.name))
        obj = getattr(obj, "parent", None)
    return "/".join(reversed(parts)) if parts else ""


def snapshot_stats(vm: vim.VirtualMachine) -> tuple[int, float]:
    try:
        layout = vm.layoutEx
    except vim.fault.NoPermission:
        return 0, 0.0
    if not layout or not layout.snapshot:
        return 0, 0.0
    files = {f.key: f.size for f in (layout.file or [])}
    total = 0
    for snap in layout.snapshot:
        keys = snap.dataKey
        if not keys:
            continue
        if not isinstance(keys, (list, tuple)):
            keys = [keys]
        for file_key in keys:
            total += files.get(file_key, 0)
    return len(layout.snapshot), round(total / (1024**3), 2)


def classify_vm(
    *,
    power_state: str,
    is_template: bool,
    idle_days: int,
    cpu_pct: float | None,
    mem_pct: float | None,
    disk_kb: float | None,
    net_kb: float | None,
    off_since: datetime | None,
    snapshot_count: int,
    storage_used_gb: float,
) -> tuple[str, str]:
    """Return (Recommendation, Reason)."""
    if is_template:
        return "OK", "Template VM excluded"

    now = datetime.now(timezone.utc)
    if off_since and off_since.tzinfo is None:
        off_since = off_since.replace(tzinfo=timezone.utc)
    days_off = (now - off_since).days if off_since else None

    if power_state == "poweredOff":
        if days_off is not None and days_off >= idle_days:
            if snapshot_count > 0 or storage_used_gb >= 100:
                return (
                    "DELETE",
                    f"Powered off {days_off}d; {snapshot_count} snapshot(s), "
                    f"{storage_used_gb:.1f} GB used",
                )
            return "POWER_OFF", f"Already off {days_off}d (review for decommission)"
        if days_off is not None:
            return "OK", f"Powered off {days_off}d (< {idle_days}d threshold)"
        return "OK", "Powered off (power-off date unknown)"

    # poweredOn
    cpu = cpu_pct if cpu_pct is not None else 999.0
    mem = mem_pct if mem_pct is not None else 999.0
    disk = disk_kb or 0.0
    net = net_kb or 0.0
    activity_kb = disk + net

    if cpu <= CPU_IDLE_PCT and mem <= MEM_IDLE_PCT and activity_kb <= DISK_NET_IDLE_KBPS:
        return (
            "POWER_OFF",
            f"Idle {idle_days}d lookback: CPU {cpu:.1f}%, mem {mem:.1f}%, "
            f"I/O {activity_kb:.0f} KB/s",
        )

    if cpu <= CPU_DOWNSIZE_PCT and mem <= MEM_DOWNSIZE_PCT:
        return (
            "DOWNSIZE",
            f"Low utilization {idle_days}d: CPU {cpu:.1f}%, mem {mem:.1f}%",
        )

    if cpu_pct is None and mem_pct is None:
        return "OK", "No performance samples in lookback window"

    return "OK", f"Active: CPU {cpu:.1f}%, mem {mem:.1f}%, I/O {activity_kb:.0f} KB/s"


def esxi_host_name(summary, host_names: dict[str, str]) -> str:
    host_ref = summary.runtime.host if summary and summary.runtime else None
    if not host_ref:
        return ""
    return host_names.get(host_ref._moId, host_ref._moId)


def collect_vm_rows(
    content,
    vms: list[vim.VirtualMachine],
    perf_by_id: dict,
    idle_days: int,
    host_names: dict[str, str],
    progress_interval_sec: int = DEFAULT_PROGRESS_INTERVAL_SEC,
) -> list[dict]:
    rows = []
    off_vms = [
        vm
        for vm in vms
        if vm.summary.runtime.powerState == vim.VirtualMachinePowerState.poweredOff
    ]
    off_times: dict[str, datetime | None] = {}
    progress = Progress("power-off events", len(off_vms), progress_interval_sec)
    for vm in off_vms:
        off_times[vm._moId] = last_powered_off_time(content, vm)
        progress.tick(1, vm.name)

    progress = Progress("build report", len(vms), progress_interval_sec)
    for vm in vms:
        summary = vm.summary
        cfg = summary.config
        rt = summary.runtime
        power = rt.powerState
        snap_count, snap_gb = snapshot_stats(vm)
        committed_gb = round((summary.storage.committed or 0) / (1024**3), 2)

        perf = perf_by_id.get(vm._moId, {})
        cpu_pct = to_percent(perf.get("cpu.usage.average"))
        mem_pct = to_percent(perf.get("mem.usage.average"))
        disk_kb = (perf.get("disk.read.average") or 0) + (perf.get("disk.write.average") or 0)
        net_kb = (perf.get("net.received.average") or 0) + (perf.get("net.transmitted.average") or 0)

        recommendation, reason = classify_vm(
            power_state=str(power),
            is_template=bool(cfg.template),
            idle_days=idle_days,
            cpu_pct=cpu_pct,
            mem_pct=mem_pct,
            disk_kb=disk_kb,
            net_kb=net_kb,
            off_since=off_times.get(vm._moId),
            snapshot_count=snap_count,
            storage_used_gb=committed_gb,
        )

        boot = rt.bootTime.strftime("%Y-%m-%d %H:%M:%S") if rt.bootTime else ""
        off_at = off_times.get(vm._moId)
        rows.append(
            {
                "Name": cfg.name,
                "Recommendation": recommendation,
                "Reason": reason,
                "PowerState": str(power),
                "vCPUs": cfg.numCpu,
                "Memory_GB": round(cfg.memorySizeMB / 1024, 1),
                "Avg_CPU_Pct": round(cpu_pct, 1) if cpu_pct is not None else "",
                "Avg_Mem_Pct": round(mem_pct, 1) if mem_pct is not None else "",
                "Avg_DiskNet_KBps": round(disk_kb + net_kb, 1) if perf else "",
                "ESXi_Host": esxi_host_name(summary, host_names),
                "Folder": folder_path(vm),
                "Storage_Used_GB": committed_gb,
                "Snapshot_Count": snap_count,
                "Snapshot_Size_GB": snap_gb,
                "Last_Boot_Time": boot,
                "Last_Powered_Off": off_at.strftime("%Y-%m-%d %H:%M:%S") if off_at else "",
            }
        )
        progress.tick(1, f"{cfg.name} -> {recommendation}")
    progress.finish(f"{len(rows)} rows")
    return rows


def parse_args():
    parser = argparse.ArgumentParser(description="VMware VM utilization and idle analyzer")
    parser.add_argument("--host", default=os.environ.get("VMW_VCENTER_HOST", "10.143.11.129"))
    parser.add_argument(
        "--user",
        default=os.environ.get("VMW_VCENTER_USER", "kevin.mcdonald@jumpcloud.com"),
    )
    parser.add_argument("--port", type=int, default=int(os.environ.get("VMW_VCENTER_PORT", "443")))
    parser.add_argument("--idle-days", type=int, default=DEFAULT_IDLE_DAYS, help="Lookback / idle threshold in days")
    parser.add_argument(
        "--output",
        default=os.path.expanduser("~/Desktop/vcenter_analysis.csv"),
        help="CSV output path",
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=int(os.environ.get("VMW_PROGRESS_INTERVAL", DEFAULT_PROGRESS_INTERVAL_SEC)),
        help="Seconds between progress updates (default: 60)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    password = os.environ.get("VMW_VCENTER_PASSWORD") or getpass.getpass(
        prompt=f"Password for {args.user}: "
    )

    print(f"Connecting to {args.host}...")
    si = connect_vcenter(args.host, args.user, password, args.port)
    content = si.RetrieveContent()

    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    vms = list(container.view)
    container.Destroy()

    powered_on = sum(
        1 for v in vms if v.summary.runtime.powerState == vim.VirtualMachinePowerState.poweredOn
    )
    powered_off = len(vms) - powered_on
    print(
        f"Found {len(vms)} VMs ({powered_on} on, {powered_off} off). "
        f"Progress every {args.progress_interval}s.",
        flush=True,
    )

    print("Loading ESXi host names...", flush=True)
    host_names = build_host_name_map(content)

    print(f"Collecting {args.idle_days}-day performance metrics...", flush=True)
    counter_map = build_counter_map(content.perfManager)
    perf_by_id = query_vm_performance(
        content.perfManager,
        counter_map,
        vms,
        args.idle_days,
        progress_interval_sec=args.progress_interval,
    )

    rows = collect_vm_rows(
        content,
        vms,
        perf_by_id,
        args.idle_days,
        host_names,
        progress_interval_sec=args.progress_interval,
    )
    Disconnect(si)

    print(f"Writing CSV to {args.output}...", flush=True)
    df = pd.DataFrame(rows).sort_values(["Recommendation", "Name"])
    df.to_csv(args.output, index=False)

    summary = df["Recommendation"].value_counts()
    print(f"\nAnalyzed {len(df)} VMs -> {args.output}\n")
    for label in ["DELETE", "POWER_OFF", "DOWNSIZE", "OK"]:
        if label in summary.index:
            print(f"  {label}: {summary[label]}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
