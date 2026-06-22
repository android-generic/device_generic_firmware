#!/bin/bash

# vendorsetup.sh
# Run the Android.bp generation script whenever `lunch` is executed

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# Environment variables for generate_bp.py:
# export FIRMWARE_SRC_DIR="${SCRIPT_DIR}"
# export VENDOR_FW_DIR="${SCRIPT_DIR}/../../../vendor/generic/firmware"
# export RECIPE_FILE="${SCRIPT_DIR}/recipe.json"

echo "Checking firmware Android.bp generation..."
python3 "${SCRIPT_DIR}/generate_bp.py"
