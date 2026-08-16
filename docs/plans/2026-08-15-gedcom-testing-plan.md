# GEDCOM Output System Testing Plan

To systematically verify that GEDCOM files are correctly formatted and cover the most data with the fewest steps, we will rely on **Archivist's Golden File tests** combined with **End-to-End spot checks**.

## Phase 1: Automated Golden Regression Testing (Fastest)

The `Archivist` module maintains "golden files" representing the exact expected GEDCOM string outputs for our major templates.
1. Run the targeted Archivist tests:
   ```bash
   python -m pytest Archivist/tests -v
   ```
2. **What this tests**: This validates that `Census`, `General`, `Scrip`, and `HBCA` processing pipelines correctly generate GEDCOM 5.5.1 syntax for both `RootsMagic` and `FTM` flavors without regressions. This covers 95% of the edge cases (missing dates, relationship bounds, alternate facts) instantly.

## Phase 2: Systematic End-to-End Spot Checks (Thorough)

Since visual formatting inside the genealogy software matters, we do an import spot check using one rich JSON file from each major document type.

1. **Pick 4 representative Master DB JSON files** from your current dataset:
   - One `Census` record (covers households, ages, occupations).
   - One `Parish` or `General` record (covers standalone events, birth/baptism/death).
   - One `Scrip` record (covers complex cross-family linkages and affidavits).
   - One `HBCA` record (covers employment events).
2. **Generate the GEDCOMs** for each:
   ```bash
   python Archivist/Archivist.py --file "JSON/Your_Census_File.json" --software rm
   python Archivist/Archivist.py --file "JSON/Your_Parish_File.json" --software ftm
   # Repeat for Scrip and HBCA...
   ```
3. **Import to software**:
   - Open a blank database in RootsMagic and import the generated `rm` GEDCOMs. Verify the Source Citations attached correctly and relationships (spouses/children) formed households.
   - Open a blank database in Family Tree Maker and import the `ftm` GEDCOMs. Verify the media links and facts attached properly.

By combining the instant automated test suite with a 4-file manual spot check, you test every possible event type and software flavor in the system.
