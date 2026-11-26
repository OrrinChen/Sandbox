.PHONY: portfolio-demo dense-lsa

portfolio-demo:
	@python3 scripts/build_portfolio_screenshots.py
	@python3 scripts/build_data_platform_artifacts.py >/dev/null
	@python3 scripts/smoke_cli_workflow.py
	@python3 scripts/smoke_interview_packaging.py
	@printf '%s\n' 'expected: screenshots=3 commands=6 verify_verdict=support docs=6 api_key_required=False'

dense-lsa:
	python3 scripts/run_dense_lsa_experiment.py --config configs/dense_lsa.yaml
