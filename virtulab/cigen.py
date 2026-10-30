"""Generate the CI file for virtulab.yml. The CI setup is one step; settings stay in the file."""

from .config import ProjectConfig

ACTION = "yann-zurstrassen/virtulab-ci@v1"
IMAGE = "ghcr.io/yann-zurstrassen/virtulab-ci:1"
DOCKER_ONE_LINER = f'docker run --rm -v "$PWD:/workspace" {IMAGE} run'

WORKFLOW_PATH = {"github": ".github/workflows/virtulab.yml", "gitlab": ".gitlab-ci.yml"}


def github_workflow(cfg: ProjectConfig) -> str:
    branches = ", ".join(cfg.ci_branches)
    crashes = ("""
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: virtulab-crashes
          path: fuzz/crashes
          if-no-files-found: ignore
""" if "fuzz" in cfg.tests else "")
    return f"""name: VirtuLab CI

on:
  push:
    branches: [{branches}]
  pull_request:

permissions:
  contents: read

jobs:
  # Runs the pull request's code, so it gets a read-only token and keeps no credentials on disk.
  virtulab:
    name: Virtual board tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # the footprint check compares with the base branch
          persist-credentials: false

      # Board, sensors and tests come from virtulab.yml.
      - uses: {ACTION}
        with:
          comment: false

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: virtulab-report
          path: .virtulab/report.md
          include-hidden-files: true   # upload-artifact skips dot folders by default
          if-no-files-found: error
{crashes}
  # Holds the write token and never runs the pull request's code: it only posts the report.
  report:
    name: PR comment
    needs: virtulab
    if: always() && github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: virtulab-report
      - name: Post the report
        continue-on-error: true   # pull requests from forks get a read-only token
        run: gh pr comment "$PR" --repo "$GITHUB_REPOSITORY" --edit-last --create-if-none --body-file report.md
        env:
          GH_TOKEN: ${{{{ github.token }}}}
          PR: ${{{{ github.event.pull_request.number }}}}
"""


def gitlab_pipeline(cfg: ProjectConfig) -> str:
    branches = " || ".join(f'$CI_COMMIT_BRANCH == "{b}"' for b in cfg.ci_branches)
    paths = "    - .virtulab/report.md\n" + ("    - fuzz/crashes\n" if "fuzz" in cfg.tests else "")
    return f"""# VirtuLab CI: board, sensors and tests come from virtulab.yml.
virtulab:
  image:
    name: {IMAGE}
    entrypoint: [""]
  variables:
    GIT_DEPTH: "0"   # the footprint check compares with the target branch
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: {branches}
  script:
    - virtulab run --baseline "${{CI_MERGE_REQUEST_DIFF_BASE_SHA:-HEAD~1}}"
  artifacts:
    when: always
    paths:
{paths}"""


def render(cfg: ProjectConfig, provider: str | None = None) -> tuple[str, str]:
    """Return (path, content) of the CI file for the provider."""
    provider = provider or cfg.ci_provider
    content = github_workflow(cfg) if provider == "github" else gitlab_pipeline(cfg)
    return WORKFLOW_PATH[provider], content
