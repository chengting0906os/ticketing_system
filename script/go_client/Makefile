# Ticketing System - Go Load Testing Makefile
# Run from: script/go_client/
# Usage: make <target>

# ==============================================================================
# 📋 CONFIGURATION
# ==============================================================================

# Load .env file if it exists (for local development)
# This reads ENVIRONMENT from .env and uses it as DEPLOY_ENV default
ENV_FILE := $(wildcard ../../.env)
ifneq ($(ENV_FILE),)
  # Extract ENVIRONMENT from .env file
  ENV_FROM_FILE := $(shell grep -E '^ENVIRONMENT=' ../../.env 2>/dev/null | cut -d'=' -f2)
  ifneq ($(ENV_FROM_FILE),)
    DEPLOY_ENV ?= $(ENV_FROM_FILE)
  else
    DEPLOY_ENV ?= local_dev
  endif
else # No .env file, default to local_dev for safety
  DEPLOY_ENV ?= local_dev
endif

# API Configuration - auto-detect based on DEPLOY_ENV if not set
ifndef API_HOST
  ifeq ($(DEPLOY_ENV),development)
    API_HOST = http://ticketing-alb-879134627.us-west-2.elb.amazonaws.com
  else ifeq ($(DEPLOY_ENV),staging)
    API_HOST = http://ticketing-alb-staging.us-west-2.elb.amazonaws.com
  else ifeq ($(DEPLOY_ENV),production)
    API_HOST = http://ticketing-alb-prod.us-west-2.elb.amazonaws.com
  else
    API_HOST = http://localhost:8100
  endif
endif

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

build-concurrent:  ## 🔨 Build concurrent load test binary (skipped if binary exists)
	@if [ -x "./$(CONCURRENT_BIN)" ]; then \
		echo "$(COLOR_GREEN)✅ $(CONCURRENT_BIN) already exists, skipping build$(COLOR_RESET)"; \
	else \
		echo "$(COLOR_CYAN)🔨 Building concurrent load test...$(COLOR_RESET)"; \
		go build -tags concurrent -o $(CONCURRENT_BIN); \
		echo "$(COLOR_GREEN)✅ Built: $(CONCURRENT_BIN)$(COLOR_RESET)"; \
	fi

build-reserved:  ## 🔨 Build reserved load test binary (skipped if binary exists)
	@if [ -x "./$(RESERVED_BIN)" ]; then \
		echo "$(COLOR_GREEN)✅ $(RESERVED_BIN) already exists, skipping build$(COLOR_RESET)"; \
	else \
		echo "$(COLOR_CYAN)🔨 Building reserved load test...$(COLOR_RESET)"; \
		go build -tags reserved -o $(RESERVED_BIN); \
		echo "$(COLOR_GREEN)✅ Built: $(RESERVED_BIN)$(COLOR_RESET)"; \
	fi

build-full-reserved:  ## 🔨 Build full reserved load test binary (skipped if binary exists)
	@if [ -x "./$(FULL_RESERVED_BIN)" ]; then \
		echo "$(COLOR_GREEN)✅ $(FULL_RESERVED_BIN) already exists, skipping build$(COLOR_RESET)"; \
	else \
		echo "$(COLOR_CYAN)🔨 Building full reserved load test...$(COLOR_RESET)"; \
		go build -tags full_reserved -o $(FULL_RESERVED_BIN); \
		echo "$(COLOR_GREEN)✅ Built: $(FULL_RESERVED_BIN)$(COLOR_RESET)"; \
	fi

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


# Backward compatibility aliases (for main Makefile forwarding: make go-clt-t → make -C script/go_client clt-t)
clt-t: clt-tiny
clt-s: clt-small
clt-m: clt-medium
clt-l: clt-large
clt-f: clt-full

# ==============================================================================
# 🔥 RESERVED LOAD TEST (Sellout Testing)
# ==============================================================================

.PHONY: rlt rlt-dev rlt-5k rlt-50k frlt frlt-1k frlt-2k frlt-5k frlt-50k
rlt: build-reserved  ## 🔥 Reserved Load Test - Auto-detect env (random 1-4 tickets, 100 workers)
	@echo "$(COLOR_BLUE)🔥 Running reserved load test...$(COLOR_RESET)"
	@if [ "$(DEPLOY_ENV)" = "production" ]; then \
		echo "$(COLOR_YELLOW)📊 Production mode: 50,000 seats$(COLOR_RESET)"; \
		./$(RESERVED_BIN) -env production -event 1 -workers 100 -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "staging" ]; then \
		echo "$(COLOR_YELLOW)📊 Staging mode: 5,000 seats$(COLOR_RESET)"; \
		./$(RESERVED_BIN) -env staging -event 1 -workers 100 -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "local_dev_2k" ]; then \
		echo "$(COLOR_YELLOW)📊 Local Dev 2k mode: 2,000 seats$(COLOR_RESET)"; \
		./$(RESERVED_BIN) -env local_dev_2k -event 1 -workers 100 -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "local_dev_1000" ]; then \
		echo "$(COLOR_YELLOW)📊 Local Dev 1000 mode: 1,000 seats$(COLOR_RESET)"; \
		./$(RESERVED_BIN) -env local_dev_1000 -event 1 -workers 100 -host $(API_HOST); \
	else \
		echo "$(COLOR_YELLOW)📊 Local dev mode: 500 seats$(COLOR_RESET)"; \
		./$(RESERVED_BIN) -env local_dev -event 1 -workers 100 -host $(API_HOST); \
	fi

rlt-dev: build-reserved  ## 🔥 Reserved Load Test - Local dev (500 seats)
	@echo "$(COLOR_BLUE)🔥 Running reserved load test (Local dev)...$(COLOR_RESET)"
	@./$(RESERVED_BIN) -env local_dev -event 1 -workers 100 -host $(API_HOST)

rlt-1k: build-reserved  ## 🔥 Reserved Load Test - Local Dev 1000 (1,000 seats)
	@echo "$(COLOR_BLUE)🔥 Running reserved load test (Local Dev 1000)...$(COLOR_RESET)"
	@./$(RESERVED_BIN) -env local_dev_1000 -event 1 -workers 100 -host $(API_HOST)

rlt-5k: build-reserved  ## 🔥 Reserved Load Test - Staging (5,000 seats)
	@echo "$(COLOR_BLUE)🔥 Running reserved load test (Staging)...$(COLOR_RESET)"
	@./$(RESERVED_BIN) -env staging -event 1 -workers 100 -host $(API_HOST)

rlt-50k: build-reserved  ## 🔥 Reserved Load Test - Production (50,000 seats)
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
	elif [ "$(DEPLOY_ENV)" = "local_dev_2k" ]; then \
		echo "$(COLOR_YELLOW)📊 Local Dev 2k mode: 2,000 seats$(COLOR_RESET)"; \
		./$(FULL_RESERVED_BIN) -env local_dev_2k -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "local_dev_1000" ]; then \
		echo "$(COLOR_YELLOW)📊 Local Dev 1000 mode: 1,000 seats$(COLOR_RESET)"; \
		./$(FULL_RESERVED_BIN) -env local_dev_1000 -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST); \
	else \
		echo "$(COLOR_YELLOW)📊 Local dev mode: 500 seats$(COLOR_RESET)"; \
		./$(FULL_RESERVED_BIN) -env local_dev -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST); \
	fi

frlt-1k: build-full-reserved  ## 🚀 Full Reserved Load Test - 1000 seats (local_dev_1000)
	@$(MAKE) frlt DEPLOY_ENV=local_dev_1000

frlt-2k: build-full-reserved  ## 🚀 Full Reserved Load Test - 2000 seats (local_dev_2k)
	@$(MAKE) frlt DEPLOY_ENV=local_dev_2k

frlt-5k: build-full-reserved  ## 🚀 Full Reserved Load Test - 5000 seats (staging)
	@$(MAKE) frlt DEPLOY_ENV=staging

frlt-50k: build-full-reserved  ## 🚀 Full Reserved Load Test - 50000 seats (production)
	@$(MAKE) frlt DEPLOY_ENV=production



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
	elif [ "$(DEPLOY_ENV)" = "local_dev_2k" ]; then \
		echo "  📊 Seats:     2,000 seats"; \
	elif [ "$(DEPLOY_ENV)" = "local_dev_1000" ]; then \
		echo "  📊 Seats:     1,000 seats"; \
	else \
		echo "  📊 Seats:     500 seats"; \
	fi

show-config: check-env  ## 🔍 Alias for check-env

version:  ## 📌 Show Go version
	@go version

# ==============================================================================
# 📊 K6 LOAD TESTS
# ==============================================================================

K6_SCRIPT_DIR ?= /app/k6/local

.PHONY: k6-load k6-stress
k6-load:  ## 📊 Run k6 load test (peak 250 RPS)
	@echo "$(COLOR_CYAN)📊 Running k6 load test...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)  API_HOST=$(API_HOST)$(COLOR_RESET)"
	k6 run $(K6_SCRIPT_DIR)/load-test.js

k6-stress:  ## 📊 Run k6 stress test (peak 500 RPS)
	@echo "$(COLOR_CYAN)📊 Running k6 stress test...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)  API_HOST=$(API_HOST)$(COLOR_RESET)"
	k6 run $(K6_SCRIPT_DIR)/stress-test.js

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
	@echo "  rlt-5k        - Staging (5,000 seats)"
	@echo "  rlt-50k           - Production (50,000 seats)"
	@echo ""
	@echo "$(COLOR_CYAN)🚀 FULL RESERVED LOAD TEST (All Seats, 1 per Worker)$(COLOR_RESET)"
	@echo "  frlt               - Full reserved (configurable: WORKERS=100 BATCH=1)"
	@echo "  frlt-1k            - Full reserved - 1000 seats (local_dev_1000)"
	@echo "  frlt-2k            - Full reserved - 2000 seats (local_dev_2k)"
	@echo "  frlt-5k       - Full reserved - 5000 seats (staging)"
	@echo "  frlt-50k          - Full reserved - 50000 seats (production)"
	@echo ""
	@echo ""
	@echo "$(COLOR_CYAN)🐳 DOCKER$(COLOR_RESET)"
	@echo "  docker-build       - Build Docker image"
	@echo "  docker-run         - Run load test in Docker (ARGS='-env dev -event 1')"
	@echo "  docker-test        - Quick Docker test (10 workers)"
	@echo ""
	@echo "$(COLOR_CYAN)📊 K6 LOAD TESTS$(COLOR_RESET)"
	@echo "  k6-load            - k6 load test (peak 250 RPS, 60s)"
	@echo "  k6-stress          - k6 stress test (peak 500 RPS, 70s)"
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
	@echo "  make frlt-2k                        # Full reserved test (2000 seats)"
	@echo "  make frlt-5k                   # Full reserved test (5000 seats)"
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
