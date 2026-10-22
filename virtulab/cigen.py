"""Generate the CI file for virtulab.yml. The CI setup is one step; settings stay in the file."""

from .config import ProjectConfig

ACTION = "yann-zurstrassen/virtulab-ci@v1"
IMAGE = "ghcr.io/yann-zurstrassen/virtulab-ci:1"
DOCKER_ONE_LINER = f'docker run --rm -v "$PWD:/workspace" {IMAGE} run'

WORKFLOW_PATH = {"github": ".github/workflows/virtulab.yml", "gitlab": ".gitlab-ci.yml"}


def github_workflow(cfg: ProjectConfig) -> str:
    branches = ", ".join(cfg.ci_branches)
    fuzz = ("            fuzz/crashes\n" if "fuzz" in cfg.tests else "")
    return f"""name: VirtuLab CI

on:
  push:
    branches: [{branches}]
  pull_request:

permissions:
  contents: read
  pull-requests: write   # lets VirtuLab post its report as a PR comment

jobs:
  virtulab:
    name: Virtual board tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # the footprint check compares with the base branch

      # Board, sensors and tests come from virtulab.yml.
      - uses: {ACTION}

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: virtulab-report
          path: |
            .virtulab/report.md
{fuzz}          if-no-files-found: ignore
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
