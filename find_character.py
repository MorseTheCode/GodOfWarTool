import re
import sys

def extract_values(file_path):
    results = []
    seen = set()
    pattern = re.compile(r'S:(.*?):')
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        for line in file:
            match = pattern.search(line)
            if match:
                value = match.group(1)
                if value not in seen:
                    seen.add(value)
                    results.append(value)
                    
    for r in results:
        print(r)
    return results

if __name__ == '__main__':
    if len(sys.argv) > 1:
        extract_values(sys.argv[1])
    else:
        print("Usage: python script.py <file_path>")