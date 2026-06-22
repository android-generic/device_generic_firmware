#!/usr/bin/env python3
import os
import re
import sys
import subprocess
import fnmatch
import json

def parse_whence(whence_path):
    files = []
    links = []
    with open(whence_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if line.startswith('File:') or line.startswith('RawFile:'):
                filename = line.split(':', 1)[1].strip().strip('"')
                files.append(filename)
            elif line.startswith('Link:'):
                parts = line.split(':', 1)[1].split('->')
                if len(parts) == 2:
                    link_name = parts[0].strip().strip('"')
                    link_target = parts[1].strip().strip('"')
                    links.append((link_name, link_target))
    return files, links

def matches_pattern(filename, pattern):
    if fnmatch.fnmatch(filename, pattern):
        return True
    if fnmatch.fnmatch(filename, pattern + '/*'):
        return True
    return False

def generate_bp():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    
    # Environment variables for flexibility
    fw_src_dir = os.environ.get('FIRMWARE_SRC_DIR', script_dir)
    vendor_fw_dir = os.environ.get('VENDOR_FW_DIR', os.path.abspath(os.path.join(fw_src_dir, '../../../vendor/generic/proprietary/firmware')))
    recipe_file = os.environ.get('RECIPE_FILE', os.path.join(fw_src_dir, 'recipe.json'))
    
    whence_path = os.path.join(fw_src_dir, 'WHENCE')
    copy_script = os.path.join(fw_src_dir, 'copy-firmware.sh')
    
    if not os.path.exists(recipe_file):
        print(f"Error: Recipe file not found at {recipe_file}")
        print("Please run extract_recipe.py first or set RECIPE_FILE correctly.")
        sys.exit(1)
    
    # 1. Check version
    try:
        commit_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=fw_src_dir).decode('utf-8').strip()
    except Exception:
        commit_hash = "unknown"
        
    version_file = os.path.join(vendor_fw_dir, 'version.txt')
    if os.path.exists(version_file):
        with open(version_file, 'r') as f:
            if f.read().strip() == commit_hash and commit_hash != "unknown":
                print("Firmware Android.bp generation is up-to-date.")
                return
                
    print(f"Generating firmware Android.bp (commit: {commit_hash})...")
    print(f"Using Firmware Source Dir: {fw_src_dir}")
    print(f"Using Vendor Firmware Dir: {vendor_fw_dir}")
    print(f"Using Recipe File: {recipe_file}")
    
    # 2. Copy and compress using copy-firmware.sh
    import shutil
    if os.path.exists(vendor_fw_dir):
        shutil.rmtree(vendor_fw_dir, ignore_errors=True)
    os.makedirs(vendor_fw_dir, exist_ok=True)
    subprocess.check_call([copy_script, '--zstd', vendor_fw_dir], cwd=fw_src_dir)
    
    # 3. Load Recipe
    with open(recipe_file, 'r') as f:
        packages = json.load(f)
    
    # 4. Parse WHENCE
    files, links = parse_whence(whence_path)
    
    # 5. Categorize Files
    categorized_files = {pkg: [] for pkg in packages.keys()}
    categorized_files['other'] = []
    
    categorized_links = {pkg: [] for pkg in packages.keys()}
    categorized_links['other'] = []
    
    skipped = []
    
    for f in files:
        if ' ' in f:
            skipped.append(f)
            continue
            
        matched_pkg = 'other'
        for pkg, patterns in packages.items():
            for pat in patterns:
                if matches_pattern(f, pat):
                    matched_pkg = pkg
                    break
            if matched_pkg != 'other':
                break
        categorized_files[matched_pkg].append(f)
        
    for link_name, link_target in links:
        if ' ' in link_name or ' ' in link_target:
            skipped.append(link_name)
            continue
            
        matched_pkg = 'other'
        for pkg, patterns in packages.items():
            for pat in patterns:
                if matches_pattern(link_name, pat):
                    matched_pkg = pkg
                    break
            if matched_pkg != 'other':
                break
        categorized_links[matched_pkg].append((link_name, link_target))
        
    # Write skip.txt
    with open(os.path.join(vendor_fw_dir, 'skip.txt'), 'w') as f:
        for s in skipped:
            f.write(f"{s}\n")
            
    legacy_mode = '--legacy' in sys.argv
    if legacy_mode:
        print("Legacy mode enabled: Generating Android.mk for symlinks.")
        
    use_namespace = '--soong-namespace' in sys.argv
    if use_namespace:
        print("Soong namespace enabled.")
        
    # 6. Generate Android.bp and Android.mk files
    main_bp_path = os.path.join(vendor_fw_dir, 'Android.bp')
    mk_path = os.path.join(vendor_fw_dir, 'Android.mk')
    
    sub_bps = []
    mk_content = ["LOCAL_PATH := $(call my-dir)\n"]
    
    for pkg in list(packages.keys()) + ['other']:
        if not categorized_files[pkg] and not categorized_links[pkg]:
            continue
            
        bp_name = f"Android.{pkg}.bp"
        sub_bps.append(bp_name)
        
        pkg_phony_name = f"linux-firmware-{pkg}" if pkg not in ('amd-ucode', 'linux-firmware') else pkg
        
        bp_path = os.path.join(vendor_fw_dir, bp_name)
        with open(bp_path, 'w') as f:
            f.write("// Automatically generated. DO NOT EDIT.\n\n")
            
            reqs = []
            
            for file in categorized_files[pkg]:
                is_raw = os.path.exists(os.path.join(vendor_fw_dir, file))
                ext = '' if is_raw else '.zst'
                
                module_name = "fw_" + file.replace('/', '_') + ext.replace('.', '_')
                module_name = re.sub(r'[^a-zA-Z0-9_-]', '_', module_name)
                reqs.append(module_name)
                
                sub_dir = os.path.dirname(file)
                f.write("prebuilt_firmware {\n")
                f.write(f'    name: "{module_name}",\n')
                f.write(f'    src: "{file}{ext}",\n')
                f.write('    filename_from_src: true,\n')
                if sub_dir:
                    f.write(f'    sub_dir: "{sub_dir}",\n')
                f.write('    vendor: true,\n')
                f.write("}\n\n")
                
            for link_name, link_target in categorized_links[pkg]:
                is_raw = os.path.exists(os.path.join(vendor_fw_dir, link_name))
                ext = '' if is_raw else '.zst'
                
                module_name = "fw_link_" + link_name.replace('/', '_') + ext.replace('.', '_')
                module_name = re.sub(r'[^a-zA-Z0-9_-]', '_', module_name)
                reqs.append(module_name)
                
                if legacy_mode:
                    target_dir = os.path.dirname(link_name)
                    if target_dir:
                        installed_path = f"$(TARGET_OUT_VENDOR)/firmware/{target_dir}"
                    else:
                        installed_path = f"$(TARGET_OUT_VENDOR)/firmware"
                        
                    target_file = f"{link_target}{ext}"
                    link_file = f"{os.path.basename(link_name)}{ext}"
                    
                    mk_content.append("include $(CLEAR_VARS)")
                    mk_content.append(f"LOCAL_MODULE := {module_name}")
                    mk_content.append("LOCAL_MODULE_CLASS := FAKE")
                    mk_content.append("LOCAL_MODULE_TAGS := optional")
                    mk_content.append("include $(BUILD_SYSTEM)/base_rules.mk")
                    mk_content.append(f"$(LOCAL_BUILT_MODULE): $(LOCAL_PATH)/Android.mk")
                    mk_content.append(f"\t@echo \"Symlink: {module_name}\"")
                    mk_content.append(f"\tmkdir -p {installed_path}")
                    mk_content.append(f"\tln -sf {target_file} {installed_path}/{link_file}")
                    mk_content.append(f"\ttouch $@\n")
                else:
                    f.write("install_symlink {\n")
                    f.write(f'    name: "{module_name}",\n')
                    f.write(f'    installed_location: "firmware/{link_name}{ext}",\n')
                    f.write(f'    symlink_target: "{link_target}{ext}",\n')
                    f.write('    vendor: true,\n')
                    f.write("}\n\n")
                
            f.write("phony {\n")
            f.write(f'    name: "{pkg_phony_name}",\n')
            if reqs:
                f.write('    required: [\n')
                for req in reqs:
                    f.write(f'        "{req}",\n')
                f.write('    ],\n')
            f.write("}\n")
            
    with open(main_bp_path, 'w') as f:
        f.write("// Automatically generated. DO NOT EDIT.\n\n")
        if use_namespace:
            f.write("soong_namespace {\n}\n\n")
        f.write("build = [\n")
        for bp in sub_bps:
            f.write(f'    "{bp}",\n')
        f.write("]\n")
        
    if legacy_mode and len(mk_content) > 1:
        with open(mk_path, 'w') as f:
            f.write("\n".join(mk_content) + "\n")
    elif not legacy_mode and os.path.exists(mk_path):
        os.remove(mk_path)
        
    with open(version_file, 'w') as f:
        f.write(f"{commit_hash}\n")
        
    print(f"Generated Android.bp for {len(sub_bps)} packages.")

if __name__ == '__main__':
    generate_bp()
