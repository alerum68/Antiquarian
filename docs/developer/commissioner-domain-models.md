# Commissioner Domain Models & Validation

The `Commissioner` module serves as Antiquarian's central schema validator and domain model definition layer.

---

## Core Domain Schemas (`Commissioner/models.py`)

All domain objects inherit from Pydantic v2 `BaseModel` with strict field type validation:

### 1. `Collection`
Represents an entire record collection (e.g., a parish register volume or census district).
- `collection_title` (str): Descriptive title of the archival collection.
- `record_type_name` (str): Associated document type (e.g., `"Parish"`, `"Scrip"`, `"Census"`).
- `sheets` (List[Sheet]): List of page/sheet objects.

### 2. `Sheet`
Represents a single document image or page.
- `page_id` (str): Identifier or file name of the document page.
- `document_metadata` (dict): Technical details (file name, format, resolution, source repository).
- `records` (List[Record]): Extracted historical events or entries on this sheet.

### 3. `Record`
Represents an individual historical event (e.g., a baptism, marriage, burial, or census household row).
- `event_type` (str): Standardized event classification (`"Baptism"`, `"Marriage"`, `"Burial"`, `"Census"`).
- `event_date` (Optional[str]): Extracted date string.
- `event_place` (Optional[str]): Historical location.
- `participants` (List[Participant]): Individuals participating in the event.
- `type_specific_fields` (dict): Document-type specific facts defined in `.pmt` extra fields.

### 4. `Participant`
Represents an individual person recorded in an event.
- `role_name` (str): Role played in the event (e.g., `"Groom"`, `"Bride"`, `"Primary"`, `"Head"`, `"Witness"`).
- `std_given` (Optional[str]): Standardized given name.
- `std_surname` (Optional[str]): Standardized surname.
- `verbatim_name` (Optional[str]): Exact spelling from the manuscript.
- `sex` (Optional[str]): `"M"`, `"F"`, or `None`.
- `type_specific_fields` (dict): Role-specific facts (e.g., age, marital status, occupation).

---

## Validation Contract & Soft-Fail Mode

Validation occurs via `Commissioner.record_registry.validate_soft()`:

```python
from Commissioner.record_registry import validate_collection_softly

validate_collection_softly(data, document_type, label)
```

- **Graceful Degradation**: `validate_collection_softly` catches all Pydantic validation errors and schema exceptions without raising.
- **Logging**: When validation fails, a warning is printed to stdout in the exact format:
  ```text
  [WARN] Commissioner validation failed for 'Test Volume': <error details>
  ```
- **Execution Flow**: Processing continues uninterrupted, allowing invalid or partial extractions to be saved and corrected manually in the Master DB editor.

---

## Role Validation Modes

Document types declare their role validation policy in `.pmt` front matter:

- **`closed` Mode** (Default for `Parish` and `Scrip`):
  - Only roles declared in the `.pmt` front matter `roles:` list are accepted.
  - Unknown role names raise a `ValidationError`.
- **`open` Mode** (Used by `Census`):
  - Any role name is accepted without error.
  - Role validation becomes a passthrough, preserving arbitrary relationship descriptions.
