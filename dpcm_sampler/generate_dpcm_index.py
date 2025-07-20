import os
import json

def generate_dpcm_index(dmc_folder, output_json):
    index = {}
    current_id = 0

    for root, _, files in os.walk(dmc_folder):
        for f in sorted(files):
            if f.lower().endswith('.dmc'):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, dmc_folder)
                name = os.path.splitext(os.path.basename(f))[0]

                index[name] = {
                    "id": current_id,
                    "filename": rel_path.replace("\\", "/")
                }
                current_id += 1

    with open(output_json, 'w') as f:
        json.dump(index, f, indent=2)

    print(f"Indexed {len(index)} DPCM samples → {output_json}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python generate_dpcm_index.py dmc_folder output.json")
        sys.exit(1)

    generate_dpcm_index(sys.argv[1], sys.argv[2])
