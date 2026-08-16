# Complex Field Integration Design

**Goal:** Implement complex mapping rules for advanced census fields (Income, dynamic Occupation, 1935 Residence, etc.) across both Ancestry and FamilySearch pipelines, without requiring structural changes to `Commissioner`.

## Architecture & Scope

This design encompasses two major areas of the pipeline:
1. **Voyageur / Schema Mapping (`Voyageur/field_maps/*`)**: Directing raw, granular fields to existing standard fact types (`Property`, `Nationality`, etc.).
2. **Archivist / GEDCOM Generation (`Archivist/Census.py`)**: Dynamically composing complex sentence templates (like `Occupation`) at the point of GEDCOM assembly, preserving raw data granularity in the underlying JSON.

*Note: The `Marriage Details` custom fact was explicitly scoped out of this design and deferred to a future plan to avoid structural `Commissioner` changes at this time.*

## Section 1: Unified Standard Mappings (Voyageur)

The `ancestry_census.yaml` and `familysearch_census.yaml` maps will be updated to route the remaining unmapped fields to standard `FactTypes.json` targets:

* **Property**: `Income`, `IncomeOtherSources`, `InsuranceCost`, `LifeInsuranceCost`, `MonthlyRental`, `AmountOfLand`, and all livestock/agricultural counts (`NumberOfHorses`, `ValueOfLivestock`, etc.).
* **Nationality**: Indigenous fields (`Tribe`, `Clan`, `IndianBlood`).
* **Education**: `EducationCost`.
* **Death**: `CauseOfDeath` (value will be injected into the `Details` / `Notes` of the Death fact).
* **Duplicate Events**: Numbered Canadian variants (`Widowed1`, `CannotRead1`, etc.) will map as duplicate events of their base type.
* **Residence (1935)**: The 1940 census "5-years-ago" fields (`ResidenceCityInNineteenThirtyFive`, etc.) will generate a `Residence` fact with the date hardcoded to `1935`.
* **Residence (Dwellings)**: `VesselVisitedNumber` and `ShantyVisitedNumber` will map to a `Residence` fact, with the specific vessel/shanty details placed in the `Notes`.

## Section 2: Dynamic Occupation Template (Archivist)

Instead of concatenating fields during extraction, `Archivist/Census.py` will dynamically build the `Occupation` string from granular components (`Occupation`, `Employer`, `Industry`, `Class of Worker`, `Unemployment` flags).

**Template Logic (`get_occupation_value`):**
1. **Primary Selection**: If `UsualOccupation` exists, it takes priority over current `Occupation`.
2. **Unemployment Override**: If the person is flagged as unemployed (`OutOfWork` or `SeekingWork` = True), the base string becomes `"Unemployed"`.
3. **Concatenation**: Append `[ from {Occupation}]` (if unemployed) or `[ {Occupation}]` (if employed), followed by `[ at {Employer}][, working in {Industry}]`.
4. **Notes Injection**: Any remaining employment metadata (`ClassOfWorker`, `HoursWorked`, `WeeksWorked`, `MonthsUnEmployedPastYear`) will be formatted into a clean sentence and injected directly into the `Notes` field of the generated `Occupation` fact.

## Section 3: Foreign Birthplace as Nationality

During `Archivist` compilation, if a person's `Birthplace` is recorded as a foreign country (e.g., "Ireland") and the `Nationality` fact is otherwise empty, the pipeline will automatically generate a `Nationality` fact using the foreign birthplace value.
