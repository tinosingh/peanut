#!/bin/bash
#
# Peanut Helper Script
# Usage: ./peanut.sh [command] [options]
#
# Commands:
#   start       Start the Docker Compose stack
#   stop        Stop the Docker Compose stack
#   restart     Restart the Docker Compose stack
#   reset       Stop and remove volumes, then restart (wipes data)
#   status      Show service status
#   logs        Tail service logs
#   tui         Launch the Textual TUI
#   health      Check all service health
#   help        Show this help message
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_help() {
    cat << 'HELP'
Peanut Helper Script

Usage: ./peanut.sh [command] [options]

Commands:
  start       Start the Docker Compose stack
              Usage: ./peanut.sh start
              
  stop        Stop the Docker Compose stack
              Usage: ./peanut.sh stop
              
  restart     Restart the Docker Compose stack
              Usage: ./peanut.sh restart
              
  reset       Stop and remove volumes, then restart (WIPES ALL DATA)
              Usage: ./peanut.sh reset [--confirm]
              
  status      Show service status
              Usage: ./peanut.sh status
              
  logs        Tail service logs
              Usage: ./peanut.sh logs [service]
              Example: ./peanut.sh logs pkg-ingest
              
  tui         Launch the Textual TUI
              Usage: ./peanut.sh tui
              Requires: Stack must be running
              
  health      Check all service health
              Usage: ./peanut.sh health
              
  help        Show this help message
              Usage: ./peanut.sh help

Examples:
  ./peanut.sh start          # Start all services
  ./peanut.sh stop           # Stop all services
  ./peanut.sh restart        # Restart services
  ./peanut.sh tui            # Launch TUI (after stack is running)
  ./peanut.sh logs pkg-tui   # View TUI logs
  ./peanut.sh health         # Check health of all services

HELP
}

print_status() {
    echo -e "${BLUE}Status:${NC}"
    docker-compose ps
}

start_services() {
    echo -e "${BLUE}Starting Peanut services...${NC}"
    
    # Copy .env if not exists
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            echo -e "${GREEN}✓${NC} Created .env from .env.example"
        fi
    fi
    
    docker-compose up -d
    echo -e "${GREEN}✓${NC} Services started"
    echo ""
    echo -e "${YELLOW}Waiting for services to be ready...${NC}"
    sleep 10
    
    echo ""
    echo -e "${BLUE}Status:${NC}"
    docker-compose ps
    
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Check health:  ./peanut.sh health"
    echo "  2. View logs:     ./peanut.sh logs"
    echo "  3. Launch TUI:    ./peanut.sh tui"
}

stop_services() {
    echo -e "${YELLOW}Stopping Peanut services...${NC}"
    docker-compose down
    echo -e "${GREEN}✓${NC} Services stopped"
}

restart_services() {
    echo -e "${YELLOW}Restarting Peanut services...${NC}"
    docker-compose restart
    sleep 5
    echo -e "${GREEN}✓${NC} Services restarted"
    echo ""
    docker-compose ps
}

reset_services() {
    if [ "$1" != "--confirm" ]; then
        echo -e "${RED}WARNING: This will delete all data (documents, embeddings, graph, etc.)${NC}"
        echo -e "${YELLOW}Run with --confirm to proceed:${NC}"
        echo "  ./peanut.sh reset --confirm"
        exit 1
    fi
    
    echo -e "${RED}Resetting Peanut (removing all volumes)...${NC}"
    docker-compose down -v
    echo -e "${GREEN}✓${NC} Volumes removed"
    echo ""
    sleep 2
    
    start_services
}

check_health() {
    echo -e "${BLUE}Checking service health...${NC}"
    echo ""
    
    # Check Docker Compose status
    echo -e "${YELLOW}1. Docker Compose Services:${NC}"
    if docker-compose ps | grep -q "Exit"; then
        echo -e "${RED}✗${NC} Some services are not running"
        docker-compose ps
        exit 1
    else
        echo -e "${GREEN}✓${NC} All services running"
    fi
    echo ""
    
    # Check API health
    echo -e "${YELLOW}2. API Health:${NC}"
    if curl -s http://localhost:8000/health | grep -q "ok"; then
        echo -e "${GREEN}✓${NC} API is healthy"
    else
        echo -e "${RED}✗${NC} API health check failed"
    fi
    echo ""
    
    # Check Database
    echo -e "${YELLOW}3. Database:${NC}"
    if docker exec pkg-db psql -U pkg -d pkg -c "SELECT 1" >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Database is accessible"
    else
        echo -e "${RED}✗${NC} Database check failed"
    fi
    echo ""
    
    # Check FalkorDB
    echo -e "${YELLOW}4. FalkorDB (Graph):${NC}"
    if docker exec pkg-graph redis-cli PING | grep -q "PONG"; then
        echo -e "${GREEN}✓${NC} FalkorDB is accessible"
    else
        echo -e "${RED}✗${NC} FalkorDB check failed"
    fi
    echo ""
    
    # Check Ollama
    echo -e "${YELLOW}5. Ollama (Embeddings):${NC}"
    if docker exec pkg-ingest curl -s http://host.docker.internal:11434/api/tags >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Ollama is accessible"
    else
        echo -e "${RED}✗${NC} Ollama is not reachable (ensure Ollama is running on host)"
    fi
    echo ""
    
    echo -e "${GREEN}All systems operational!${NC}"
}

launch_tui() {
    # Check if stack is running
    if ! docker inspect pkg-tui --format="{{.State.Running}}" 2>/dev/null | grep -q "true"; then
        echo -e "${RED}Error: Stack is not running${NC}"
        echo "Start services first with:  ./peanut.sh start"
        exit 1
    fi
    
    echo -e "${BLUE}Launching Peanut TUI...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to exit${NC}"
    echo ""
    
    docker exec -it pkg-tui python -m src.tui.main
}

tail_logs() {
    SERVICE="$1"
    
    if [ -z "$SERVICE" ]; then
        echo -e "${BLUE}Tailing all service logs...${NC}"
        echo -e "${YELLOW}Press Ctrl+C to exit${NC}"
        docker-compose logs -f
    else
        echo -e "${BLUE}Tailing ${SERVICE} logs...${NC}"
        echo -e "${YELLOW}Press Ctrl+C to exit${NC}"
        docker-compose logs -f "$SERVICE"
    fi
}

# Main command dispatcher
COMMAND="${1:-help}"

case "$COMMAND" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    reset)
        reset_services "$2"
        ;;
    status)
        print_status
        ;;
    logs)
        tail_logs "$2"
        ;;
    tui)
        launch_tui
        ;;
    health)
        check_health
        ;;
    help)
        print_help
        ;;
    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        echo ""
        print_help
        exit 1
        ;;
esac
