.PHONY: setup build up down restart logs shell user backup clean

# Force bash
SHELL := /bin/bash

# Auto-detect docker compose
DOCKER_COMPOSE := $(shell if command -v docker-compose >/dev/null 2>&1; then echo "docker-compose"; else echo "docker compose"; fi)

# Colors
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m

# Default target shows help
.DEFAULT_GOAL := show_commands

show_commands:
	@echo -e "$(GREEN)Storm Cloud - Make Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[0;32m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""

setup: ## First-time setup (creates .env, generates secrets)
	@./scripts/setup.sh

build: ## Build Docker images
	@echo -e "$(GREEN)Building images...$(NC)"
	@$(DOCKER_COMPOSE) build

up: ## Start services (auto-fixes container conflicts)
	@echo -e "$(GREEN)Starting services...$(NC)"
	@$(DOCKER_COMPOSE) down 2>/dev/null || true
	@$(DOCKER_COMPOSE) up -d --remove-orphans
	@sleep 5
	@$(DOCKER_COMPOSE) ps

down: ## Stop services
	@$(DOCKER_COMPOSE) down

restart: ## Restart services
	@$(DOCKER_COMPOSE) restart

logs: ## View logs (interactive)
	@echo -e "$(GREEN)Which logs do you want to view?$(NC)"
	@echo "  [1] All services (snapshot)"
	@echo "  [2] Web only (snapshot)"
	@echo "  [3] Database only (snapshot)"
	@echo "  [f] Follow all (live)"
	@echo "  [w] Follow web (live)"
	@echo "  [d] Follow database (live)"
	@echo ""
	@read -p "Select: " choice; \
	case $$choice in \
		1) $(DOCKER_COMPOSE) logs --tail=100 ;; \
		2) $(DOCKER_COMPOSE) logs --tail=100 web ;; \
		3) $(DOCKER_COMPOSE) logs --tail=100 db ;; \
		f|F) $(DOCKER_COMPOSE) logs -f ;; \
		w|W) $(DOCKER_COMPOSE) logs -f web ;; \
		d|D) $(DOCKER_COMPOSE) logs -f db ;; \
		*) echo "Invalid choice" ;; \
	esac

shell: ## Interactive shell (web or postgres)
	@echo -e "$(GREEN)Which shell do you want?$(NC)"
	@echo "  [1] Web server (bash)"
	@echo "  [2] PostgreSQL (psql)"
	@echo ""
	@read -p "Select: " choice; \
	case $$choice in \
		1) $(DOCKER_COMPOSE) exec web bash ;; \
		2) $(DOCKER_COMPOSE) exec db psql -U stormcloud -d stormcloud ;; \
		*) echo "Invalid choice" ;; \
	esac

superuser: ## Create superuser (admin account)
	@$(DOCKER_COMPOSE) exec web python manage.py createsuperuser
	@echo ""
	@echo -e "$(GREEN)Next step: Generate an API key with 'make api_key'$(NC)"

api_key: ## Generate API key for a user (interactive)
	@echo "Run 'make superuser' first if you haven't created an admin account."
	@read -p "Username: " username; \
	$(DOCKER_COMPOSE) exec web python manage.py generate_api_key $$username

backup: ## Backup database + uploads
	@./scripts/backup.sh

restore: ## Restore from backup
	@./scripts/restore.sh

clean: ## Delete EVERYTHING (containers, volumes, images)
	@echo -e "$(RED)WARNING: This deletes ALL data!$(NC)"
	@read -p "Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		$(DOCKER_COMPOSE) down -v; \
		docker rmi stormcloud_web 2>/dev/null || true; \
		echo -e "$(GREEN)Cleaned!$(NC)"; \
	else \
		echo "Cancelled."; \
	fi

ps: ## Show container status
	@$(DOCKER_COMPOSE) ps

# Catch-all for 'make logs f'
%:
	@:
