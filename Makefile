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
        deploy deploy-check deploy-app deploy-nginx deploy-ssl \
        destroy destroy-check destroy-app destroy-force

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
	@echo "$(GREEN)Checking secrets...$(NC)"
	@if [ -z "$$STORMCLOUD_POSTGRES_PASSWORD" ]; then \
		echo "$(YELLOW)⚠️  STORMCLOUD_POSTGRES_PASSWORD not set$(NC)"; \
		echo "   You will be prompted during deployment."; \
		echo ""; \
		echo "$(CYAN)Tip: Set secrets beforehand for non-interactive deployment:$(NC)"; \
		echo "  export STORMCLOUD_POSTGRES_PASSWORD=\"your-password\""; \
		echo "  export STORMCLOUD_SECRET_KEY=\"your-key\"  # Optional (auto-generates)"; \
		echo ""; \
		echo "Generate secure password: $(GREEN)openssl rand -base64 32$(NC)"; \
		echo ""; \
		echo "See: deploy/README.md#secrets"; \
		echo ""; \
	else \
		echo "$(GREEN)✓ STORMCLOUD_POSTGRES_PASSWORD is set$(NC)"; \
	fi
	@echo "$(GREEN)Checking Ansible Galaxy requirements...$(NC)"
	@if ! deploy/ansible/check-galaxy-deps.sh 2>/dev/null; then \
		echo "$(GREEN)Installing Ansible Galaxy requirements...$(NC)"; \
		cd deploy/ansible && ansible-galaxy install -r requirements.yml --force && \
		touch ~/.ansible/.stormcloud_galaxy_timestamp; \
	fi
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
	@echo "$(GREEN)Checking Ansible Galaxy requirements...$(NC)"
	@if ! deploy/ansible/check-galaxy-deps.sh 2>/dev/null; then \
		echo "$(GREEN)Installing Ansible Galaxy requirements...$(NC)"; \
		cd deploy/ansible && ansible-galaxy install -r requirements.yml --force && \
		touch ~/.ansible/.stormcloud_galaxy_timestamp; \
	fi
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
	@cd deploy/ansible && ansible-playbook playbook.yml \
		-i inventory.yml \
		--extra-vars "@../config.yml" \
		--tags ssl -K

# =============================================================================
# DESTRUCTION 💀
# =============================================================================

destroy: ## 💀 DESTROY entire deployment (INTERACTIVE - requires confirmations)
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@echo "$(CYAN)  💀 STORM CLOUD SERVER - DESTRUCTION SEQUENCE 💀$(NC)"
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(YELLOW)⚠️  WARNING: This will PERMANENTLY DELETE:$(NC)"
	@echo "  - All Docker containers, images, volumes"
	@echo "  - Application directory and ALL uploaded files"
	@echo "  - Database data"
	@echo "  - nginx configuration"
	@echo "  - SSL certificates"
	@echo "  - User account ($(shell grep app_user $(CONFIG_FILE) 2>/dev/null | cut -d: -f2 | tr -d ' ' || echo stormcloud))"
	@echo "  - Docker, nginx, and certbot packages"
	@echo ""
	@if [ ! -f "$(CONFIG_FILE)" ]; then \
		echo "$(YELLOW)ERROR: $(CONFIG_FILE) not found$(NC)"; \
		echo ""; \
		echo "Cannot determine target server."; \
		exit 1; \
	fi
	@echo "$(GREEN)Checking Ansible Galaxy requirements...$(NC)"
	@if ! deploy/ansible/check-galaxy-deps.sh 2>/dev/null; then \
		echo "$(GREEN)Installing Ansible Galaxy requirements...$(NC)"; \
		cd deploy/ansible && ansible-galaxy install -r requirements.yml --force && \
		touch ~/.ansible/.stormcloud_galaxy_timestamp; \
	fi
	@echo ""
	@echo "$(YELLOW)You will be prompted to confirm destruction...$(NC)"
	@echo ""
	@cd deploy/ansible && ansible-playbook destroy.yml \
		-i inventory.yml \
		--extra-vars "@../config.yml" \
		--extra-vars "destruction_mode=full" \
		-K

destroy-check: ## 💀 Dry-run destruction (show what would be deleted)
	@echo "$(CYAN)Destruction dry-run (no changes will be made)$(NC)"
	@echo ""
	@if [ ! -f "$(CONFIG_FILE)" ]; then \
		echo "$(YELLOW)ERROR: $(CONFIG_FILE) not found$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Checking what would be destroyed...$(NC)"
	@echo ""
	@cd deploy/ansible && ansible-playbook destroy.yml \
		-i inventory.yml \
		--extra-vars "@../config.yml" \
		--extra-vars "destruction_mode=full" \
		--extra-vars "force_destroy=true" \
		--check --diff -K

destroy-app: ## 💀 DESTROY application only (keep system packages)
	@echo "$(CYAN)Application-only destruction$(NC)"
	@echo ""
	@if [ ! -f "$(CONFIG_FILE)" ]; then \
		echo "$(YELLOW)ERROR: $(CONFIG_FILE) not found$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)This will remove Docker containers and app files but keep packages installed.$(NC)"
	@echo ""
	@cd deploy/ansible && ansible-playbook destroy.yml \
		-i inventory.yml \
		--extra-vars "@../config.yml" \
		--extra-vars "destruction_mode=app_only" \
		-K

destroy-force: ## 💀💀💀 SCORCHED EARTH - Skip confirmations (USE WITH EXTREME CAUTION)
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@echo "$(CYAN)  ☢️  FORCED DESTRUCTION - NO CONFIRMATIONS ☢️$(NC)"
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(YELLOW)⚠️  Destruction will proceed WITHOUT confirmations!$(NC)"
	@echo "$(YELLOW)⚠️  Press Ctrl+C within 5 seconds to abort...$(NC)"
	@sleep 5
	@if [ ! -f "$(CONFIG_FILE)" ]; then \
		echo "$(YELLOW)ERROR: $(CONFIG_FILE) not found$(NC)"; \
		exit 1; \
	fi
	@cd deploy/ansible && ansible-playbook destroy.yml \
		-i inventory.yml \
		--extra-vars "@../config.yml" \
		--extra-vars "destruction_mode=scorched_earth" \
		--extra-vars "force_destroy=true" \
		-K
