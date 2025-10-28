#!/bin/bash
# Generate a test-specific config that only monitors test directories

create_test_config() {
    local base_config="$1"
    local test_dir="$2"
    local output_config="$3"

    # Copy base config
    cp "$base_config" "$output_config"

    # Replace log_directories section to only monitor test directory
    cat > /tmp/test_log_dirs.yaml << EOF
log_directories:
  - path: ${test_dir}/terminal
    source: terminal
  - path: ${test_dir}/ros
    source: ros
  - path: ${test_dir}/syslog
    source: syslog
  - path: ${test_dir}/other
    source: other
EOF

    # Use awk to replace the log_directories section
    awk '
    /^log_directories:/ {
        print "# MODIFIED FOR TESTING - Only monitoring test directories"
        system("cat /tmp/test_log_dirs.yaml")
        skip=1
        next
    }
    /^[a-z_]+:/ && skip {
        skip=0
    }
    !skip {
        print
    }
    ' "$base_config" > "$output_config"

    rm -f /tmp/test_log_dirs.yaml

    echo "$output_config"
}

# Export function
export -f create_test_config
