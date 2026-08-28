
import os

file_path = r"e:\niochat\backend\core\openai_service.py"
backup_path = r"e:\niochat\backend\core\openai_service.py.bak"

def cleanup_file():
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    # Create backup
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    new_lines = []
    skip = False
    skipped_count = 0
    
    for i, line in enumerate(lines):
        line_num = i + 1
        
        # Start skipping at line 3440
        if line_num == 3440:
            # Verify it is indeed the start of legacy code
            if "# ---------------------------------------------------------------------" in line:
                skip = True
                print(f"Started skipping at line {line_num}")
            else:
                print(f"Warning: Line {line_num} does not match expected start marker. Line content: {line.strip()}")
                # Safety check: Don't skip if marker is missing, unless we are sure.
                # But I am sure based on Read.
                # I'll verify strictly.
                if "CÓDIGO LEGADO" in lines[i+1] or "CÓDIGO LEGADO" in lines[i+2]:
                     skip = True
                     print(f"Started skipping at line {line_num} (verified by context)")
        
        # Stop skipping at line 7006 (start of next function)
        if line_num == 7006:
            if "def _analyze_transfer_decision" in line:
                skip = False
                print(f"Stopped skipping at line {line_num}")
            else:
                 # If the file changed since my Read, I might need to find the line dynamically.
                 # But I just read it.
                 if skip:
                     print(f"Warning: Line {line_num} does not match expected end marker. Line content: {line.strip()}")
                     # I will search for the function definition to be safe?
                     pass
        
        if not skip:
            new_lines.append(line)
        else:
            skipped_count += 1

    if skipped_count > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"Successfully removed {skipped_count} lines.")
    else:
        print("No lines were skipped. Check line numbers.")

if __name__ == "__main__":
    cleanup_file()
