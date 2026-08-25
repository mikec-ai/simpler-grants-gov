"""Static contract for bounded hosted portable-catalog dispatches."""

from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / "workflows/ci-frontend-e2e.yml"


def main() -> None:
    workflow = WORKFLOW.read_text()

    assert workflow.count("portable_browser_form_ids:") == 2
    assert (
        "PORTABLE_BROWSER_FORM_IDS: ${{ inputs.portable_browser_form_ids || '' }}"
        in workflow
    )
    assert "PLAYWRIGHT_WORKERS: 6" in workflow
    assert workflow.count("workers: ${{ env.PLAYWRIGHT_WORKERS }}") == 3
    assert "-e PORTABLE_BROWSER_FORM_IDS" in workflow
    assert "portable_browser_form_ids must be a comma-separated list" in workflow
    assert "test_group_tags=@portable-catalog" in workflow

    selector_branch = 'if [[ -n "$PORTABLE_BROWSER_FORM_IDS" ]]; then'
    pull_request_branch = 'elif [[ $GITHUB_EVENT_NAME = "pull_request" ]]; then'
    routing = workflow[workflow.index("- name: Determine test groups to run") :]
    assert routing.index(selector_branch) < routing.index(pull_request_branch)

    assert (
        "if: ${{ env.PORTABLE_BROWSER_FORM_IDS == '' "
        "&& env.E2E_UTILS_CHANGED == 'true' }}" in workflow
    )
    assert (
        "if: ${{ env.PORTABLE_BROWSER_FORM_IDS != '' "
        "|| env.E2E_UTILS_CHANGED != 'true' }}" in workflow
    )
    assert (
        "if: ${{ env.PORTABLE_BROWSER_FORM_IDS == '' "
        "&& env.E2E_SPECS_CHANGED != '' && env.E2E_UTILS_CHANGED != 'true' }}"
        in workflow
    )
    assert (
        "shard: ${{ fromJSON(inputs.portable_browser_form_ids != '' "
        "&& '[1]' || '[1,2,3,4]') }}" in workflow
    )
    assert (
        "total_shards: ${{ fromJSON(inputs.portable_browser_form_ids != '' "
        "&& '[1]' || '[4]') }}" in workflow
    )
    assert (
        workflow.count(
            "do-firefox-install: ${{ (inputs.portable_browser_form_ids != '' "
            "|| matrix.shard == 2) && 'true' || 'false' }}"
        )
        == 3
    )
    assert (
        workflow.count(
            "do-webkit-install: ${{ (inputs.portable_browser_form_ids != '' "
            "|| matrix.shard == 3) && 'true' || 'false' }}"
        )
        == 3
    )


if __name__ == "__main__":
    main()
