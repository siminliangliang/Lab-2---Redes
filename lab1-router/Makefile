# Compilador P4
P4_COMPILER = p4c-bm2-ss
P4_FILE = p4src/router.p4
BUILD_DIR = build
JSON_FILE = $(BUILD_DIR)/router.json

# Python de la VM P4
PYTHON = /home/p4/src/p4dev-python-venv/bin/python3
MININET = /home/p4/src/p4dev-python-venv/bin/mn

.PHONY: all compile topology test clean help

all: compile

# Compilar el programa P4
compile:
	mkdir -p $(BUILD_DIR)
	$(P4_COMPILER) --p4v 16 -o $(JSON_FILE) $(P4_FILE)

# Iniciar la topología
topology:
	sudo $(PYTHON) topology.py

# Ejecutar pruebas del router
test:
	sudo /home/p4/src/p4dev-python-venv/bin/python3 tests/router_tests.py | tee tests/results.txt

# Limpiar Mininet
clean:
	sudo $(MININET) -c

# Comandos disponibles
help:
	@echo "Comandos disponibles:"
	@echo "  make compile   - Compilar router.p4"
	@echo "  make topology  - Iniciar la topologia"
	@echo "  make test      - Ejecutar router_tests.py"
	@echo "  make clean     - Limpiar Mininet"