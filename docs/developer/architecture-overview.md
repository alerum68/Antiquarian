# Architecture Overview

Scriptorium is structured as a pipeline with four primary operational stages and a centralized domain-validation core.

---

## High-Level System Architecture

```mermaid
graph TD
    UI[Scriptorium.py UI Layer] --> Voyageur[Voyageur - Gather Stage]
    UI --> Paleographer[Paleographer - Analyze Stage]
    UI --> Archivist[Archivist - Create Stage]
    UI --> Tools[Registrar & Gazetteer - Maintenance]
    
    Voyageur -->|Scaffold Master DB| MasterDB[(Master DB JSON)]
    Paleographer -->|Read & Write Sheets| MasterDB
    MasterDB -->|Read Collections| Archivist
    Archivist -->|Export GEDCOM| GED[GEDCOM 5.5.1 File]
    
    Voyageur -.->|validate_soft| Commissioner[Commissioner Domain Core]
    Paleographer -.->|validate_soft| Commissioner
```

---

## Core Subsystems

### 1. UI Layer (`Scriptorium.py`)
- Built using CustomTkinter.
- Manages tabbed navigation across Voyageur, Paleographer, Archivist, Registrar, Gazetteer, PDFix, and Global Settings.
- Loads `.env` configuration and manages background thread pools for non-blocking downloads and AI processing.

### 2. Gather Stage (`Voyageur/`)
- Extracts index data and downloads archival page images.
- Modules:
  - `LAC.py`: Programmatic multi-worker downloading of Library and Archives Canada microfilm reels and volume bundles.
  - `FS.py`: FamilySearch church register index table processing and citation mapping.
  - `A.py`: Scraped census page processing and image staging.
  - `census_schema.py`: Census record normalization and household grouping heuristics.

### 3. Analyze Stage (`Paleographer/`)
- Transcribes document images into structured JSON records using AI models.
- Modules:
  - `Paleographer.py`: Main engine managing single-sheet live extraction, batch jobs, prompt execution, and Master DB merging.
  - `prompts/`: `.pmt` files (`Parish.pmt`, `Scrip.pmt`, `Census.pmt`) specifying document types, roles, extra fields, and LLM prompt text.

### 4. Create Stage (`Archivist/`)
- Generates GEDCOM 5.5.1 family tree files from Master DB JSON data.
- Modules:
  - `Archivist.py`: Household reconstruction, GEDCOM tag generation, citation linking, and ambiguity note formatting.

### 5. Domain Validation Kernel (`Commissioner/`)
- Pydantic v2 domain models and schema validation registry.
- Modules:
  - `models.py`: Core domain classes (`Collection`, `Sheet`, `Record`, `Participant`, `Fact`, `Citation`).
  - `record_registry.py`: Dynamic `.pmt` scanner, document type schemas, and `validate_soft()` non-raising helper.
  - `normalization.py`: Shared string cleaning, date parsing, and role normalization utilities.

### 6. Maintenance & Utilities
- `Registrar/`: Scans RootsMagic `.rmtree` SQLite databases for duplicate individuals.
- `Gazetteer/`: Historical place name normalization using Newberry Atlas shapefiles.
- `PDFix/`: PDF repair and image extraction helper.
