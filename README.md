# Scriptorium

Historical records are being digitized faster than ever. Parish registers, census schedules, newspapers, court records, and government files can now be downloaded with a few clicks. The problem is that a scanned image is still just an image. You can read it, but you can't easily search across thousands of pages, discover connections between people, or answer questions that span an entire collection.

Scriptorium grew out of that problem.

The original goal was simple: make large collections of historical records useful for research instead of leaving them trapped in PDFs and image files.

While working through Métis Scrip applications, I realized that every file contained pieces of a much larger story. A parent mentioned in one application appeared as a witness in another. Communities overlapped. Families resurfaced years later in entirely different records. The information existed, but finding those connections depended on remembering where they had been seen before.

Scriptorium helps organize that information as you work. Instead of producing another transcription to store in a folder, it builds a collection that can be searched, explored, corrected, and expanded over time.

It is intended for projects measured in hundreds or thousands of records rather than a handful of documents. That might be a church register, a township census, a collection of probate files, or an archive that has never been indexed before. Whatever the source, the objective is the same: spend more time researching the records and less time managing them.

---

## What Scriptorium does

Scriptorium assists with the process of turning historical records into structured research data.

Current capabilities include:

* AI-assisted transcription from document images.
* Extraction of people, relationships, places, dates, and events.
* Source and citation management.
* Project organization for large record collections.
* GEDCOM export for genealogy software, including RootsMagic.

Development is ongoing, and additional record types and export formats are planned.

---

## Is this the right tool?

Probably, if your work involves collections of historical records.

For example, you may be creating a searchable index of parish registers, reconstructing a historical community from census records, preserving the contents of a local archive, or building a research database from a series of government files.

If your goal is simply to enter an occasional birth, marriage, or death record into your family tree, Scriptorium is probably more than you need.

---

## Getting Started

Detailed installation and setup instructions are available in the project Wiki.

In general, the workflow is straightforward:

1. Create a project.
2. Import document images.
3. Process and review the extracted information.
4. Continue building your collection.
5. Export your work when you're ready.

---

## Requirements

Scriptorium relies on a few external services, depending on how you choose to use it.

* Windows 10 or Windows 11.
* Antigravity (agy) for document processing.
* Internet access while processing records.
* Antigravity initialized via the CLI.
* Optional subscriptions for external services such as Ancestry if you want to retrieve records directly from those platforms.

Some features may require additional software or accounts. These are documented in the Wiki.

---

## Documentation

### User Guides

Comprehensive guides for setup, configuration, and module workflows are available on the project Wiki:

* [Getting Started](https://github.com/alerum68/Scriptorium/wiki/Getting-Started)
* [Configuration & Settings](https://github.com/alerum68/Scriptorium/wiki/Configuration-&-Settings)
* [Voyageur User Guide](https://github.com/alerum68/Scriptorium/wiki/Voyageur-User-Guide)
* [Paleographer User Guide](https://github.com/alerum68/Scriptorium/wiki/Paleographer-User-Guide)
* [Archivist User Guide](https://github.com/alerum68/Scriptorium/wiki/Archivist-User-Guide)
* [Registrar & Gazetteer](https://github.com/alerum68/Scriptorium/wiki/Registrar-&-Gazetteer)
* [PDFix Utility](https://github.com/alerum68/Scriptorium/wiki/PDFix-Utility)
* [Troubleshooting & FAQ](https://github.com/alerum68/Scriptorium/wiki/Troubleshooting-&-FAQ)

### Developer Documentation

Technical specifications and architecture guides are maintained in the `docs/developer/` directory:

* [Architecture Overview](docs/developer/architecture-overview.md)
* [Commissioner Domain Models](docs/developer/commissioner-domain-models.md)
* [Prompt Template Specification](docs/developer/pmt-specification.md)
* [Scaffold Data Contract](docs/developer/scaffold-data-contract.md)
* [Developer Workflow](docs/developer/development-workflow.md)

---

## Project Status

Scriptorium is under active development.

Suggestions, bug reports, and discussions are always welcome. If you work with historical records and have encountered a workflow that Scriptorium could improve, I'd like to hear about it.

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for future plans for Scriptorium.

---

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE). In short: you're free to
use, modify, and share it for any noncommercial purpose (personal genealogy research, other historical or
genealogical societies, education, etc.), but it may not be used to build or sell a commercial product or
service. See the [LICENSE](LICENSE) file for the full terms.
