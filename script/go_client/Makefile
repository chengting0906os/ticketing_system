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
SPIKE_TEST_BIN = full_reserved_spike_test

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
build: build-spike-test  ## 🔨 Build all binaries

build-all: build

build-spike-test:  ## 🔨 Build spike test binary
	@if [ -x "./$(SPIKE_TEST_BIN)" ]; then \
		echo "$(COLOR_GREEN)✅ $(SPIKE_TEST_BIN) exists$(COLOR_RESET)"; \
	else \
		echo "$(COLOR_CYAN)🔨 Building spike test...$(COLOR_RESET)"; \
		go build -tags full_reserved -o $(SPIKE_TEST_BIN); \
		echo "$(COLOR_GREEN)✅ Built: $(SPIKE_TEST_BIN)$(COLOR_RESET)"; \
	fi

clean:  ## 🧹 Remove all binaries
	@echo "$(COLOR_YELLOW)🧹 Cleaning binaries...$(COLOR_RESET)"
	@rm -f $(SPIKE_TEST_BIN)
	@echo "$(COLOR_GREEN)✅ Cleaned!$(COLOR_RESET)"

# ==============================================================================
# 🚀 FULL RESERVED SPIKE TEST (Sellout Testing)
# ==============================================================================
# Environments: 500, 1k, 2k, 3k, 5k, 50k, 200k, 400k

.PHONY: frst frst-500 frst-1k frst-2k frst-3k frst-5k frst-10k frst-50k frst-200k frst-400k frst-1m

frst: build-spike-test  ## 🚀 Full Reserved Spike Test (SEATS=500 WORKERS=100)
	@WORKERS=$${WORKERS:-100}; \
	SEATS=$${SEATS:-500}; \
	echo "$(COLOR_BLUE)🚀 Running FULL reserved spike test (Seats: $$SEATS, Workers: $$WORKERS)...$(COLOR_RESET)"; \
	./$(SPIKE_TEST_BIN) -env $$SEATS -event 1 -workers $$WORKERS -host $(API_HOST)

frst-500: build-spike-test  ## 🚀 500 seats
	@./$(SPIKE_TEST_BIN) -env 500 -event 1 -workers $${WORKERS:-100} -host $(API_HOST)

frst-1k: build-spike-test  ## 🚀 1,000 seats
	@./$(SPIKE_TEST_BIN) -env 1k -event 1 -workers $${WORKERS:-100} -host $(API_HOST)

frst-2k: build-spike-test  ## 🚀 2,000 seats
	@./$(SPIKE_TEST_BIN) -env 2k -event 1 -workers $${WORKERS:-100} -host $(API_HOST)

frst-3k: build-spike-test  ## 🚀 3,000 seats
	@./$(SPIKE_TEST_BIN) -env 3k -event 1 -workers $${WORKERS:-100} -host $(API_HOST)

frst-5k: build-spike-test  ## 🚀 5,000 seats
	@./$(SPIKE_TEST_BIN) -env 5k -event 1 -workers $${WORKERS:-100} -host $(API_HOST)

frst-10k: build-spike-test  ## 🚀 10,000 seats
	@./$(SPIKE_TEST_BIN) -env 10k -event 1 -workers $${WORKERS:-100} -host $(API_HOST)


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
	@echo "$(COLOR_CYAN)🚀 FULL RESERVED SPIKE TEST (Sellout)$(COLOR_RESET)"
	@echo "  frst               Auto-detect env (WORKERS=100)"
	@echo "  frst-500           500 seats"
	@echo "  frst-1k            1,000 seats"
	@echo "  frst-2k            2,000 seats"
	@echo "  frst-3k            3,000 seats"
	@echo "  frst-5k            5,000 seats"
	@echo "  frst-10k           10,000 seats"
	@echo "  frst-50k           50,000 seats"
	@echo "  frst-200k          200,000 seats"
	@echo "  frst-400k          400,000 seats"
	@echo "  frst-1m            1,000,000 seats"
	@echo ""
	@echo "$(COLOR_YELLOW)💡 EXAMPLES$(COLOR_RESET)"
	@echo "  make frst-5k                        # 5K sellout test"
	@echo "  WORKERS=200 make frst-50k           # 50K with 200 workers"
	@echo "  API_HOST=http://alb.aws.com make frst-5k"
	@echo ""
	@echo "$(COLOR_YELLOW)🔧 Current: API_HOST=$(API_HOST) SEATS=$(SEATS)$(COLOR_RESET)"

.DEFAULT_GOAL := help
