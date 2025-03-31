APP_NAME = loganomaly
PYTHON = python3

.PHONY: install clean format lint test run show-results

install:
	@echo "🔧 Installing dependencies..."
	pip install -r requirements.txt

format:
	@echo "🎨 Formatting code..."
	black $(APP_NAME) tests

lint:
	@echo "🔍 Running linter..."
	flake8 $(APP_NAME)

test:
	@echo "✅ Running tests..."
	pytest tests

clean:
	@echo "🧹 Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -r {} +
	rm -rf .pytest_cache
	rm -f error.log

run:
	@echo "🚀 Running log anomaly detection..."
	$(PYTHON) -m $(APP_NAME).cli --process

show-results:
	@echo "📊 Launching Dashboard..."
	$(PYTHON) -m $(APP_NAME).dashboard

package:
	@echo "📦 Packaging CLI..."
	python3 setup.py sdist bdist_wheel

