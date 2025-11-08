#!/bin/bash
# run_tests.sh - Professional test runner with coverage

set -e

# Get script directory and navigate to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Change to project root so all paths work correctly
cd "$PROJECT_ROOT"

VENV_DIR="venv"
PYTHON="python3"
AWS_PROFILE="${AWS_PROFILE:-china}"
COVERAGE="${COVERAGE:-false}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

setup_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}Creating virtual environment...${NC}"
        $PYTHON -m venv $VENV_DIR
    fi
    source $VENV_DIR/bin/activate
}

# Build pytest command with optional coverage
build_pytest_cmd() {
    local cmd="pytest $1 -v --tb=short $VERBOSE_FLAG"  # ← Add $VERBOSE_FLAG

    if [ "$COVERAGE" = "true" ]; then
        cmd="$cmd --cov=src --cov-report=term --cov-report=html"
    fi

    echo "$cmd"
}

test_unit() {
    echo -e "${BLUE}▶ Running unit tests...${NC}"
    eval "$(build_pytest_cmd 'tests/unit/')"
}

test_integration() {
    echo -e "${BLUE}▶ Running integration tests...${NC}"
    eval "$(build_pytest_cmd 'tests/integration/')"
}

test_e2e() {
    echo -e "${BLUE}▶ Running E2E tests (AWS: $AWS_PROFILE)...${NC}"
    AWS_PROFILE=$AWS_PROFILE pytest tests/e2e/ -v --tb=short -m "e2e or real_aws" $VERBOSE_FLAG
}

test_all() {
    if [ "$COVERAGE" = "true" ]; then
        echo -e "${CYAN}Running all tests with coverage...${NC}"
        pytest tests/unit/ tests/integration/ -v --cov=src --cov-report=term --cov-report=html
        test_e2e
        echo -e "${GREEN}Coverage report: htmlcov/index.html${NC}"
    else
        test_unit
        test_integration
        test_e2e
    fi
}

show_help() {
    echo -e "${CYAN}╔════════════════════════════════════════════════════════╗"
    echo -e "║  TVM Upload System - Test Runner                      ║"
    echo -e "╚════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Usage:${NC} $0 [COMMAND] [OPTIONS]"
    echo ""
    echo -e "${YELLOW}Commands:${NC}"
    echo "  unit          Run unit tests only (~5s)"
    echo "  integration   Run integration tests only (~15s)"
    echo "  e2e           Run E2E tests only (requires AWS, ~60s)"
    echo "  all           Run all tests (default)"
    echo "  fast          Run unit + integration (skip E2E)"
    echo "  help          Show this help message"
    echo ""
    echo -e "${YELLOW}Options:${NC}"
    echo "  --coverage    Generate coverage report"
    echo "  --verbose     Extra verbose output"
    echo ""
    echo -e "${YELLOW}Environment Variables:${NC}"
    echo "  AWS_PROFILE   AWS profile for E2E tests (default: china)"
    echo "  COVERAGE      Set to 'true' to enable coverage (default: false)"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0                           # Run all tests"
    echo "  $0 unit                      # Run unit tests only"
    echo "  $0 all --coverage            # Run all with coverage"
    echo "  $0 fast                      # Quick test (no E2E)"
    echo "  AWS_PROFILE=prod $0 e2e      # E2E with prod profile"
    echo "  COVERAGE=true $0 all         # All tests with coverage"
    echo ""
    echo -e "${YELLOW}Time Estimates:${NC}"
    echo "  unit:         ~5 seconds"
    echo "  integration:  ~15 seconds"
    echo "  e2e:          ~60 seconds"
    echo "  all:          ~80 seconds"
    echo ""
    echo -e "${YELLOW}Output:${NC}"
    echo "  Logs:         Console output"
    echo "  Coverage:     htmlcov/index.html (if --coverage used)"
    echo ""
}

main() {
    # Parse all arguments first
    COMMAND=""
    VERBOSE_FLAG=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --coverage)
                COVERAGE=true
                shift
                ;;
            --verbose)
                VERBOSE_FLAG="-vv -s"
                shift
                ;;
            -h|--help|help)
                show_help
                exit 0
                ;;
            unit|integration|e2e|all|fast)
                COMMAND="$1"
                shift
                ;;
            *)
                if [ -z "$COMMAND" ]; then
                    echo -e "${RED}❌ Unknown command: $1${NC}"
                    show_help
                    exit 1
                fi
                shift
                ;;
        esac
    done

    # Default to 'all' if no command specified
    COMMAND="${COMMAND:-all}"

    setup_venv

    echo -e "${CYAN}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║       TVM Upload System - Test Suite                  ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════╝${NC}"
    echo ""

    if [ "$COVERAGE" = "true" ]; then
        echo -e "${YELLOW}📊 Coverage reporting enabled${NC}"
        echo ""
    fi

    START_TIME=$(date +%s)

    case "$COMMAND" in
        unit)
            test_unit
            ;;
        integration)
            test_integration
            ;;
        e2e)
            test_e2e
            ;;
        all)
            test_all
            ;;
        fast)
            test_unit
            test_integration
            ;;
    esac

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ Tests completed successfully!                     ║${NC}"
    echo -e "${GREEN}║  ⏱️  Duration: ${DURATION}s                                    ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"

    if [ "$COVERAGE" = "true" ]; then
        echo ""
        echo -e "${CYAN}📊 Coverage report generated: ${YELLOW}htmlcov/index.html${NC}"
        echo -e "${CYAN}   Open with: ${YELLOW}xdg-open htmlcov/index.html${NC}"
    fi
}

main "$@"
