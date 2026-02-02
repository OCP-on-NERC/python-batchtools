import openshift_client as oc


def is_logged_in() -> bool:
    try:
        oc.invoke("whoami")
        return True
    except oc.OpenShiftPythonException:
        return False


def is_on_project() -> bool:
    if not is_logged_in():
        return False
    try:
        oc.get_project_name()
        return True
    except oc.OpenShiftPythonException:
        return False


def pretty_print(pod: oc.APIObject) -> str:
    formatted_logs: str = ""
    try:
        logs: dict[str, str] = pod.logs()
        # ⋆ ˚｡⋆୨୧˚ stringify and pretty print for readibility ⋆ ˚｡⋆୨୧˚
        formatted_logs = str(logs).replace("\\n", "\n")
    except oc.OpenShiftPythonException as e:
        print(f"Error occurred while retrieving logs: {e}")
    return formatted_logs


def oc_delete(obj_type: str, obj_name: str) -> None:
    try:
        # print(f"Deleting {obj_type}/{obj_name}")
        oc.selector(f"{obj_type}/{obj_name}").delete()
    except oc.OpenShiftPythonException as e:
        print(f"Error occurred while deleting {obj_type}/{obj_name}: {e}")


def is_kueue_managed_job(job_obj) -> bool:
    try:
        md = job_obj.model.metadata
        labels = getattr(md, "labels", {}) or {}
        if "kueue.x-k8s.io/queue-name" in labels:
            return True
    except Exception:
        return False


def fmt(x):
    return f"{x:.3f}s" if x is not None else "n/a"


def is_kueue_managed_pod(pod) -> bool:
    try:
        owners = getattr(pod.model.metadata, "ownerReferences", []) or []
        job_owner = next((o for o in owners if o.kind == "Job"), None)
        if not job_owner:
            return False

        job_name = job_owner.name
        job_obj = oc.selector(f"job/{job_name}").object()
        return is_kueue_managed_job(job_obj)

    except Exception:
        return False
