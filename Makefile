.PHONY: deploy-dashboard deploy-dashboard-local deploy-dashboard-pull nightly-briefbot setup-launchd unload-launchd setup-dashboard-service unload-dashboard-service

deploy-dashboard:
	./scripts/deploy_dashboard.sh

deploy-dashboard-local:
	LOCAL=1 ./scripts/deploy_dashboard.sh

deploy-dashboard-pull:
	DEPLOY_PULL=1 ./scripts/deploy_dashboard.sh

nightly-briefbot:
	./briefbot/nightly_briefbot.sh

setup-launchd:
	./scripts/setup_launchd.sh

unload-launchd:
	./scripts/setup_launchd.sh --unload

setup-dashboard-service:
	./scripts/setup_dashboard_service.sh

unload-dashboard-service:
	./scripts/setup_dashboard_service.sh --unload
