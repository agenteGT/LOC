#!/usr/bin/env python3
# =============================================================================
# run_test.py - Kogito DMN Test Runner
# =============================================================================
# Script para construir, ejecutar y probar archivos DMN con Kogito Quarkus
# en Docker.
#
# Uso:
#   python run_test.py build       Construir/reconstruir imagen Docker
#   python run_test.py start       Iniciar contenedor Kogito
#   python run_test.py test        Enviar inputs Excel → Kogito → output Excel
#   python run_test.py stop        Detener y eliminar contenedor
#   python run_test.py status      Ver estado del contenedor y endpoints
#   python run_test.py all         build + start + test (flujo completo)
#   python run_test.py rebuild     stop + build + start (recompilar DMN)
# =============================================================================

import subprocess
import requests
import pandas as pd
import json
import time
import sys
import os
import glob
import shutil
import argparse
from datetime import datetime
from pathlib import Path

# =============================================================================
# Configuración
# =============================================================================
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent

# Directorios
DMN_SOURCE_DIR = PROJECT_ROOT / "00 Archivos"
INPUT_DIR = PROJECT_ROOT / "03 Input"
OUTPUT_DIR = PROJECT_ROOT / "04 Output"
KOGITO_APP_DIR = SCRIPT_DIR / "kogito-app"
RESOURCES_DIR = KOGITO_APP_DIR / "src" / "main" / "resources"

# Docker
DOCKER_IMAGE = "kogito-dmn-service"
CONTAINER_NAME = "kogito-dmn-container"
KOGITO_PORT = 8080

# URLs
BASE_URL = f"http://localhost:{KOGITO_PORT}"
HEALTH_URL = f"{BASE_URL}/q/health/ready"
OPENAPI_URL = f"{BASE_URL}/q/openapi"
SWAGGER_URL = f"{BASE_URL}/q/swagger-ui"

# =============================================================================
# Utilidades
# =============================================================================

def log(msg, level="INFO"):
    """Log con timestamp."""
    ts = datetime.now().strftime("%H:%M:%S")
    symbol = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERR": "❌", "RUN": "🔄"}.get(level, "  ")
    print(f"[{ts}] {symbol}  {msg}")


def run_cmd(cmd, check=True, capture=False):
    """Ejecutar comando del sistema."""
    log(f"$ {' '.join(cmd)}", "RUN")
    result = subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True
    )
    return result


def docker_available():
    """Verificar que Docker está disponible."""
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

# =============================================================================
# Gestión de archivos DMN
# =============================================================================

def copy_dmn_files():
    """Copiar archivos DMN desde 00 Archivos a los recursos de Quarkus."""
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

    # Buscar archivos .dmn en la carpeta de archivos
    dmn_files = list(DMN_SOURCE_DIR.glob("*.dmn"))

    if not dmn_files:
        log(f"No se encontraron archivos .dmn en {DMN_SOURCE_DIR}", "WARN")
        log("Coloca tus archivos DMN exportados de KIE Sandbox en '00 Archivos/'", "INFO")
        return []

    # Limpiar DMN anteriores del directorio de recursos
    for old_dmn in RESOURCES_DIR.glob("*.dmn"):
        old_dmn.unlink()

    # Copiar nuevos DMN
    copied = []
    for dmn_file in dmn_files:
        dest = RESOURCES_DIR / dmn_file.name
        shutil.copy2(dmn_file, dest)
        log(f"DMN copiado: {dmn_file.name}", "OK")
        copied.append(dmn_file.name)

    return copied

# =============================================================================
# Docker: Build / Start / Stop
# =============================================================================

def build_image():
    """Construir la imagen Docker con los archivos DMN actuales."""
    if not docker_available():
        log("Docker no está disponible. Asegúrate de que Docker Desktop esté corriendo.", "ERR")
        sys.exit(1)

    # Copiar archivos DMN al proyecto
    dmn_files = copy_dmn_files()
    if not dmn_files:
        log("No hay archivos DMN para compilar. Abortando build.", "ERR")
        sys.exit(1)

    log(f"Construyendo imagen Docker '{DOCKER_IMAGE}' con {len(dmn_files)} archivo(s) DMN...")
    log("Esto puede tardar unos minutos la primera vez (descarga de dependencias Maven)...", "INFO")

    run_cmd([
        "docker", "build",
        "-t", DOCKER_IMAGE,
        "-f", str(SCRIPT_DIR / "Dockerfile"),
        str(SCRIPT_DIR)
    ])

    log(f"Imagen '{DOCKER_IMAGE}' construida exitosamente", "OK")


def start_container():
    """Iniciar el contenedor Docker."""
    if not docker_available():
        log("Docker no está disponible.", "ERR")
        sys.exit(1)

    # Verificar si ya hay un contenedor corriendo
    result = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name={CONTAINER_NAME}"],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        log(f"El contenedor '{CONTAINER_NAME}' ya está corriendo.", "WARN")
        return

    # Eliminar contenedor anterior detenido si existe
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True
    )

    log(f"Iniciando contenedor '{CONTAINER_NAME}' en puerto {KOGITO_PORT}...")
    run_cmd([
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "-p", f"{KOGITO_PORT}:8080",
        DOCKER_IMAGE
    ])

    # Esperar a que el servicio esté listo
    log("Esperando a que Quarkus + Kogito esté listo...")
    ready = wait_for_service()

    if ready:
        log(f"Servicio listo en {BASE_URL}", "OK")
        log(f"Swagger UI: {SWAGGER_URL}", "OK")
    else:
        log("El servicio no respondió después de 120 segundos.", "ERR")
        log("Revisa los logs con: docker logs kogito-dmn-container", "INFO")
        sys.exit(1)


def stop_container():
    """Detener y eliminar el contenedor."""
    log(f"Deteniendo contenedor '{CONTAINER_NAME}'...")
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)
    log("Contenedor detenido", "OK")


def wait_for_service(timeout=120):
    """Esperar a que el servicio de health responda OK."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(HEALTH_URL, timeout=5)
            if r.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        except requests.Timeout:
            pass
        time.sleep(3)
    return False

# =============================================================================
# Descubrimiento de endpoints DMN
# =============================================================================

def discover_endpoints():
    """Descubrir endpoints DMN disponibles desde OpenAPI."""
    try:
        r = requests.get(OPENAPI_URL, timeout=10,
                         headers={"Accept": "application/json"})
        if r.status_code != 200:
            log(f"No se pudo obtener OpenAPI spec (HTTP {r.status_code})", "WARN")
            return []

        spec = r.json()
        paths = spec.get("paths", {})

        # Filtrar solo endpoints DMN (excluir los internos de Quarkus /q/*)
        dmn_endpoints = []
        for path, methods in paths.items():
            if path.startswith("/q/") or path == "/":
                continue
            if "post" in methods:
                dmn_endpoints.append(path)

        return dmn_endpoints

    except Exception as e:
        log(f"Error descubriendo endpoints: {e}", "ERR")
        return []

# =============================================================================
# Procesamiento de inputs/outputs
# =============================================================================

def process_inputs(endpoint=None):
    """Leer inputs de Excel, enviar a Kogito, generar Excel de output."""
    # Verificar que el servicio está corriendo
    try:
        requests.get(HEALTH_URL, timeout=5)
    except Exception:
        log("El servicio Kogito no está corriendo. Usa 'start' primero.", "ERR")
        sys.exit(1)

    # Descubrir endpoints disponibles
    endpoints = discover_endpoints()
    if not endpoints:
        log("No se encontraron endpoints DMN. ¿Hay archivos .dmn compilados?", "ERR")
        sys.exit(1)

    log(f"Endpoints DMN disponibles: {endpoints}", "INFO")

    # Seleccionar endpoint
    if endpoint:
        target_endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    else:
        target_endpoint = endpoints[0]
        log(f"Usando primer endpoint encontrado: {target_endpoint}", "INFO")

    # Buscar archivos Excel de input
    input_files = list(INPUT_DIR.glob("*.xlsx"))
    if not input_files:
        log(f"No se encontraron archivos .xlsx en {INPUT_DIR}", "ERR")
        log("Coloca tu archivo Excel con la columna 'input' (JSON) en '03 Input/'", "INFO")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for input_file in input_files:
        log(f"Procesando: {input_file.name}")
        process_single_file(input_file, target_endpoint)


def process_single_file(input_file, endpoint):
    """Procesar un solo archivo Excel de input."""
    try:
        df = pd.read_excel(input_file, engine="openpyxl")
    except Exception as e:
        log(f"Error leyendo {input_file.name}: {e}", "ERR")
        return

    # Verificar que existe la columna 'input'
    if "input" not in df.columns:
        log(f"Columna 'input' no encontrada en {input_file.name}. "
            f"Columnas disponibles: {list(df.columns)}", "ERR")
        return

    results = []
    total = len(df)
    success = 0
    errors = 0

    for idx, row in df.iterrows():
        # Parsear el JSON de input
        try:
            raw_input = row["input"]
            if isinstance(raw_input, str):
                input_json = json.loads(raw_input)
            elif isinstance(raw_input, dict):
                input_json = raw_input
            else:
                input_json = json.loads(str(raw_input))
        except (json.JSONDecodeError, TypeError) as e:
            log(f"  Fila {idx + 1}: JSON inválido - {e}", "ERR")
            results.append({
                "fila": idx + 1,
                "input": str(raw_input),
                "output": None,
                "status": "ERROR_JSON",
                "error": str(e)
            })
            errors += 1
            continue

        # Enviar al endpoint Kogito
        try:
            response = requests.post(
                f"{BASE_URL}{endpoint}",
                json=input_json,
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code == 200:
                output_json = response.json()
                results.append({
                    "fila": idx + 1,
                    "input": json.dumps(input_json, ensure_ascii=False),
                    "output": json.dumps(output_json, ensure_ascii=False),
                    "status": "OK",
                    "error": None
                })
                success += 1
            else:
                results.append({
                    "fila": idx + 1,
                    "input": json.dumps(input_json, ensure_ascii=False),
                    "output": response.text,
                    "status": f"HTTP_{response.status_code}",
                    "error": response.text[:500]
                })
                errors += 1

        except requests.RequestException as e:
            results.append({
                "fila": idx + 1,
                "input": json.dumps(input_json, ensure_ascii=False),
                "output": None,
                "status": "ERROR_REQUEST",
                "error": str(e)
            })
            errors += 1

    # Generar archivo de output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"output_{input_file.stem}_{timestamp}.xlsx"
    output_path = OUTPUT_DIR / output_filename

    output_df = pd.DataFrame(results)
    output_df.to_excel(output_path, index=False, engine="openpyxl")

    log(f"Resultados escritos en: {output_path.name}", "OK")
    log(f"  Total: {total} | Exitosos: {success} | Errores: {errors}", "INFO")

# =============================================================================
# Status
# =============================================================================

def show_status():
    """Mostrar estado del contenedor y endpoints disponibles."""
    # Estado del contenedor
    result = subprocess.run(
        ["docker", "ps", "-a", "-f", f"name={CONTAINER_NAME}",
         "--format", "table {{.Status}}\t{{.Ports}}"],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        log(f"Contenedor: {result.stdout.strip()}", "INFO")
    else:
        log("Contenedor no encontrado", "WARN")
        return

    # Endpoints
    endpoints = discover_endpoints()
    if endpoints:
        log(f"Endpoints DMN: {endpoints}", "OK")
    else:
        log("No se detectaron endpoints DMN", "WARN")

    log(f"Swagger UI: {SWAGGER_URL}", "INFO")

# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Kogito DMN Test Runner - Construye, ejecuta y prueba archivos DMN"
    )
    parser.add_argument(
        "action",
        choices=["build", "start", "stop", "test", "status", "all", "rebuild"],
        help="Acción a ejecutar"
    )
    parser.add_argument(
        "--endpoint",
        help="Endpoint DMN específico (ej: /mi-decision). Si no se indica, se auto-detecta.",
        default=None
    )

    args = parser.parse_args()
    action = args.action

    log(f"=== Kogito DMN Test Runner === Acción: {action}")

    if action == "build":
        build_image()

    elif action == "start":
        start_container()

    elif action == "stop":
        stop_container()

    elif action == "test":
        process_inputs(endpoint=args.endpoint)

    elif action == "status":
        show_status()

    elif action == "all":
        build_image()
        start_container()
        process_inputs(endpoint=args.endpoint)

    elif action == "rebuild":
        stop_container()
        build_image()
        start_container()

    log("=== Finalizado ===")


if __name__ == "__main__":
    main()
