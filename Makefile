# =============================================================================
# Storm Cloud Server - Makefile
# =============================================================================
#
# Usage:
#   make help         Show all commands
#   make setup        First-time local setup
#   make up           Start local containers
#   make deploy       Deploy to production server
#
# =============================================================================

.PHONY: help setup build up down restart logs shell superuser api_key migrate backup clean \
        deploy deploy-check deploy-app deploy-nginx deploy-ssl

# Colors
GREEN := \033[0;32m
YELLOW := \033[1;33m
CYAN := \033[0;36m
NC := \033[0m

# Docker compose detection
DOCKER_COMPOSE := $(shell if command -v docker-compose >/dev/null 2>&1; then echo "docker-compose"; else echo "docker compose"; fi)

# Default config file for deployment
CONFIG_FILE ?= deploy/config.yml

.DEFAULT_GOAL := help

# =============================================================================
# HELP
# =============================================================================

help: ## Show this help message
	@echo ""
	@echo "$(CYAN)Storm Cloud Server$(NC)"
	@echo ""
	@echo "$(GREEN)Local Development:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(setup|build|up|down|restart|logs|shell|superuser|api_key|migrate|backup|clean)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Production Deployment:$(NC)"
	@grep -E '^deploy[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# LOCAL DEVELOPMENT
# =============================================================================

setup: ## First-time local setup (creates .env, generates secrets)
	@./scripts/setup.sh

build: ## Build Docker images
	@echo "$(GREEN)Building images...$(NC)"
	@$(DOCKER_COMPOSE) build

up: ## Start local containers
	@echo "$(GREEN)Starting services...$(NC)"
	@$(DOCKER_COMPOSE) down 2>/dev/null || true
	@$(DOCKER_COMPOSE) up -d --remove-orphans
	@sleep 5
	@$(DOCKER_COMPOSE) ps

down: ## Stop containers
	@$(DOCKER_COMPOSE) down

restart: ## Restart containers
	@$(DOCKER_COMPOSE) restart

logs: ## View logs (interactive)
	@echo "$(GREEN)Log Options:$(NC)"
	@echo "  [1] All services (snapshot)"
	@echo "  [2] Web only (snapshot)"
	@echo "  [f] Follow all (live)"
	@echo ""
	@read -p "Select: " choice; \
	case $$choice in \
		1) $(DOCKER_COMPOSE) logs --tail=100 ;; \
		2) $(DOCKER_COMPOSE) logs --tail=100 web ;; \
		f|F) $(DOCKER_COMPOSE) logs -f ;; \
		*) echo "Invalid choice" ;; \
	esac

shell: ## Open shell in web container
	@$(DOCKER_COMPOSE) exec web bash

superuser: ## Create admin superuser
	@$(DOCKER_COMPOSE) exec web python manage.py createsuperuser
	@echo ""
	@echo "$(GREEN)Next: Generate API key with 'make api_key'$(NC)"

api_key: ## Generate API key for a user
	@echo "Enter username to generate API key for:"
	@read -p "Username: " username; \
	$(DOCKER_COMPOSE) exec web python manage.py generate_api_key $$username

migrate: ## Run database migrations
	@$(DOCKER_COMPOSE) exec web python manage.py migrate

backup: ## Backup database and uploads
	@./scripts/backup.sh

clean: ## Remove all containers, volumes, and images (destructive!)
	@echo "$(YELLOW)WARNING: This will delete all data!$(NC)"
	@read -p "Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		$(DOCKER_COMPOSE) down -v --rmi all; \
		echo "$(GREEN)Cleaned.$(NC)"; \
	else \
		echo "Cancelled."; \
	fi

# =============================================================================
# PRODUCTION DEPLOYMENT
# =============================================================================

deploy: ## Deploy to production server (full deployment)
	@echo "$(CYAN)═══════════════════════════════════════════════════$(NC)"
	@echo "$(CYAN)  Storm Cloud Server - Production Deployment$(NC)"
	@echo "$(CYAN)═══════════════════════════════════════════════════$(NC)"
	@echo ""
	@if [ ! -f "$(CONFIG_FILE)" ]; then \
		echo "$(YELLOW)ERROR: $(CONFIG_FILE) not found$(NC)"; \
		echo ""; \
		echo "Create it with:"; \
		echo "  cp deploy/config.example.yml deploy/config.yml"; \
		echo "  nano deploy/config.yml"; \
		echo ""; \
		exit 1; \
	fi
	@echo "$(GREEN)Validating configuration...$(NC)"
	@VALIDATION_FAILED=0; \
	server_ip=$$(grep -E "^server_ip:" "$(CONFIG_FILE)" | sed -E 's/^server_ip:[[:space:]]*["'\'']?([^"'\''#]*)["'\'']?.*$$/\1/' | sed 's/^[[:space:]]*//;s/[[:space:]]*$$//'); \
	domain=$$(grep -E "^domain:" "$(CONFIG_FILE)" | sed -E 's/^domain:[[:space:]]*["'\'']?([^"'\''#]*)["'\'']?.*$$/\1/' | sed 's/^[[:space:]]*//;s/[[:space:]]*$$//'); \
	admin_email=$$(grep -E "^admin_email:" "$(CONFIG_FILE)" | sed -E 's/^admin_email:[[:space:]]*["'\'']?([^"'\''#]*)["'\'']?.*$$/\1/' | sed 's/^[[:space:]]*//;s/[[:space:]]*$$//'); \
	postgres_password=$$(grep -E "^postgres_password:" "$(CONFIG_FILE)" | sed -E 's/^postgres_password:[[:space:]]*["'\'']?([^"'\''#]*)["'\'']?.*$$/\1/' | sed 's/^[[:space:]]*//;s/[[:space:]]*$$//'); \
	if [ -z "$$server_ip" ] || [ "$$server_ip" = "" ]; then \
		echo "$(YELLOW)✗ server_ip is missing or empty$(NC)"; \
		VALIDATION_FAILED=1; \
	fi; \
	if [ -z "$$domain" ] || [ "$$domain" = "" ]; then \
		echo "$(YELLOW)✗ domain is missing or empty$(NC)"; \
		VALIDATION_FAILED=1; \
	fi; \
	if [ -z "$$admin_email" ] || [ "$$admin_email" = "" ]; then \
		echo "$(YELLOW)✗ admin_email is missing or empty$(NC)"; \
		VALIDATION_FAILED=1; \
	fi; \
	if [ -z "$$postgres_password" ] || [ "$$postgres_password" = "" ]; then \
		echo "$(YELLOW)✗ postgres_password is missing or empty$(NC)"; \
		VALIDATION_FAILED=1; \
	fi; \
	if [ $$VALIDATION_FAILED -eq 1 ]; then \
		echo ""; \
		echo "$(YELLOW)═══════════════════════════════════════════════════$(NC)"; \
		echo "$(YELLOW)  Missing required configuration$(NC)"; \
		echo "$(YELLOW)═══════════════════════════════════════════════════$(NC)"; \
		echo ""; \
		echo "Edit $(CONFIG_FILE) and set:"; \
		echo ""; \
		if [ -z "$$server_ip" ] || [ "$$server_ip" = "" ]; then \
			echo "  $(YELLOW)server_ip:$(NC)       \"your-vps-ip-address\""; \
		fi; \
		if [ -z "$$domain" ] || [ "$$domain" = "" ]; then \
			echo "  $(YELLOW)domain:$(NC)          \"your-domain.com\""; \
		fi; \
		if [ -z "$$admin_email" ] || [ "$$admin_email" = "" ]; then \
			echo "  $(YELLOW)admin_email:$(NC)      \"you@example.com\""; \
		fi; \
		if [ -z "$$postgres_password" ] || [ "$$postgres_password" = "" ]; then \
			echo "  $(YELLOW)postgres_password:$(NC) \"your-secure-password\""; \
		fi; \
		echo ""; \
		exit 1; \
	fi; \
	echo "$(GREEN)✓ Configuration valid$(NC)"
	@if ! command -v ansible-galaxy >/dev/null 2>&1; then \
		echo "$(YELLOW)ERROR: ansible-galaxy not found$(NC)"; \
		echo ""; \
		echo "Ansible is required for deployment. Install it with:"; \
		echo ""; \
		if [ -d "venv" ]; then \
			echo "  $(GREEN)Option 1: Install in virtual environment (recommended)$(NC)"; \
			echo "    source venv/bin/activate"; \
			echo "    pip install ansible"; \
			echo ""; \
		fi; \
		echo "  $(GREEN)Option 2: Install globally$(NC)"; \
		echo "    pip install ansible"; \
		echo ""; \
		echo "  $(GREEN)Option 3: Install via system package manager$(NC)"; \
		echo "    # Ubuntu/Debian:"; \
		echo "    sudo apt-get install ansible"; \
		echo ""; \
		echo "    # macOS:"; \
		echo "    brew install ansible"; \
		echo ""; \
		echo "After installing, run 'make deploy' again."; \
		echo ""; \
		exit 1; \
	fi
	@echo "$(GREEN)Installing Ansible Galaxy requirements...$(NC)"
	@cd deploy/ansible && ansible-galaxy install -r requirements.yml --force
	@echo ""
	@echo "$(GREEN)Running deployment playbook...$(NC)"
	@cd deploy/ansible && ansible-playbook playbook.yml \
		-i inventory.yml \
		--extra-vars "@../config.yml" \
		-K \
		$(if $(EXTRA_VARS),--extra-vars "$(EXTRA_VARS)",)

deploy-check: ## Dry-run deployment (shows what would change)
	@echo "$(CYAN)Dry-run deployment (no changes will be made)$(NC)"
	@echo ""
	@if [ ! -f "$(CONFIG_FILE)" ]; then \
		echo "$(YELLOW)ERROR: $(CONFIG_FILE) not found$(NC)"; \
		exit 1; \
	fi
	@if ! command -v ansible-galaxy >/dev/null 2>&1; then \
		echo "$(YELLOW)ERROR: ansible-galaxy not found$(NC)"; \
		echo ""; \
		echo "Install Ansible: pip install ansible"; \
		echo "Or activate venv: source venv/bin/activate && pip install ansible"; \
		exit 1; \
	fi
	@cd deploy/ansible && ansible-galaxy install -r requirements.yml --force
	@cd deploy/ansible && ansible-playbook playbook.yml \
		-i inventory.yml \
		--extra-vars "@../config.yml" \
		--check --diff -K

deploy-app: ## Update application only (skip system setup)
	@echo "$(GREEN)Deploying application updates...$(NC)"
	@if [ ! -f "$(CONFIG_FILE)" ]; then \
		echo "$(YELLOW)ERROR: $(CONFIG_FILE) not found$(NC)"; \
		exit 1; \
	fi
	@if ! command -v ansible-playbook >/dev/null 2>&1; then \
		echo "$(YELLOW)ERROR: ansible-playbook not found$(NC)"; \
		echo ""; \
		echo "Install Ansible: pip install ansible"; \
		echo "Or activate venv: source venv/bin/activate && pip install ansible"; \
		exit 1; \
	fi
	@cd deploy/ansible && ansible-playbook playbook.yml \
		-i inventory.yml \
		--extra-vars "@../config.yml" \
		--tags app,docker -K

deploy-nginx: ## Update nginx configuration only
	@echo "$(GREEN)Updating nginx configuration...$(NC)"
	@if [ ! -f "$(CONFIG_FILE)" ]; then \
		echo "$(YELLOW)ERROR: $(CONFIG_FILE) not found$(NC)"; \
		exit 1; \
	fi
	@if ! command -v ansible-playbook >/dev/null 2>&1; then \
		echo "$(YELLOW)ERROR: ansible-playbook not found$(NC)"; \
		echo ""; \
		echo "Install Ansible: pip install ansible"; \
		echo "Or activate venv: source venv/bin/activate && pip install ansible"; \
		exit 1; \
	fi
	@cd deploy/ansible && ansible-playbook playbook.yml \
		-i inventory.yml \
		--extra-vars "@../config.yml" \
		--tags nginx -K

deploy-ssl: ## Renew/update SSL certificates
	@echo "$(GREEN)Updating SSL certificates...$(NC)"
	@if [ ! -f "$(CONFIG_FILE)" ]; then \
		echo "$(YELLOW)ERROR: $(CONFIG_FILE) not found$(NC)"; \
		exit 1; \
	fi
	@if ! command -v ansible-playbook >/dev/null 2>&1; then \
		echo "$(YELLOW)ERROR: ansible-playbook not found$(NC)"; \
		echo ""; \
		echo "Install Ansible: pip install ansible"; \
		echo "Or activate venv: source venv/bin/activate && pip install ansible"; \
		exit 1; \
	fi
	@cd deploy/ansible && ansible-playbook playbook.yml \
		-i inventory.yml \
		--extra-vars "@../config.yml" \
		--tags ssl -K