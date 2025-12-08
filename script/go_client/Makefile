# Ticketing System - Go Load Testing Makefile
# Run from: script/go_client/
# Usage: make <target>

# ==============================================================================
# 📋 CONFIGURATION
# ==============================================================================

# Load .env file from project root if it exists
ifneq (,$(wildcard ../../.env))
  include ../../.env
  export $(shell sed 's/=.*//' ../../.env 2>/dev/null)
endif

# Defaults (can be overridden by .env or command line)
API_HOST ?= http://localhost:8100
SEATS ?= 500

# Binary names
CONCURRENT_BIN = concurrent_loadtest
FULL_RESERVED_BIN = full_reserved_loadtest

# Colors
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
build: build-concurrent build-full-reserved  ## 🔨 Build all binaries

build-all: build

build-concurrent:  ## 🔨 Build concurrent load test binary
	@if [ -x "./$(CONCURRENT_BIN)" ]; then \
		echo "$(COLOR_GREEN)✅ $(CONCURRENT_BIN) exists$(COLOR_RESET)"; \
	else \
		echo "$(COLOR_CYAN)🔨 Building concurrent load test...$(COLOR_RESET)"; \
		go build -tags concurrent -o $(CONCURRENT_BIN); \
		echo "$(COLOR_GREEN)✅ Built: $(CONCURRENT_BIN)$(COLOR_RESET)"; \
	fi

build-full-reserved:  ## 🔨 Build full reserved load test binary
	@if [ -x "./$(FULL_RESERVED_BIN)" ]; then \
		echo "$(COLOR_GREEN)✅ $(FULL_RESERVED_BIN) exists$(COLOR_RESET)"; \
	else \
		echo "$(COLOR_CYAN)🔨 Building full reserved load test...$(COLOR_RESET)"; \
		go build -tags full_reserved -o $(FULL_RESERVED_BIN); \
		echo "$(COLOR_GREEN)✅ Built: $(FULL_RESERVED_BIN)$(COLOR_RESET)"; \
	fi

clean:  ## 🧹 Remove all binaries
	@echo "$(COLOR_YELLOW)🧹 Cleaning binaries...$(COLOR_RESET)"
	@rm -f $(CONCURRENT_BIN) $(FULL_RESERVED_BIN)
	@echo "$(COLOR_GREEN)✅ Cleaned!$(COLOR_RESET)"

# ==============================================================================
# ⚡ CONCURRENT LOAD TEST (Pressure Testing)
# ==============================================================================

.PHONY: clt-tiny clt-small clt-medium clt-large clt-full clt-t clt-s clt-m clt-l clt-f
clt-tiny: build-concurrent  ## 🧪 Tiny (10 req, 5 concurrency)
	@./$(CONCURRENT_BIN) -requests 10 -concurrency 5 -clients 5 -host $(API_HOST)

clt-small: build-concurrent  ## 🧪 Small (100 req, 10 concurrency)
	@./$(CONCURRENT_BIN) -requests 100 -concurrency 10 -clients 10 -host $(API_HOST)

clt-medium: build-concurrent  ## ⚡ Medium (500 req, 25 concurrency)
	@./$(CONCURRENT_BIN) -requests 500 -concurrency 25 -clients 25 -host $(API_HOST)

clt-large: build-concurrent  ## ⚡ Large (15K req, 50 concurrency)
	@./$(CONCURRENT_BIN) -requests 15000 -concurrency 50 -clients 50 -host $(API_HOST)

clt-full: build-concurrent  ## 💪 Full (150K req, 100 concurrency)
	@./$(CONCURRENT_BIN) -requests 150000 -concurrency 100 -clients 100 -host $(API_HOST)

# Aliases
clt-t: clt-tiny
clt-s: clt-small
clt-m: clt-medium
clt-l: clt-large
clt-f: clt-full

# ==============================================================================
# 🚀 FULL RESERVED LOAD TEST (Sellout Testing)
# ==============================================================================
# Environments: 500, 1k, 2k, 3k, 5k, 50k, 200k

.PHONY: frlt frlt-500 frlt-1k frlt-2k frlt-3k frlt-5k frlt-50k frlt-200k

frlt: build-full-reserved  ## 🚀 Full Reserved Load Test (SEATS=500 WORKERS=100 BATCH=1)
	@WORKERS=$${WORKERS:-100}; \
	BATCH=$${BATCH:-1}; \
	SEATS=$${SEATS:-500}; \
	echo "$(COLOR_BLUE)🚀 Running FULL reserved load test (Seats: $$SEATS, Workers: $$WORKERS, Batch: $$BATCH)...$(COLOR_RESET)"; \
	./$(FULL_RESERVED_BIN) -env $$SEATS -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST)

frlt-500: build-full-reserved  ## 🚀 500 seats
	@./$(FULL_RESERVED_BIN) -env 500 -event 1 -workers $${WORKERS:-100} -batch $${BATCH:-1} -host $(API_HOST)

frlt-1k: build-full-reserved  ## 🚀 1,000 seats
	@./$(FULL_RESERVED_BIN) -env 1k -event 1 -workers $${WORKERS:-100} -batch $${BATCH:-1} -host $(API_HOST)

frlt-2k: build-full-reserved  ## 🚀 2,000 seats
	@./$(FULL_RESERVED_BIN) -env 2k -event 1 -workers $${WORKERS:-100} -batch $${BATCH:-1} -host $(API_HOST)

frlt-3k: build-full-reserved  ## 🚀 3,000 seats
	@./$(FULL_RESERVED_BIN) -env 3k -event 1 -workers $${WORKERS:-100} -batch $${BATCH:-1} -host $(API_HOST)

frlt-5k: build-full-reserved  ## 🚀 5,000 seats
	@./$(FULL_RESERVED_BIN) -env 5k -event 1 -workers $${WORKERS:-100} -batch $${BATCH:-1} -host $(API_HOST)

frlt-50k: build-full-reserved  ## 🚀 50,000 seats
	@./$(FULL_RESERVED_BIN) -env 50k -event 1 -workers $${WORKERS:-100} -batch $${BATCH:-1} -host $(API_HOST)

frlt-200k: build-full-reserved  ## 🚀 200,000 seats
	@./$(FULL_RESERVED_BIN) -env 200k -event 1 -workers $${WORKERS:-100} -batch $${BATCH:-1} -host $(API_HOST)

# ==============================================================================
# 📊 UTILITIES
# ==============================================================================

.PHONY: check-env version
check-env:  ## 🔍 Check current environment settings
	@echo "$(COLOR_CYAN)📋 Configuration:$(COLOR_RESET)"
	@echo "  API_HOST: $(API_HOST)"
	@echo "  SEATS:    $(SEATS)"

version:  ## 📌 Show Go version
	@go version

# ==============================================================================
# 📖 HELP
# ==============================================================================

.PHONY: help
help:  ## 📖 Show this help
	@echo "$(COLOR_BOLD)╔═══════════════════════════════════════════════════════════════╗$(COLOR_RESET)"
	@echo "$(COLOR_BOLD)║         🚀 Go Load Testing - Makefile Commands               ║$(COLOR_RESET)"
	@echo "$(COLOR_BOLD)╚═══════════════════════════════════════════════════════════════╝$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_CYAN)🔨 BUILD$(COLOR_RESET)"
	@echo "  build              Build all binaries"
	@echo "  clean              Remove all binaries"
	@echo ""
	@echo "$(COLOR_CYAN)⚡ CONCURRENT LOAD TEST$(COLOR_RESET)"
	@echo "  clt-t / clt-tiny   Tiny    (10 req)"
	@echo "  clt-s / clt-small  Small   (100 req)"
	@echo "  clt-m / clt-medium Medium  (500 req)"
	@echo "  clt-l / clt-large  Large   (15K req)"
	@echo "  clt-f / clt-full   Full    (150K req)"
	@echo ""
	@echo "$(COLOR_CYAN)🚀 FULL RESERVED LOAD TEST (Sellout)$(COLOR_RESET)"
	@echo "  frlt               Auto-detect env (WORKERS=100 BATCH=1)"
	@echo "  frlt-500           500 seats"
	@echo "  frlt-1k            1,000 seats"
	@echo "  frlt-2k            2,000 seats"
	@echo "  frlt-3k            3,000 seats"
	@echo "  frlt-5k            5,000 seats"
	@echo "  frlt-50k           50,000 seats"
	@echo "  frlt-200k          200,000 seats"
	@echo ""
	@echo "$(COLOR_YELLOW)💡 EXAMPLES$(COLOR_RESET)"
	@echo "  make frlt-5k                        # 5K sellout test"
	@echo "  WORKERS=200 make frlt-50k           # 50K with 200 workers"
	@echo "  API_HOST=http://alb.aws.com make frlt-5k"
	@echo ""
	@echo "$(COLOR_YELLOW)🔧 Current: API_HOST=$(API_HOST) SEATS=$(SEATS)$(COLOR_RESET)"

.DEFAULT_GOAL := help
