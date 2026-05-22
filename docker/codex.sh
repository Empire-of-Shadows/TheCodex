#!/bin/bash

# Discord Bot + Dashboard Deployment Script
set -e  # Exit on any error

# Always run from the directory where this script lives (docker/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
BOT_CONTAINER="TheCodex"
DASH_CONTAINER="TheCodex-Dashboard"
BOT_IMAGE="the-codex"
DASH_IMAGE="the-codex-dashboard"
BACKUP_TAG_BOT="the-codex:backup"
BACKUP_TAG_DASH="the-codex-dashboard:backup"
HEALTH_CHECK_TIMEOUT=120  # seconds to wait for health check

NO_CACHE=0
BRANCH=Revamp
REPO_URL=https://github.com/Empire-of-Shadows/TheCodex.git
for arg in "$@"; do
    case "$arg" in
        -n|--no-cache)
            NO_CACHE=1
            ;;
        -h|--help)
            echo "Usage: $0 [-n|--no-cache]"
            echo "  -n, --no-cache   Build images from scratch (skip Docker layer cache)"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [-n|--no-cache]"
            exit 1
            ;;
    esac
done

echo "==== Starting TheCodex Deployment ===="
echo "Timestamp: $(date)"
if [ "$NO_CACHE" = "1" ]; then
    echo "Mode: no-cache build"
else
    echo "Mode: cached build"
fi
echo "Branch: $BRANCH"
# Step 0: Git Update
echo ""
echo "--- Updating source code from branch $BRANCH ---"
# Move to project root (one level up from docker/ script dir)
pushd .. > /dev/null
if [ ! -d ".git" ]; then
    echo "  No git repo found, initializing from $REPO_URL"
    git init -q -b "$BRANCH"
    git remote add origin "$REPO_URL"
fi
git fetch origin
git reset --hard "origin/$BRANCH"
popd > /dev/null
# Function to check container health
check_container_health() {
    local container=$1
    local timeout=$HEALTH_CHECK_TIMEOUT
    local elapsed=0
    local interval=5

    echo "Checking $container health..."

    while [ $elapsed -lt $timeout ]; do
        local status
        status=$(docker inspect "$container" --format='{{.State.Health.Status}}' 2>/dev/null || echo "not_found")

        if [ "$status" = "healthy" ]; then
            echo "  $container is healthy!"
            return 0
        elif [ "$status" = "unhealthy" ]; then
            echo "  $container is unhealthy!"
            return 1
        else
            echo "  Waiting for $container... (${elapsed}s/${timeout}s)"
            sleep $interval
            elapsed=$((elapsed + interval))
        fi
    done

    echo "  Health check timeout for $container"
    return 1
}

# Function to rollback to previous version
rollback() {
    echo "Rolling back to previous version..."

    docker compose down 2>/dev/null || true

    # Restore bot backup
    if docker images "$BACKUP_TAG_BOT" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | grep -q "$BACKUP_TAG_BOT"; then
        docker rmi -f "$BOT_IMAGE" 2>/dev/null || true
        docker tag "$BACKUP_TAG_BOT" "$BOT_IMAGE"
    fi

    # Restore dashboard backup
    if docker images "$BACKUP_TAG_DASH" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | grep -q "$BACKUP_TAG_DASH"; then
        docker rmi -f "$DASH_IMAGE" 2>/dev/null || true
        docker tag "$BACKUP_TAG_DASH" "$DASH_IMAGE"
    fi

    docker compose up -d

    local rollback_ok=true
    check_container_health "$BOT_CONTAINER" || rollback_ok=false
    check_container_health "$DASH_CONTAINER" || rollback_ok=false

    if $rollback_ok; then
        echo "Rollback completed successfully"
    else
        echo "Rollback failed - one or more containers unhealthy"
        exit 1
    fi
}

# Pre-deployment checks
echo ""
echo "--- Pre-deployment checks ---"

if ! command -v docker &> /dev/null; then
    echo "Docker is not installed or not in PATH"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "docker compose is not installed or not in PATH"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo ".env file not found in $SCRIPT_DIR"
    exit 1
fi

# Backup current images if they exist
echo ""
echo "--- Backing up current images ---"

if docker images "$BOT_IMAGE" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | grep -q "$BOT_IMAGE"; then
    docker tag "$BOT_IMAGE" "$BACKUP_TAG_BOT" 2>/dev/null && echo "  Backed up $BOT_IMAGE" || echo "  Warning: Failed to backup $BOT_IMAGE"
fi

if docker images "$DASH_IMAGE" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | grep -q "$DASH_IMAGE"; then
    docker tag "$DASH_IMAGE" "$BACKUP_TAG_DASH" 2>/dev/null && echo "  Backed up $DASH_IMAGE" || echo "  Warning: Failed to backup $DASH_IMAGE"
fi

# Step 1: Graceful shutdown
echo ""
echo "--- Stopping containers ---"

if docker ps --filter "name=$BOT_CONTAINER" --filter "name=$DASH_CONTAINER" --format "{{.Names}}" | grep -qE "$BOT_CONTAINER|$DASH_CONTAINER"; then
    docker compose down --timeout 30 || {
        echo "Warning: Graceful shutdown failed, forcing stop..."
        docker kill "$BOT_CONTAINER" "$DASH_CONTAINER" 2>/dev/null || true
        docker rm -f "$BOT_CONTAINER" "$DASH_CONTAINER" 2>/dev/null || true
    }
else
    echo "  No containers were running"
fi

# Step 2: Clean up old images
echo ""
echo "--- Cleaning up old images ---"
docker rmi -f "$BOT_IMAGE" 2>/dev/null || echo "  No old $BOT_IMAGE to remove"
docker rmi -f "$DASH_IMAGE" 2>/dev/null || echo "  No old $DASH_IMAGE to remove"

# Step 3: Build and start
echo ""
echo "--- Building and starting containers ---"

if [ "$NO_CACHE" = "1" ]; then
    echo "Building (no cache)..."
    docker compose build --no-cache
    BUILD_CMD="docker compose up -d"
else
    BUILD_CMD="docker compose up --build -d"
fi

if $BUILD_CMD; then
    echo ""
    echo "--- Waiting for health checks ---"

    all_healthy=true
    check_container_health "$BOT_CONTAINER" || all_healthy=false
    check_container_health "$DASH_CONTAINER" || all_healthy=false

    if $all_healthy; then
        echo ""
        echo "==== Deployment Successful! ===="
        echo "Timestamp: $(date)"
        echo ""
        echo "  Bot:       $BOT_CONTAINER (port 50002)"
        echo "  Dashboard: $DASH_CONTAINER (port 54002)"

        # Clean up backup images
        docker rmi -f "$BACKUP_TAG_BOT" 2>/dev/null || true
        docker rmi -f "$BACKUP_TAG_DASH" 2>/dev/null || true

        echo ""
        echo "Following logs (Ctrl+C to exit):"
        echo "================================="
        docker compose logs -f
    else
        echo ""
        echo "Health check failed, initiating rollback..."
        rollback
        exit 1
    fi
else
    echo ""
    echo "Failed to build/start containers, initiating rollback..."
    rollback
    exit 1
fi