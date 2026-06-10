#!/bin/bash
# ==============================================================================
# Script: tc_enhanced.sh
# Description: Advanced Traffic Control (tc) wrapper for multi-queue latency injection
# ==============================================================================

# Default values
INTERFACES=("enp65s0f0")
LATENCY=""
ACTION=""

# Colors for pretty output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

usage() {
    echo -e "${YELLOW}Usage:${NC} $0 [options]"
    echo
    echo -e "${BOLD}Options:${NC}"
    echo "  -i, --interface <ifs>   Comma-separated list of interfaces (Default: enp65s0f0)"
    echo "  -j, --inject <latency>  Inject latency (e.g., 5ms, 50ms)"
    echo "  -s, --show              Show current traffic control status for interfaces"
    echo "  -r, --reset, --del      Reset/delete tc rules on the specified interfaces"
    echo "  -h, --help              Display this help message"
    echo
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0 --inject 50ms"
    echo "  $0 --interface enp65s0f0,enp65s0f1 --inject 10ms"
    echo "  $0 --show"
    echo "  $0 --reset"
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--interface)
            if [[ -n "$2" && "$2" != -* ]]; then
                IFS=',' read -r -a INTERFACES <<< "$2"
                shift 2
            else
                echo -e "${RED}Error: Argument for $1 is missing.${NC}" >&2
                usage
            fi
            ;;
        -j|--inject)
            if [[ -n "$2" && "$2" != -* ]]; then
                LATENCY="$2"
                ACTION="inject"
                shift 2
            else
                echo -e "${RED}Error: Argument for $1 is missing.${NC}" >&2
                usage
            fi
            ;;
        -s|--show)
            ACTION="show"
            shift
            ;;
        -r|--reset|--del)
            ACTION="reset"
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Error: Invalid option '$1'${NC}" >&2
            usage
            ;;
    esac
done

if [[ -z "$ACTION" ]]; then
    echo -e "${RED}Error: You must specify an action like --inject, --show, or --reset.${NC}" >&2
    usage
fi

if [[ "$ACTION" == "inject" ]]; then
    if [[ ! "$LATENCY" =~ ^[0-9]+ms$ ]]; then
        echo -e "${RED}Error: Invalid latency format '$LATENCY'. Use values like 5ms or 50ms.${NC}" >&2
        exit 1
    fi
fi

# Function to inject latency
inject_latency() {
    local iface=$1
    echo -e "${GREEN}[*] Injecting ${LATENCY} latency into ${iface}...${NC}"
    
    # 1. Break the hardware lock by flushing the unmanaged mq 0: root layout
    sudo tc qdisc del dev "$iface" root 2>/dev/null
    
    # 2. Instantiate a clean, editable managed multi-queue root handle 1:
    sudo tc qdisc add dev "$iface" root handle 1: mq 2>/dev/null
    if [[ $? -ne 0 ]]; then
        echo -e "${RED}[X] Critical Error: Kernel refused to bind root handle 1: on ${iface}.${NC}"
        return 1
    fi

    # 3. Read back the newly spawned channel map from the kernel
    local raw_dump=$(sudo tc qdisc show dev "$iface" 2>/dev/null)
    
    echo -e "${YELLOW}[*] Parsing newly provisioned hardware channels...${NC}"
    
    # Extract clean hex IDs belonging specifically to our new open handle 1:
    local map_queues=$(echo "$raw_dump" | grep "parent 1:" | awk '{print $4}' | cut -d':' -f2 | grep -E '^[0-9a-fA-F]+$' | sort -u)

    # Static boundary loop fallback if dynamic sysfs reading acts up
    if [[ -z "$map_queues" ]]; then
        echo -e "${YELLOW}[!] Dynamic query empty. Processing standard 768 queue mapping loop...${NC}"
        map_queues=$(for i in $(seq 1 768); do printf "%x\n" $i; done)
    fi

    # 4. Sequential Execution Loop
    local count=0
    for raw_hex in $map_queues; do
        local hex_id=$(echo "$raw_hex" | grep -oE '^[0-9a-fA-F]+$')
        if [[ -z "$hex_id" ]]; then
            continue
        fi

        local dec_id=$((16#$hex_id))
        
        # Inject netem child elements using strict key spaces map over handle 1:
        sudo tc qdisc add dev "$iface" parent 1:"$hex_id" handle "${dec_id}0:" netem delay "$LATENCY" 2>/dev/null
        if [[ $? -eq 0 ]]; then
            ((count++))
        fi
    done
    
    if [[ $count -gt 0 ]]; then
        echo -e "${GREEN}[✓] Successfully configured ${count} active network queues on ${iface}${NC}"
    else
        echo -e "${RED}[X] Injection failed. Run --reset and check interface constraints.${NC}"
    fi
}

# Function to display human-readable status
show_status() {
    local iface=$1
    echo -e "${BOLD}Traffic Control Status for: ${YELLOW}${iface}${NC}"
    echo "--------------------------------------------------------"
    
    local raw_rules=$(sudo tc qdisc show dev "$iface" 2>/dev/null)
    
    if ! echo "$raw_rules" | grep -qE "netem|mq"; then
        echo -e "  Status: ${GREEN}Normal Operating Mode (Bypass / No Emulation Active)${NC}"
        echo "--------------------------------------------------------"
        return
    fi
    
    if echo "$raw_rules" | grep -q "mq"; then
        local found_handle=$(echo "$raw_rules" | grep "root" | awk '{print $2, $3}')
        echo -e "  Root Qdisc:  ${YELLOW}Multi-Queue Engine Active (${found_handle})${NC}"
        
        local netem_count=$(echo "$raw_rules" | grep -c "qdisc netem")
        if [[ "$netem_count" -gt 0 ]]; then
            local discovered_latencies=$(echo "$raw_rules" | grep "qdisc netem" | sed -E 's/.*delay ([0-9]+ms).*/\1/' | sort -u | xargs)
            echo -e "  Status:      ${RED}LATENCY INJECTION ACTIVE${NC}"
            echo -e "  Queues:      ${BOLD}${netem_count}${NC} dynamic hardware paths modified"
            echo -e "  Delay Value: ${GREEN}${discovered_latencies}${NC}"
        else
            echo -e "  Status:      ${GREEN}Clear / Inactive${NC} (Base hardware queues exposed without delays)"
        fi
    else
        local base_qdisc=$(echo "$raw_rules" | head -n 1 | awk '{print $2, $3}')
        echo -e "  Root Qdisc:  Custom layout (${base_qdisc})"
    fi
    echo "--------------------------------------------------------"
}

# Function to reset interface completely back to original unmanaged baseline (mq 0:)
reset_interface() {
    local iface=$1
    echo -e "${YELLOW}[*] Resetting traffic control layout configuration on ${iface}...${NC}"
    
    # Tear down our managed handles completely
    sudo tc qdisc del dev "$iface" root 2>/dev/null
    
    # Re-apply original fallback layout expected by VAST-OS/the card driver
    sudo tc qdisc add dev "$iface" root handle 0: mq 2>/dev/null

    echo -e "${GREEN}[✓] ${iface} cleanly restored to default hardware operating mode (mq 0:).${NC}"
}

# --- Main Execution Loop ---
for iface in "${INTERFACES[@]}"; do
    iface=$(echo "$iface" | tr -d ' ')
    
    if ! ip link show "$iface" > /dev/null 2>&1; then
        echo -e "${RED}[X] Error: Interface '$iface' does not exist.${NC}" >&2
        continue
    fi

    if [[ "$ACTION" == "inject" ]]; then
        inject_latency "$iface"
    elif [[ "$ACTION" == "show" ]]; then
        show_status "$iface"
    elif [[ "$ACTION" == "reset" ]]; then
        reset_interface "$iface"
    fi
done