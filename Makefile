.PHONY: lint style

lint:
	isort --check --diff es2loki demo
	black --check --diff es2loki demo

style:
	isort es2loki demo
	black es2loki demo
