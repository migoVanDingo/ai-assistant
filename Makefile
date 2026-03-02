.PHONY: deploy-dashboard nightly-briefbot

deploy-dashboard:
	./scripts/deploy_dashboard.sh

nightly-briefbot:
	./briefbot/nightly_briefbot.sh
