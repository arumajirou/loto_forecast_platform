.PHONY: test smoke api

test:
	pytest -q

smoke:
	python examples/generate_sample.py
	LOTO_SEAL_SECRET=test-secret PYTHONPATH=src python -m loto.cli experiment run --input examples/sample_loto7.csv --output runs/smoke --backtest-draws 20

api:
	LOTO_OUTPUT_DIR=runs/smoke uvicorn loto.api.app:app --host 127.0.0.1 --port 8088
