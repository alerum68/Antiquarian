# Prompt Template (.pmt) Specification

Prompt Template (`.pmt`) files define document types, validation rules, and extraction engine instructions for Paleographer transcription passes.

---

## File Layout

A `.pmt` file consists of two parts: YAML front matter enclosed in `---` delimiters, followed by the extraction engine instructions in Markdown.

```yaml
---
document_type: Parish
roles:
  - Primary
  - Father
  - Mother
  - Groom
  - Bride
  - Witness
  - Godparent
role_validation: closed
record_extra_fields:
  sacrament_type: str
participant_extra_fields:
  age: str
  occupation: str
---
# Transcription Instructions
Extract all individuals, dates, places, and relationships from the document image...
```

---

## Front Matter Keys

| Key | Required | Type | Description |
| :--- | :--- | :--- | :--- |
| `document_type` | Yes | `str` | Unique name of the record type (e.g., `Parish`, `Scrip`, `Census`). Matches file stem. |
| `roles` | Yes | `List[str]` | List of valid role names for participants in this document type. |
| `role_validation` | No | `str` | Validation mode: `closed` (strict whitelist) or `open` (allow any role). Defaults to `closed`. |
| `record_extra_fields` | No | `dict` | Key-value mapping of type-specific fields attached to each `Record`. |
| `participant_extra_fields` | No | `dict` | Key-value mapping of type-specific fields attached to each `Participant`. |

---

## Adding a New Document Type

To add support for a new record format (e.g., Wills & Probate):

1. Create `Paleographer/prompts/Probate.pmt`.
2. Define the front matter schema:
   ```yaml
   ---
   document_type: Probate
   roles:
     - Deceased
     - Executor
     - Heir
     - Witness
   role_validation: closed
   record_extra_fields:
     court_jurisdiction: str
   participant_extra_fields:
     bequest_summary: str
   ---
   ```
3. Write the instructions directing the extraction engine how to format JSON output.
4. Antiquarian automatically discovers `Probate.pmt` on startup and adds `Probate` to the dropdown options in Paleographer. No code changes are required.
