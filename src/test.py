import yaml, json

with open("src/data.yaml") as f:
  data = f.read()

obj = yaml.safe_load(data)

print(json.dumps(obj, indent=4))