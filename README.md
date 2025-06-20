# JUB-Scrap

This project scrapes decisions from the Unified Patent Court website and saves them to an Excel file.

## Setup

1. Ensure you have Python installed (version 3.8 or later).
2. Install the required dependencies:

```bash
pip install -r requirements.txt
=======
This repository contains a small script, `scrap_html.py`, used to collect the public decisions available on the Unified Patent Court website.

## Purpose of `scrap_html.py`

`scrap_html.py` automates a headless Chrome session with Selenium to iterate through the pages of the UPC "decisions and orders" table. It extracts basic information (date, registry number, parties, etc.), then writes or appends the results to an Excel file. Logging information is written to `scrap_html.log` to track progress and issues.

The collected data is saved in **`decisions_html.xlsx`** in the repository root.

## Requirements

- Python 3.10 or newer
- Google Chrome installed on the machine

The script requires the following Python packages:

- `selenium`
- `webdriver-manager`
- `pandas`
- `openpyxl` (used by pandas to create the Excel file)

## Setup

Create and activate a virtual environment, then install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U selenium webdriver-manager pandas openpyxl
```

## Running the script

Execute `scrap_html.py` to start scraping:
=======
Once the dependencies are installed, execute the script directly with Python:


```bash
python scrap_html.py
```

By default JavaScript is disabled for faster scraping. Use `--enable-js` to
allow JavaScript, or `--disable-js` to explicitly disable it.

The results will be stored in `decisions_html.xlsx` in the project root.
=======
During execution the script will crawl each page until no more data is found. Parsed records are added to `decisions_html.xlsx` and diagnostic messages are stored in **`scrap_html.log`**.

