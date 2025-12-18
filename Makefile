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
        deploy deploy-check deploy-app deploy-nginx deploy-ssl gotosocial-user gotosocial-token

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
# GOTOSOCIAL
# =============================================================================

GOTOSOCIAL_CONTAINER := stormcloud_gotosocial

gotosocial-user: ## Create a GoToSocial user account (optional - deployment creates automatically)
	@echo "$(CYAN)═══════════════════════════════════════════════════$(NC)"
	@echo "$(CYAN)  GoToSocial - Create User Account$(NC)"
	@echo "$(CYAN)═══════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(YELLOW)NOTE: make deploy now creates accounts automatically$(NC)"
	@echo "$(YELLOW)This command is for manual account creation only$(NC)"
	@echo ""
	@# Check if container is running
	@if ! docker ps --format '{{.Names}}' | grep -q "^$(GOTOSOCIAL_CONTAINER)$$"; then \
		echo "$(YELLOW)ERROR: GoToSocial container is not running$(NC)"; \
		echo ""; \
		echo "Make sure GoToSocial is enabled and deployed:"; \
		echo "  1. Set install_gotosocial: true in deploy/config.yml"; \
		echo "  2. Run: make deploy"; \
		echo ""; \
		exit 1; \
	fi
	@# Prompt for username
	@read -p "Username: " username; \
	if [ -z "$$username" ]; then \
		echo "$(YELLOW)ERROR: Username is required$(NC)"; \
		exit 1; \
	fi; \
	\
	read -p "Email: " email; \
	if [ -z "$$email" ]; then \
		echo "$(YELLOW)ERROR: Email is required$(NC)"; \
		exit 1; \
	fi; \
	\
	stty -echo; \
	read -p "Password (minimum 16 characters): " password; \
	stty echo; \
	echo ""; \
	if [ -z "$$password" ]; then \
		echo "$(YELLOW)ERROR: Password is required$(NC)"; \
		exit 1; \
	fi; \
	if [ $${#password} -lt 16 ]; then \
		echo "$(YELLOW)ERROR: Password must be at least 16 characters$(NC)"; \
		exit 1; \
	fi; \
	\
	echo ""; \
	echo "$(GREEN)Creating account...$(NC)"; \
	if ! docker exec -it $(GOTOSOCIAL_CONTAINER) \
		/gotosocial/gotosocial admin account create \
		--username "$$username" \
		--email "$$email" \
		--password "$$password"; then \
		echo "$(YELLOW)ERROR: Failed to create account$(NC)"; \
		exit 1; \
	fi; \
	\
	echo ""; \
	echo "$(GREEN)Confirming account...$(NC)"; \
	if ! docker exec -it $(GOTOSOCIAL_CONTAINER) \
		/gotosocial/gotosocial admin account confirm \
		--username "$$username"; then \
		echo "$(YELLOW)ERROR: Failed to confirm account$(NC)"; \
		exit 1; \
	fi; \
	\
	echo ""; \
	echo "$(GREEN)Promoting to admin...$(NC)"; \
	if ! docker exec -it $(GOTOSOCIAL_CONTAINER) \
		/gotosocial/gotosocial admin account promote \
		--username "$$username"; then \
		echo "$(YELLOW)ERROR: Failed to promote account$(NC)"; \
		exit 1; \
	fi; \
	\
	echo ""; \
	echo "$(GREEN)Restarting GoToSocial for admin changes to take effect...$(NC)"; \
	docker restart $(GOTOSOCIAL_CONTAINER); \
	\
	echo ""; \
	echo "$(CYAN)═══════════════════════════════════════════════════$(NC)"; \
	echo "$(GREEN)Account created successfully!$(NC)"; \
	echo "$(CYAN)═══════════════════════════════════════════════════$(NC)"; \
	echo ""; \
	echo "You can now log in at your GoToSocial instance."

gotosocial-token: ## Generate GoToSocial API token for Django integration
	@echo "$(CYAN)═══════════════════════════════════════════════════$(NC)"
	@echo "$(CYAN)  GoToSocial - Generate API Token$(NC)"
	@echo "$(CYAN)═══════════════════════════════════════════════════$(NC)"
	@echo ""
	@read -p "GoToSocial domain (e.g., social.example.com): " domain; \
	if [ -z "$$domain" ]; then \
		echo "$(YELLOW)ERROR: Domain is required$(NC)"; \
		exit 1; \
	fi; \
	\
	echo ""; \
	echo "$(GREEN)Step 1: Creating application...$(NC)"; \
	response=$$(curl -s -X POST "https://$$domain/api/v1/apps" \
		-H "Content-Type: application/json" \
		-d '{"client_name":"stormcloud","redirect_uris":"urn:ietf:wg:oauth:2.0:oob","scopes":"read write"}'); \
	\
	client_id=$$(echo "$$response" | grep -o '"client_id":"[^"]*"' | cut -d'"' -f4); \
	client_secret=$$(echo "$$response" | grep -o '"client_secret":"[^"]*"' | cut -d'"' -f4); \
	\
	if [ -z "$$client_id" ] || [ -z "$$client_secret" ]; then \
		echo "$(YELLOW)ERROR: Failed to create application$(NC)"; \
		echo "Response: $$response"; \
		exit 1; \
	fi; \
	echo "done"; \
	\
	echo ""; \
	echo "$(GREEN)Step 2: Open this URL in your browser:$(NC)"; \
	echo ""; \
	echo "  https://$$domain/oauth/authorize?client_id=$$client_id&redirect_uri=urn:ietf:wg:oauth:2.0:oob&response_type=code&scope=read+write"; \
	echo ""; \
	echo "  1. Log in with your GoToSocial account"; \
	echo "  2. Click \"Allow\""; \
	echo "  3. Copy the code shown"; \
	echo ""; \
	read -p "Paste authorization code: " auth_code; \
	if [ -z "$$auth_code" ]; then \
		echo "$(YELLOW)ERROR: Authorization code is required$(NC)"; \
		exit 1; \
	fi; \
	\
	echo ""; \
	echo "$(GREEN)Step 3: Exchanging for token...$(NC)"; \
	token_response=$$(curl -s -X POST "https://$$domain/oauth/token" \
		-H "Content-Type: application/json" \
		-d "{\"redirect_uri\":\"urn:ietf:wg:oauth:2.0:oob\",\"client_id\":\"$$client_id\",\"client_secret\":\"$$client_secret\",\"grant_type\":\"authorization_code\",\"code\":\"$$auth_code\"}"); \
	\
	access_token=$$(echo "$$token_response" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4); \
	\
	if [ -z "$$access_token" ]; then \
		echo "$(YELLOW)ERROR: Failed to get access token$(NC)"; \
		echo "Response: $$token_response"; \
		exit 1; \
	fi; \
	echo "done"; \
	\
	echo ""; \
	echo "$(CYAN)═══════════════════════════════════════════════════$(NC)"; \
	echo "$(GREEN)  Success! Add these to your .env file:$(NC)"; \
	echo "$(CYAN)═══════════════════════════════════════════════════$(NC)"; \
	echo ""; \
	echo "  GOTOSOCIAL_DOMAIN=$$domain"; \
	echo "  GOTOSOCIAL_TOKEN=$$access_token"; \
	echo ""; \
	echo "  Then restart Django: make restart"; \
	echo ""
