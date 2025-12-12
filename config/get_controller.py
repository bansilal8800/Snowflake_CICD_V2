import yaml
import sys
import os
import json

def get_controllers():
    controllers_yml = os.path.join(os.path.dirname(__file__), "controller.yml")
    try:
        with open(controllers_yml, 'r') as file:
            data = yaml.safe_load(file)
            if data and 'controllers' in data and data['controllers']:
                return data['controllers']
            else:
                print("Error: No valid schemas found in controller.yml", file=sys.stderr)
                sys.exit(1)
    except FileNotFoundError:
        print(f"Error: {controllers_yml} not found", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML in {controllers_yml} - {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    controllers = get_controllers()
    # ✅ only JSON goes to stdout
    print(json.dumps(controllers))
