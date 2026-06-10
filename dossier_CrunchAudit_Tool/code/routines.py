from pathlib import Path
import subprocess
import shutil
import time
import csv
import os
from datetime import datetime
import json
import sys
import traceback

# ── Dossiers de base ───────────────────────────────────────────────────────
def get_application_dir():
    """Retourne le dossier où se trouve l'exécutable ou le script principal."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent

# Dossier de l'application (lecture seule : cas, exécutable, exercices)
APP_DIR = get_application_dir()

# Dossier de travail dans Documents (écriture : Database, résultats, test, reference)
BASE_DIR = Path.home() / "Documents" / "CrunchODiTi"
BASE_DIR.mkdir(parents=True, exist_ok=True)

# Sous-dossiers dans BASE_DIR
RESULTS_DIR = BASE_DIR / "resultats_timeout"
CSV_FILE = RESULTS_DIR / "resultats_time_out.csv"
DATABASE_DIR = BASE_DIR / "Database"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

# Fichiers de configuration dans BASE_DIR
EXTRA_FILES_JSON = BASE_DIR / "extra_files_config.json"
EXPORT_CONFIG_FILE = BASE_DIR / "export_lists_config.json"
COMPARISON_CSV_DIR = BASE_DIR / "comparaisons"
COMPARISON_CSV_FILE = COMPARISON_CSV_DIR / "comparaisons.csv"


def find_executable():
    """Cherche CrunchODiTi.exe dans APP_DIR."""
    exe = APP_DIR / "CrunchODiTi.exe"
    if exe.exists():
        return exe
    for f in APP_DIR.rglob("CrunchODiTi.exe"):
        return f
    return exe


def find_exercices_dir():
    """Cherche le dossier exercices dans APP_DIR."""
    exercices = APP_DIR / "exercices"
    if exercices.exists():
        return exercices
    for d in APP_DIR.rglob("exercices"):
        if d.is_dir():
            return d
    return None


# ---------------------------------------------------------------------------
# ÉTAPE 1 – Détection des nouveaux cas
# ---------------------------------------------------------------------------

def find_all_cases():
    """
    Retourne un dict : {nom_cas: Path}
    Cherche les cas dans APP_DIR.
    """
    cases = {}
    IGNORE_DIRS = {"test", "reference", "resultats_timeout", "database", "__pycache__"}

    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = [d for d in dirs if d.lower() not in IGNORE_DIRS]
        path = Path(root)
        in_files = list(path.glob("*.in"))
        if in_files:
            cases[path.name] = path
    return cases


def find_reference_cases():
    """Cherche les références dans BASE_DIR/reference/."""
    ref_root = BASE_DIR / "reference"
    if not ref_root.exists():
        return set()
    return {d.name for d in ref_root.iterdir() if d.is_dir()}


def classify_cases(cases_dict):
    """Sépare les cas connus et nouveaux."""
    ref_names = find_reference_cases()
    known = {}
    new = {}
    for name, path in cases_dict.items():
        norm = name.lower().replace("-", "_")
        if norm in ref_names or name in ref_names:
            known[name] = path
        else:
            new[name] = path
    return known, new


# ---------------------------------------------------------------------------
# ÉTAPE 2 – Gestion des fichiers .xyz
# ---------------------------------------------------------------------------

def find_latest_xyz(case_dir):
    """Trouve le proc_0Crunchfile.xyz avec le plus grand suffixe numérique."""
    candidates = []
    for f in case_dir.rglob("proc_0Crunchfile.xyz.*"):
        suffix = f.name.split(".")[-1]
        try:
            candidates.append((int(suffix), f))
        except ValueError:
            pass
    if not candidates:
        return None
    return max(candidates, key=lambda t: t[0])[1]


# ---------------------------------------------------------------------------
# ÉTAPE 3 – Fichiers supplémentaires par cas
# ---------------------------------------------------------------------------

def validate_extra_files(case_dir, extra_names):
    """Vérifie que les fichiers supplémentaires existent."""
    found = []
    missing = []
    for name in extra_names:
        name = name.strip()
        if not name:
            continue
        matches = list(case_dir.rglob(name))
        if matches:
            found.append(matches[0])
        else:
            missing.append(name)
    return found, missing


# ---------------------------------------------------------------------------
# Helpers fichiers
# ---------------------------------------------------------------------------

def find_all_in_files(case_dir):
    return list(case_dir.rglob("*.in"))


def get_last_in_file(case_dir):
    files = find_all_in_files(case_dir)
    return max(files, key=lambda f: f.stat().st_mtime)


def get_reference_in_file(case_dir):
    files = find_all_in_files(case_dir)
    return min(files, key=lambda f: f.stat().st_mtime)


def run_clean(case_dir):
    """Nettoie les fichiers de sortie."""
    for f in case_dir.rglob("*"):
        if f.suffix in [".out", ".rst", ".vtk", ".tec"]:
            try:
                f.unlink()
            except Exception:
                pass
    for f in case_dir.rglob("proc_0Crunchfile.xyz.*"):
        try:
            f.unlink()
        except Exception:
            pass


def run_case_timed(case_name, case_dir, in_file):
    """Exécute un cas et retourne le temps d'exécution."""
    exe = find_executable()
    start = time.perf_counter()
    try:
        subprocess.run(
            ["mpiexec", "-n", "1", "-delegate", str(exe), str(in_file)],
            cwd=str(case_dir),
            timeout=300,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        pass
    return round(time.perf_counter() - start, 4)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def init_csv(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f, delimiter=";").writerow(
                ["case", "date", "A", "B", "compare", "pourcentage_difference"]
            )


def compare_times(a, b, tolerance=0.2):
    if a == 0:
        return "indetermine"
    diff = abs(b - a) / a
    if diff <= tolerance:
        return "egal"
    elif b < a:
        return "plus_rapide"
    else:
        return "plus_lent"


def compute_diff(tA, tB):
    diff = round(tA - tB, 4)
    percent = round(diff / tA * 100, 2) if tA != 0 else 0
    return diff, percent


def format_result_label(case, tA, tB):
    diff, percent = compute_diff(tA, tB)
    return (
        case + " | A=" + str(round(tA, 4)) + "s"
        + " -> B=" + str(round(tB, 4)) + "s"
        + " | diff=" + str(diff) + "s"
        + " (" + str(percent) + "%)"
    )


def write_csv_line(path, case, a, b):
    diff_percent = round(abs(b - a) / a * 100, 2) if a != 0 else 0
    result = compare_times(a, b)
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=";").writerow(
            [case, datetime.now().strftime("%d/%m/%Y %H:%M"), a, b, result, diff_percent]
        )


# ---------------------------------------------------------------------------
# Export Database
# ---------------------------------------------------------------------------

def find_global_database():
    """Cherche CrunchDatabase*.dbs dans exercices/ de APP_DIR."""
    exercices_dir = find_exercices_dir()
    if exercices_dir:
        dbs_files = list(exercices_dir.rglob("CrunchDatabase*.dbs"))
        if dbs_files:
            return max(dbs_files, key=lambda f: f.stat().st_mtime)
    dbs_files = list(APP_DIR.rglob("CrunchDatabase*.dbs"))
    if dbs_files:
        return max(dbs_files, key=lambda f: f.stat().st_mtime)
    return None


def find_case_run_database(case_dir):
    """Cherche RunDatabase.dbs dans le dossier du cas."""
    if not case_dir.exists():
        return None
    dbs_files = list(case_dir.rglob("RunDatabase.dbs"))
    if dbs_files:
        return max(dbs_files, key=lambda f: f.stat().st_mtime)
    return None


def export_global_database(log_func=None):
    """Exporte la database globale vers DATABASE_DIR (dans Documents)."""
    if log_func is None:
        log_func = print

    log_func("[Database] Recherche du fichier CrunchDatabase global...")
    db_file = find_global_database()

    if db_file is None:
        msg = "⚠ Aucun fichier CrunchDatabase trouvé dans exercices/"
        log_func(msg)
        return False, msg

    log_func(f"[Database] Fichier trouvé : {db_file}")

    dest_dir = DATABASE_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%Hh%M")
    dest_name = f"{db_file.stem}_{timestamp}{db_file.suffix}"
    dest_path = dest_dir / dest_name

    existing_files = list(dest_dir.glob(f"{db_file.stem}_*{db_file.suffix}"))

    if existing_files:
        latest_existing = max(existing_files, key=lambda f: f.stat().st_mtime)
        if (latest_existing.stat().st_size == db_file.stat().st_size and
            latest_existing.stat().st_mtime == db_file.stat().st_mtime):
            log_func(f"[Database] Fichier identique déjà présent : {latest_existing.name}")
            return True, f"Fichier identique déjà présent : {latest_existing.name}"
        else:
            log_func(f"[Database] Nouvelle version détectée, export en cours...")

    try:
        shutil.copy2(db_file, dest_path)
        log_func(f"[Database] ✓ Exporté : {dest_name}")
        return True, f"Exporté : {dest_name}"
    except Exception as e:
        msg = f" Erreur lors de l'export : {e}"
        log_func(msg)
        return False, msg


def export_case_run_database(case_name, case_dir, log_func=None):
    """Exporte le RunDatabase.dbs du cas vers DATABASE_DIR/<case_name>/."""
    if log_func is None:
        log_func = print

    log_func(f"[Database] Recherche de RunDatabase.dbs pour le cas '{case_name}'...")
    db_file = find_case_run_database(case_dir)

    if db_file is None:
        msg = f"⚠ Aucun RunDatabase.dbs trouvé pour le cas '{case_name}'"
        log_func(msg)
        return False, msg, None

    log_func(f"[Database] Fichier trouvé : {db_file}")

    dest_dir = DATABASE_DIR / case_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%Hh%M")
    dest_name = f"RunDatabase_{timestamp}.dbs"
    dest_path = dest_dir / dest_name

    existing_files = sorted(dest_dir.glob("RunDatabase_*.dbs"))

    if existing_files:
        latest_existing = existing_files[-1]
        if latest_existing.stat().st_size == db_file.stat().st_size:
            try:
                with open(latest_existing, 'rb') as f1, open(db_file, 'rb') as f2:
                    if f1.read() == f2.read():
                        log_func(f"[Database] RunDatabase identique déjà présent : {latest_existing.name}")
                        return True, f"Identique au fichier existant : {latest_existing.name}", latest_existing
            except Exception:
                pass
        log_func(f"[Database] Nouvelle version de RunDatabase détectée, export en cours...")
    else:
        log_func(f"[Database] Premier export de RunDatabase pour ce cas.")

    try:
        shutil.copy2(db_file, dest_path)
        log_func(f"[Database] ✓ Exporté : {case_name}/{dest_name}")
        return True, f"Exporté : {dest_name}", dest_path
    except Exception as e:
        msg = f" Erreur lors de l'export : {e}"
        log_func(msg)
        return False, msg, None


def export_all_databases(log_func=None):
    """Exporte toutes les databases (globale + par cas)."""
    if log_func is None:
        log_func = print

    log_func("=" * 60)
    log_func("[Database] DÉBUT DE L'EXPORT DES DATABASES")
    log_func("=" * 60)

    log_func("\n [Database] Export de la database globale...")
    success, msg = export_global_database(log_func)
    log_func(f"   Résultat : {msg}")

    cases = find_all_cases()
    log_func(f"\n [Database] Export des RunDatabase pour {len(cases)} cas...")

    exported_count = 0
    for case_name, case_dir in cases.items():
        success, msg, path = export_case_run_database(case_name, case_dir, log_func)
        if success and path:
            exported_count += 1

    log_func(f"\n[Database] Export terminé : {exported_count} RunDatabase exportés")
    log_func("=" * 60)


# ---------------------------------------------------------------------------
# Export / référence
# ---------------------------------------------------------------------------

def collect_export_files(case_dir, extra_paths=None):
    """Collecte tous les fichiers à exporter."""
    files = list(case_dir.rglob("*.out"))
    xyz = find_latest_xyz(case_dir)
    if xyz:
        files.append(xyz)
    if extra_paths:
        files.extend(extra_paths)
    return files


def get_default_export_files(case_dir):
    """Retourne la liste des noms de fichiers exportés par défaut."""
    files = []
    for f in find_all_in_files(case_dir):
        files.append(f.name)
    for f in case_dir.rglob("*.out"):
        files.append(f.name)
    xyz = find_latest_xyz(case_dir)
    if xyz:
        files.append(xyz.name)
    return sorted(set(files))


def export_case(case_name, case_dir, timestamp, extra_paths=None):
    """Exporte les fichiers dans BASE_DIR/test/ et BASE_DIR/reference/."""
    case_norm = case_name.lower().replace("-", "_")
    test_dir = BASE_DIR / "test" / case_norm
    ref_dir = BASE_DIR / "reference" / case_norm
    in_files = find_all_in_files(case_dir)
    out_files = collect_export_files(case_dir, extra_paths)
    exported_files = []

    for d in [test_dir / "input", test_dir / "output"]:
        d.mkdir(parents=True, exist_ok=True)

    for f in in_files:
        dest_name = timestamp + "_" + f.name
        shutil.copy2(f, test_dir / "input" / dest_name)
        exported_files.append("input/" + dest_name)

    for f in out_files:
        dest_name = timestamp + "_" + f.name
        shutil.copy2(f, test_dir / "output" / dest_name)
        exported_files.append("output/" + dest_name)

    if not ref_dir.exists():
        (ref_dir / "input").mkdir(parents=True, exist_ok=True)
        (ref_dir / "output").mkdir(parents=True, exist_ok=True)
        for f in in_files:
            shutil.copy2(f, ref_dir / "input" / f.name)
        for f in out_files:
            shutil.copy2(f, ref_dir / "output" / f.name)

    return test_dir, ref_dir, exported_files


def replace_reference(case_name, case_dir):
    """Remplace la référence par les fichiers de test."""
    case_norm = case_name.lower().replace("-", "_")
    test_dir = BASE_DIR / "test" / case_norm / "output"
    ref_dir = BASE_DIR / "reference" / case_norm / "output"
    if not test_dir.exists():
        return
    ref_dir.mkdir(parents=True, exist_ok=True)
    for f in ref_dir.glob("*"):
        try:
            f.unlink()
        except Exception:
            pass
    for f in test_dir.glob("*"):
        shutil.copy2(f, ref_dir / f.name)


# ---------------------------------------------------------------------------
# Fichiers exportés (configuration)
# ---------------------------------------------------------------------------

def load_export_lists():
    if not EXPORT_CONFIG_FILE.exists():
        return {}
    try:
        with open(EXPORT_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_export_lists(config):
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    with open(EXPORT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_export_files_for_case(case_name, case_dir):
    config = load_export_lists()
    default_files = get_default_export_files(case_dir)
    if case_name in config:
        custom_files = config[case_name]
        all_files = list(set(default_files + custom_files))
        return sorted(all_files)
    else:
        return default_files


def update_export_list(case_name, file_list):
    config = load_export_lists()
    files = [f.strip() for f in file_list.split(",") if f.strip()]
    if files:
        config[case_name] = files
    else:
        if case_name in config:
            del config[case_name]
    save_export_lists(config)
    return files


# ---------------------------------------------------------------------------
# Fonctions supplémentaires (extra_files_config)
# ---------------------------------------------------------------------------

def load_extra_files_config():
    if not EXTRA_FILES_JSON.exists():
        return {}
    try:
        with open(EXTRA_FILES_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_extra_files_config(config):
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    with open(EXTRA_FILES_JSON, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Orchestration principale
# ---------------------------------------------------------------------------

def run_benchmark_case(case_name, case_dir, timestamp, is_new=False, extra_names=None):
    """
    Exécute un cas complet : clean, run ref, run test, export, csv.
    Retourne un dict avec les résultats.
    """
    logs = []
    missing_files = []

    try:
        tag = "[NEW] " if is_new else ""
        logs.append("=" * 60)
        logs.append(f" DÉBUT DU TRAITEMENT : {tag}{case_name}")
        logs.append("=" * 60)
        logs.append(f" Chemin du cas : {case_dir}")
        logs.append(f" Horodatage : {timestamp}")
        logs.append(f" Type : {'Nouveau cas' if is_new else 'Cas connu'}")

        # Validation des fichiers supplémentaires
        extra_paths = []
        if extra_names:
            logs.append(f" Vérification des fichiers supplémentaires : {extra_names}")
            found, missing = validate_extra_files(case_dir, extra_names)
            extra_paths = found
            missing_files = missing
            if found:
                logs.append(f"   ✓ {len(found)} fichier(s) trouvé(s) :")
                for f in found:
                    logs.append(f"      • {f.name}")
            if missing:
                for m in missing:
                    logs.append(f"   ⚠ Fichier supplémentaire INTROUVABLE → {m}")

        # Étape 1 : Nettoyage
        logs.append("")
        logs.append(" ÉTAPE 1/5 : Nettoyage du dossier de travail...")
        run_clean(case_dir)
        logs.append("   ✓ Nettoyage terminé")

        # Étape 2 : Identification des fichiers d'entrée
        logs.append("")
        logs.append(" ÉTAPE 2/5 : Identification des fichiers d'entrée...")
        ref_in = get_reference_in_file(case_dir)
        test_in = get_last_in_file(case_dir)
        logs.append(f"   • Fichier référence : {ref_in.name}")
        logs.append(f"   • Fichier test      : {test_in.name}")

        # Étape 3 : Exécution référence
        logs.append("")
        logs.append("  ÉTAPE 3/5 : Exécution du cas de RÉFÉRENCE...")
        logs.append(f"   • Commande : mpiexec -n 1 -delegate CrunchODiTi.exe {ref_in.name}")
        tA = run_case_timed(case_name, case_dir, ref_in)
        logs.append(f"   ✓ Terminé en {tA:.4f} secondes")

        # Étape 4 : Exécution test
        logs.append("")
        logs.append("  ÉTAPE 4/5 : Exécution du cas de TEST...")
        logs.append(f"   • Commande : mpiexec -n 1 -delegate CrunchODiTi.exe {test_in.name}")
        tB = run_case_timed(case_name, case_dir, test_in)
        logs.append(f"   ✓ Terminé en {tB:.4f} secondes")

        # Étape 5 : Export
        logs.append("")
        logs.append(" ÉTAPE 5/5 : Export des résultats...")
        write_csv_line(CSV_FILE, case_name, tA, tB)
        logs.append(f"   ✓ Ligne CSV ajoutée dans {CSV_FILE.name}")

        test_dir, ref_dir, exported_files = export_case(case_name, case_dir, timestamp, extra_paths)
        logs.append(f"   • Dossier test      : {test_dir}")
        logs.append(f"   • Dossier référence : {ref_dir}")

        # Log des fichiers exportés
        logs.append("")
        logs.append(" Fichiers exportés :")
        for ef in exported_files:
            logs.append(f"   ✓ {ef}")
        logs.append(f"   Total : {len(exported_files)} fichier(s)")

        # Comparaison des temps
        logs.append("")
        logs.append(" RÉSULTATS DE PERFORMANCE :")
        diff, percent = compute_diff(tA, tB)
        logs.append(f"   • Temps référence (A) : {tA:.4f}s")
        logs.append(f"   • Temps test (B)      : {tB:.4f}s")
        logs.append(f"   • Différence          : {diff:.4f}s ({percent:+.2f}%)")

        comparison = compare_times(tA, tB)
        if comparison == "plus_rapide":
            logs.append(f"    Le test est PLUS RAPIDE de {abs(percent):.2f}%")
        elif comparison == "plus_lent":
            logs.append(f"   ⚠ Le test est PLUS LENT de {abs(percent):.2f}%")
        else:
            logs.append(f"     Pas de différence significative")

        if is_new:
            logs.append("")
            logs.append(" Nouveau cas : référence initiale créée.")

        # Vérification des databases
        logs.append("")
        logs.append("  VÉRIFICATION DES DATABASES :")
        run_db = find_case_run_database(case_dir)
        if run_db:
            logs.append(f"   • RunDatabase trouvé : {run_db.name}")
            success, msg, path = export_case_run_database(
                case_name, case_dir,
                log_func=lambda m: logs.append(f"   {m}")
            )
            if success:
                logs.append(f"   ✓ Database exportée avec succès")
            else:
                logs.append(f"   ⚠ {msg}")
        else:
            logs.append(f"   • Aucun RunDatabase.dbs trouvé pour ce cas")

        logs.append("")
        logs.append(f" FIN DU TRAITEMENT : {case_name}")
        logs.append("=" * 60)

        return {
            "tA": tA,
            "tB": tB,
            "test_dir": test_dir,
            "ref_dir": ref_dir,
            "logs": logs,
            "error": None,
            "missing_files": missing_files,
            "exported_files": exported_files,
        }

    except Exception as e:
        logs.append("")
        logs.append(f" ERREUR lors du traitement de {case_name}")
        logs.append(f"   {str(e)}")
        logs.append(f"   Traceback: {traceback.format_exc()}")
        logs.append("=" * 60)
        return {
            "tA": None,
            "tB": None,
            "test_dir": None,
            "ref_dir": None,
            "logs": logs,
            "error": str(e),
            "missing_files": missing_files,
            "exported_files": [],
        }


def apply_reference_update(case_name, case_dir):
    """Applique la mise à jour de la référence pour un cas."""
    replace_reference(case_name, case_dir)
    return [
        "Reference updated for " + case_name,
        "Path: " + str(case_dir),
        "Files copied from test to reference",
    ]


# ---------------------------------------------------------------------------
# COMPARAISON .out – tabulated.out et proc_0Crunchfile.xyz.<N>
# ---------------------------------------------------------------------------

def find_comparable_cases():
    """Trouve les cas qui ont à la fois un dossier test et un dossier reference."""
    test_root = BASE_DIR / "test"
    ref_root = BASE_DIR / "reference"
    if not test_root.exists() or not ref_root.exists():
        return []
    test_cases = {d.name for d in test_root.iterdir() if d.is_dir()}
    ref_cases = {d.name for d in ref_root.iterdir() if d.is_dir()}
    return sorted(test_cases & ref_cases)


def _find_file_in_output(output_dir, pattern):
    """Trouve le fichier le plus récent correspondant au pattern dans output_dir."""
    candidates = list(output_dir.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime)


def find_output_pair(case_name, file_pattern):
    """Trouve la paire de fichiers (référence, test) pour un pattern donné."""
    case_norm = case_name.lower().replace("-", "_")
    ref_out = BASE_DIR / "reference" / case_norm / "output"
    test_out = BASE_DIR / "test" / case_norm / "output"
    ref_file = _find_file_in_output(ref_out, file_pattern) if ref_out.exists() else None
    test_file = _find_file_in_output(test_out, file_pattern) if test_out.exists() else None
    return ref_file, test_file


def parse_tabulated_out(path):
    """Parse un fichier tabulated.out."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip("\n") for l in f if l.strip()]
        if len(lines) < 4:
            return None
        headers = lines[0].split()
        units = lines[1].split()
        numbers = lines[2].split()
        rows = [l.split() for l in lines[3:]]
        return {"headers": headers, "units": units, "numbers": numbers, "rows": rows}
    except Exception:
        return None


def parse_xyz_out(path):
    """Parse un fichier proc_0Crunchfile.xyz."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip("\n") for l in f if l.strip() and not l.startswith("#")]
        if not lines:
            return None
        headers = lines[0].split()
        rows = [l.split() for l in lines[1:]]
        return {"headers": headers, "rows": rows}
    except Exception:
        return None


def _safe_float(s):
    """Convertit une chaîne en float, retourne None si impossible."""
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def classify_value(diff, thresh_green, thresh_red):
    """Classifie une différence selon les seuils."""
    if diff is None:
        return "red"
    if diff <= thresh_green:
        return "green"
    elif diff >= thresh_red:
        return "red"
    else:
        return "orange"


def compare_headers(ref_headers, test_headers):
    """Compare les en-têtes de deux fichiers."""
    result = []
    max_len = max(len(ref_headers), len(test_headers))
    for i in range(max_len):
        ref_v = ref_headers[i] if i < len(ref_headers) else None
        test_v = test_headers[i] if i < len(test_headers) else None
        if ref_v is None:
            statut = "EN_TROP"
        elif test_v is None:
            statut = "MANQUANT"
        elif ref_v == test_v:
            statut = "OK"
        else:
            statut = "DIFFERENT"
        result.append((i, ref_v, test_v, statut))
    return result


def compare_columns(ref_data, test_data, thresh_green, thresh_red):
    """Compare les colonnes de deux fichiers de données."""
    results = []
    ref_h = ref_data["headers"]
    test_h = test_data["headers"]
    ref_rows = ref_data["rows"]
    test_rows = test_data["rows"]

    for ci, col_name in enumerate(ref_h):
        if ci >= len(test_h):
            results.append({
                "col_index": ci, "col_name": col_name,
                "status": "missing", "max_diff": None,
                "ref_val": None, "test_val": None,
                "row_index": None, "header_ok": False,
            })
            continue

        header_ok = (test_h[ci] == col_name)
        max_diff = None
        worst_ref = None
        worst_test = None
        worst_row = None

        for ri, ref_row in enumerate(ref_rows):
            if ri >= len(test_rows):
                break
            ref_cell = ref_row[ci] if ci < len(ref_row) else None
            test_cell = test_rows[ri][ci] if ci < len(test_rows[ri]) else None
            rv = _safe_float(ref_cell)
            tv = _safe_float(test_cell)
            if rv is None or tv is None:
                continue
            diff = abs(rv - tv)
            if max_diff is None or diff > max_diff:
                max_diff = diff
                worst_ref = ref_cell
                worst_test = test_cell
                worst_row = ri

        if max_diff is None:
            status = "struct"
        else:
            status = classify_value(max_diff, thresh_green, thresh_red)

        results.append({
            "col_index": ci, "col_name": col_name,
            "status": status, "max_diff": max_diff,
            "ref_val": worst_ref, "test_val": worst_test,
            "row_index": worst_row, "header_ok": header_ok,
        })

    for ci in range(len(ref_h), len(test_h)):
        results.append({
            "col_index": ci, "col_name": test_h[ci],
            "status": "extra", "max_diff": None,
            "ref_val": None, "test_val": None,
            "row_index": None, "header_ok": False,
        })

    return results


def run_comparison(case_name, thresh_green, thresh_red):
    """Exécute la comparaison complète pour un cas."""
    out = {"case": case_name, "files": {}}

    for label, pattern, parser in [
        ("tabulated", "*tabulated.out", parse_tabulated_out),
        ("xyz", "*proc_0Crunchfile.xyz.*", parse_xyz_out),
    ]:
        ref_f, test_f = find_output_pair(case_name, pattern)

        if label == "xyz" and ref_f is None:
            out["files"][label] = None
            continue

        entry = {"ref": ref_f, "test": test_f, "columns": None, "header_issues": [], "error": None}

        if ref_f is None:
            entry["error"] = "Reference file missing"
        elif test_f is None:
            entry["error"] = "Test file missing"
        else:
            ref_data = parser(ref_f)
            test_data = parser(test_f)
            if ref_data is None or test_data is None:
                entry["error"] = "File read error"
            else:
                header_cmp = compare_headers(ref_data["headers"], test_data["headers"])
                entry["header_issues"] = [h for h in header_cmp if h[3] != "OK"]
                entry["columns"] = compare_columns(ref_data, test_data, thresh_green, thresh_red)

        out["files"][label] = entry

    return out


def export_comparison_csv(all_results):
    """Exporte les résultats de comparaison en CSV."""
    COMPARISON_CSV_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not COMPARISON_CSV_FILE.exists()
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    with open(COMPARISON_CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")

        if write_header:
            writer.writerow([
                "date", "cas", "fichier", "colonne",
                "col_index", "delta_max", "row_index", "statut"
            ])

        for res in all_results:
            case_name = res["case"]
            for file_key, file_label in [("tabulated", "tabulated.out"),
                                          ("xyz", "proc_0Crunchfile.xyz")]:
                fdata = res["files"].get(file_key)
                if fdata is None:
                    continue
                cols = fdata.get("columns") or []
                error = fdata.get("error")
                if error:
                    writer.writerow([now, case_name, file_label, "—", "—", "—", "—",
                                     "ERROR: " + error])
                    continue
                for col in cols:
                    diff_str = "{:.6e}".format(col["max_diff"]) if col["max_diff"] is not None else "—"
                    col_idx_str = str(col["col_index"] + 1)
                    row_idx_str = str(col["row_index"] + 1) if col["row_index"] is not None else "—"
                    writer.writerow([
                        now, case_name, file_label,
                        col["col_name"], col_idx_str, diff_str, row_idx_str,
                        col["status"].upper(),
                    ])

    return COMPARISON_CSV_FILE
