# pyright: reportExplicitAny=false
from typing import Any

rsync_script = """
set -e
export RSYNC_RSH='oc rsh -c {devcontainer}'

mkdir -p {job_name}

rsync -q --archive --no-owner --no-group --omit-dir-times \
    --numeric-ids {devpod_name}:{getlist_path} {job_name}/getlist
rsync -q -r --archive --no-owner --no-group \
    --omit-dir-times --numeric-ids --files-from={job_name}/getlist \
    {devpod_name}:{context_dir}/ {job_name}/
find {job_name} -mindepth 1 -maxdepth 1 > {job_name}/gotlist

(
  cd {job_name} && {cmdline} |& tee {job_name}.log
)

rsync -q --archive --no-owner --no-group \
    --omit-dir-times --no-relative --numeric-ids  \
    --exclude-from={job_name}/gotlist \
    {job_name} {devpod_name}:{jobs_dir}

oc rsh {devpod_name} rm -f \
  {jobs_dir}/{job_name}/getlist

"""


def build_job_body(
    job_name: str,
    queue_name: str,
    image: str,
    container_name: str,
    cmdline: str,
    max_sec: int,
    gpu: str,
    gpu_req: int,
    gpu_lim: int,
    context: bool,
    devpod_name: str,
    devcontainer: str,
    context_dir: str,
    jobs_dir: str,
    getlist_path: str,
) -> dict[str, Any]:
    """
    Build a batch/v1 Job as a dict to pass to oc.create()
    """
    if gpu == "none":
        resources = {
            "requests": {"cpu": "1", "memory": "1Gi"},
            "limits": {"cpu": "1", "memory": "1Gi"},
        }
    else:
        resources = {
            "requests": {"nvidia.com/gpu": str(gpu_req)},
            "limits": {"nvidia.com/gpu": str(gpu_lim)},
        }

    # - when context is False, just run the provided command via /bin/sh -
    if context:
        print("Copying context")
        command = [
            "/bin/bash",
            "-c",
            rsync_script.format_map(locals()),
        ]
    else:
        command = ["/bin/bash", "-c", cmdline]

    body = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "labels": {
                "kueue.x-k8s.io/queue-name": queue_name,
                "test_name": "kueue_test",
            },
        },
        "spec": {
            "parallelism": 1,
            "completions": 1,
            "backoffLimit": 0,
            "activeDeadlineSeconds": max_sec,
            "template": {
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": container_name,
                            "image": image,
                            "command": command,
                            "resources": resources,
                        }
                    ],
                }
            },
        },
    }
    return body
