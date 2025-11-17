# Ticketing System - Go Load Tesㄠg Makefile
# Run from: script/go_client/
# Usage: make <target>

# ==============================================================================
# 📋 CONFIGURATION
# ==============================================================================

# API Configuration (can be overridden via environment variables)
API_HOST ?= http://localhost:8100

# Deployment environment (development, staging, production, local_dev_1000)
DEPLOY_ENV ?= development

# Binary names
CONCURRENT_BIN = concurrent_loadtest
RESERVED_BIN = reserved_loadtest
FULL_RESERVED_BIN = full_reserved_loadtest

# Colors for pretty output
COLOR_RESET = \033[0m
COLOR_BOLD = \033[1m
COLOR_GREEN = \033[32m
COLOR_YELLOW = \033[33m
COLOR_BLUE = \033[34m
COLOR_CYAN = \033[36m

# ==============================================================================
# 🔨 BUILD TARGETS
# ==============================================================================

.PHONY: build build-all clean
build: build-concurrent build-reserved build-full-reserved  ## 🔨 Build all binaries

build-all: build  ## 🔨 Alias for 'build'

build-concurrent:  ## 🔨 Build concurrent load test binary
	@echo "$(COLOR_CYAN)🔨 Building concurrent load test...$(COLOR_RESET)"
	@go build -tags concurrent -o $(CONCURRENT_BIN)
	@echo "$(COLOR_GREEN)✅ Built: $(CONCURRENT_BIN)$(COLOR_RESET)"

build-reserved:  ## 🔨 Build reserved load test binary
	@echo "$(COLOR_CYAN)🔨 Building reserved load test...$(COLOR_RESET)"
	@go build -tags reserved -o $(RESERVED_BIN)
	@echo "$(COLOR_GREEN)✅ Built: $(RESERVED_BIN)$(COLOR_RESET)"

build-full-reserved:  ## 🔨 Build full reserved load test binary (500 workers, 1 ticket each)
	@echo "$(COLOR_CYAN)🔨 Building full reserved load test...$(COLOR_RESET)"
	@go build -tags full_reserved -o $(FULL_RESERVED_BIN)
	@echo "$(COLOR_GREEN)✅ Built: $(FULL_RESERVED_BIN)$(COLOR_RESET)"

clean:  ## 🧹 Remove all binaries
	@echo "$(COLOR_YELLOW)🧹 Cleaning binaries...$(COLOR_RESET)"
	@rm -f $(CONCURRENT_BIN) $(RESERVED_BIN) $(FULL_RESERVED_BIN)
	@echo "$(COLOR_GREEN)✅ Cleaned!$(COLOR_RESET)"

# ==============================================================================
# ⚡ CONCURRENT LOAD TEST (Pressure Testing)
# ==============================================================================

.PHONY: clt-tiny clt-small clt-medium clt-large clt-full
clt-tiny: build-concurrent  ## 🧪 Concurrent Load Test - Tiny (10 requests, 5 concurrency, 5 clients)
	@echo "$(COLOR_BLUE)🧪 Running Tiny concurrent load test...$(COLOR_RESET)"
	@./$(CONCURRENT_BIN) -requests 10 -concurrency 5 -clients 5 -host $(API_HOST)

clt-small: build-concurrent  ## 🧪 Concurrent Load Test - Small (100 requests, 10 concurrency, 10 clients)
	@echo "$(COLOR_BLUE)🧪 Running Small concurrent load test...$(COLOR_RESET)"
	@./$(CONCURRENT_BIN) -requests 100 -concurrency 10 -clients 10 -host $(API_HOST)

clt-medium: build-concurrent  ## ⚡ Concurrent Load Test - Medium (500 requests, 25 concurrency, 25 clients)
	@echo "$(COLOR_BLUE)⚡ Running Medium concurrent load test...$(COLOR_RESET)"
	@./$(CONCURRENT_BIN) -requests 500 -concurrency 25 -clients 25 -host $(API_HOST)

clt-large: build-concurrent  ## ⚡ Concurrent Load Test - Large (15000 requests, 50 concurrency, 50 clients)
	@echo "$(COLOR_BLUE)⚡ Running Large concurrent load test...$(COLOR_RESET)"
	@./$(CONCURRENT_BIN) -requests 15000 -concurrency 50 -clients 50 -host $(API_HOST)

clt-full: build-concurrent  ## 💪 Concurrent Load Test - Full (150000 requests, 100 concurrency, 100 clients)
	@echo "$(COLOR_BLUE)💪 Running Full concurrent load test...$(COLOR_RESET)"
	@./$(CONCURRENT_BIN) -requests 150000 -concurrency 100 -clients 100 -host $(API_HOST)

# Shortcuts
t: clt-tiny
s: clt-small
m: clt-medium
l: clt-large
f: clt-full

# Backward compatibility aliases (for main Makefile forwarding: make go-clt-t → make -C script/go_client clt-t)
clt-t: clt-tiny
clt-s: clt-small
clt-m: clt-medium
clt-l: clt-large
clt-f: clt-full
both-m: both-medium
both-l: both-large
both-f: both-full

# ==============================================================================
# 🔥 RESERVED LOAD TEST (Sellout Testing)
# ==============================================================================

.PHONY: rlt rlt-dev rlt-staging rlt-prod frlt frlt-1k frlt-staging frlt-prod
rlt: build-reserved  ## 🔥 Reserved Load Test - Auto-detect env (random 1-4 tickets, 100 workers)
	@echo "$(COLOR_BLUE)🔥 Running reserved load test...$(COLOR_RESET)"
	@if [ "$(DEPLOY_ENV)" = "production" ]; then \
		echo "$(COLOR_YELLOW)📊 Production mode: 50,000 seats$(COLOR_RESET)"; \
		./$(RESERVED_BIN) -env production -event 1 -workers 100 -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "staging" ]; then \
		echo "$(COLOR_YELLOW)📊 Staging mode: 5,000 seats$(COLOR_RESET)"; \
		./$(RESERVED_BIN) -env staging -event 1 -workers 100 -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "local_dev_1000" ]; then \
		echo "$(COLOR_YELLOW)📊 Local Dev 1000 mode: 1,000 seats$(COLOR_RESET)"; \
		./$(RESERVED_BIN) -env local_dev_1000 -event 1 -workers 100 -host $(API_HOST); \
	else \
		echo "$(COLOR_YELLOW)📊 Development mode: 500 seats$(COLOR_RESET)"; \
		./$(RESERVED_BIN) -env development -event 1 -workers 100 -host $(API_HOST); \
	fi

rlt-dev: build-reserved  ## 🔥 Reserved Load Test - Development (500 seats)
	@echo "$(COLOR_BLUE)🔥 Running reserved load test (Development)...$(COLOR_RESET)"
	@./$(RESERVED_BIN) -env development -event 1 -workers 100 -host $(API_HOST)

rlt-1k: build-reserved  ## 🔥 Reserved Load Test - Local Dev 1000 (1,000 seats)
	@echo "$(COLOR_BLUE)🔥 Running reserved load test (Local Dev 1000)...$(COLOR_RESET)"
	@./$(RESERVED_BIN) -env local_dev_1000 -event 1 -workers 100 -host $(API_HOST)

rlt-staging: build-reserved  ## 🔥 Reserved Load Test - Staging (5,000 seats)
	@echo "$(COLOR_BLUE)🔥 Running reserved load test (Staging)...$(COLOR_RESET)"
	@./$(RESERVED_BIN) -env staging -event 1 -workers 100 -host $(API_HOST)

rlt-prod: build-reserved  ## 🔥 Reserved Load Test - Production (50,000 seats)
	@echo "$(COLOR_BLUE)🔥 Running reserved load test (Production)...$(COLOR_RESET)"
	@./$(RESERVED_BIN) -env production -event 1 -workers 100 -host $(API_HOST)

frlt: build-full-reserved  ## 🚀 Full Reserved Load Test - Configurable (WORKERS=100 BATCH=1)
	@WORKERS=$${WORKERS:-100}; \
	BATCH=$${BATCH:-1}; \
	echo "$(COLOR_BLUE)🚀 Running FULL reserved load test (Workers: $$WORKERS, Batch: $$BATCH)...$(COLOR_RESET)"; \
	if [ "$(DEPLOY_ENV)" = "production" ]; then \
		echo "$(COLOR_YELLOW)📊 Production mode: 50,000 seats$(COLOR_RESET)"; \
		./$(FULL_RESERVED_BIN) -env production -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "staging" ]; then \
		echo "$(COLOR_YELLOW)📊 Staging mode: 5,000 seats$(COLOR_RESET)"; \
		./$(FULL_RESERVED_BIN) -env staging -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "local_dev_1000" ]; then \
		echo "$(COLOR_YELLOW)📊 Local Dev 1000 mode: 1,000 seats$(COLOR_RESET)"; \
		./$(FULL_RESERVED_BIN) -env local_dev_1000 -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST); \
	else \
		echo "$(COLOR_YELLOW)📊 Development mode: 500 seats$(COLOR_RESET)"; \
		./$(FULL_RESERVED_BIN) -env development -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST); \
	fi

frlt-1k: build-full-reserved  ## 🚀 Full Reserved Load Test - 1000 seats (local_dev_1000)
	@$(MAKE) frlt DEPLOY_ENV=local_dev_1000

frlt-staging: build-full-reserved  ## 🚀 Full Reserved Load Test - 5000 seats (staging)
	@$(MAKE) frlt DEPLOY_ENV=staging

frlt-prod: build-full-reserved  ## 🚀 Full Reserved Load Test - 50000 seats (production)
	@$(MAKE) frlt DEPLOY_ENV=production

# ==============================================================================
# 🔄 COMBINED LOAD TESTS (Run in PARALLEL)
# ==============================================================================

.PHONY: both-medium both-large both-full
both-medium: build-concurrent build-reserved  ## 🔄 Both Tests PARALLEL - Medium (CLT: 500/25 + RLT: 100 workers)
	@echo "$(COLOR_BLUE)🔄 Running BOTH tests in PARALLEL - Medium$(COLOR_RESET)"
	@./$(RESERVED_BIN) -env development -event 1 -workers 100 -host $(API_HOST) & \
		./$(CONCURRENT_BIN) -requests 500 -concurrency 25 -clients 25 -host $(API_HOST) & \
		wait
	@echo "$(COLOR_GREEN)✅ Both tests completed!$(COLOR_RESET)"

both-large: build-concurrent build-reserved  ## 🔄 Both Tests PARALLEL - Large (CLT: 5000/50 + RLT: 50 workers)
	@echo "$(COLOR_BLUE)🔄 Running BOTH tests in PARALLEL - Large$(COLOR_RESET)"
	@./$(CONCURRENT_BIN) -requests 5000 -concurrency 50 -clients 50 -host $(API_HOST) & \
		./$(RESERVED_BIN) -env staging -event 1 -workers 50 -host $(API_HOST) & \
		wait
	@echo "$(COLOR_GREEN)✅ Both tests completed!$(COLOR_RESET)"

both-full: build-concurrent build-reserved  ## 🔄 Both Tests PARALLEL - Full (CLT: 50000/100 + RLT: 100 workers)
	@echo "$(COLOR_BLUE)🔄 Running BOTH tests in PARALLEL - Full$(COLOR_RESET)"
	@./$(CONCURRENT_BIN) -requests 50000 -concurrency 100 -clients 100 -host $(API_HOST) & \
		./$(RESERVED_BIN) -env production -event 1 -workers 100 -host $(API_HOST) & \
		wait
	@echo "$(COLOR_GREEN)✅ Both tests completed!$(COLOR_RESET)"

# ==============================================================================
# 🐳 DOCKER BUILD & RUN
# ==============================================================================

.PHONY: docker-build docker-run docker-test
docker-build:  ## 🐳 Build Docker image for load testing
	@echo "$(COLOR_CYAN)🐳 Building Docker image...$(COLOR_RESET)"
	@docker build -f Dockerfile -t go-loadtest:latest ../
	@echo "$(COLOR_GREEN)✅ Docker image built: go-loadtest:latest$(COLOR_RESET)"

docker-run:  ## 🚀 Run load test in Docker container (usage: make docker-run ARGS='-env development -event 1')
	@ARGS=$${ARGS:-"-env development -event 1 -workers 50"}; \
	echo "$(COLOR_CYAN)🚀 Running load test in Docker: $$ARGS$(COLOR_RESET)"; \
	docker run --rm -e API_HOST=$(API_HOST) go-loadtest:latest ./reserved_loadtest $$ARGS

docker-test:  ## 🧪 Quick Docker test (10 workers, development)
	@echo "$(COLOR_CYAN)🧪 Running quick Docker test...$(COLOR_RESET)"
	@docker run --rm -e API_HOST=$(API_HOST) go-loadtest:latest ./reserved_loadtest -env development -event 1 -workers 10

# ==============================================================================
# 📊 UTILITIES
# ==============================================================================

.PHONY: check-env show-config version
check-env:  ## 🔍 Check current environment settings
	@echo "$(COLOR_CYAN)📋 Current Configuration:$(COLOR_RESET)"
	@echo "  API_HOST:    $(API_HOST)"
	@echo "  DEPLOY_ENV:  $(DEPLOY_ENV)"
	@echo ""
	@if [ "$(DEPLOY_ENV)" = "production" ]; then \
		echo "  📊 Seats:     50,000 seats"; \
	elif [ "$(DEPLOY_ENV)" = "staging" ]; then \
		echo "  📊 Seats:     5,000 seats"; \
	elif [ "$(DEPLOY_ENV)" = "local_dev_1000" ]; then \
		echo "  📊 Seats:     1,000 seats"; \
	else \
		echo "  📊 Seats:     500 seats"; \
	fi

show-config: check-env  ## 🔍 Alias for check-env

version:  ## 📌 Show Go version
	@go version

# ==============================================================================
# 📖 HELP
# ==============================================================================

.PHONY: help
help:  ## 📖 Show this help message
	@echo "$(COLOR_BOLD)╔═══════════════════════════════════════════════════════════════╗$(COLOR_RESET)"
	@echo "$(COLOR_BOLD)║         🚀 Go Load Testing - Makefile Commands               ║$(COLOR_RESET)"
	@echo "$(COLOR_BOLD)╚═══════════════════════════════════════════════════════════════╝$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_CYAN)🔨 BUILD TARGETS$(COLOR_RESET)"
	@echo "  build              - Build all binaries"
	@echo "  build-concurrent   - Build concurrent load test binary"
	@echo "  build-reserved     - Build reserved load test binary"
	@echo "  build-full-reserved- Build full reserved load test binary"
	@echo "  clean              - Remove all binaries"
	@echo ""
	@echo "$(COLOR_CYAN)⚡ CONCURRENT LOAD TEST (Pressure Testing)$(COLOR_RESET)"
	@echo "  clt-tiny    (t)    - Tiny    (10 req, 5 concurrency)"
	@echo "  clt-small   (s)    - Small   (100 req, 10 concurrency)"
	@echo "  clt-medium  (m)    - Medium  (500 req, 25 concurrency)"
	@echo "  clt-large   (l)    - Large   (15K req, 50 concurrency)"
	@echo "  clt-full    (f)    - Full    (150K req, 100 concurrency)"
	@echo ""
	@echo "$(COLOR_CYAN)🔥 RESERVED LOAD TEST (Sellout Testing)$(COLOR_RESET)"
	@echo "  rlt                - Auto-detect environment"
	@echo "  rlt-dev            - Development (500 seats)"
	@echo "  rlt-1k             - Local Dev 1000 (1,000 seats)"
	@echo "  rlt-staging        - Staging (5,000 seats)"
	@echo "  rlt-prod           - Production (50,000 seats)"
	@echo ""
	@echo "$(COLOR_CYAN)🚀 FULL RESERVED LOAD TEST (All Seats, 1 per Worker)$(COLOR_RESET)"
	@echo "  frlt               - Full reserved (configurable: WORKERS=100 BATCH=1)"
	@echo "  frlt-1k            - Full reserved - 1000 seats (local_dev_1000)"
	@echo "  frlt-staging       - Full reserved - 5000 seats (staging)"
	@echo "  frlt-prod          - Full reserved - 50000 seats (production)"
	@echo ""
	@echo "$(COLOR_CYAN)🔄 COMBINED TESTS (Parallel)$(COLOR_RESET)"
	@echo "  both-medium        - CLT Medium + RLT Development"
	@echo "  both-large         - CLT Large + RLT Staging"
	@echo "  both-full          - CLT Full + RLT Production"
	@echo ""
	@echo "$(COLOR_CYAN)🐳 DOCKER$(COLOR_RESET)"
	@echo "  docker-build       - Build Docker image"
	@echo "  docker-run         - Run load test in Docker (ARGS='-env dev -event 1')"
	@echo "  docker-test        - Quick Docker test (10 workers)"
	@echo ""
	@echo "$(COLOR_CYAN)📊 UTILITIES$(COLOR_RESET)"
	@echo "  check-env          - Show current configuration"
	@echo "  version            - Show Go version"
	@echo "  help               - Show this help"
	@echo ""
	@echo "$(COLOR_YELLOW)💡 EXAMPLES$(COLOR_RESET)"
	@echo "  make t                              # Quick tiny test"
	@echo "  make rlt                            # Run sellout test (auto-detect env)"
	@echo "  make rlt-dev                        # Run sellout test (500 seats)"
	@echo "  make rlt-1k                         # Run sellout test (1000 seats)"
	@echo "  make frlt-1k                        # Full reserved test (1000 seats)"
	@echo "  make frlt-staging                   # Full reserved test (5000 seats)"
	@echo "  API_HOST=http://alb.aws.com make m  # Test against AWS"
	@echo "  DEPLOY_ENV=production make rlt      # Test production (50K seats)"
	@echo "  WORKERS=500 BATCH=2 make frlt       # Custom full reserved test"
	@echo "  make both-medium                    # Run both tests in parallel"
	@echo ""
	@echo "$(COLOR_YELLOW)🔧 CONFIGURATION$(COLOR_RESET)"
	@echo "  API_HOST=$(API_HOST)"
	@echo "  DEPLOY_ENV=$(DEPLOY_ENV)"
	@echo ""
	@echo "$(COLOR_CYAN)📚 Run 'make check-env' to see current settings$(COLOR_RESET)"

# Default target
.DEFAULT_GOAL := help
