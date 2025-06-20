import argparse
import logging
import pandas as pd
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# --- CONFIGURATION PAR DÉFAUT ---
BASE_URL        = "https://www.unified-patent-court.org/en/decisions-and-orders"
OUTPUT_FILE     = Path("decisions_html.xlsx")
WAIT_SECONDS    = 10   # Délai max pour attendre le tableau
MAX_EMPTY_PAGES = 3    # Arrêt après X pages consécutives vides
MAX_ERRORS      = 3    # Arrêt après X erreurs consécutives
LOG_FILE        = "scrap_html.log"

# Colonnes du DataFrame
PAGE_COL = "Page"
COLUMNS = [
    "Date",          # Date de la décision au format JJ/MM/AAAA
    "Registry",      # Numéro de dossier(s), plusieurs lignes séparées par '\n'
    "Full Details",  # URL vers la page de détails
    "Court",         # Instance judiciaire
    "Type of action",# Type d’action
    "Parties",       # Parties impliquées
    "UPC Document",  # Lien PDF du document
    PAGE_COL          # Index de page lors du scraping
]

# --- LOGGER SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- ARGUMENTS ---
def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Scrape UPC decisions table")
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help="Base URL of the decisions table",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=OUTPUT_FILE,
        help="Excel file to write results",
    )
    parser.add_argument(
        "--max-empty-pages",
        type=int,
        default=MAX_EMPTY_PAGES,
        help="Maximum number of consecutive empty pages before stopping",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=MAX_ERRORS,
        help="Maximum number of consecutive errors before aborting",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=WAIT_SECONDS,
        help="Maximum seconds to wait for table loading",
    )
    parser.add_argument(
        "--enable-js",
        dest="enable_js",
        action="store_true",
        help="Enable JavaScript in the headless browser",
    )
    parser.add_argument(
        "--disable-js",
        dest="enable_js",
        action="store_false",
        help="Disable JavaScript in the headless browser (default)",
    )
    parser.set_defaults(enable_js=False)
    return parser.parse_args()

# --- FONCTIONS UTILES ---

def setup_driver(enable_js: bool = False):
    """Configure Chrome headless and optionally enable JavaScript."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    js_setting = 1 if enable_js else 2
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.javascript": js_setting,
    }
    options.add_experimental_option("prefs", prefs)
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def wait_for_table(driver, wait_seconds: int) -> None:
    """Attend que le tableau soit chargé dans le DOM."""
    WebDriverWait(driver, wait_seconds).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table.views-table tbody tr"))
    )


def parse_table(driver, page_index: int):
    """
    Parcourt chaque ligne du tableau et extrait les champs :
      Date, Registry, Full Details, Court, Type of action, Parties, UPC Document.
    """
    records = []
    rows = driver.find_elements(By.CSS_SELECTOR, "table.views-table tbody tr")
    for tr in rows:
        cells = tr.find_elements(By.TAG_NAME, "td")
        if len(cells) < 6:
            continue  # ligne inattendue

        # 1. Date
        raw_date = cells[0].text.strip()
        try:
            dt = datetime.strptime(raw_date, "%d %B %Y")
            date = dt.strftime("%d/%m/%Y")
        except ValueError:
            date = raw_date

        # 2. Registry (sans "Full Details" dans le texte)
        registry_lines = [l for l in cells[1].text.splitlines() if l and "Full Details" not in l]
        registry = "\n".join(registry_lines)

        # 3. Full Details URL (lien présent dans la même cellule)
        try:
            full_details = cells[1].find_element(By.LINK_TEXT, "Full Details").get_attribute("href")
        except Exception:
            full_details = ""

        # 4. Court, Type of action, Parties
        court   = cells[2].text.strip()
        action  = cells[3].text.strip()
        parties = cells[4].text.strip()

        # 5. UPC Document URL (dernier <td>)
        try:
            upc_doc = cells[5].find_element(By.TAG_NAME, "a").get_attribute("href")
        except Exception:
            upc_doc = ""

        records.append({
            "Date": date,
            "Registry": registry,
            "Full Details": full_details,
            "Court": court,
            "Type of action": action,
            "Parties": parties,
            "UPC Document": upc_doc,
            PAGE_COL: page_index
        })
    return records


def load_existing(output_file: Path) -> pd.DataFrame:
    """Charge l'Excel existant ou crée un DataFrame vide."""
    if output_file.exists():
        df = pd.read_excel(output_file, dtype=str)
        if PAGE_COL not in df.columns:
            df[PAGE_COL] = pd.NA
        logger.info(f"Loaded existing file with {len(df)} records.")
        return df
    logger.info("No existing file found, starting fresh.")
    return pd.DataFrame(columns=COLUMNS)


def save(df: pd.DataFrame, output_file: Path) -> None:
    """Sauvegarde le DataFrame dans l'Excel."""
    df.to_excel(output_file, index=False)
    logger.info(f"Saved {len(df)} total records to {output_file}.")

# --- SCRIPT PRINCIPAL ---

def main() -> None:
    args = parse_args()
    logger.info("Script démarré.")
    df_old = load_existing(args.output_file)
    driver = setup_driver(args.enable_js)
    empty_count, error_count = 0, 0
    if PAGE_COL in df_old.columns and not df_old[PAGE_COL].dropna().empty:
        page = int(df_old[PAGE_COL].dropna().astype(int).max()) + 1
    else:
        page = 0
    all_records = []
    persistent_error = False

    while True:
        url = args.base_url + (f"?page={page}" if page > 0 else "")
        try:
            driver.get(url)
            wait_for_table(driver, args.wait_seconds)
        except (WebDriverException, TimeoutException) as e:
            error_count += 1
            logger.error(
                f"Error loading page {page}: {e} ({error_count}/{args.max_errors})"
            )
            if error_count >= args.max_errors:
                logger.error("Maximum consecutive errors reached. Aborting.")
                persistent_error = True
                break
            page += 1
            continue
        except Exception as e:
            error_count += 1
            logger.error(
                f"Unexpected error on page {page}: {e} ({error_count}/{args.max_errors})"
            )
            if error_count >= args.max_errors:
                logger.error("Maximum consecutive errors reached. Aborting.")
                persistent_error = True
                break
            page += 1
            continue
        else:
            error_count = 0
        logger.info(f"Parsing page {page}...")

        records = parse_table(driver, page)
        if not records:
            empty_count += 1
            logger.info(
                f"Page {page} empty ({empty_count}/{args.max_empty_pages})."
            )
            if empty_count >= args.max_empty_pages:
                logger.info("Maximum empty pages reached. Stopping pagination.")
                break
        else:
            empty_count = 0
            logger.info(f"Page {page}: {len(records)} records found.")
            all_records.extend(records)
        page += 1

    driver.quit()
    if persistent_error:
        logger.error("Script stopped due to repeated errors.")

    df_new = pd.DataFrame(all_records, columns=COLUMNS)
    logger.info(f"Parsed {len(df_new)} new records.")
    df_all = pd.concat([df_old, df_new], ignore_index=True)
    df_all.drop_duplicates(subset=["Registry", "UPC Document"], keep="first", inplace=True)
    df_all.sort_values(by=PAGE_COL, inplace=True, ignore_index=True)

    save(df_all, args.output_file)
    logger.info("Script terminé.")

if __name__ == "__main__":
    main()
