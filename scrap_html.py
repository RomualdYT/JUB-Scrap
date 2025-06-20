import logging
import pandas as pd
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# --- CONFIGURATION ---
BASE_URL        = "https://www.unified-patent-court.org/en/decisions-and-orders"
OUTPUT_FILE     = Path("decisions_html.xlsx")
WAIT_SECONDS    = 10   # Délai max pour attendre le tableau
MAX_EMPTY_PAGES = 3    # Arrêt après X pages consécutives vides
LOG_FILE        = "scrap_html.log"

# Colonnes du DataFrame
COLUMNS = [
    "Date",          # Date de la décision au format JJ/MM/AAAA
    "Registry",      # Numéro de dossier(s), plusieurs lignes séparées par '\n'
    "Full Details",  # URL vers la page de détails
    "Court",         # Instance judiciaire
    "Type of action",# Type d’action
    "Parties",       # Parties impliquées
    "UPC Document"   # Lien PDF du document
]

# --- LOGGER SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- FONCTIONS UTILES ---

def setup_driver():
    """Configure Chrome headless, désactive images et JS pour accélérer."""  
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    prefs = {"profile.managed_default_content_settings.images": 2,
             "profile.managed_default_content_settings.javascript": 2}
    options.add_experimental_option("prefs", prefs)
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def wait_for_table(driver):
    """Attend que le tableau soit chargé dans le DOM."""
    WebDriverWait(driver, WAIT_SECONDS).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table.views-table tbody tr"))
    )


def parse_table(driver):
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
            "UPC Document": upc_doc
        })
    return records


def load_existing():
    """Charge l'Excel existant ou crée un DataFrame vide """
    if OUTPUT_FILE.exists():
        df = pd.read_excel(OUTPUT_FILE, dtype=str)
        logger.info(f"Loaded existing file with {len(df)} records.")
        return df
    logger.info("No existing file found, starting fresh.")
    return pd.DataFrame(columns=COLUMNS)


def save(df):
    """Sauvegarde le DataFrame dans l'Excel."""
    df.to_excel(OUTPUT_FILE, index=False)
    logger.info(f"Saved {len(df)} total records to {OUTPUT_FILE}.")

# --- SCRIPT PRINCIPAL ---

def main():
    logger.info("Script démarré.")
    df_old = load_existing()
    driver = setup_driver()
    empty_count, all_records, page = 0, [], 0

    while True:
        url = BASE_URL + (f"?page={page}" if page > 0 else "")
        driver.get(url)
        try:
            wait_for_table(driver)
        except Exception as e:
            logger.warning(f"Table not found on page {page}: {e}")
        logger.info(f"Parsing page {page}...")

        records = parse_table(driver)
        if not records:
            empty_count += 1
            logger.info(f"Page {page} empty ({empty_count}/{MAX_EMPTY_PAGES}).")
            if empty_count >= MAX_EMPTY_PAGES:
                logger.info("Maximum empty pages reached. Stopping pagination.")
                break
        else:
            empty_count = 0
            logger.info(f"Page {page}: {len(records)} records found.")
            all_records.extend(records)
        page += 1

    driver.quit()

    df_new = pd.DataFrame(all_records)
    logger.info(f"Parsed {len(df_new)} new records.")
    df_all = pd.concat([df_old, df_new], ignore_index=True)
    df_all.drop_duplicates(subset=["Registry", "UPC Document"], keep="last", inplace=True)

    save(df_all)
    logger.info("Script terminé.")

if __name__ == "__main__":
    main()
