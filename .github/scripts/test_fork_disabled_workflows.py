"""Static contract for workflows disabled only in repository forks."""

from pathlib import Path

FORK_WORKFLOW = Path(__file__).parents[1] / "workflows/fork-disable-unneeded-actions.yml"
FRONTEND_DEPLOY_WORKFLOW = Path(__file__).parents[1] / "workflows/cd-frontend.yml"
STORYBOOK_DEPLOY_WORKFLOW = Path(__file__).parents[1] / "workflows/cd-storybook.yml"


def main() -> None:
    fork_workflow = FORK_WORKFLOW.read_text()

    fork_only_guard = "if: ${{ github.repository != 'hhs/simpler-grants-gov' }}"
    guarded_step = fork_workflow[fork_workflow.index(fork_only_guard) :]

    assert 'name: Deploy frontend' in FRONTEND_DEPLOY_WORKFLOW.read_text()
    assert 'name: Deploy Storybook' in STORYBOOK_DEPLOY_WORKFLOW.read_text()
    assert 'gh workflow disable "Deploy frontend" || true' in guarded_step
    assert 'gh workflow disable "Deploy Storybook" || true' in guarded_step
    assert fork_workflow.count('gh workflow disable "Deploy frontend"') == 1
    assert fork_workflow.count('gh workflow disable "Deploy Storybook"') == 1


if __name__ == "__main__":
    main()
