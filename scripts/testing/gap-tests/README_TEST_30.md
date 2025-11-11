# Test 30: Production Simulation - Campus Vehicle Operation

## Overview

**Test 30** is a comprehensive long-running test that simulates real-world campus vehicle deployment scenarios. It runs continuously for 2-24 hours (configurable) and tests the system under realistic operational conditions.

## Purpose

Validate the TVM Upload System under production-like conditions including:
- Variable WiFi availability (campus WiFi zones)
- WiFi micro-disconnections (2-3 second flapping)
- Continuous multi-source file generation
- System crashes and recovery
- Network degradation and latency
- Disk pressure scenarios
- Queue buildup and drain cycles

## Key Scenarios Tested

### 1. WiFi Patterns (Critical)
- **WiFi Available**: Normal upload operations
- **WiFi Unavailable**: Queue builds up, no uploads
- **Intermittent WiFi**: 30-second on/off cycles
- **WiFi Flapping**: 2-3 second micro-disconnections (CRITICAL for campus deployment)
- **Degraded WiFi**: High latency (500ms) + packet loss (10%)

### 2. File Generation
- **Normal Mode**: 50 files/min across 4 sources
- **Heavy Mode**: 100 files/min with larger files
- **Burst Mode**: 200 files/min short bursts
- **Nested Directories**: Multi-level folder structures
- **Multiple Sources**: Terminal, ROS, ROS2, Syslog simultaneously

### 3. System Resilience
- **Hard Crashes**: SIGKILL (kill -9) simulation
- **Crash Recovery**: Service restart and state verification
- **Queue Persistence**: Survives crashes
- **Registry Integrity**: No corruption under stress

### 4. Resource Management
- **Disk Pressure**: Fill to 90%+ and verify emergency cleanup
- **Memory Monitoring**: Detect leaks during long runs
- **CPU Usage**: Track resource consumption
- **Queue Management**: Handle 1000+ file queues

## Test Phases (100-minute cycle)

Each cycle runs through 5 phases:

### Phase 1: Campus Entry - WiFi Available (15 min)
- Enable WiFi
- Generate 50 files/min
- Normal upload operations

### Phase 2: Campus Interior - No WiFi (30 min)
- Disable WiFi (simulate moving to area without coverage)
- Generate 100 files/min (queue builds up)
- Monitor queue growth

### Phase 3: WiFi Zone Return - Queue Drain (10 min)
- Enable WiFi
- Watch queue drain (3000+ files upload)
- Monitor upload rate

### Phase 4: Network Instability (30 min)
**Pattern A**: Regular Intermittent (10 min)
- 30 seconds WiFi ON
- 30 seconds WiFi OFF
- Repeat for 10 minutes

**Pattern B**: WiFi Flapping - CRITICAL (10 min)
- 2-3 seconds WiFi ON
- 2-3 seconds WiFi OFF
- 100+ flaps in 10 minutes
- Tests connection pool, retry logic, state management

**Pattern C**: Degraded WiFi (10 min)
- 500ms latency
- 10% packet loss
- Simulates poor signal quality

### Phase 5: Chaos Testing - Crashes & Recovery (15 min)
- Generate burst files (200/min)
- Simulate hard crash (SIGKILL)
- Verify service recovery
- Verify queue/registry integrity
- Resume normal operations

## Usage

### Quick Start (2-hour test)
```bash
# From project root
./scripts/testing/gap-tests/run_production_simulation.sh

# Or with custom config
./scripts/testing/gap-tests/run_production_simulation.sh config/config.yaml

# Or run directly
./scripts/testing/gap-tests/30_production_simulation.sh config/config.yaml vehicle-TEST 2
```

### Custom Duration
```bash
# 8-hour test (recommended for pre-production)
./scripts/testing/gap-tests/run_production_simulation.sh config/config.yaml vehicle-TEST 8

# 24-hour test (full day simulation)
./scripts/testing/gap-tests/run_production_simulation.sh config/config.yaml vehicle-TEST 24
```

### Parameters
```bash
./scripts/testing/gap-tests/30_production_simulation.sh <config_file> <vehicle_id> <duration_hours>
```

- `config_file`: Path to config.yaml (default: config/config.yaml)
- `vehicle_id`: Base vehicle ID for test (default: vehicle-PROD-SIM)
- `duration_hours`: Test duration in hours (default: 2)

## Requirements

### System Requirements
- **Sudo Access**: Required for network manipulation (iptables, tc)
- **Disk Space**: At least 2× duration in hours (e.g., 8-hour test needs 16GB+)
- **Time**: Dedicated system for entire test duration
- **Network**: Active network interface for traffic control

### Software Requirements
- Python 3.8+
- AWS CLI configured with China region credentials
- iptables (for WiFi simulation)
- tc (traffic control - for latency/loss simulation)
- All project dependencies installed

## Monitoring

### Real-time Metrics
The test collects metrics every 60 seconds:
- Service status (UP/DOWN)
- Queue size
- Disk usage (%)
- Memory usage (MB)
- CPU usage (%)
- Error count

### Log Files
- **Service Log**: `/tmp/tvm-service-prod-sim.log`
- **Metrics Log**: `/tmp/tvm-metrics-prod-sim.log`
- **Test Output**: stdout (real-time)

### Viewing Metrics During Test
```bash
# Watch metrics log (in another terminal)
tail -f /tmp/tvm-metrics-prod-sim.log

# Watch service log
tail -f /tmp/tvm-service-prod-sim.log

# Monitor queue size
watch -n 10 'grep -c "filepath" /tmp/queue-prod-sim.json 2>/dev/null || echo 0'
```

## Expected Results

### Success Criteria
After 8-24 hours of testing:

✅ **Service Uptime**: 99%+ (allowing for crash recovery tests)
✅ **Files Uploaded**: 10,000 - 100,000+ (depends on duration)
✅ **Queue Recovery**: 100% success after every crash/outage
✅ **No Duplicate Uploads**: Verified via registry
✅ **Emergency Cleanup**: Triggers correctly at disk thresholds
✅ **Memory Stability**: No leaks detected
✅ **WiFi Transitions**: Smooth handling of on/off cycles
✅ **WiFi Flapping**: Service survives 500+ micro-disconnections
✅ **Crash Recovery**: 100% success rate

### Acceptable Metrics
- **Error Rate**: <100 errors per hour (excluding expected network errors)
- **Upload Success Rate**: >95% (when WiFi available)
- **Queue Integrity**: 100% (no corruption)
- **Memory Growth**: <50MB per hour
- **Max Queue Size**: Depends on WiFi outage duration (expected 3000+ during 30-min outage)

## WiFi Flapping Details

### Why This Is Critical

WiFi flapping (2-3 second on/off cycles) is the **most challenging** network pattern because:

1. **Connection Pool Issues**: Connections don't have time to close properly
2. **Upload Failures**: Files start uploading but immediately fail
3. **Retry Storms**: Risk of excessive retry attempts
4. **State Management**: Files can get stuck in "uploading" state

### What Gets Tested

During 10 minutes of flapping (100-120 flaps):
- ✅ Boto3 connection handling
- ✅ Upload state transitions
- ✅ Retry backoff logic
- ✅ Queue file writes during chaos
- ✅ Memory management (connection cleanup)
- ✅ Service stability (no crashes)

### Expected Behavior

**During Flapping:**
- Uploads fail rapidly (expected)
- Errors logged (1-2 per flap, acceptable)
- Queue remains intact
- Service stays running
- Memory stable

**After Flapping:**
- WiFi stabilizes
- Queue starts draining
- Upload success rate returns to >95%
- No stuck uploads
- Service responsive

## Troubleshooting

### Test Fails to Start

**Issue**: "Permission denied" for network commands
```bash
# Solution: Ensure sudo access
sudo -v
```

**Issue**: "Service already running"
```bash
# Solution: Stop existing service
sudo systemctl stop tvm-upload
pkill -f "python.*src.main"
```

### Test Crashes

**Issue**: Service crashes during WiFi flapping
```bash
# Check service log for errors
tail -100 /tmp/tvm-service-prod-sim.log

# Check for connection pool exhaustion
grep -i "pool\|connection" /tmp/tvm-service-prod-sim.log
```

**Issue**: Disk full during test
```bash
# Check disk usage
df -h /tmp

# The test should trigger emergency cleanup automatically
# If not, check deletion config
```

### Network Issues

**Issue**: iptables rules not working
```bash
# Check current rules
sudo iptables -L OUTPUT -n -v

# Manually clear rules
sudo iptables -F OUTPUT

# Verify network interface
ip route get 8.8.8.8
```

**Issue**: Traffic control not working
```bash
# Check tc rules
sudo tc qdisc show

# Clear all tc rules
for iface in $(ip -o link show | awk -F': ' '{print $2}'); do
    sudo tc qdisc del dev $iface root 2>/dev/null || true
done
```

## Cleanup

The test automatically cleans up:
- ✅ Stops TVM service
- ✅ Removes test files
- ✅ Clears network rules (iptables, tc)
- ✅ Deletes test queue/registry
- ✅ Removes S3 test data

### Manual Cleanup (if needed)
```bash
# Stop service
sudo systemctl stop tvm-upload 2>/dev/null || true
pkill -f "python.*src.main"

# Clear network rules
sudo iptables -F OUTPUT
for iface in $(ip -o link show | awk -F': ' '{print $2}'); do
    sudo tc qdisc del dev $iface root 2>/dev/null || true
done

# Remove test files
rm -rf /tmp/tvm-production-sim
rm -f /tmp/tvm-service-prod-sim.log
rm -f /tmp/tvm-metrics-prod-sim.log
rm -f /tmp/queue-prod-sim.json
rm -f /tmp/registry-prod-sim.json

# Clean S3 (replace with your vehicle ID)
aws s3 rm s3://t01logs/vehicle-PROD-SIM-TIMESTAMP/ --recursive --profile china --region cn-north-1
```

## Integration with Test Suite

### Standalone Test
Test 30 is **NOT** included in `make test-gap` or `make test-all-manual` because:
- It's too long (2-24 hours)
- It's resource-intensive
- It requires sudo access
- It manipulates network settings

### Running Test 30
```bash
# Use dedicated runner
./scripts/testing/gap-tests/run_production_simulation.sh

# Or add to Makefile for convenience (optional)
make test-production-sim  # If added to Makefile
```

## Recommended Testing Strategy

### Pre-Production Validation
1. **Week 1**: Run 2-hour test daily (quick validation)
2. **Week 2**: Run 8-hour test 2-3 times (standard validation)
3. **Week 3**: Run 24-hour test once (final validation)
4. **Pre-deployment**: Run 24-hour test with production config

### Post-Deployment Validation
- Run 8-hour test monthly
- Run 24-hour test quarterly
- Run after major code changes

## Success Stories

After successful 24-hour test, you can be confident that:
- ✅ System handles real campus WiFi patterns
- ✅ Queue survives extended WiFi outages (2+ hours)
- ✅ Service recovers from crashes automatically
- ✅ No memory leaks in long-running deployments
- ✅ Emergency cleanup prevents disk full scenarios
- ✅ WiFi micro-disconnections don't crash the service

## Questions?

If Test 30 fails, check:
1. Metrics log for patterns
2. Service log for errors
3. Queue/registry file integrity
4. Network rule cleanup
5. Disk space availability

The test is designed to find issues that short tests miss. Failures here are **good** - they prevent production problems!

---

**Test 30 Author**: Claude (Anthropic)
**Last Updated**: 2025-11-11
**Test Duration Options**: 2h (quick), 8h (standard), 24h (comprehensive)
