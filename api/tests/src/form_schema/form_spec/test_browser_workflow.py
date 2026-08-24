"""Static contract for bounded hosted portable-catalog dispatches."""

from pathlib import Path


WORKFLOW = Path(__file__).parents[5] / ".github/workflows/ci-frontend-e2e.yml"


def test_hosted_browser_workflow_propagates_bounded_form_selection() -> None:
    workflow = WORKFLOW.read_text()

    assert workflow.count("portable_browser_form_ids:") == 2
    assert "PORTABLE_BROWSER_FORM_IDS: ${{ inputs.portable_browser_form_ids || '' }}" in workflow
    assert "-e PORTABLE_BROWSER_FORM_IDS" in workflow
    assert (
        "shard: ${{ fromJSON(inputs.portable_browser_form_ids != '' "
        "&& '[1]' || '[1,2,3,4]') }}" in workflow
    )
    assert (
        "total_shards: ${{ fromJSON(inputs.portable_browser_form_ids != '' "
        "&& '[1]' || '[4]') }}" in workflow
    )
