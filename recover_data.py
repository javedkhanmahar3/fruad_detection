"""
==================================================================
 Local Disk File Carving / Recovery Tool  (JPG + MP4)
==================================================================
Yeh script C: drive (NTFS) ko RAW mode mein scan karke deleted
JPG aur MP4 files dhoondti hai aur unhe D: drive par recover
karti hai (file system ko bypass karke, raw byte signatures se).

ZAROORI:
  1. Yeh script ADMINISTRATOR rights ke saath chalani hogi
     (warna raw drive access fail ho jayega).
  2. C: drive par naya data likhna BAND kar dein jab tak
     recovery complete na ho jaye.
  3. Output D: drive par jaa raha hai (taake C: par overwrite
     na ho aur naye sectors disturb na hon).
  4. Bara disk hai to isme KAAFI time lag sakta hai (ghanton mein).
==================================================================
"""

import os
import sys
import ctypes
import time

# ------------------------------------------------------------
# Config - inhe zaroorat ke hisaab se badal sakte hain
# ------------------------------------------------------------
SOURCE_DRIVE = r"\\.\C:"          # Jis drive se recover karna hai
OUTPUT_DIR   = r"D:\Recovered"    # Jahan recovered files save hongi
SECTOR_SIZE  = 512                # Disk sector size (almost always 512)
READ_CHUNK   = 4 * 1024 * 1024    # Ek baar mein 4MB padhna (speed ke liye)
MAX_FILE_SIZE = 200 * 1024 * 1024 # Ek file ka max size limit (200MB) - corrupt/garbage data se bachne ke liye

# File signatures: (extension, start_marker, end_marker_or_None)
# MP4 ka koi fixed end marker nahi hota, isliye size-based cutoff use karenge
SIGNATURES = {
    "jpg": {
        "start": [b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1', b'\xff\xd8\xff\xdb'],
        "end":   b'\xff\xd9',
        "max_size": 30 * 1024 * 1024,   # JPG generally 30MB se chota hota hai
    },
    "mp4": {
        "start": [b'\x00\x00\x00\x18\x66\x74\x79\x70', b'\x00\x00\x00\x20\x66\x74\x79\x70',
                  b'ftyp'],  # 'ftyp' box kahin bhi shuru ke 12 bytes mein milta hai
        "end":   None,                  # MP4 ka clean end marker nahi hota
        "max_size": MAX_FILE_SIZE,
    },
}


def is_admin():
    """Check karta hai ke script Administrator rights ke saath chal rahi hai ya nahi."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "jpg"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "mp4"), exist_ok=True)


def find_signature(buffer, signature_list):
    """Buffer mein se signature list ka koi bhi match dhoondta hai. Returns (index, matched_bytes) ya (-1, None)."""
    best_idx = -1
    best_sig = None
    for sig in signature_list:
        idx = buffer.find(sig)
        if idx >= 0 and (best_idx == -1 or idx < best_idx):
            best_idx = idx
            best_sig = sig
    return best_idx, best_sig


def carve_file(fileD, file_type, start_offset, counter):
    """
    Ek file ko start_offset se carve karta hai aur disk se
    end marker (ya max_size limit) tak data padh kar save karta hai.
    """
    config = SIGNATURES[file_type]
    out_path = os.path.join(OUTPUT_DIR, file_type, f"recovered_{counter:05d}.{file_type}")

    fileD.seek(start_offset)
    bytes_written = 0
    found_end = False

    with open(out_path, "wb") as out_f:
        while bytes_written < config["max_size"]:
            chunk = fileD.read(READ_CHUNK)
            if not chunk:
                break  # disk khatam ho gaya

            if config["end"] is not None:
                end_idx = chunk.find(config["end"])
                if end_idx >= 0:
                    out_f.write(chunk[:end_idx + 2])
                    bytes_written += end_idx + 2
                    found_end = True
                    break

            out_f.write(chunk)
            bytes_written += len(chunk)

    # Agar file bohot chhoti hai (false positive signature match), discard kar dete hain
    if bytes_written < 1024:
        try:
            os.remove(out_path)
        except OSError:
            pass
        return False, 0

    return True, bytes_written


def main():
    print("=" * 60)
    print(" Local Drive Data Recovery Tool - JPG + MP4")
    print("=" * 60)

    if not is_admin():
        print("\n[X] ERROR: Yeh script Administrator rights ke bina nahi chal sakti.")
        print("    Right-click karke 'Run as Administrator' se chalayein.\n")
        sys.exit(1)

    ensure_output_dir()

    print(f"\nSource Drive : {SOURCE_DRIVE}")
    print(f"Output Folder: {OUTPUT_DIR}")
    print("\n[!] NOTE: Yeh process disk size ke hisaab se ghanton tak chal sakta hai.")
    print("[!] Is dauraan C: drive par koi naya data save na karein.\n")

    confirm = input("Continue karein? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Cancelled by user.")
        sys.exit(0)

    try:
        fileD = open(SOURCE_DRIVE, "rb")
    except PermissionError:
        print("\n[X] ERROR: Drive access denied. Administrator rights check karein.")
        sys.exit(1)
    except FileNotFoundError:
        print(f"\n[X] ERROR: Drive {SOURCE_DRIVE} nahi mila.")
        sys.exit(1)

    counters = {"jpg": 0, "mp4": 0}
    total_found = {"jpg": 0, "mp4": 0}

    offset = 0
    start_time = time.time()
    last_print = start_time

    print("\nScanning shuru ho raha hai...\n")

    try:
        while True:
            chunk = fileD.read(READ_CHUNK)
            if not chunk:
                break

            # Har file type ke liye is chunk mein signature dhoondo
            for file_type, config in SIGNATURES.items():
                idx, matched = find_signature(chunk, config["start"])
                if idx >= 0:
                    absolute_offset = offset + idx
                    success, size = carve_file(fileD, file_type, absolute_offset, counters[file_type])
                    if success:
                        counters[file_type] += 1
                        total_found[file_type] += 1
                        size_mb = size / (1024 * 1024)
                        print(f"  [+] Found {file_type.upper()} @ offset {hex(absolute_offset)} "
                              f"-> recovered_{counters[file_type]-1:05d}.{file_type} ({size_mb:.2f} MB)")
                    # Carving ke baad disk pointer aage badh chuka hai, isliye
                    # agla chunk wahin se padhenge - outer loop khud sambhal lega
                    fileD.seek(offset + len(chunk))
                    break  # is chunk se aage mat dhoondo, agla chunk le aao

            offset += len(chunk)

            # Har 5 second mein progress dikhao
            now = time.time()
            if now - last_print >= 5:
                gb_scanned = offset / (1024 ** 3)
                elapsed = now - start_time
                print(f"  ... {gb_scanned:.2f} GB scan ho chuki ({elapsed:.0f}s) | "
                      f"JPG: {total_found['jpg']} | MP4: {total_found['mp4']}")
                last_print = now

    except KeyboardInterrupt:
        print("\n\n[!] User ne rok diya (Ctrl+C).")
    except Exception as e:
        print(f"\n[X] Error during scan: {e}")
    finally:
        fileD.close()

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(" SCAN COMPLETE")
    print("=" * 60)
    print(f" Time taken : {elapsed/60:.1f} minutes")
    print(f" JPG found  : {total_found['jpg']}")
    print(f" MP4 found  : {total_found['mp4']}")
    print(f" Saved in   : {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
