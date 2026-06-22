#!/usr/bin/env python3
import os
import re
import sys
import json

def expand_braces(s):
    match = re.search(r'\{([^{}]+)\}', s)
    if not match:
        return [s]
    
    options = match.group(1).split(',')
    prefix = s[:match.start()]
    suffix = s[match.end():]
    
    res = []
    for opt in options:
        expanded = prefix + opt + suffix
        res.extend(expand_braces(expanded))
    return res

def parse_pkgbuild(pkgbuild_path):
    packages = {}
    with open(pkgbuild_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('_pick '):
                parts = line.split(' ', 2)
                if len(parts) >= 3:
                    pkg_name = parts[1]
                    raw_pattern = parts[2]
                    if pkg_name not in packages:
                        packages[pkg_name] = []
                    sub_patterns = raw_pattern.split('"${fwdir}"/')
                    for sub in sub_patterns:
                        sub = sub.strip().strip("'").strip('"')
                        if sub:
                            packages[pkg_name].extend(expand_braces(sub))
    return packages

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('-h', '--help'):
        print(f"Usage: {sys.argv[0]} [path/to/PKGBUILD] [path/to/recipe.json]")
        sys.exit(0)

    script_dir = os.path.dirname(os.path.realpath(__file__))
    
    pkgbuild_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(script_dir, '../../../linux-firmware/PKGBUILD')
    recipe_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(script_dir, 'recipe.json')
    
    if not os.path.exists(pkgbuild_path):
        print(f"Error: PKGBUILD not found at {pkgbuild_path}")
        sys.exit(1)
        
    print(f"Extracting recipe from: {pkgbuild_path}")
    packages = parse_pkgbuild(pkgbuild_path)
    
    with open(recipe_path, 'w') as f:
        json.dump(packages, f, indent=4)
        
    print(f"Recipe extracted to: {recipe_path}")

if __name__ == '__main__':
    main()
