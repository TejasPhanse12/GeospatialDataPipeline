# Makefile for Soil Moisture Analysis Project

PYTHON = python3
CONDA = conda
ENV_FILE = environment.yml
ENV_NAME =  geo_env


# Script filenames
LANDSAT_SCRIPT = landsat_access.py
MOISTURE_SCRIPT = mositure_analysis.py
EDA_SCRIPTS = landsat_EDA.py mesonet_satation_EDA.py meso_landsat_norm_EDA.py
HTML_FILES = plotly_station_graphs/all_stations_NDMI_14day_roll_norm.html plotly_station_graphs/all_stations_TR05_14day_roll_norm.html

# Data files to check
LINKS_CSV = data/scene_links.csv
MOISTURE_CSV = data/moisture_data.csv

.PHONY: all setup check run clean help eda

# Default target: show help
all: help

## help: Show this help message
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^## [-[:alnum:]_]+:.*' $(MAKEFILE_LIST) | sed 's/^## //g' | awk -F ': ' '{printf "  %-15s %s\n", $$1, $$2}'

## setup: Create the conda environment and install dependencies
setup:
	@echo "Creating conda environment '$(ENV_NAME)'..."
	$(CONDA) env create -f $(ENV_FILE)
	@echo "Environment created. Run 'conda activate $(ENV_NAME)' to begin."

## check: Verify conda installation and environment status
check:
	@echo "Checking if conda is installed..."
	@$(CONDA) --version > /dev/null 2>&1 || (echo "Error: conda is not installed."; exit 1)
	@echo "Checking if environment '$(ENV_NAME)' exists..."
	@$(CONDA) info --envs | grep -q "$(ENV_NAME)" || (echo "Warning: Environment '$(ENV_NAME)' not found. Run 'make setup'"; exit 1)

## eda: Run all EDA scripts and open results
eda: check
	@echo "Running EDA scripts..."
	@for script in $(EDA_SCRIPTS); do \
		echo "Executing $$script..."; \
		$(PYTHON) $$script; \
	done
	@echo "Opening EDA HTML results..."
	@open $(HTML_FILES)

## run: Execute the full pipeline including extraction, EDA, and analysis
run: check
	@if [ ! -s $(LINKS_CSV) ] || [ ! -s $(MOISTURE_CSV) ]; then \
		echo "Data files are missing or empty. Running extraction..."; \
		$(PYTHON) $(LANDSAT_SCRIPT); \
	fi
	@echo "Running EDA scripts..."
	@for script in $(EDA_SCRIPTS); do \
		echo "Executing $$script..."; \
		$(PYTHON) $$script; \
	done
	@echo "Opening EDA HTML results..."
	@open $(HTML_FILES)
	@echo "Running analysis dashboard..."
	$(PYTHON) $(MOISTURE_SCRIPT)

## clean: Remove python cache files
clean:
	@echo "Cleaning up __pycache__..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
