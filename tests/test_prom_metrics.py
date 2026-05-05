import re
from unittest import mock
import batchtools.prom_metrics as pm


def _base_labels():
    return {
        "job_name": "job-none-xyz",
        "gpu": "none",
        "queue": "dummy-localqueue",
        "instance": pm.PROMETHEUS_INSTANCE or "test",
    }


def test_record_batch_observation_updates_hist_and_counters():
    labels = _base_labels()
    pm.record_batch_observation(labels=labels, elapsed_sec=1.23, result="succeeded")
    body, _ = pm.generate_metrics_text()
    # Verify histogram/counter series were created with the expected labels
    assert "batch_duration_seconds_bucket" in body
    assert "batch_duration_total_seconds" in body
    assert "batch_runs_total" in body
    # spot-check that our labelset is present
    assert 'job_name="job-none-xyz"' in body
    assert 'queue="dummy-localqueue"' in body
    assert 'result="succeeded"' in body


def test_record_queue_and_wall_observation_update_metrics():
    labels = _base_labels()
    pm.record_queue_observation(labels=labels, elapsed_sec=2.5, result="succeeded")
    pm.record_wall_observation(labels=labels, elapsed_sec=3.5, result="succeeded")
    body, _ = pm.generate_metrics_text()
    assert "batch_queue_wait_seconds_bucket" in body
    assert "batch_queue_wait_total_seconds" in body
    assert "batch_total_wall_seconds_bucket" in body
    assert "batch_total_wall_total_seconds" in body


def test_set_in_progress_inc_and_dec_affect_gauge():
    labels = _base_labels()
    # inc
    pm.set_in_progress(labels=labels, result="running", inc=True)
    body_inc, _ = pm.generate_metrics_text()
    assert "batch_in_progress" in body_inc
    assert 'result="running"' in body_inc
    # dec (should not throw; series may remain visible in exposition)
    pm.set_in_progress(labels=labels, result="running", inc=False)
    body_dec, _ = pm.generate_metrics_text()
    assert "batch_in_progress" in body_dec


def test_push_registry_text_no_url_prints_payload(capsys, monkeypatch):
    # Simulate "no address configured" by blanking the module variable.
    monkeypatch.setattr(pm, "PUSHGATEWAY_ADDR", "", raising=False)
    pm.push_registry_text()
    out = capsys.readouterr().out
    assert "PUSHGATEWAY_ADDR not set; below is the metrics payload:" in out
    assert "# HELP" in out and "# TYPE" in out  # payload printed


def test_push_registry_text_posts_success(monkeypatch):
    monkeypatch.setattr(
        pm, "PUSHGATEWAY_ADDR", "pushgateway.example:9091", raising=False
    )
    with mock.patch.object(pm, "pushadd_to_gateway", autospec=True) as m:
        pm.push_registry_text(grouping_key={"instance": "test", "job_name": "job-1"})

        # Verify the actual behavior: pushadd_to_gateway was called correctly
        m.assert_called_once_with(
            "pushgateway.example:9091",
            job="batchtools",
            registry=pm.registry,
            grouping_key={"instance": "test", "job_name": "job-1"}
        )


def test_push_registry_text_posts_failure(monkeypatch):
    monkeypatch.setattr(
        pm, "PUSHGATEWAY_ADDR", "pushgateway.example:9091", raising=False
    )
    with mock.patch.object(
        pm, "pushadd_to_gateway", side_effect=Exception("boom"), autospec=True
    ) as m:
        # Should not raise even when pushadd_to_gateway fails
        pm.push_registry_text(grouping_key={"instance": "test", "job_name": "job-2"})

        # Verify the function was called (failure is handled gracefully)
        m.assert_called_once()
