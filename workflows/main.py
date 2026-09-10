"""Readiness-only Render Workflow registration."""

from render_sdk import TaskContext, Workflows


app = Workflows()


@app.task
def readiness_smoke(
    context: TaskContext,
    check_id: str,
    metadata: str = "",
) -> dict[str, str]:
    """Return the deterministic readiness result without performing I/O."""
    return {
        "check_id": check_id,
        "metadata": metadata,
        "status": "ready",
    }


if __name__ == "__main__":
    app.start()
