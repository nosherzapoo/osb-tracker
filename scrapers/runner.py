"""Run all state scrapers and generate states.json manifest."""

import json
from pathlib import Path

from .ny import NYScraper
from .nj import NJScraper
from .pa import PAScraper
from .il import ILScraper
from .oh import OHScraper
from .az import AZScraper
from .co import COScraper
from .ct import CTScraper
from .ia import IAScraper
from .ky import KYScraper
from .la import LAScraper
from .me import MEScraper
from .ma import MAScraper
from .mi import MIScraper
from .ms import MSScraper
from .ri import RIScraper
from .sd import SDScraper
from .tn import TNScraper
from .mt import MTScraper
from .wy import WYScraper

DATA_DIR = Path("data")
SCRAPERS = [NYScraper, NJScraper, PAScraper, ILScraper, OHScraper, AZScraper, COScraper, CTScraper, IAScraper, KYScraper, LAScraper, MEScraper, MAScraper, MIScraper, MSScraper, RIScraper, SDScraper, TNScraper, MTScraper, WYScraper]


def run_all():
    """Run every state scraper and write data/states.json."""
    DATA_DIR.mkdir(exist_ok=True)
    results = []

    for cls in SCRAPERS:
        name = cls.STATE_NAME
        print(f"\n{'='*50}")
        print(f"  {name}")
        print(f"{'='*50}")
        try:
            scraper = cls(data_dir=DATA_DIR)
            result = scraper.run()
            results.append(result)
            print(f"  {name} complete.")
        except Exception as e:
            print(f"  ERROR running {name}: {e}")

    # Build states.json manifest
    manifest = {"states": [], "lastUpdated": None}
    for r in results:
        if r.metadata:
            manifest["states"].append(r.metadata)

    if manifest["states"]:
        from datetime import datetime, timezone
        manifest["lastUpdated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest_path = DATA_DIR / "states.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nWrote {manifest_path} with {len(manifest['states'])} states.")


if __name__ == "__main__":
    run_all()
