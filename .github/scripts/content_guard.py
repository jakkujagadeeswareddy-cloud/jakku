import os
import sys

def check_content():
    print("Initializing ASF Free Content Guard verification...")
    
    # Simple dummy validation check
    target_dir = "."
    forbidden_terms = ["restricted-placeholder", "dummy-bad-content"]
    
    issues_found = False
    for root, dirs, files in os.walk(target_dir):
        # Skip hidden git folders
        if ".git" in root:
            continue
        for file in files:
            if file.endswith((".py", ".md", ".txt", ".yml")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        for term in forbidden_terms:
                            if term in content:
                                print(f"Warning: Found '{term}' in {file_path}")
                                issues_found = True
                except Exception:
                    pass

    if issues_found:
        print("Content Guard check failed: Restricted terms detected.")
        sys.exit(1)
    else:
        print("Content Guard check passed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    check_content()