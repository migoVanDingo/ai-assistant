.PHONY: deploy-dashboard deploy-dashboard-pull nightly-briefbot

deploy-dashboard:
	./scripts/deploy_dashboard.sh

deploy-dashboard-pull:
	DEPLOY_PULL=1 ./scripts/deploy_dashboard.sh

nightly-briefbot:
	./briefbot/nightly_briefbot.sh
