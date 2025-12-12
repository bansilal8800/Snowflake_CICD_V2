# config/get_vars.py
import yaml
import json
import sys

def parse_vars(yml_path):
    try:
        with open(yml_path) as f:
            data = yaml.safe_load(f)

        # Extract the 'variables' section if present
        vars_dict = data.get('variables', data) if isinstance(data, dict) else {}

        # Always return valid JSON with spaces (survives GitHub Actions)
        return json.dumps(vars_dict)
    except Exception as e:
        print(f"Error parsing {yml_path}: {e}", file=sys.stderr)
        return "{}"

if __name__ == '__main__':
    if len(sys.argv) > 1:
        print(parse_vars(sys.argv[1]))
    else:
        print("{}")
