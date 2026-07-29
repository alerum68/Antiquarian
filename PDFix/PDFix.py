"""
PDFix: Bulk PDF Optimizer.

Recursively finds every .pdf under a target directory and losslessly shrinks it via
PyMuPDF's garbage-collection + stream-deflate save flags (dead objects removed, streams
re-compressed). This is a structural optimization only - it does NOT rescale embedded
image resolution/DPI the way Paleographer's optimize_image() does for standalone images,
so gains on an already-tightly-scanned PDF may be modest.
"""

import os
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
from dotenv import load_dotenv

# Global settings come from the project root's .env; this tool's own settings come from
# its own subfolder's .env, so PDFix stays runnable standalone.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


# ==========================================
# CONFIGURATION
# ==========================================
PROGRAM_DIR = os.getenv("PROGRAM_DIR", "")

_target = os.getenv("PDFIX_TARGET_DIR", ".")
TARGET_DIR = _target if os.path.isabs(_target) else os.path.join(PROGRAM_DIR, _target)


def _get_env_int(key: str, default: int) -> int:
    val = os.getenv(key, "")
    try:
        return int(val.strip()) if val.strip() else default
    except ValueError:
        return default


def _get_env_float(key: str, default: float = 0.0) -> float:
    val = os.getenv(key, "")
    try:
        return float(val.strip()) if val.strip() else default
    except ValueError:
        return default


COMPRESSION_LEVEL = _get_env_int("PDFIX_COMPRESSION_LEVEL", 2)
CREATE_BACKUP = str(os.getenv("PDFIX_CREATE_BACKUP", "True")).lower() in ("true", "1", "yes")
REPAIR_MODE = str(os.getenv("PDFIX_REPAIR_MODE", "False")).lower() in ("true", "1", "yes")
_size_threshold = _get_env_float("PDFIX_SIZE_THRESHOLD_MB", 0.0)
SIZE_THRESHOLD_MB = _size_threshold if _size_threshold > 0 else None

# Module-level so Paleographer/engine.py can import it directly for the pre-send
# optimization step, rather than duplicating these params in two places.
COMPRESSION_PARAMS = {
    0: {"garbage": 1, "deflate": True, "clean": True},  # Low
    1: {"garbage": 3, "deflate": True, "clean": True},  # Medium
    2: {"garbage": 4, "deflate": True, "clean": True},  # High
}


# ==========================================
# CORE OPTIMIZATION
# ==========================================
def optimize_pdfs(directory, compression_level=1, backup=False, size_threshold_mb=None, repair_mode=False):
    """
    Optimize all PDFs in the given directory and its subdirectories.

    Args:
        directory: Directory to scan for PDFs
        compression_level: 0=low, 1=medium, 2=high compression
        backup: Whether to create backups of original files
        size_threshold_mb: Only optimize PDFs larger than this size (in MB)
        repair_mode: Whether to attempt repairs on damaged PDFs

    Returns:
        dict: Statistics about the optimization process
    """
    stats = {
        "total_files": 0,
        "optimized_files": 0,
        "skipped_files": 0,
        "failed_files": 0,
        "repaired_files": 0,
        "original_size_bytes": 0,
        "optimized_size_bytes": 0,
        "start_time": datetime.now(),
    }

    params = COMPRESSION_PARAMS.get(compression_level, COMPRESSION_PARAMS[1])

    # Track processed files to handle potential file system race conditions
    processed_files = set()

    # Iterate through the directory and its subdirectories
    for root, _, files in os.walk(directory):
        for file in files:
            if not file.lower().endswith('.pdf'):
                continue

            pdf_path = os.path.join(root, file)

            # Skip if already processed or temporary file
            if pdf_path in processed_files or ".temp_optimized.pdf" in pdf_path:
                continue

            processed_files.add(pdf_path)
            stats["total_files"] += 1

            try:
                # Check if file exists and is accessible
                if not os.path.exists(pdf_path) or not os.access(pdf_path, os.R_OK):
                    print(f'Cannot access file: {pdf_path}')
                    stats["failed_files"] += 1
                    continue

                # Get file size
                try:
                    file_size = os.path.getsize(pdf_path)
                    file_size_mb = file_size / (1024 * 1024)
                    stats["original_size_bytes"] += file_size
                except OSError as e:
                    print(f'Error getting size of {pdf_path}: {str(e)}')
                    stats["failed_files"] += 1
                    continue

                # Check file size if threshold is set
                if size_threshold_mb and file_size_mb < size_threshold_mb:
                    print(f'Skipping {pdf_path} (size: {file_size_mb:.2f} MB, below threshold)')
                    stats["skipped_files"] += 1
                    stats["optimized_size_bytes"] += file_size  # No change for skipped files
                    continue

                # Check available disk space
                try:
                    disk_usage = shutil.disk_usage(os.path.dirname(pdf_path))
                    if disk_usage.free < file_size * 2:  # Need at least 2x file size
                        print(f'Skipping {pdf_path}: Not enough disk space')
                        stats["skipped_files"] += 1
                        stats["optimized_size_bytes"] += file_size
                        continue
                except Exception as e:
                    print(f'Warning: Could not check disk space for {pdf_path}: {str(e)}')

                # Create backup if requested
                if backup:
                    backup_path = pdf_path + '.backup'
                    try:
                        shutil.copy2(pdf_path, backup_path)
                    except Exception as e:
                        print(f'Warning: Could not create backup of {pdf_path}: {str(e)}')

                # Optimize the PDF
                result = optimize_pdf(pdf_path, params, repair_mode)
                if result["success"]:
                    stats["optimized_files"] += 1
                    stats["optimized_size_bytes"] += result["new_size"]

                    # Calculate and display size reduction
                    original_size = result["original_size"]
                    new_size = result["new_size"]
                    reduction_percent = ((original_size - new_size) / original_size * 100) if original_size > 0 else 0

                    print(f'Optimized: {pdf_path}')
                    print(
                        f'  Size: {original_size / 1024 / 1024:.2f} MB → '
                        f'{new_size / 1024 / 1024:.2f} MB ({reduction_percent:.1f}% reduction)')

                    if result.get("repaired", False):
                        stats["repaired_files"] += 1
                        print(f'  Note: Repaired PDF structure before optimization')
                else:
                    stats["failed_files"] += 1
                    stats["optimized_size_bytes"] += result["original_size"]  # No change in size for failed files
            except Exception as e:
                print(f'Unexpected error processing {pdf_path}: {str(e)}')
                stats["failed_files"] += 1
                # Try to add the file size to stats if possible
                try:
                    if os.path.exists(pdf_path):
                        file_size = os.path.getsize(pdf_path)
                        stats["optimized_size_bytes"] += file_size
                except Exception:
                    pass

    # Calculate overall statistics
    stats["end_time"] = datetime.now()
    stats["duration"] = stats["end_time"] - stats["start_time"]
    if stats["original_size_bytes"] > 0:
        stats["overall_reduction_percent"] = ((stats["original_size_bytes"] - stats["optimized_size_bytes"]) /
                                              stats["original_size_bytes"] * 100)
    else:
        stats["overall_reduction_percent"] = 0

    return stats


def optimize_pdf(pdf_path, params, repair_mode=False):
    """
    Optimize a single PDF file.

    Args:
        pdf_path: Path to the PDF file
        params: Optimization parameters
        repair_mode: Whether to attempt repair of damaged PDFs

    Returns:
        dict: Result of the optimization
    """
    original_size = os.path.getsize(pdf_path)
    result = {
        "success": False,
        "original_size": original_size,
        "new_size": original_size,
        "error": None,
        "repaired": False
    }

    # Generate a unique filename for the temporary file
    temp_dir = os.path.dirname(pdf_path)
    temp_filename = f".temp_opt_{os.path.basename(pdf_path)}_{os.getpid()}_{int(time.time())}.pdf"
    temp_optimized_pdf_path = os.path.join(temp_dir, temp_filename)

    try:
        # Try to open the PDF using PyMuPDF
        try:
            pdf_document = fitz.open(pdf_path)
        except Exception as e:
            if not repair_mode:
                raise e

            # Special handling for damaged PDFs
            print(f'Attempting to repair damaged PDF: {pdf_path}')
            result["repaired"] = True
            pdf_document = page_by_page_recovery(pdf_path)
            if not pdf_document:
                raise Exception("PDF repair failed")

        # Skip password-protected documents
        if pdf_document.is_encrypted:
            print(f'Skipping encrypted PDF: {pdf_path}')
            pdf_document.close()
            result["error"] = "PDF is encrypted"
            return result

        # Check if document can be modified
        if not pdf_document.can_save_incrementally():
            print(f'Warning: {pdf_path} may not support all optimizations')

        try:
            # Try standard optimization
            pdf_document.save(
                temp_optimized_pdf_path,
                incremental=False,
                garbage=params["garbage"],
                deflate=params["deflate"],
                clean=params["clean"]
            )
        except Exception as save_error:
            if not repair_mode:
                raise save_error

            # Try with special parameters for problematic PDFs
            print(f'Using safe mode to optimize problematic PDF: {pdf_path}')
            try:
                # Use more conservative parameters
                pdf_document.save(
                    temp_optimized_pdf_path,
                    incremental=True,  # Less aggressive
                    garbage=1,  # Minimal garbage collection
                    deflate=True,  # Still compress
                    clean=False  # Skip cleaning step
                )
                result["repaired"] = True
            except Exception:
                # Last resort: try copying page by page to a new document
                print(f'Attempting page-by-page reconstruction for: {pdf_path}')
                pdf_document.close()  # Close document before trying page-by-page recovery
                if page_by_page_recovery(pdf_path, temp_optimized_pdf_path):
                    result["repaired"] = True
                else:
                    raise Exception("Could not repair PDF even with page-by-page method")

        # Make sure the document is closed
        try:
            pdf_document.close()
        except Exception:
            pass

        # Verify the temporary file exists before proceeding
        if not os.path.exists(temp_optimized_pdf_path):
            raise Exception(f"Temporary optimized file was not created: {temp_optimized_pdf_path}")

        # Check if optimization actually reduced the size
        new_size = os.path.getsize(temp_optimized_pdf_path)

        if new_size < original_size:
            # Replace the original PDF with the optimized one
            try:
                # Use safer approach to replace the file
                shutil.move(temp_optimized_pdf_path, pdf_path)
                result["success"] = True
                result["new_size"] = new_size
            except Exception as e:
                raise Exception(f"Failed to replace original file: {str(e)}")
        else:
            # If no size reduction, remove the temporary file and keep original
            os.remove(temp_optimized_pdf_path)
            print(f'  No size reduction for {pdf_path}, keeping original')
            result["success"] = True  # Still mark as success since processing completed

    except Exception as e:
        error_msg = str(e)
        print(f'Error optimizing {pdf_path}: {error_msg}')
        result["error"] = error_msg

        # Provide guidance for specific error messages
        if "cannot find object in xref" in error_msg:
            print(f'  → This PDF has structural issues. Try using repair mode (-r flag)')
        elif "malformed or missing" in error_msg:
            print(f'  → This PDF may be damaged. Try using repair mode (-r flag)')

        # Cleanup temp file if it exists
        try:
            if os.path.exists(temp_optimized_pdf_path):
                os.remove(temp_optimized_pdf_path)
        except Exception as cleanup_error:
            print(f'  Warning: Could not remove temporary file: {str(cleanup_error)}')

    return result


def attempt_pdf_repair(pdf_path):
    """
    Attempt to repair a damaged PDF file.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        fitz.Document or None: Repaired document or None if repair failed
    """
    try:
        # First try opening normally
        pdf_document = fitz.open(pdf_path)
        if pdf_document.is_pdf and pdf_document.page_count > 0:
            return pdf_document
        pdf_document.close()
    except Exception:
        pass

    # If that fails, try a more aggressive approach
    try:
        # Create a temporary file for the repaired PDF
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        temp_file.close()

        # Try to use a basic approach without special parameters
        pdf_document = fitz.open()
        source_doc = fitz.open(pdf_path)  # No repair parameter
        pdf_document.insert_pdf(source_doc)  # No garbage parameter
        source_doc.close()

        pdf_document.save(temp_file.name)
        pdf_document.close()

        # Try to open the repaired PDF
        repaired_doc = fitz.open(temp_file.name)
        if repaired_doc.page_count > 0:
            # Copy the repaired file back to original path
            temp_repaired = pdf_path + '.repaired.pdf'
            shutil.copy2(temp_file.name, temp_repaired)
            os.replace(temp_repaired, pdf_path)
            os.unlink(temp_file.name)
            # Re-open the repaired file
            return fitz.open(pdf_path)
    except Exception:
        # Clean up temp file if it exists
        if os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass

    return None


def page_by_page_recovery(pdf_path):
    """
    Attempt to repair a damaged PDF file.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        fitz.Document or None: Repaired document or None if repair failed
    """
    try:
        # First try opening normally
        pdf_document = fitz.open(pdf_path)
        if pdf_document.is_pdf and pdf_document.page_count > 0:
            return pdf_document
        pdf_document.close()
    except Exception as e:
        print(f"Initial open failed: {e}")
        pass

    # If that fails, try a more aggressive approach
    try:
        # Create a temporary file for the repaired PDF
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        temp_file.close()

        # Try to use a simpler approach - just copy pages one by one
        src_doc = None
        try:
            # Try to open the source document
            src_doc = fitz.open(pdf_path)

            # Create a new document
            new_doc = fitz.open()

            # Copy pages one by one, skipping problematic ones
            for page_num in range(src_doc.page_count):
                try:
                    new_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)
                except Exception:
                    print(f"Skipping problematic page {page_num}")
                    continue

            # Save the repaired document
            new_doc.save(temp_file.name)
            new_doc.close()

        except Exception as e:
            print(f"Page-by-page recovery failed: {e}")
            if src_doc:
                src_doc.close()
            raise
        finally:
            if src_doc:
                src_doc.close()

        # Try to open the repaired PDF
        repaired_doc = fitz.open(temp_file.name)
        if repaired_doc.page_count > 0:
            # Copy the repaired file back to original path
            temp_repaired = pdf_path + '.repaired.pdf'
            shutil.copy2(temp_file.name, temp_repaired)
            os.replace(temp_repaired, pdf_path)
            repaired_doc.close()
            # Re-open the repaired file
            return fitz.open(pdf_path)
        else:
            repaired_doc.close()

    except Exception as e:
        print(f"Recovery attempt failed: {e}")
    finally:
        # Clean up temp file if it exists
        if os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass

    return None


def print_summary(stats):
    """Print a summary of the optimization results."""
    print("\n" + "=" * 50)
    print("PDF OPTIMIZATION SUMMARY")
    print("=" * 50)
    print(f"Total PDFs processed: {stats['total_files']}")
    print(f"Successfully optimized: {stats['optimized_files']}")
    print(f"Repaired and optimized: {stats.get('repaired_files', 0)}")
    print(f"Skipped: {stats['skipped_files']}")
    print(f"Failed: {stats['failed_files']}")

    # Size statistics
    original_size_mb = stats["original_size_bytes"] / (1024 * 1024)
    optimized_size_mb = stats["optimized_size_bytes"] / (1024 * 1024)
    saved_mb = original_size_mb - optimized_size_mb

    print(f"\nOriginal size: {original_size_mb:.2f} MB")
    print(f"Optimized size: {optimized_size_mb:.2f} MB")
    print(f"Space saved: {saved_mb:.2f} MB ({stats['overall_reduction_percent']:.1f}%)")
    print(f"\nTime taken: {stats['duration']}")
    print("=" * 50)


# ==========================================
# MAIN EXECUTION
# ==========================================
def main() -> None:
    if not os.path.isdir(TARGET_DIR):
        print(f"Error: Target directory not found: {TARGET_DIR}")
        return

    print(f"\nStarting PDF optimization in {TARGET_DIR}...")
    stats = optimize_pdfs(
        TARGET_DIR,
        compression_level=COMPRESSION_LEVEL,
        backup=CREATE_BACKUP,
        size_threshold_mb=SIZE_THRESHOLD_MB,
        repair_mode=REPAIR_MODE
    )
    print_summary(stats)


if __name__ == "__main__":
    main()
