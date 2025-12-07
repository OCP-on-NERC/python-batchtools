# pyright: reportUninitializedInstanceVariable=false
from typing import cast
from typing_extensions import override, Optional

import argparse
import os
import socket
import sys
import time
import uuid

import openshift_client as oc

from .basecommand import Command
from .basecommand import SubParserFactory
from .build_yaml import build_job_body
from .helpers import pretty_print
from .helpers import oc_delete
from .helpers import fmt
from .file_setup import prepare_context
from .prom_metrics import (
    PROMETHEUS_INSTANCE,
    IN_PROGRESS,
    record_batch_observation,
    record_queue_observation,
    record_wall_observation,
    push_registry_text,
)


class CreateJobCommandArgs(argparse.Namespace):
    """Typed args + defaults for `br` command."""

    gpu: str = "v100"
    image: str = "image-registry.openshift-image-registry.svc:5000/redhat-ods-applications/csw-run-f25:latest"
    context: bool = True
    name: str = "job"
    job_id: str = uuid.uuid5(uuid.NAMESPACE_OID, f"{os.getpid()}-{time.time()}").hex
    job_delete: bool = True
    wait: bool = True
    timeout: int = 60 * 15 * 4
    max_sec: int = 60 * 15
    gpu_numreq: int = 1
    gpu_numlim: int = 1
    verbose: int = 0
    command: list[str]


class CreateJobCommand(Command):
    """br: Create and submit a GPU batch job."""

    name: str = "br"
    help: str = "Create and submit a GPU batch job"

    @classmethod
    @override
    def build_parser(cls, subparsers: SubParserFactory):
        p = super().build_parser(subparsers)
        p.add_argument(
            "--gpu", default=CreateJobCommandArgs.gpu, help="Select GPU type"
        )
        p.add_argument(
            "--image", default=CreateJobCommandArgs.image, help="Container image"
        )
        p.add_argument(
            "--context",
            action=argparse.BooleanOptionalAction,
            default=CreateJobCommandArgs.context,
            help="Copy working directory to job context",
        )
        p.add_argument(
            "--name", default=CreateJobCommandArgs.name, help="Base job name"
        )
        p.add_argument(
            "--job-id", default=CreateJobCommandArgs.job_id, help="Job ID suffix"
        )
        p.add_argument(
            "--job-delete",
            action=argparse.BooleanOptionalAction,
            default=CreateJobCommandArgs.job_delete,
            help="Delete job on completion",
        )
        p.add_argument(
            "--wait",
            action=argparse.BooleanOptionalAction,
            default=CreateJobCommandArgs.wait,
            help="Wait for job completion",
        )
        p.add_argument(
            "--timeout",
            default=CreateJobCommandArgs.timeout,
            type=int,
            help="Wait timeout in seconds",
        )
        p.add_argument(
            "--max-sec",
            default=CreateJobCommandArgs.max_sec,
            type=int,
            help="Maximum runtime",
        )
        p.add_argument(
            "--gpu-numreq",
            default=CreateJobCommandArgs.gpu_numreq,
            type=int,
            help="GPUs requested",
        )
        p.add_argument(
            "--gpu-numlim",
            default=CreateJobCommandArgs.gpu_numlim,
            type=int,
            help="GPU limit",
        )
        p.add_argument(
            "command", nargs=argparse.REMAINDER, help="Command to execute in container"
        )
        return p

    @staticmethod
    @override
    def run(args: argparse.Namespace):
        args = cast(CreateJobCommandArgs, args)
        DEFAULT_QUEUES = {
            "v100": "v100-localqueue",
            "a100": "a100-localqueue",
            "h100": "h100-localqueue",
            "none": "dummy-localqueue",
        }

        if not args.command:
            sys.exit("ERROR: you must provide a command")

        if args.gpu not in DEFAULT_QUEUES:
            sys.exit(f"ERROR: unsupported GPU {args.gpu} : no queue found")

        queue_name = DEFAULT_QUEUES[args.gpu]
        job_name = f"{args.name}-{args.gpu}-{args.job_id}"
        container_name = f"{job_name}-container"
        file_to_execute = " ".join(args.command).strip()

        pwd = os.getcwd()
        context_directory = pwd
        jobs_directory = os.path.join(pwd, "jobs")
        output_directory = os.path.join(jobs_directory, job_name)
        dev_pod_name = socket.gethostname()
        getlist = os.path.join(output_directory, "getlist")

        pod = oc.selector(f"pod/{dev_pod_name}").object()
        container = getattr(pod.model.spec, "containers", []) or []
        dev_container_name = container[0].name

        prepare_context(
            context=args.context,
            context_dir=context_directory,
            jobs_dir=jobs_directory,
            output_dir=output_directory,
            getlist_path=getlist,
        )

        try:
            # Build job YAML
            job_body = build_job_body(
                job_name=job_name,
                queue_name=queue_name,
                image=args.image,
                container_name=container_name,
                cmdline=file_to_execute,
                max_sec=args.max_sec,
                gpu=args.gpu,
                gpu_req=args.gpu_numreq,
                gpu_lim=args.gpu_numlim,
                context=args.context,
                devpod_name=dev_pod_name,
                devcontainer=dev_container_name,
                context_dir=context_directory,
                jobs_dir=jobs_directory,
                getlist_path=getlist,
            )

            print(f"Creating job {job_name} in {queue_name}...")
            oc.create(job_body)
            print(f"Job {job_name} created successfully.")

            result_phase = "unknown"
            run_elapsed = None
            queue_wait = None
            total_wall = None

            if args.wait:
                result_phase, run_elapsed, queue_wait, total_wall = log_job_output(
                    job_name=job_name, wait=True, timeout=args.timeout
                )

            if (
                run_elapsed is not None
                or queue_wait is not None
                or total_wall is not None
            ):
                labels = {
                    "job_name": job_name,
                    "gpu": args.gpu,
                    "queue": queue_name,
                    "instance": PROMETHEUS_INSTANCE,
                }

                IN_PROGRESS.labels(**labels, result=result_phase).inc()

                if run_elapsed is not None:
                    record_batch_observation(
                        labels=labels, elapsed_sec=run_elapsed, result=result_phase
                    )
                if queue_wait is not None:
                    record_queue_observation(
                        labels=labels, elapsed_sec=queue_wait, result=result_phase
                    )
                if total_wall is not None:
                    record_wall_observation(
                        labels=labels, elapsed_sec=total_wall, result=result_phase
                    )

                IN_PROGRESS.labels(**labels, result=result_phase).dec()

                group = {
                    "instance": PROMETHEUS_INSTANCE,  # oc project
                    "job_name": job_name,  # unique name
                }

                push_registry_text(grouping_key=group)

        except oc.OpenShiftPythonException as e:
            sys.exit(f"Error occurred while creating job: {e}")

        if args.job_delete and args.wait:
            print(f"RUNDIR: jobs/{job_name}")
            oc_delete("job", job_name)
        else:
            print(
                f"User specified not to wait, or not to delete, so {job_name} must be deleted by user.\n"
                f"You can do this by running:\n"
                f"  batchtools bd {job_name} OR\n"
                f"  oc delete job {job_name}"
            )


def get_pod_status(pod_name: str | None = None) -> str:
    """Return the current status.phase of a pod."""
    pod = oc.selector(f"pod/{pod_name}").object()
    return pod.model.status.phase or "Unknown"


def log_job_output(
    job_name: str, *, wait: bool, timeout: int | None
) -> tuple[str, Optional[float], Optional[float], Optional[float]]:
    """
    Wait for job completion and print logs.

    Returns:
      (result_phase, run_elapsed, queue_wait, total_wall)
    """
    pods = oc.selector("pod", labels={"job-name": job_name}).objects()
    if not pods:
        print(f"No pods found for job {job_name}")
        return ("unknown", None, None, None)

    pod = pods[0]
    pod_name = pod.model.metadata.name

    run_start = None
    result_phase = "unknown"
    run_elapsed = None
    queue_wait = None
    total_wall = None

    if wait:
        start_poll = time.monotonic()
        while True:
            phase = get_pod_status(pod_name)
            if phase == "Running" and run_start is None:
                # time waiting in queue is time from entering the queue to the time it takes to start running
                run_start = time.monotonic()
                queue_wait = run_start - start_poll  # submit -> running

            if phase in ("Succeeded", "Failed"):
                result_phase = phase.lower()
                total_wall = time.monotonic() - start_poll  # submit -> terminal
                print(f"Pod {pod_name} finished with phase={phase}")
                break

            if timeout and (time.monotonic() - start_poll) > timeout:
                print(f"Timeout waiting for pod {pod_name} to complete")
                print(f"Deleting job {job_name}")
                oc_delete("job", job_name)
                total_wall = time.monotonic() - start_poll
                # timeout: no run duration (didn't finish), queue_wait may or may not be set
                print_timing(queue_wait, None, total_wall)
                return ("timeout", None, queue_wait, total_wall)

            time.sleep(2)

    print(pretty_print(pod))

    # compute the runtime using the total time (total_wall)- time waiting in queue (queue_wait)
    if wait:
        if run_start is not None:
            # running status was reached, run_elapsed = terminal - run_start
            if total_wall is None:
                total_wall = time.monotonic() - start_poll  # fallback
            run_elapsed = total_wall - (queue_wait or 0.0)
        else:
            # Never reached Running; keep convention for failures:
            run_elapsed = 0.0 if result_phase == "failed" else None
            if total_wall is None:
                total_wall = 0.0
            if total_wall is not None and queue_wait is None:
                queue_wait = total_wall

    print_timing(queue_wait, run_elapsed, total_wall)
    return (result_phase, run_elapsed, queue_wait, total_wall)


def print_timing(
    queue_wait: Optional[float],
    run_elapsed: Optional[float],
    total_wall: Optional[float],
) -> None:
    print(
        "TIMING: "
        f"queue_wait={fmt(queue_wait)}, "
        f"run_duration={fmt(run_elapsed)}, "
        f"total_wall={fmt(total_wall)}"
    )
