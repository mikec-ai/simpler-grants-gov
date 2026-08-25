"""Static contract for bounded hosted portable-catalog dispatches."""

from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / "workflows/ci-frontend-e2e.yml"
API_WORKFLOW = Path(__file__).parents[1] / "workflows/ci-api.yml"


def main() -> None:
    workflow = WORKFLOW.read_text()
    api_workflow = API_WORKFLOW.read_text()

    assert workflow.count("portable_browser_form_ids:") == 2
    assert "portable_form_ids: ${{ steps.classify.outputs.portable_form_ids }}" in workflow
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
        "shard: ${{ fromJSON(needs.classify-form-spec-change.outputs.portable_form_ids != '' "
        "&& '[1]' || '[1,2,3,4]') }}" in workflow
    )
    assert (
        "total_shards: ${{ fromJSON(needs.classify-form-spec-change.outputs.portable_form_ids != '' "
        "&& '[1]' || '[4]') }}" in workflow
    )
    assert (
        workflow.count(
            "do-firefox-install: ${{ (needs.classify-form-spec-change.outputs.portable_form_ids != '' "
            "|| matrix.shard == 2) && 'true' || 'false' }}"
        )
        == 3
    )
    assert (
        workflow.count(
            "do-webkit-install: ${{ (needs.classify-form-spec-change.outputs.portable_form_ids != '' "
            "|| matrix.shard == 3) && 'true' || 'false' }}"
        )
        == 3
    )
    assert (
        "PORTABLE_BROWSER_FORM_IDS: "
        "${{ needs.classify-form-spec-change.outputs.portable_form_ids }}" in workflow
    )
    assert 'echo "portable_form_ids=$PORTABLE_BROWSER_FORM_IDS"' in workflow
    assert "tier: ${{ steps.classify.outputs.tier }}" in api_workflow
    assert "reason: ${{ steps.classify.outputs.reason }}" in api_workflow
    assert (
        "portable_frontend_evidence_files: "
        "${{ steps.classify.outputs.portable_frontend_evidence_files }}" in api_workflow
    )
    assert "### Portable form CI classification" in api_workflow
    assert "### Portable browser CI classification" in workflow
    assert "CI_REASON: ${{ steps.classify.outputs.reason" in api_workflow
    assert "CI_REASON: ${{ steps.classify.outputs.reason" in workflow
    assert "needs.classify-form-spec-change.outputs.tier == 'portable_focused'" in api_workflow
    assert (
        "docker compose run -T --rm grants-api pytest "
        "tests/src/form_schema/form_spec" in api_workflow
    )
    assert "python bin/build_portable_legacy_differential.py" in api_workflow
    assert 'TESTED_REVISION="$(git rev-parse HEAD)"' in api_workflow
    assert "--pr-head-revision" in api_workflow
    assert "oracleReceipts + .noOracleDispositions" in api_workflow
    assert "differential-cohort.json" not in api_workflow
    assert "test_[a-z0-9_]+\\.py" in api_workflow


if __name__ == "__main__":
    main()
