#!/usr/bin/env bash
# Build the firmware-compliance execution environment.
#   ./awx/build-ee.sh [image-tag]
set -euo pipefail
TAG="${1:-ghcr.io/msf2105/firmware-compliance-ee:1.0}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cp "$HERE/../workflow/requirements.yml" "$HERE/collections-requirements.yml"
pip install --quiet "ansible-builder>=3.1"
ansible-builder build -f "$HERE/execution-environment.yml" -t "$TAG" --context "$HERE/context" -v 2
echo "Built $TAG — push with: podman push $TAG"
