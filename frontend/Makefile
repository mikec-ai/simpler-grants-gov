.PHONY : \
	release-build

FRONTEND_COMPOSE_PROJECT ?= frontend
FRONTEND_COMPOSE := docker compose --project-name $(FRONTEND_COMPOSE_PROJECT)

# Docker user configuration
# This logic is to avoid issues with permissions and mounting local volumes,
# which should be owned by the same UID for Linux distros. Mac OS can use root,
# but it is best practice to run things as with least permission where possible

# Can be set by adding user=<username> and/ or uid=<id> after the make command
# If variables are not set explicitly: try looking up values from current
# environment, otherwise fixed defaults.
# uid= defaults to 0 if user= set (which makes sense if user=root, otherwise you
# probably want to set uid as well).
ifeq ($(user),)
RUN_USER ?= $(or $(strip $(USER)),nodummy)
RUN_UID ?= $(or $(strip $(shell id -u)),4000)
else
RUN_USER = $(user)
RUN_UID = $(or $(strip $(uid)),0)
endif

export RUN_USER
export RUN_UID

##################################################
# Release
##################################################
release-build:
	docker buildx build \
	  --target release \
		--platform=linux/amd64 \
		--build-arg RUN_USER=$(RUN_USER) \
		--build-arg RUN_UID=$(RUN_UID) \
		$(OPTS) \
		.

##################################################
# Local development
##################################################
build-dev: # Build the Next.js local dev server in Docker
	$(FRONTEND_COMPOSE) build --no-cache nextjs

build-storybook: # Build Storybook in Docker
	$(FRONTEND_COMPOSE) build --no-cache storybook

build-prod: # Build the Next.js local prod server in Docker
	$(FRONTEND_COMPOSE) build --no-cache --progress plain nextjs-prod

reinstall-deps:
	rm -rf node_modules
	npm install

dev: # Run the Next.js local dev server in Docker
	$(FRONTEND_COMPOSE) up --detach nextjs
	$(FRONTEND_COMPOSE) logs --follow nextjs

run-prod: # Run the Next.js local prod server in Docker
	$(FRONTEND_COMPOSE) up --detach nextjs-prod
	$(FRONTEND_COMPOSE) logs --follow nextjs-prod

storybook: # Run the Storybook local dev server in Docker
	$(FRONTEND_COMPOSE) up --detach storybook
	$(FRONTEND_COMPOSE) logs --follow storybook

stop:
	$(FRONTEND_COMPOSE) down

##################################################
# Load testing
##################################################

load-test-local: # Load test the local environment at localhost:3000
	artillery run -e local artillery-load-test.yml

load-test-dev: # Load test the dev environment in aws
	artillery run -e dev artillery-load-test.yml

load-test-staging: # Load test the staging environment in aws
	artillery run -e stage artillery-load-test.yml

load-test-prod: # Load test the production environment in aws. Please test responsibly
	artillery run -e prod artillery-load-test.yml

test-group-counts: # Print the number of tests currently assigned to each test group
	grep -roE 'tag:.*SMOKE*]' ./tests/e2e/ | wc -l
	grep -roE 'tag:.*CORE_REGRESSION.*]' ./tests/e2e/ | wc -l
	grep -roE 'tag:.*FULL_REGRESSION.*]' ./tests/e2e/ | wc -l
	grep -roE 'tag:.*EXTENDED.*]' ./tests/e2e/ | wc -l
