import pytest
from unittest import mock

import tempfile
import argparse

import batchtools.build_yaml

from batchtools.br import CreateJobCommand, get_pod_status, log_job_output
from tests.helpers import DictToObject


@pytest.fixture
def tempdir():
    with tempfile.TemporaryDirectory() as t:
        yield t


def test_invalid_gpu(args: argparse.Namespace):
    args.gpu = "invalid"
    args.command = ["true"]
    with pytest.raises(SystemExit) as err:
        CreateJobCommand.run(args)

    assert "ERROR: unsupported GPU invalid" in err.value.code


@pytest.mark.parametrize(
    "gpu, resources",
    [
        (
            "v100",
            {
                "requests": {"nvidia.com/gpu": "1"},
                "limits": {"nvidia.com/gpu": "1"},
            },
        ),
        (
            "none",
            {
                "requests": {"cpu": "1", "memory": "1Gi"},
                "limits": {"cpu": "1", "memory": "1Gi"},
            },
        ),
    ],
)
@mock.patch("batchtools.br.log_job_output", return_value=("succeeded", 1.0, 0.5, 1.5))
@mock.patch("openshift_client.create", name="create")
@mock.patch("openshift_client.selector", name="selector")
@mock.patch("socket.gethostname", name="gethostname")
@mock.patch("os.getcwd", name="getcwd")
def test_create_job_nowait(
    mock_getcwd,
    mock_gethostname,
    mock_selector,
    mock_create,
    mock_log_job_output,
    gpu,
    resources,
    args: argparse.Namespace,
    tempdir,
    parser,
    subparsers,
):
    """
    Even if args.wait is False, CreateJobCommand.run should still build the
    correct Job object and call oc.create() with it. We stub out
    log_job_output so this test does not depend on pod selectors or timing.
    """
    CreateJobCommand.build_parser(subparsers)
    args = parser.parse_args(["br"])
    args.wait = False
    args.job_id = "test"
    args.image = "test-image"
    args.gpu = gpu
    args.command = ["true"]

    queue_name = "dummy-localqueue" if gpu == "none" else f"{gpu}-localqueue"

    mock_getcwd.return_value = tempdir
    mock_gethostname.return_value = "testhost"

    pod = DictToObject(
        {
            "model": {
                "metadata": {"name": "testpod"},
                "spec": {"containers": [{"name": "container1"}]},
            }
        }
    )

    mock_result = mock.Mock()
    mock_result.object.return_value = pod
    mock_selector.return_value = mock_result

    expected = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": f"job-{gpu}-test",
            "labels": {
                "kueue.x-k8s.io/queue-name": queue_name,
                "test_name": "kueue_test",
            },
        },
        "spec": {
            "parallelism": 1,
            "completions": 1,
            "backoffLimit": 0,
            "activeDeadlineSeconds": 900,
            "template": {
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "command": [
                                "/bin/bash",
                                "-c",
                                f"testcommand {' '.join(args.command).strip()}",
                            ],
                            "name": f"job-{gpu}-test-container",
                            "image": "test-image",
                            "resources": resources,
                        }
                    ],
                }
            },
        },
    }

    # Make the rsync_script simple and deterministic for the test
    batchtools.build_yaml.rsync_script = "testcommand {cmdline}"

    CreateJobCommand.run(args)

    # Verify we created the expected Job spec
    assert mock_create.call_args.args[0] == expected
    # And that we did call log_job_output once (even with wait=False)
    mock_log_job_output.assert_called_once()
    called_job_name = mock_log_job_output.call_args.kwargs["job_name"]
    assert called_job_name == f"job-{gpu}-test"


@mock.patch("openshift_client.create", name="create")
@mock.patch("openshift_client.selector", name="selector")
@mock.patch("socket.gethostname", name="gethostname")
@mock.patch("os.getcwd", name="getcwd")
def test_create_job_raises_from_oc_create(
    mock_getcwd,
    mock_gethostname,
    mock_selector,
    mock_create,
    parser,
    subparsers,
    tmp_path,
):
    """OpenShiftPythonException from oc.create should exit with a helpful message."""
    CreateJobCommand.build_parser(subparsers)
    args = parser.parse_args(["br"])
    args.wait = False
    args.job_id = "boom"
    args.gpu = "v100"
    args.image = "img"
    args.command = ["true"]

    mock_getcwd.return_value = str(tmp_path)
    mock_gethostname.return_value = "devpod"

    devpod = DictToObject(
        {
            "model": {
                "metadata": {"name": "devpod"},
                "spec": {"containers": [{"name": "c"}]},
            }
        }
    )
    mock_selector.return_value = mock.Mock(**{"object.return_value": devpod})

    import openshift_client as oc

    mock_create.side_effect = oc.OpenShiftPythonException("kaboom")

    with pytest.raises(SystemExit) as err:
        CreateJobCommand.run(args)
    assert "Error occurred while creating job: kaboom" in str(err.value)


@mock.patch("openshift_client.selector", name="selector")
def test_get_pod_status_running(mock_selector):
    pod = DictToObject({"model": {"status": {"phase": "Running"}}})
    mock_selector.return_value = mock.Mock(**{"object.return_value": pod})
    assert get_pod_status("mypod") == "Running"


@mock.patch("batchtools.br.oc_delete")
@mock.patch("batchtools.br.get_pod_status")
@mock.patch("openshift_client.selector", name="selector")
def test_log_job_output_success(mock_selector, mock_get_pod_status, mock_oc_delete):
    # pod list for job
    pod = DictToObject({"model": {"metadata": {"name": "pod-1"}}})
    mock_selector.return_value = mock.Mock(**{"objects.return_value": [pod]})

    # simulate states until success
    mock_get_pod_status.side_effect = ["Pending", "Running", "Succeeded"]

    # avoid real sleep
    with mock.patch("time.sleep", return_value=None):
        result_phase, run_elapsed, queue_wait, total_wall = log_job_output(
            "job-abc", wait=True, timeout=30
        )

    # Verify the behavior: job completed successfully
    assert result_phase == "succeeded"
    assert run_elapsed is not None
    assert queue_wait is not None
    assert total_wall is not None
    mock_oc_delete.assert_not_called()


@mock.patch("batchtools.br.oc_delete")
@mock.patch("batchtools.br.get_pod_status", return_value="Running")
@mock.patch("openshift_client.selector", name="selector")
def test_log_job_output_timeout_deletes_job(
    mock_selector, mock_get_pod_status, mock_oc_delete, capsys
):
    pod = DictToObject({"model": {"metadata": {"name": "pod-timeout"}}})
    mock_selector.return_value = mock.Mock(**{"objects.return_value": [pod]})

    # make time.monotonic jump past the timeout quickly
    times = [0.0, 2.0]

    def fake_monotonic():
        return times.pop(0) if times else 2.0

    with (
        mock.patch("time.monotonic", side_effect=fake_monotonic),
        mock.patch("time.sleep", return_value=None),
    ):
        log_job_output("job-timeout", wait=True, timeout=1)

    out = capsys.readouterr().out
    assert "Timeout waiting for pod pod-timeout to complete" in out
    mock_oc_delete.assert_called_once_with("job", "job-timeout")
