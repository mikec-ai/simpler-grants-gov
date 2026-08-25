"""Static contracts for PR-only cancellation and Pa11y path routing."""

from pathlib import Path

WORKFLOWS = Path(__file__).parents[1] / "workflows"
API_WORKFLOW = WORKFLOWS / "ci-api.yml"
PA11Y_WORKFLOW = WORKFLOWS / "ci-frontend-a11y.yml"

CONCURRENCY_GROUP = (
    "group: ${{ github.workflow }}-"
    "${{ github.event.pull_request.number || github.run_id }}"
)
PR_ONLY_CANCELLATION = (
    "cancel-in-progress: ${{ github.event_name == 'pull_request' }}"
)


def pull_request_paths(workflow: str) -> tuple[str, ...]:
    start = workflow.index("  pull_request:\n    paths:\n")
    path_block = workflow[start:].split("\n\n", 1)[0]
    return tuple(
        line.removeprefix("      - ").strip('"')
        for line in path_block.splitlines()
        if line.startswith("      - ")
    )


def main() -> None:
    api_workflow = API_WORKFLOW.read_text()
    pa11y_workflow = PA11Y_WORKFLOW.read_text()

    for workflow in (api_workflow, pa11y_workflow):
        assert workflow.count(CONCURRENCY_GROUP) == 1
        assert workflow.count(PR_ONLY_CANCELLATION) == 1

    assert pull_request_paths(pa11y_workflow) == (
        "frontend/**",
        "!frontend/tests/**",
        "!frontend/**/*.test.ts",
        "!frontend/**/*.test.tsx",
        "!frontend/**/__fixtures__/**",
        ".github/workflows/ci-frontend-a11y.yml",
    )


if __name__ == "__main__":
    main()
