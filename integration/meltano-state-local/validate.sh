#!/usr/bin/env bash

set -euo pipefail

LOG_FILE="./docs/example-library/meltano-state-local/integration-test.log"

# we could also run psql statements
# check for the existance of files
# etc
source "$(git rev-parse --show-toplevel)/integration/commons.sh"
cd "${TEST_DOCS_DIR}"
meltano state list | grep "dev:tap-gitlab-to-target-jsonl"
meltano state get dev:tap-gitlab-to-target-jsonl | grep "singer_state"

meltano state set dev:tap-gitlab-to-target-jsonl '{"singer_state": {"bookmark-1": 0}}'

meltano state get dev:tap-gitlab-to-target-jsonl | grep '{"singer_state": {"bookmark-1": 0}}'
